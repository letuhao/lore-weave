package api

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

// 🔴 THE PLATFORM'S LARGEST SINGLE CONTEXT COST, AND THE COMPACTOR ALREADY EXISTED.
//
// `compactBookOntologyOf` was written for this exact bloat and is applied at
// `glossary_book_ontology_read`. The durable-gate result replays the same effect and returned
// its RAW HTTP body, so the identical ontology reached the model uncompacted. Measured over
// tool calls since 2026-08-24:
//
//	glossary_book_ontology_read    81 calls     385 kB    avg  4.8 kB   compacted
//	glossary_task_provide_input    98 calls   4,485 kB    avg 46.0 kB   NOT compacted
//
// Ten times the size for the same data, which made that one tool 37.6% of ALL tool-result
// bytes on the platform — three times the next contributor.

// taskResult mirrors effectResultFromRecorder: the raw effect body AND its generic parse.
// Both are needed, because the compactor reads the TYPED shape.
func taskResult(t *testing.T, m map[string]any) any {
	t.Helper()
	body, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var v any
	if err := json.Unmarshal(body, &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	return compactOntologyForTheModel(body, v)
}

func ontologyBody() map[string]any {
	return map[string]any{
		"book_id": "01a060a4-6e8b-7cd3-b8fc-52236777ea13",
		"genres": []any{map[string]any{
			"genre_id": "g1", "code": "universal", "name": "Universal",
			"base_version": "2026-08-23T04:00:00Z"}},
		"kinds": []any{map[string]any{
			"book_kind_id": "k1", "code": "character", "name": "Character",
			"base_version": "2026-08-23T04:00:01Z"}},
		"kind_genres": []any{map[string]any{"kind_id": "k1", "genre_id": "g1"}},
		"attributes": []any{map[string]any{
			"attr_id": "a1", "kind_id": "k1", "genre_id": "g1",
			"code": "name", "name": "Name", "field_type": "text", "is_required": true,
			"description":      strings.Repeat("a long definition a reader does not act on. ", 12),
			"auto_fill_prompt": strings.Repeat("a whole LLM prompt inlined per attribute. ", 12),
			"options":          []any{"one", "two", "three"},
			"sort_order":       float64(1),
			"source_ref":       "system:4b60dd22",
			"merge_strategy":   "fill_if_empty",
			"base_version":     "2026-08-23T04:00:03.965255Z",
		}},
	}
}

func TestTheGateResultIsCompactedLikeTheReadTool(t *testing.T) {
	out, ok := taskResult(t, ontologyBody()).(*compactBookOntology)
	if !ok {
		t.Fatalf("the ontology result was not compacted: %T", taskResult(t, ontologyBody()))
	}
	blob, _ := json.Marshal(out)
	for _, gone := range []string{"auto_fill_prompt", "kind_genres", "attr_id", "merge_strategy"} {
		if strings.Contains(string(blob), gone) {
			t.Errorf("%q is still on the wire — this is the bloat the compactor exists to drop", gone)
		}
	}
	if len(out.Attributes) != 1 || out.Attributes[0].Code != "name" {
		t.Fatalf("the attribute row did not survive: %+v", out.Attributes)
	}
	// Addressed by CODE, which is what glossary_book_patch takes.
	if out.Attributes[0].KindCode != "character" {
		t.Errorf("kind_code = %q, want the resolved code — an id the patch tool cannot use "+
			"is worse than no id", out.Attributes[0].KindCode)
	}
}

// 🔴 THE FIELD THAT MUST SURVIVE. base_version is passed back 442 times across 5 tools; the
// read tool's own note says a compact shape MUST keep it "or a read→patch flow breaks (the OCC
// token would be un-obtainable without a re-read)".
func TestEveryOCCTokenSurvivesTheCompaction(t *testing.T) {
	out := taskResult(t, ontologyBody()).(*compactBookOntology)
	if out.Attributes[0].BaseVersion == "" {
		t.Error("the attribute lost its base_version — every guarded patch degrades to " +
			"last-writer-wins")
	}
	if out.Kinds[0].BaseVersion == "" || out.Genres[0].BaseVersion == "" {
		t.Error("a kind or genre lost its base_version")
	}
}

// 🔴 THE TEETH AGAINST A BLANKET PROJECTION. This resolver dispatches EVERY glossary
// descriptor. Compacting anything else would strip `kind_id` from a create_kind result — the
// very id that result exists to return.
func TestANonOntologyResultIsUntouched(t *testing.T) {
	created := map[string]any{"kind_id": "k9", "code": "faction", "outcome": "action_done"}
	out, ok := taskResult(t, created).(map[string]any)
	if !ok || out["kind_id"] != "k9" {
		t.Fatalf("a create_kind result was mangled: %v", out)
	}
	// A PARTIAL ontology is not the adopt shape and must not be compacted.
	partial := map[string]any{"genres": []any{}, "kinds": []any{},
		"attributes": []any{map[string]any{"attr_id": "a1"}}}
	if _, compacted := taskResult(t, partial).(*compactBookOntology); compacted {
		t.Error("a partial shape was compacted — the gate must require all four collections")
	}
	// Non-object bodies pass through rather than being dropped.
	if got := compactOntologyForTheModel([]byte("[1,2]"), []any{1, 2}); got == nil {
		t.Error("a non-object result was dropped")
	}
	// An unreadable body hands back the generic parse rather than losing the result.
	if got := compactOntologyForTheModel([]byte("not json"), ontologyBody()); got == nil {
		t.Error("an unreadable body dropped a result the caller is waiting on")
	}
}

func TestItIsMateriallySmaller(t *testing.T) {
	before, _ := json.Marshal(ontologyBody())
	after, _ := json.Marshal(taskResult(t, ontologyBody()))
	if len(after) >= len(before) {
		t.Fatalf("no reduction: %d -> %d", len(before), len(after))
	}
	t.Logf("payload %d -> %d bytes (%.0f%% smaller)", len(before), len(after),
		100*(1-float64(len(after))/float64(len(before))))
}

// 🔴 THE GUARD ABOVE WAS VACUOUS FOR THE WIRING AND THIS ONE IS WHY.
//
// Every test above calls `compactOntologyForTheModel` directly, so they prove the projection
// WORKS — not that anything USES it. Bypassing the call site (returning the raw `v` from
// effectResultFromRecorder) left them all green, which is precisely the shape of a mechanism
// that fires in a test and never runs in production. This one goes through the real
// chokepoint: the recorder the durable-gate resolver actually returns from.
func TestTheRESOLVERSOwnPathCompactsTheOntology(t *testing.T) {
	body, err := json.Marshal(ontologyBody())
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	rec := httptest.NewRecorder()
	rec.Code = 200
	rec.Body = bytes.NewBuffer(body)

	got, err := effectResultFromRecorder(rec)
	if err != nil {
		t.Fatalf("effectResultFromRecorder: %v", err)
	}
	if _, ok := got.(*compactBookOntology); !ok {
		t.Fatalf("the resolver returned the RAW ontology (%T) — the compactor is not wired "+
			"into the path the model actually reads, which is the whole defect", got)
	}
	blob, _ := json.Marshal(got)
	if strings.Contains(string(blob), "auto_fill_prompt") {
		t.Error("a whole LLM prompt per attribute is still reaching the model")
	}
}

// The error/empty arms of the same chokepoint must be unchanged by the projection.
func TestTheRESOLVERSOtherOutcomesAreUnchanged(t *testing.T) {
	bad := httptest.NewRecorder()
	bad.Code = 409
	bad.Body = bytes.NewBufferString(`{"message":"already adopted"}`)
	if _, err := effectResultFromRecorder(bad); err == nil {
		t.Error("a 4xx effect stopped producing a failed task")
	}
	empty := httptest.NewRecorder()
	empty.Code = 204
	empty.Body = bytes.NewBuffer(nil)
	got, err := effectResultFromRecorder(empty)
	if err != nil {
		t.Fatalf("204: %v", err)
	}
	if m, ok := got.(map[string]any); !ok || m["outcome"] != "action_done" {
		t.Errorf("an empty 2xx no longer yields action_done: %v", got)
	}
}
