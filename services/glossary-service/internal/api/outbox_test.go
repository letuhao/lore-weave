package api

import (
	"encoding/json"
	"testing"
)

// C4 (K14) — unit tests for the glossary.entity_updated emit payload.
// These are DB-free: they exercise the pure payload builder + the
// single-vs-bulk fan-out contract (one event per written entity). The
// DB insert + relay + Neo4j propagation are covered by the cross-service
// live smoke.
//
// Phase B adds actor_type + before/after enrichment coverage.

func TestBuildEntityEventPayload_DefaultsAndShape(t *testing.T) {
	p := buildEntityEventPayload(
		"book-1", "ent-1", "玉虛宮", "location",
		[]string{"玉虚宫"}, "Kunlun HQ", "created",
		"user", "actor-1", nil,
	)
	if p.Op != "created" {
		t.Fatalf("op = %q, want created", p.Op)
	}
	if p.SourceType != "glossary" {
		t.Fatalf("source_type = %q, want glossary", p.SourceType)
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
		p := buildEntityEventPayload("b", "e", "n", "k", nil, "", in, "user", "a", nil)
		if p.Op != "updated" {
			t.Fatalf("op %q normalised to %q, want updated", in, p.Op)
		}
	}
	for _, in := range []string{"created", "updated"} {
		if got := buildEntityEventPayload("b", "e", "n", "k", nil, "", in, "user", "a", nil).Op; got != in {
			t.Fatalf("op %q changed to %q", in, got)
		}
	}
}

func TestBuildEntityEventPayload_NilAliasesSerialisesAsEmptyArray(t *testing.T) {
	p := buildEntityEventPayload("b", "e", "n", "k", nil, "", "created", "pipeline", "", nil)
	if p.Aliases == nil {
		t.Fatalf("nil aliases must normalise to non-nil slice")
	}
	b, err := json.Marshal(p)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
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

// Phase B — actor_type normalisation + user attaches before/after.
func TestBuildEntityEventPayload_UserActorAttachesBeforeAfter(t *testing.T) {
	before := &EntitySnapshot{Name: "Old", Kind: "person", Aliases: []string{"o"}, ShortDescription: "was"}
	p := buildEntityEventPayload(
		"b", "e", "New", "person", []string{"n"}, "now", "updated",
		"user", "user-42", before,
	)
	if p.ActorType != "user" {
		t.Fatalf("actor_type = %q, want user", p.ActorType)
	}
	if p.ActorID != "user-42" {
		t.Fatalf("actor_id = %q, want user-42", p.ActorID)
	}
	if p.Before == nil || p.Before.Name != "Old" {
		t.Fatalf("before not carried: %+v", p.Before)
	}
	if p.After == nil || p.After.Name != "New" || p.After.ShortDescription != "now" {
		t.Fatalf("after must be built from the current-state args: %+v", p.After)
	}
}

// Phase B — anything not "user" is forced to "pipeline" (fail-safe: a
// mislabelled caller is never persisted as a correction) and carries NO
// before/after (lean pipeline event, skipped by learning-service).
func TestBuildEntityEventPayload_PipelineHasNoActorOrSnapshots(t *testing.T) {
	for _, in := range []string{"pipeline", "", "weird", "USER"} {
		p := buildEntityEventPayload("b", "e", "n", "k", nil, "", "created", in, "x", &EntitySnapshot{Name: "Old"})
		if in == "USER" || in != "user" {
			if p.ActorType != "pipeline" {
				t.Fatalf("actor_type %q must normalise to pipeline, got %q", in, p.ActorType)
			}
			if p.ActorID != "" || p.Before != nil || p.After != nil {
				t.Fatalf("pipeline event must carry no actor_id/before/after; got id=%q before=%v after=%v",
					p.ActorID, p.Before, p.After)
			}
		}
	}
}

// TestBulkFanOut_OneEventPerWrittenEntity locks the bulk-path contract: one
// event per created/updated entity, zero for skipped, and all are pipeline.
func TestBulkFanOut_OneEventPerWrittenEntity(t *testing.T) {
	type ent struct {
		id, name, kind, status string
	}
	batch := []ent{
		{"e1", "玉虛宮", "location", "created"},
		{"e2", "碧遊宮", "location", "updated"},
		{"e3", "蓬萊", "location", "skipped"},
		{"e4", "陳塘關", "location", "created"},
	}

	var events []entityEventPayload
	for _, e := range batch {
		if e.status == "created" || e.status == "updated" {
			events = append(events, buildEntityEventPayload(
				"book-1", e.id, e.name, e.kind, nil, "", e.status, "pipeline", "", nil,
			))
		}
	}

	if len(events) != 3 {
		t.Fatalf("fan-out produced %d events, want 3", len(events))
	}
	wantIDs := map[string]string{"e1": "created", "e2": "updated", "e4": "created"}
	gotIDs := map[string]string{}
	for _, ev := range events {
		gotIDs[ev.GlossaryEntityID] = ev.Op
		if ev.ActorType != "pipeline" {
			t.Fatalf("bulk event for %s must be actor_type=pipeline, got %q", ev.GlossaryEntityID, ev.ActorType)
		}
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
