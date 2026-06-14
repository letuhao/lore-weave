package meta

import (
	"context"
	"errors"
	"strings"
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

// S13 D-S13-LIFECYCLE-AUDIT-ATOMICITY: the SUCCESS lifecycle audit must ride in the
// SAME TX as the status UPDATE — exactly ONE BeginTx, and the lifecycle_transition_audit
// INSERT must be among that single TX's execs (not a separate transaction that a
// crash could skip).
func TestAttemptStateTransition_LifecycleAuditIsSameTx(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	// ONE TX: data UPDATE + meta_write_audit + lifecycle audit (no Outbox configured).
	prequeue.queue = [][]txResponse{
		{{rows: 1, err: nil}, {rows: 1, err: nil}, {rows: 1, err: nil}},
	}
	_, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "reality", ResourceID: "11111111-1111-1111-1111-111111111111",
		FromState: "active", ToState: "pending_close", Reason: "close",
		Actor: Actor{Type: ActorOwner, ID: "user-1"},
	})
	if err != nil {
		t.Fatalf("AttemptStateTransition: %v", err)
	}
	if prequeue.begins != 1 {
		t.Errorf("BeginTx called %d times; success path MUST use exactly ONE TX (atomic audit)", prequeue.begins)
	}
	if prequeue.lastTx == nil || !prequeue.lastTx.committed {
		t.Fatal("expected the single TX to commit")
	}
	var sawLifecycle bool
	for _, e := range prequeue.lastTx.execs {
		if strings.Contains(e.Query, "lifecycle_transition_audit") {
			sawLifecycle = true
		}
	}
	if !sawLifecycle {
		t.Errorf("lifecycle_transition_audit INSERT not found in the status-UPDATE TX — audit is not atomic with the transition")
	}
}

// Atomicity teeth: if a later exec in the TX fails, the status change AND the
// lifecycle audit roll back together (the TX never commits) — proving they share
// fate. (The data UPDATE + meta_write_audit succeed; the lifecycle audit exec fails.)
func TestAttemptStateTransition_LifecycleAuditRollsBackWithTransition(t *testing.T) {
	cfg, prequeue := newReadyCfg(t)
	prequeue.queue = [][]txResponse{
		// data UPDATE ok, meta_write_audit ok, lifecycle audit FAILS → whole TX rolls back.
		{{rows: 1, err: nil}, {rows: 1, err: nil}, {rows: 0, err: errors.New("lifecycle audit insert boom")}},
	}
	_, err := AttemptStateTransition(context.Background(), cfg, TransitionRequest{
		ResourceType: "reality", ResourceID: "11111111-1111-1111-1111-111111111111",
		FromState: "active", ToState: "pending_close", Reason: "close",
		Actor: Actor{Type: ActorOwner, ID: "user-1"},
	})
	if err == nil {
		t.Fatal("expected error when the lifecycle audit insert fails")
	}
	// The MAIN TX (txs[0]) carries the status UPDATE + meta_write_audit + the failing
	// lifecycle audit — it MUST roll back (never commit). (A 2nd TX is then opened for
	// the failed-attempt audit, which DOES commit by design — that's txs[1].)
	if len(prequeue.txs) == 0 {
		t.Fatal("no TX opened")
	}
	main := prequeue.txs[0]
	if main.committed {
		t.Error("main TX committed despite the lifecycle audit failing — status change NOT rolled back with the audit (atomicity broken)")
	}
	if main.rollbacks == 0 {
		t.Error("main TX never rolled back")
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
