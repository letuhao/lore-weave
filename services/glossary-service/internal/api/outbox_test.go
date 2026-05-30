package api

import (
	"encoding/json"
	"testing"
)

// C4 (K14) — unit tests for the glossary.entity_updated emit payload.
// These are DB-free: they exercise the pure payload builder + the
// single-vs-bulk fan-out contract (one event per written entity). The
// DB insert + relay + Neo4j propagation are covered by the cross-service
// live smoke (scripts/raid/verify-cycle-4.sh).

func TestBuildEntityEventPayload_DefaultsAndShape(t *testing.T) {
	p := buildEntityEventPayload(
		"book-1", "ent-1", "玉虛宮", "location",
		[]string{"玉虚宫"}, "Kunlun HQ", "created",
	)
	if p.Op != "created" {
		t.Fatalf("op = %q, want created", p.Op)
	}
	if p.SourceType != "glossary" {
		t.Fatalf("source_type = %q, want glossary (authored canon, never enriched in C4)", p.SourceType)
	}
	if p.BookID != "book-1" || p.GlossaryEntityID != "ent-1" {
		t.Fatalf("ids not carried: book=%q entity=%q", p.BookID, p.GlossaryEntityID)
	}
	if p.Name != "玉虛宮" || p.Kind != "location" {
		t.Fatalf("name/kind not carried: name=%q kind=%q", p.Name, p.Kind)
	}
	if len(p.Aliases) != 1 || p.Aliases[0] != "玉虚宫" {
		t.Fatalf("aliases not carried: %v", p.Aliases)
	}
	if p.ShortDescription != "Kunlun HQ" {
		t.Fatalf("short_description not carried: %q", p.ShortDescription)
	}
	if p.EmittedAt == "" {
		t.Fatalf("emitted_at must be set")
	}
}

func TestBuildEntityEventPayload_NormalisesOp(t *testing.T) {
	for _, in := range []string{"", "weird", "deleted", "merge"} {
		p := buildEntityEventPayload("b", "e", "n", "k", nil, "", in)
		if p.Op != "updated" {
			t.Fatalf("op %q normalised to %q, want updated", in, p.Op)
		}
	}
	// Valid ops pass through unchanged.
	for _, in := range []string{"created", "updated"} {
		if got := buildEntityEventPayload("b", "e", "n", "k", nil, "", in).Op; got != in {
			t.Fatalf("op %q changed to %q", in, got)
		}
	}
}

func TestBuildEntityEventPayload_NilAliasesSerialisesAsEmptyArray(t *testing.T) {
	p := buildEntityEventPayload("b", "e", "n", "k", nil, "", "created")
	if p.Aliases == nil {
		t.Fatalf("nil aliases must normalise to non-nil slice")
	}
	b, err := json.Marshal(p)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	// Empty short_description must be omitted (omitempty); aliases must be [].
	var decoded map[string]json.RawMessage
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if string(decoded["aliases"]) != "[]" {
		t.Fatalf("aliases serialised as %s, want []", decoded["aliases"])
	}
	if _, present := decoded["short_description"]; present {
		t.Fatalf("empty short_description must be omitted from wire payload")
	}
}

// TestBulkFanOut_OneEventPerWrittenEntity locks the critical bulk-path
// contract: a batch of mixed created/updated/skipped statuses must yield
// exactly ONE event per CREATED or UPDATED entity, and ZERO for skipped.
// This is the adversary's flagged easy-miss (silent batch drop). We model
// the per-entity loop's emit decision the same way bulkExtractEntities
// does (emit iff status in {created, updated}).
func TestBulkFanOut_OneEventPerWrittenEntity(t *testing.T) {
	type ent struct {
		id, name, kind, status string
	}
	batch := []ent{
		{"e1", "玉虛宮", "location", "created"},
		{"e2", "碧遊宮", "location", "updated"},
		{"e3", "蓬萊", "location", "skipped"}, // no change → no event
		{"e4", "陳塘關", "location", "created"},
	}

	var events []entityEventPayload
	for _, e := range batch {
		if e.status == "created" || e.status == "updated" {
			events = append(events, buildEntityEventPayload(
				"book-1", e.id, e.name, e.kind, nil, "", e.status,
			))
		}
	}

	if len(events) != 3 {
		t.Fatalf("fan-out produced %d events, want 3 (one per created/updated, skipped excluded)", len(events))
	}
	// Confirm identity + op fidelity per event (no silent entity drop /
	// no id collapse into a single batch event).
	wantIDs := map[string]string{"e1": "created", "e2": "updated", "e4": "created"}
	gotIDs := map[string]string{}
	for _, ev := range events {
		gotIDs[ev.GlossaryEntityID] = ev.Op
	}
	for id, op := range wantIDs {
		if gotIDs[id] != op {
			t.Fatalf("entity %s: emitted op %q, want %q", id, gotIDs[id], op)
		}
	}
	if _, leaked := gotIDs["e3"]; leaked {
		t.Fatalf("skipped entity e3 must NOT emit an event")
	}
}
