package meta

import "testing"

// TestPkColumnFor_L1A2Tables locks in the cycle 3 (L1.A-2) PK column
// mappings — pii_registry, pii_kek, user_consent_ledger, player_character_index.
// Cycle 4-10 will add more entries; this test guards against accidental
// regression of the 4 PII+identity+consent tables.
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
		{"player_character_index", "pc_index_id"},
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
	wantTables := []string{"pii_registry", "pii_kek", "user_consent_ledger", "player_character_index"}
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
	// player_character_index INSERT/UPDATE.
	if name, ok := a.EmitsEvent("player_character_index", OpInsert); !ok || name != "pc.index.created" {
		t.Errorf("player_character_index INSERT: got (%q, %v)", name, ok)
	}
	if name, ok := a.EmitsEvent("player_character_index", OpUpdate); !ok || name != "pc.index.status.changed" {
		t.Errorf("player_character_index UPDATE: got (%q, %v)", name, ok)
	}
}

// TestSensitivePaths_PlayerIndexCrossUserStillTagged confirms cycle 2's
// platform-owned sensitive-path id remains valid now that the actual
// player_character_index table ships (cycle 3). The id was stable-listed
// in cycle 2 so callers could already register against it.
func TestSensitivePaths_PlayerIndexCrossUserStillTagged(t *testing.T) {
	sp, err := LoadSensitivePaths("meta-sensitive-read-paths.yml")
	if err != nil {
		t.Fatalf("LoadSensitivePaths: %v", err)
	}
	if !sp.Has("player_index_cross_user") {
		t.Fatalf("player_index_cross_user sensitive path missing (cycle 2 regression)")
	}
	p := sp.Get("player_index_cross_user")
	found := false
	for _, tbl := range p.Tables {
		if tbl == "player_character_index" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("player_index_cross_user path no longer references player_character_index table")
	}
}
