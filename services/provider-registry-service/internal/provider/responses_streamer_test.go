package provider

import (
	"context"
	"strings"
	"testing"
)

func collectResponsesChunks(t *testing.T, body string) []StreamChunk {
	t.Helper()
	var chunks []StreamChunk
	emit := func(c StreamChunk) error {
		chunks = append(chunks, c)
		return nil
	}
	if err := streamResponsesSSE(context.Background(), strings.NewReader(body), emit); err != nil {
		t.Fatalf("streamResponsesSSE: %v", err)
	}
	return chunks
}

func TestStreamResponsesSSE_TextAndUsageWithCacheAndChainId(t *testing.T) {
	// the 99% measured turn: 1711 cached of 1727, plus the chain head on Done.
	body := `data: {"type":"response.created","response":{"id":"resp_abc"}}

data: {"type":"response.output_text.delta","delta":"Hello"}

data: {"type":"response.output_text.delta","delta":" there"}

data: {"type":"response.completed","response":{"id":"resp_abc","usage":{"input_tokens":1727,"output_tokens":16,"input_tokens_details":{"cached_tokens":1711}}}}

`
	chunks := collectResponsesChunks(t, body)
	var toks []string
	var usage, done *StreamChunk
	for i := range chunks {
		switch chunks[i].Kind {
		case StreamChunkToken:
			toks = append(toks, chunks[i].Delta)
		case StreamChunkUsage:
			usage = &chunks[i]
		case StreamChunkDone:
			done = &chunks[i]
		}
	}
	if strings.Join(toks, "") != "Hello there" {
		t.Fatalf("text: got %q", strings.Join(toks, ""))
	}
	if usage == nil || usage.InputTokens != 1727 {
		t.Fatalf("usage input: %+v", usage)
	}
	if usage.CacheReadTokens == nil || *usage.CacheReadTokens != 1711 {
		t.Fatalf("cache_read: got %v, want 1711", usage.CacheReadTokens)
	}
	if usage.CacheCreationTokens != nil {
		t.Fatalf("responses API has no write charge: creation must be nil, got %v", usage.CacheCreationTokens)
	}
	if done == nil || done.ResponseID != "resp_abc" {
		t.Fatalf("Done must carry the chain head resp_abc, got %+v", done)
	}
}

func TestStreamResponsesSSE_ToolCallReassembly(t *testing.T) {
	body := `data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"glossary_search"}}

data: {"type":"response.function_call_arguments.delta","output_index":0,"delta":"{\"q\":"}

data: {"type":"response.function_call_arguments.delta","output_index":0,"delta":"\"elf\"}"}

data: {"type":"response.completed","response":{"id":"resp_x","usage":{"input_tokens":10,"output_tokens":4}}}

`
	chunks := collectResponsesChunks(t, body)
	var first *StreamChunk
	var args strings.Builder
	for i := range chunks {
		if chunks[i].Kind == StreamChunkToolCall {
			if first == nil {
				first = &chunks[i]
			}
			args.WriteString(chunks[i].ArgumentsDelta)
		}
	}
	if first == nil || first.ToolCallID != "call_1" || first.ToolName != "glossary_search" {
		t.Fatalf("first tool_call must carry id+name from output_item.added, got %+v", first)
	}
	if args.String() != `{"q":"elf"}` {
		t.Fatalf("reassembled args: got %q", args.String())
	}
}

func TestStreamResponsesSSE_FailedSurfacesError(t *testing.T) {
	body := `data: {"type":"response.failed","response":{"error":{"message":"model overloaded"}}}

`
	chunks := collectResponsesChunks(t, body)
	var errc *StreamChunk
	for i := range chunks {
		if chunks[i].Kind == StreamChunkError {
			errc = &chunks[i]
		}
	}
	if errc == nil || !strings.Contains(errc.Message, "overloaded") {
		t.Fatalf("expected surfaced upstream error, got %+v", errc)
	}
}

func TestBuildResponsesBody_ConvertsMessagesToolsAndChain(t *testing.T) {
	input := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "be terse"},
			map[string]any{"role": "user", "content": "hi"},
			map[string]any{"role": "tool", "tool_call_id": "call_1", "content": "result text"},
		},
		"previous_response_id": "resp_prev",
		"tools": []any{
			map[string]any{"type": "function", "function": map[string]any{
				"name": "glossary_search", "description": "d",
				"parameters": map[string]any{"type": "object"},
			}},
		},
	}
	body := buildResponsesBody("local-model", input)

	if body["previous_response_id"] != "resp_prev" {
		t.Fatalf("chain id not forwarded: %v", body["previous_response_id"])
	}
	if body["store"] != true {
		t.Fatal("store must be true so previous_response_id can chain")
	}
	items, _ := body["input"].([]any)
	if len(items) != 3 {
		t.Fatalf("expected 3 input items, got %d", len(items))
	}
	// the tool message must become a function_call_output item
	last, _ := items[2].(map[string]any)
	if last["type"] != "function_call_output" || last["call_id"] != "call_1" || last["output"] != "result text" {
		t.Fatalf("tool result → function_call_output conversion wrong: %+v", last)
	}
	// tools flattened to responses shape (no nested "function")
	tools, _ := body["tools"].([]any)
	tool0, _ := tools[0].(map[string]any)
	if tool0["type"] != "function" || tool0["name"] != "glossary_search" {
		t.Fatalf("tool not flattened to responses shape: %+v", tool0)
	}
	if _, nested := tool0["function"]; nested {
		t.Fatal("responses tool must be FLAT (no nested function object)")
	}
}

func TestIsStatefulRequest_GatedByFlag(t *testing.T) {
	in := map[string]any{"stateful": true}
	// flag off (default) → not stateful even if the marker is present
	if isStatefulRequest(in) {
		t.Fatal("stateful must be gated off when LLM_STATEFUL_CACHE is unset")
	}
	t.Setenv("LLM_STATEFUL_CACHE", "1")
	if !isStatefulRequest(in) {
		t.Fatal("stateful must be honored when the marker is set AND the flag is on")
	}
	if isStatefulRequest(map[string]any{}) {
		t.Fatal("no marker → not stateful")
	}
}
