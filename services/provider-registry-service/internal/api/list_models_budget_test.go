package api

import (
	"encoding/json"
	"strings"
	"testing"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// D-SETTINGS-LIST-MODELS-HAS-NO-DETAIL-SELECTOR-AND-A-10KB-DEFAULT (OUT-2).
//
// Measured on the real account before this landed: the DEFAULT no-arg reply was 10,382
// bytes / ~2,595 tokens for 18 models at 15 fields each, over the kit's 8 KB warn budget —
// and the tool had no `detail` and no `limit`, so a caller had no way to ask for less. The
// per-field cost said 45% of it was fields an agent picking a model cannot act on:
//
//	pricing 14.2% · provider_credential_id 11.1% · created_at 7.4% · updated_at 7.3%
//	sort_order 2.7% · notes 1.9%
//
// This is the Go twin of the precedent the standard names,
// jobs-service test_jobs_list_default_reply_fits_the_context_budget: build more than one
// page of FAT rows, take the DEFAULT shape, and assert the reply fits the budget. It reds
// if either default (detail or limit) regresses.
//
// The cross-service OUT-2 lint cannot do this job here: scripts/context-budget-defaults-lint.py
// walks Python ASTs under /mcp/, so it never sees a Go tool at all — and it only inspects
// tools that ALREADY have detail+limit, which this one did not. A per-tool test is the only
// gate this surface has.

// fatModel mirrors what readUserModel returns, with the heavy fields at realistic size.
func fatModel(i int) map[string]any {
	return map[string]any{
		"user_model_id":          "019ebb72-27a2-72f3-a42d-d2d0e0ded1" + string(rune('a'+i%26)) + "0",
		"alias":                  strings.Repeat("gemma-3-27b-it-qat-", 2),
		"provider_kind":          "lmstudio",
		"provider_model_name":    strings.Repeat("google/gemma-3-27b-it-qat/", 2),
		"context_length":         131072,
		"capability_flags":       []string{"chat", "tools", "vision", "embedding", "rerank"},
		"tags":                   []string{"local", "fast"},
		"is_active":              true,
		"is_favorite":            false,
		"pricing":                map[string]any{"input_per_1k": 0.0, "output_per_1k": 0.0, "currency": "USD", "source": "manual"},
		"notes":                  strings.Repeat("a note the human wrote about this model. ", 3),
		"created_at":             "2026-08-14T10:11:12.131415Z",
		"updated_at":             "2026-08-24T10:11:12.131415Z",
		"sort_order":             i,
		"provider_credential_id": "019ebb72-27a2-72f3-a42d-d2d0e0ded2" + string(rune('a'+i%26)) + "0",
	}
}

// buildReply drives the REAL shaping functions the handler calls — clampListModelsLimit and
// shapeListModels — so a revert in mcp_server.go turns these tests red. Only the DB read is
// stood in for; every OUT-2 decision under test is the shipped one.
func buildReply(t *testing.T, n int, detail string, limit int) listModelsOut {
	t.Helper()
	kept := clampListModelsLimit(limit)
	if kept > n {
		kept = n
	}
	rows := make([]map[string]any, 0, kept)
	for i := 0; i < kept; i++ {
		rows = append(rows, fatModel(i))
	}
	return shapeListModels(rows, detail, n)
}

func sizeOf(t *testing.T, out listModelsOut) int {
	t.Helper()
	b, err := json.Marshal(out)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return len(b)
}

func TestListModelsDefaultReplyFitsTheContextBudget(t *testing.T) {
	// More than one page of fat rows — the default must still fit.
	got := sizeOf(t, buildReply(t, 40, "", 0))
	if warn := lwmcp.ResultWarnBytes(); got >= warn {
		t.Fatalf("default settings_list_models reply is %d bytes, over the %d-byte context-budget warn", got, warn)
	}
}

func TestTheDefaultDropsTheFieldsAnAgentCannotChooseBy(t *testing.T) {
	out := buildReply(t, 3, "", 0)
	for _, m := range out.Models {
		for _, heavy := range []string{"pricing", "notes", "created_at", "updated_at", "sort_order", "provider_credential_id"} {
			if _, present := m[heavy]; present {
				t.Fatalf("summary row still carries %q — that is 45%% of the measured payload", heavy)
			}
		}
		// The fields a model is actually CHOSEN by must survive, or the tool stops
		// answering the question it exists for.
		for _, needed := range []string{"user_model_id", "alias", "provider_kind", "capability_flags", "context_length", "is_active"} {
			if _, present := m[needed]; !present {
				t.Fatalf("summary row dropped %q — an agent cannot pick a model without it", needed)
			}
		}
	}
}

func TestDetailFullIsStillAvailable(t *testing.T) {
	// OUT-2 keeps `full` as an explicit opt-in so no caller LOSES a field.
	out := buildReply(t, 1, "full", 0)
	for _, heavy := range []string{"pricing", "notes", "created_at", "updated_at", "sort_order", "provider_credential_id"} {
		if _, present := out.Models[0][heavy]; !present {
			t.Fatalf("detail=full dropped %q — full must remain the complete shape", heavy)
		}
	}
}

func TestATruncatedListSaysSo(t *testing.T) {
	// OUT-5 — a capped list must never read as "this is everything you have".
	out := buildReply(t, 40, "", 0)
	if out.Page.Returned != listModelsDefaultLimit {
		t.Fatalf("returned %d, want the default page of %d", out.Page.Returned, listModelsDefaultLimit)
	}
	if out.Page.Total != 40 || !out.Page.HasMore {
		t.Fatalf("page %+v does not report the 30 withheld models", out.Page)
	}
	// And an UNtruncated list must not cry wolf.
	small := buildReply(t, 3, "", 0)
	if small.Page.HasMore || small.Page.Total != 3 {
		t.Fatalf("page %+v claims more when everything was returned", small.Page)
	}
}

func TestLimitIsBounded(t *testing.T) {
	// A caller can narrow UP, but not past the cap — an unbounded limit would put the
	// 45.6 KB-class reply back on the wire that OUT-2's migration exists to prevent.
	out := buildReply(t, 500, "", 10_000)
	if out.Page.Returned != listModelsMaxLimit {
		t.Fatalf("returned %d, want it clamped to %d", out.Page.Returned, listModelsMaxLimit)
	}
	if !out.Page.HasMore {
		t.Fatal("a clamped reply must still report has_more")
	}
}

func TestDetailIsAdvertisedAsAClosedSet(t *testing.T) {
	// IN-3 — the set must be in the SCHEMA, not only in the description. A closed set the
	// schema does not declare is a set the model is free to miss.
	s := lwmcp.ClosedSetSchema[listModelsIn](map[string][]any{"detail": {"summary", "full"}})
	p := lwmcp.SchemaPropAt(s, "detail")
	if len(p.Enum) == 0 {
		t.Fatal("detail carries no enum")
	}
	found := map[string]bool{}
	for _, v := range p.Enum {
		if str, ok := v.(string); ok {
			found[str] = true
		}
	}
	if !found["summary"] || !found["full"] {
		t.Fatalf("detail enum %v is missing summary/full", p.Enum)
	}
}

func TestATruncatedListWarnsInThePayloadTheModelReads(t *testing.T) {
	// 🔴 MEASURED: a structured has_more was NOT enough. With a page of 10, batch
	// c-listmodels1 asked "which of my models can do tool calling?" and the model named TWO
	// on 5/5 runs. There were FIVE — the other three sat at positions 15-17, behind
	// has_more:true, which it never mentioned and never paged past. The page was honest and
	// the ANSWER was still wrong, so the warning has to ride the text being summarised.
	out := buildReply(t, 40, "", 0)
	if !strings.Contains(out.Note, "INCOMPLETE") {
		t.Fatalf("a truncated reply must say so in the note the model reads; got %q", out.Note)
	}
	if !strings.Contains(out.Note, "limit") {
		t.Fatal("the warning must name the way OUT of it (`limit`), not just the fact")
	}
	// The original registry-vs-inventory correction must survive — it is why `note` exists.
	if !strings.Contains(out.Note, "REGISTERED") {
		t.Fatal("the truncation warning displaced the registry-vs-inventory note")
	}
	// And a COMPLETE reply must not cry wolf.
	small := buildReply(t, 3, "", 0)
	if strings.Contains(small.Note, "INCOMPLETE") {
		t.Fatalf("a complete reply must not claim truncation; got %q", small.Note)
	}
}
