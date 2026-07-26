package api

// Pure-part unit tests for the glossary Phase-1 plan op-set (plan_ops.go). These
// cover ONLY the parts that don't touch the DB: the registry builds without panic
// (G3 idempotency invariant holds), each IdentityKey yields the §16 dedupe key for
// a sample params blob, and Validate rejects a non-slug code / an empty-description
// attribute and accepts a good one. The Handlers hit Postgres and are covered by a
// later live-smoke — not exercised here.

import (
	"encoding/json"
	"testing"
)

// buildRegistry constructs the registry the way NewRegistry validates it at
// startup — a zero Server suffices because NewRegistry only stores the specs (no
// pool access until a Handler runs).
func TestPlanRegistry_BuildsWithoutPanic(t *testing.T) {
	s := &Server{}
	reg := s.planRegistry()
	// Phase 1 additive ops + Phase 2 slice-1 destructive deletes.
	wantAdditive := []string{"adopt_genres", "create_kinds", "add_attributes", "edit_attribute", "dismiss_candidate"}
	wantDestructive := []string{"delete_genre", "delete_kind", "delete_attribute", "merge_candidate"}
	for _, typ := range append(append([]string{}, wantAdditive...), wantDestructive...) {
		if _, ok := reg[typ]; !ok {
			t.Fatalf("registry missing op %q", typ)
		}
	}
	if len(reg) != len(wantAdditive)+len(wantDestructive) {
		t.Fatalf("expected %d ops, got %d", len(wantAdditive)+len(wantDestructive), len(reg))
	}
	// G1: Destructive is authoritative per registration — exactly the delete_* ops
	// are destructive; the additive ops are not. G3: every op must be idempotent.
	destructive := map[string]bool{}
	for _, typ := range wantDestructive {
		destructive[typ] = true
	}
	for typ, spec := range reg {
		if spec.Destructive != destructive[typ] {
			t.Errorf("op %q Destructive=%v, want %v", typ, spec.Destructive, destructive[typ])
		}
		if !spec.Idempotent {
			t.Errorf("op %q is not idempotent (NewRegistry should have panicked)", typ)
		}
	}
}

func TestPlanRegistry_IdentityKeys(t *testing.T) {
	s := &Server{}
	reg := s.planRegistry()

	cases := []struct {
		op     string
		params string
		want   string
	}{
		{"adopt_genres", `{"genres":["fantasy"],"kinds":["character"]}`, "adopt"},
		{"create_kinds", `{"kinds":[{"code":"faction","name":"Faction"}]}`, "create_kinds"},
		{"add_attributes", `{"kind_code":"character","attributes":[]}`, "character"},
		{"edit_attribute", `{"kind_code":"character","genre_code":"universal","code":"age"}`, "character/universal/age"},
	}
	for _, c := range cases {
		spec := reg[c.op]
		got, err := spec.IdentityKey(json.RawMessage(c.params))
		if err != nil {
			t.Fatalf("%s IdentityKey error: %v", c.op, err)
		}
		if got != c.want {
			t.Errorf("%s IdentityKey = %q, want %q", c.op, got, c.want)
		}
	}
}

func TestValidateCreateKinds(t *testing.T) {
	good := `{"kinds":[{"code":"faction","name":"Faction","attributes":[{"code":"leader","name":"Leader","description":"The faction's leader"}]}]}`
	if err := validateCreateKinds(json.RawMessage(good)); err != nil {
		t.Fatalf("good create_kinds rejected: %v", err)
	}

	badCode := `{"kinds":[{"code":"Faction-X","name":"Faction"}]}`
	if err := validateCreateKinds(json.RawMessage(badCode)); err == nil {
		t.Error("non-slug kind code accepted, want rejection")
	}

	emptyDesc := `{"kinds":[{"code":"faction","name":"Faction","attributes":[{"code":"leader","name":"Leader","description":"   "}]}]}`
	if err := validateCreateKinds(json.RawMessage(emptyDesc)); err == nil {
		t.Error("empty-description attribute accepted, want rejection")
	}

	nilDesc := `{"kinds":[{"code":"faction","name":"Faction","attributes":[{"code":"leader","name":"Leader"}]}]}`
	if err := validateCreateKinds(json.RawMessage(nilDesc)); err == nil {
		t.Error("missing-description attribute accepted, want rejection")
	}

	empty := `{"kinds":[]}`
	if err := validateCreateKinds(json.RawMessage(empty)); err == nil {
		t.Error("empty kinds list accepted, want rejection")
	}
}

func TestValidateAddAttributes(t *testing.T) {
	good := `{"kind_code":"character","attributes":[{"code":"age","name":"Age","description":"The character's age"}]}`
	if err := validateAddAttributes(json.RawMessage(good)); err != nil {
		t.Fatalf("good add_attributes rejected: %v", err)
	}

	badCode := `{"kind_code":"character","attributes":[{"code":"Age!","name":"Age","description":"x"}]}`
	if err := validateAddAttributes(json.RawMessage(badCode)); err == nil {
		t.Error("non-slug attribute code accepted, want rejection")
	}

	badKind := `{"kind_code":"Character X","attributes":[{"code":"age","name":"Age","description":"x"}]}`
	if err := validateAddAttributes(json.RawMessage(badKind)); err == nil {
		t.Error("non-slug kind_code accepted, want rejection")
	}

	emptyDesc := `{"kind_code":"character","attributes":[{"code":"age","name":"Age","description":""}]}`
	if err := validateAddAttributes(json.RawMessage(emptyDesc)); err == nil {
		t.Error("empty-description attribute accepted, want rejection")
	}

	noAttrs := `{"kind_code":"character","attributes":[]}`
	if err := validateAddAttributes(json.RawMessage(noAttrs)); err == nil {
		t.Error("empty attributes list accepted, want rejection")
	}
}
