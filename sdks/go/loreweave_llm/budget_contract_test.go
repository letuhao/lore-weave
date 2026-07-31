package loreweave_llm

// Go's half of the D-LLM-BUDGET-SSOT drift lock (contracts/llm-budget.contract.json).
//
// The omit rule — max_tokens==0 means "no cap, drop the field" — is implemented FOUR times:
// here (`omitempty`), in the Python SDK (`to_request_body` pops a 0), in the Rust SDK
// (`normalize()` coerces Some(0) to None), and in provider-registry's adapters. Each one
// documented the rule in a comment; none of them checked the others. A struct tag is
// especially easy to drift — deleting `,omitempty` is a one-word edit that silently starts
// sending `"max_tokens":0`, which most providers read as "cap output at 0 tokens".
//
// So this asserts the BEHAVIOUR (marshal a request, look at the bytes) rather than reading
// the tag back, and it reads the expected sentinel from the shared contract rather than
// hardcoding 0 in a second place.

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type budgetContract struct {
	OmitSentinel struct {
		Value               int `json:"value"`
		AnthropicSubstitute int `json:"anthropic_substitute"`
	} `json:"omit_sentinel"`
	TruncatedFinishReason string `json:"truncated_finish_reason"`
	OutputKinds           map[string]struct {
		TruncationIsFatal bool `json:"truncation_is_fatal"`
	} `json:"output_kinds"`
}

func loadBudgetContract(t *testing.T) budgetContract {
	t.Helper()
	// sdks/go/loreweave_llm -> repo root
	p := filepath.Join("..", "..", "..", "contracts", "llm-budget.contract.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read budget contract: %v", err)
	}
	var c budgetContract
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse budget contract: %v", err)
	}
	if len(c.OutputKinds) == 0 {
		t.Fatal("contract declares no output kinds — a vacuous contract passes everything")
	}
	return c
}

func TestOmitSentinelIsDroppedFromTheWire(t *testing.T) {
	c := loadBudgetContract(t)
	req := StreamRequest{
		ModelSource: ModelSourceUser,
		ModelRef:    "00000000-0000-0000-0000-000000000000",
		Messages:    []Message{{Role: "user", Content: "hi"}},
		MaxTokens:   c.OmitSentinel.Value,
	}
	b, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var body map[string]any
	if err := json.Unmarshal(b, &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, present := body["max_tokens"]; present {
		t.Fatalf("the omit sentinel %d reached the wire (%s) — most providers read it as "+
			"'cap output at 0 tokens'. Did `,omitempty` get dropped from MaxTokens?",
			c.OmitSentinel.Value, string(b))
	}
}

func TestARealBudgetSurvivesSerialization(t *testing.T) {
	// The other direction: an `omitempty` that swallowed everything would pass the test
	// above just as loudly.
	req := StreamRequest{
		ModelSource: ModelSourceUser,
		ModelRef:    "00000000-0000-0000-0000-000000000000",
		Messages:    []Message{{Role: "user", Content: "hi"}},
		MaxTokens:   1200,
	}
	b, _ := json.Marshal(req)
	var body map[string]any
	_ = json.Unmarshal(b, &body)
	if got, ok := body["max_tokens"]; !ok || int(got.(float64)) != 1200 {
		t.Fatalf("a real budget did not survive: %s", string(b))
	}
}

func TestFinishReasonIsCarriedOnTheResult(t *testing.T) {
	// A truncation-fatal call MUST be able to see this. It is populated by the client's
	// `done` handler; a Result without the field would make the check unwritable, which is
	// how glossary-service ended up repairing truncated JSON as if it were malformed.
	c := loadBudgetContract(t)
	r := Result{FinishReason: c.TruncatedFinishReason}
	if r.FinishReason != c.TruncatedFinishReason {
		t.Fatalf("Result.FinishReason does not round-trip the contract's %q",
			c.TruncatedFinishReason)
	}
}
