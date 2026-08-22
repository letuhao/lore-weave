package meta

import "testing"

// TestPkColumnFor_L1A2Tables locks in the cycle 3 (L1.A-2) PK column
// mappings — pii_registry, pii_kek, user_consent_ledger.
// Cycle 4-10 will add more entries; this test guards against accidental
// regression of the PII+identity+consent tables.
func TestPkColumnFor_L1A2Tables(t *testing.T) {
	cases := []struct {
		table string
		want  string
	}{
		// Cycle 2 baseline (regression guard)
		{"reality_registry", "reality_id"},
		// Cycle 3 new
		{"pii_registry", "user_ref_id"},
		{"pii_kek", "kek_id"},
		{"user_consent_ledger", "user_ref_id"},
		// `player_character_index` was here and is gone with migration 035. Its
		// successor `actor_control_binding` is NOT added: it has no state
		// machine and its PK is composite, so it falls through to the heuristic
		// below — which is the correct answer for it, not an omission.
		{"actor_control_binding", "id"},
		// Fallback heuristic still works for unknown tables
		{"unknown_future_table", "id"},
	}
	for _, c := range cases {
		got := pkColumnFor(c.table)
		if got != c.want {
			t.Errorf("pkColumnFor(%q) = %q, want %q", c.table, got, c.want)
		}
	}
}

// TestAllowlist_L1A2Tables_Loaded confirms the shipped events_allowlist.yaml
// includes the 4 L1.A-2 tables plus the right event bindings.
func TestAllowlist_L1A2Tables_Loaded(t *testing.T) {
	a, err := LoadAllowlist("events_allowlist.yaml")
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}
	wantTables := []string{"pii_registry", "pii_kek", "user_consent_ledger", "actor_control_binding"}
	for _, tbl := range wantTables {
		if !a.AllowsTable(tbl) {
			t.Errorf("allowlist missing %s", tbl)
		}
	}
	// Cycle 2 tables still present
	for _, tbl := range []string{"reality_registry", "session_cost_summary"} {
		if !a.AllowsTable(tbl) {
			t.Errorf("regression: allowlist lost %s", tbl)
		}
	}

	// Event bindings — pii_registry INSERT emits user.created.
	if name, ok := a.EmitsEvent("pii_registry", OpInsert); !ok || name != "user.created" {
		t.Errorf("pii_registry INSERT: got (%q, %v) want (user.created, true)", name, ok)
	}
	// pii_kek UPDATE emits user.erased (crypto-shred path).
	if name, ok := a.EmitsEvent("pii_kek", OpUpdate); !ok || name != "user.erased" {
		t.Errorf("pii_kek UPDATE: got (%q, %v) want (user.erased, true)", name, ok)
	}
	// user_consent_ledger INSERT/UPDATE emit grant/revoke.
	if name, ok := a.EmitsEvent("user_consent_ledger", OpInsert); !ok || name != "user.consent.granted" {
		t.Errorf("user_consent_ledger INSERT: got (%q, %v)", name, ok)
	}
	if name, ok := a.EmitsEvent("user_consent_ledger", OpUpdate); !ok || name != "user.consent.revoked" {
		t.Errorf("user_consent_ledger UPDATE: got (%q, %v)", name, ok)
	}
	// actor_control_binding grant/revoke/erase (migration 034; replaced
	// player_character_index, whose pc.index.* events named a character
	// lifecycle the framing deleted — see 034's column audit).
	if name, ok := a.EmitsEvent("actor_control_binding", OpInsert); !ok || name != "actor.control.granted" {
		t.Errorf("actor_control_binding INSERT: got (%q, %v)", name, ok)
	}
	if name, ok := a.EmitsEvent("actor_control_binding", OpUpdate); !ok || name != "actor.control.revoked" {
		t.Errorf("actor_control_binding UPDATE: got (%q, %v)", name, ok)
	}
	if name, ok := a.EmitsEvent("actor_control_binding", OpDelete); !ok || name != "actor.control.erased" {
		t.Errorf("actor_control_binding DELETE: got (%q, %v)", name, ok)
	}
}

// TestSensitivePaths_ActorBindingCrossUserStillTagged confirms the
// platform-owned cross-user sensitive-path id remains valid.
//
// Renamed from PlayerIndexCrossUser with migrations 034/035: the RISK is
// unchanged — "who drives which actor" is the answer an impersonation attempt
// needs — only the table it names moved.
func TestSensitivePaths_ActorBindingCrossUserStillTagged(t *testing.T) {
	sp, err := LoadSensitivePaths("meta-sensitive-read-paths.yml")
	if err != nil {
		t.Fatalf("LoadSensitivePaths: %v", err)
	}
	if !sp.Has("actor_binding_cross_user") {
		t.Fatalf("actor_binding_cross_user sensitive path missing")
	}
	p := sp.Get("actor_binding_cross_user")
	found := false
	for _, tbl := range p.Tables {
		if tbl == "actor_control_binding" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("actor_binding_cross_user path no longer references the actor_control_binding table")
	}
}
