package jobs

import (
	"encoding/json"
	"testing"
)

func TestDecodeChunkConfig_Empty(t *testing.T) {
	for _, raw := range []json.RawMessage{nil, json.RawMessage(""), json.RawMessage("null")} {
		c, err := DecodeChunkConfig(raw)
		if err != nil {
			t.Errorf("empty/null should not error: %v", err)
		}
		if c != nil {
			t.Errorf("expected nil for empty/null, got %#v", c)
		}
	}
}

func TestDecodeChunkConfig_StrategyNone(t *testing.T) {
	c, err := DecodeChunkConfig(json.RawMessage(`{"strategy":"none"}`))
	if err != nil || c != nil {
		t.Errorf("strategy=none should map to nil config, got c=%#v err=%v", c, err)
	}
}

func TestDecodeChunkConfig_Tokens(t *testing.T) {
	c, err := DecodeChunkConfig(json.RawMessage(`{"strategy":"tokens","size":1500,"overlap":150}`))
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if c == nil || c.Strategy != "tokens" || c.Size != 1500 || c.Overlap != 150 {
		t.Errorf("decoded wrong: %#v", c)
	}
}

func TestExtractChattableText_FindsLastUserMessage(t *testing.T) {
	input := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "be helpful"},
			map[string]any{"role": "user", "content": "old turn"},
			map[string]any{"role": "assistant", "content": "ok"},
			map[string]any{"role": "user", "content": "summarize this long doc"},
		},
	}
	got, ok := ExtractChattableText(input)
	if !ok || got != "summarize this long doc" {
		t.Errorf("got=%q ok=%v", got, ok)
	}
}

func TestExtractChattableText_NoMessages(t *testing.T) {
	got, ok := ExtractChattableText(map[string]any{})
	if ok || got != "" {
		t.Errorf("expected empty, got %q ok=%v", got, ok)
	}
}

func TestExtractChattableText_NoUserMessage(t *testing.T) {
	input := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "x"},
			map[string]any{"role": "assistant", "content": "y"},
		},
	}
	got, ok := ExtractChattableText(input)
	if ok || got != "" {
		t.Errorf("expected empty, got %q ok=%v", got, ok)
	}
}

func TestExtractChattableText_NonStringContent(t *testing.T) {
	// Anthropic tool calls / structured content (list of parts) — we
	// can't chunk this trivially; caller falls back to single-call.
	input := map[string]any{
		"messages": []any{
			map[string]any{"role": "user", "content": []any{
				map[string]any{"type": "text", "text": "hi"},
			}},
		},
	}
	got, ok := ExtractChattableText(input)
	if ok || got != "" {
		t.Errorf("structured content shouldn't be chunkable, got %q ok=%v", got, ok)
	}
}

func TestSubstituteLastUserMessage_ReplacesContentOnly(t *testing.T) {
	input := map[string]any{
		"temperature": 0.3,
		"messages": []any{
			map[string]any{"role": "system", "content": "preserved"},
			map[string]any{"role": "user", "content": "old"},
			map[string]any{"role": "assistant", "content": "ok"},
			map[string]any{"role": "user", "content": "OLD-CONTENT"},
		},
	}
	out, err := SubstituteLastUserMessage(input, "NEW-CHUNK")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	// Top-level fields preserved
	if out["temperature"] != 0.3 {
		t.Errorf("temperature lost: %v", out["temperature"])
	}
	msgs := out["messages"].([]any)
	if len(msgs) != 4 {
		t.Fatalf("messages length wrong: %d", len(msgs))
	}
	// System message untouched
	if msgs[0].(map[string]any)["content"] != "preserved" {
		t.Errorf("system message mutated: %v", msgs[0])
	}
	// First user message untouched
	if msgs[1].(map[string]any)["content"] != "old" {
		t.Errorf("first user message mutated: %v", msgs[1])
	}
	// Last user message replaced
	if msgs[3].(map[string]any)["content"] != "NEW-CHUNK" {
		t.Errorf("last user message not replaced: %v", msgs[3])
	}
	// Source not mutated (deep clone of last message; shallow copy of others is OK
	// because we never mutated them)
	srcLast := input["messages"].([]any)[3].(map[string]any)
	if srcLast["content"] != "OLD-CONTENT" {
		t.Errorf("source mutated: %v", srcLast)
	}
}

func TestSubstituteLastUserMessage_ErrorsOnEmptyMessages(t *testing.T) {
	_, err := SubstituteLastUserMessage(map[string]any{}, "x")
	if err == nil {
		t.Errorf("expected error for empty input")
	}
}
