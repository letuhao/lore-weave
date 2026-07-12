package api

import (
	"encoding/json"
	"strings"
	"testing"
)

// The tool used to return domain.EntityKind — every System kind with every attribute
// definition inlined (UUIDs, auto_fill_prompt, translation_hint, sort_order…). Measured on
// the live dev catalogue: **44,254 characters, 86% of it `default_attributes`** — roughly
// 11k tokens, a THIRD of a chat turn's entire budget, for ONE read.
//
// The cost was not theoretical. gemma called this tool 24 times in a single S01 run and
// built nothing: each call buried the previous call's answer deeper in the window, so the
// model could never see what it had already fetched, so it fetched it again.
//
// The agent adopts BY CODE (glossary_adopt_standards takes kind/genre codes) and the
// attributes come down with the kind. So the attribute definitions were never actionable
// here — they were pure weight.
//
// This test pins the shape so nobody re-inlines them. A tool whose result cannot fit in the
// context of the agent that calls it is not a tool: it is a context bomb with a friendly
// description.
func TestListSystemStandards_PayloadIsCompact(t *testing.T) {
	// 19 kinds is the live System catalogue's size; each carries ~6 attributes.
	kinds := make([]standardKind, 0, 19)
	for i := 0; i < 19; i++ {
		kinds = append(kinds, standardKind{
			Code:           "cultivation_system",
			Name:           "Cultivation System",
			Description:    "A progression ladder a character climbs, with stages and costs.",
			GenreTags:      []string{"universal", "xianxia"},
			AttributeCount: 6,
		})
	}
	out := listKindsToolOut{
		Kinds: kinds,
		Note:  "Adopt these by CODE with glossary_adopt_standards (pass the kind/genre codes).",
	}
	b, err := json.Marshal(out)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	const budget = 6000 // ~1.5k tokens. The old payload was 44,254 chars (~11k tokens).
	if len(b) > budget {
		t.Fatalf("the standards payload is %d chars, over the %d budget — it is drifting back "+
			"toward the 44KB context bomb that made the agent loop", len(b), budget)
	}

	// The attribute DEFINITIONS must not come back. A count is fine; the objects are not.
	s := string(b)
	for _, banned := range []string{"default_attributes", "auto_fill_prompt", "attr_def_id", "translation_hint"} {
		if strings.Contains(s, banned) {
			t.Fatalf("%q is back in the standards payload — that is 86%% of the old 44KB, and "+
				"the agent cannot act on it (it adopts by CODE)", banned)
		}
	}
	if !strings.Contains(s, "attribute_count") {
		t.Fatal("attribute_count is gone — the agent should still know a kind carries a schema")
	}
}
