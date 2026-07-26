package testsafe

import "testing"

func TestIsThrowawayDBName(t *testing.T) {
	// Real service DBs (from the live database list) — MUST be treated as production.
	production := []string{
		"loreweave_book", "loreweave_glossary", "loreweave_knowledge",
		"loreweave_composition", "loreweave_auth", "loreweave_chat",
		"loreweave_statistics", // no "test" substring — the tricky one ("statis"+"tics")
		"loreweave_provider_registry", "loreweave_usage_billing", "loreweave_learning",
		"loreweave_agent_registry", "loreweave_events", "loreweave_catalog",
	}
	for _, name := range production {
		if IsThrowawayDBName(name) {
			t.Errorf("production DB %q wrongly classified as throwaway (guard would NOT protect it)", name)
		}
		if err := EnsureThrowawayDB(name); err == nil {
			t.Errorf("EnsureThrowawayDB(%q) returned nil — a destructive test could wipe production", name)
		}
	}

	// Disposable DBs (from the live list) — MUST be allowed.
	throwaway := []string{
		"loreweave_book_test", "loreweave_book_migtest", "loreweave_book_s02test",
		"loreweave_book_ws0test", "loreweave_glossary_delattr_smoke",
		"loreweave_comp_s01audit", "loreweave_l3ef_smoke", "loreweave_pr_planner_smoke",
		"loreweave_composition_stage1_test", "throwaway_db", "book_scratch",
	}
	for _, name := range throwaway {
		if !IsThrowawayDBName(name) {
			t.Errorf("throwaway DB %q wrongly classified as production (guard would break a legit test)", name)
		}
		if err := EnsureThrowawayDB(name); err != nil {
			t.Errorf("EnsureThrowawayDB(%q) errored on a legit throwaway DB: %v", name, err)
		}
	}

	// Empty / whitespace is refused (fail-closed).
	if err := EnsureThrowawayDB(""); err == nil {
		t.Error("EnsureThrowawayDB(\"\") must refuse an empty database name")
	}
	if err := EnsureThrowawayDB("   "); err == nil {
		t.Error("EnsureThrowawayDB(\"   \") must refuse a whitespace database name")
	}
}
