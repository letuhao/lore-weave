package llmbudget

// Teeth for glossary's call-profile registry, and the service half of the
// D-LLM-BUDGET-SSOT drift lock.

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func contract(t *testing.T) map[string]any {
	t.Helper()
	// internal/llmbudget -> services/glossary-service -> services -> repo root
	p := filepath.Join("..", "..", "..", "..", "contracts", "llm-budget.contract.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read budget contract: %v", err)
	}
	var c map[string]any
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse budget contract: %v", err)
	}
	return c
}

func TestTruncatedFinishReasonMatchesTheContract(t *testing.T) {
	want, _ := contract(t)["truncated_finish_reason"].(string)
	if want == "" {
		t.Fatal("contract declares no truncated_finish_reason")
	}
	if TruncatedFinishReason != want {
		t.Fatalf("drift: package says %q, contract says %q", TruncatedFinishReason, want)
	}
	if !Truncated(want) {
		t.Fatalf("Truncated(%q) is false — a real clip would go unnoticed", want)
	}
	// The other direction: a Truncated() that returned true for everything would satisfy the
	// check above and turn every successful call into an error.
	for _, fr := range []string{"stop", "tool_calls", "", "content_filter"} {
		if Truncated(fr) {
			t.Fatalf("Truncated(%q) is true — normal completions would be reported as clips", fr)
		}
	}
}

func TestStructuredTruncationIsFatalMatchesTheContract(t *testing.T) {
	kinds, ok := contract(t)["output_kinds"].(map[string]any)
	if !ok || len(kinds) == 0 {
		t.Fatal("contract declares no output kinds — a vacuous contract passes everything")
	}
	structured, ok := kinds["structured"].(map[string]any)
	if !ok {
		t.Fatal("contract has no `structured` kind")
	}
	if fatal, _ := structured["truncation_is_fatal"].(bool); !fatal {
		t.Fatal("the contract no longer calls a clipped structured response fatal — every row " +
			"in this registry is built on that being true")
	}
	// Every glossary LLM call parses JSON, so every row must agree.
	for code, p := range Profiles {
		if !p.TruncationIsFatal {
			t.Fatalf("%q is not marked truncation-fatal, but every glossary LLM call parses JSON", code)
		}
	}
}

func TestNoRowUsesTheOmitSentinel(t *testing.T) {
	// 0 means "no cap, let the model decide" platform-wide. That is correct for a
	// translation and catastrophic for a JSON extraction — it is the exact state both
	// glossary call sites shipped in.
	sentinel := 0
	if om, ok := contract(t)["omit_sentinel"].(map[string]any); ok {
		if v, ok := om["value"].(float64); ok {
			sentinel = int(v)
		}
	}
	for code, p := range Profiles {
		if p.MaxTokens == sentinel {
			t.Fatalf("%q declares the omit sentinel %d — an uncapped structured call is the "+
				"bug this registry exists to remove", code, sentinel)
		}
		if p.MaxTokens <= 0 {
			t.Fatalf("%q has a non-positive budget %d", code, p.MaxTokens)
		}
	}
}

func TestARepairRoundGetsAtLeastAsMuchRoomAsItsFirstAttempt(t *testing.T) {
	// The repair re-emits the SAME object. A smaller allowance there would guarantee the
	// clip the first attempt just avoided — and the repair prompt cannot say so.
	for _, pair := range [][2]string{
		{"doc_extract", "doc_extract_repair"},
		{"action_plan", "action_plan_repair"},
	} {
		first, repair := MaxTokensFor(pair[0]), MaxTokensFor(pair[1])
		if repair < first {
			t.Fatalf("%s repair budget %d < first attempt %d", pair[0], repair, first)
		}
	}
}

func TestEveryRowCarriesAReason(t *testing.T) {
	for code, p := range Profiles {
		if strings.TrimSpace(p.Why) == "" {
			t.Fatalf("%q has no rationale", code)
		}
	}
}

func TestForPanicsOnAnUnknownCode(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("For() returned for an unknown code — a silent default re-creates the " +
				"unattributed budget this registry removes")
		}
	}()
	_ = For("no_such_call")
}

func TestTruncationErrorNamesTheCauseAsCapacityNotMalformedOutput(t *testing.T) {
	// The whole point. Both call sites used to feed a clipped response into a repair round
	// that said "Your previous output was invalid" — telling the model it produced malformed
	// syntax when it produced correct syntax that got cut off. The model then "fixes" grammar
	// it never got wrong, and the cheapest way to satisfy both the complaint and the same
	// limit is to emit a SHORTER list: parses cleanly, reports success, drops entities.
	msg := TruncationError("doc_extract", 4096).Error()
	for _, want := range []string{"cut off", "output limit", "capacity limit", "not a"} {
		if !strings.Contains(msg, want) {
			t.Fatalf("truncation error does not say %q: %s", want, msg)
		}
	}
	if strings.Contains(strings.ToLower(msg), "invalid") {
		t.Fatalf("truncation error reuses the malformed-output wording it exists to replace: %s", msg)
	}
}
