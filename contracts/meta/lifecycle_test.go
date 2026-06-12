package meta

import (
	"context"
	"errors"
	"testing"
)

func loadRealityGraphT(t *testing.T) *TransitionGraph {
	t.Helper()
	g, err := LoadTransitions("transitions.yaml")
	if err != nil {
		t.Fatalf("load shipped transitions.yaml: %v", err)
	}
	return g
}

func newReadyCfg(t *testing.T) (*Config, *fakeDBPrequeue) {
	t.Helper()
	allow := newStaticAllowlist(
		[]string{"reality_registry", "lifecycle_transition_audit"},
		map[string]map[MetaWriteOp]string{
			"reality_registry": {OpUpdate: "reality.status.changed"},
		},
	)
	cfg, _, _ := newDefaultTestCfg(allow, loadRealityGraphT(t))
	prequeue := &fakeDBPrequeue{}
	cfg.DB = prequeue
	return cfg, prequeue
}

func TestAttemptStateTransition_HappyPath(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	// First TX (MetaWrite): data UPDATE ok + audit INSERT ok + outbox skipped via tx.Exec append
	// Second TX (lifecycle audit): one exec ok.
	prequeue.queue = [][]txResponse{
		{{rows: 1, err: nil}, {rows: 1, err: nil}, {rows: 1, err: nil}}, // data + audit + outbox-append
		{{rows: 1, err: nil}}, // lifecycle audit
	}

	res, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "reality",
		ResourceID:   "11111111-1111-1111-1111-111111111111",
		FromState:    "active",
		ToState:      "pending_close",
		Reason:       "user-initiated close",
		Actor:        Actor{Type: ActorOwner, ID: "user-1"},
		Payload: map[string]any{
			"close_initiated_by": "user-1",
		},
	})
	if err != nil {
		t.Fatalf("AttemptStateTransition: %v", err)
	}
	if res.NewState != "pending_close" {
		t.Errorf("NewState: got %q want pending_close", res.NewState)
	}
	// AuditID must be non-zero (deterministic fakeUUIDGen returns counter-derived UUIDs).
	var zero [16]byte
	if [16]byte(res.AuditID) == zero {
		t.Errorf("AuditID is zero UUID; deterministic generator should have produced a value")
	}
	if res.TransitionAt == 0 {
		t.Errorf("TransitionAt is zero; clock should have produced a value")
	}
}

func TestAttemptStateTransition_InvalidGraph(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	// only the failed-audit TX should run
	prequeue.queue = [][]txResponse{{{rows: 1, err: nil}}}

	_, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "reality",
		ResourceID:   "abc",
		FromState:    "active",
		ToState:      "archived", // not adjacent in graph
		Actor:        Actor{Type: ActorOwner, ID: "u"},
	})
	if !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("want ErrInvalidTransition, got %v", err)
	}
}

func TestAttemptStateTransition_MutexBlocked(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	prequeue.queue = [][]txResponse{{{rows: 1, err: nil}}}

	// migrating → pending_close is forbidden by mutual_exclusion in transitions.yaml.
	_, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "reality",
		ResourceID:   "abc",
		FromState:    "migrating",
		ToState:      "pending_close",
		Actor:        Actor{Type: ActorSystem, ID: "world-service"},
	})
	// Note: migrating→pending_close isn't in the base graph either (only active→
	// and migrating→{active, frozen}), so this returns ErrInvalidTransition first.
	// To exercise pure mutex, we need a transition that IS in graph but mutex-blocked.
	// Adjust the graph: extend a copy that has mutex blocking an in-graph edge.
	if !errors.Is(err, ErrInvalidTransition) && !errors.Is(err, ErrMutualExclusion) {
		t.Fatalf("want ErrInvalidTransition or ErrMutualExclusion, got %v", err)
	}
}

func TestAttemptStateTransition_MutexBlocked_GraphAllows(t *testing.T) {
	// Construct a graph where mutex is the ONLY thing blocking the edge.
	doc := []byte(`
version: 1
resources:
  thing:
    table: reality_registry
    state_column: status
    initial_states: [a]
    terminal_states: [c]
    states: [a, b, c]
    transitions:
      - from: a
        to: [b, c]
      - from: b
        to: [c]
    mutual_exclusions:
      - if_status: a
        forbidden_transitions: [c]
`)
	g, err := ParseTransitions(doc)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}

	allow := newStaticAllowlist([]string{"reality_registry", "lifecycle_transition_audit"}, nil)
	cfg, _, _ := newDefaultTestCfg(allow, g)
	prequeue := &fakeDBPrequeue{}
	cfg.DB = prequeue
	prequeue.queue = [][]txResponse{{{rows: 1, err: nil}}}

	_, err = AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "thing",
		ResourceID:   "x",
		FromState:    "a",
		ToState:      "c",
		Actor:        Actor{Type: ActorSystem, ID: "world-service"},
	})
	if !errors.Is(err, ErrMutualExclusion) {
		t.Fatalf("want ErrMutualExclusion, got %v", err)
	}
}

func TestAttemptStateTransition_CASLost(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	// MetaWrite TX: data UPDATE returns 0 rows → ErrConcurrentStateTransition.
	// Then failed-attempt audit TX runs.
	prequeue.queue = [][]txResponse{
		{{rows: 0, err: nil}}, // data UPDATE → CAS lost
		{{rows: 1, err: nil}}, // failed-attempt audit
	}

	_, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "reality",
		ResourceID:   "abc",
		FromState:    "active",
		ToState:      "pending_close",
		Actor:        Actor{Type: ActorOwner, ID: "u"},
	})
	if !errors.Is(err, ErrConcurrentStateTransition) {
		t.Fatalf("want ErrConcurrentStateTransition, got %v", err)
	}
}

func TestAttemptStateTransition_RejectsUnknownResource(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	prequeue.queue = [][]txResponse{{{rows: 1, err: nil}}}

	_, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "no_such_resource",
		ResourceID:   "x",
		FromState:    "a",
		ToState:      "b",
		Actor:        Actor{Type: ActorSystem, ID: "x"},
	})
	if !errors.Is(err, ErrUnknownResource) {
		t.Fatalf("want ErrUnknownResource, got %v", err)
	}
}
