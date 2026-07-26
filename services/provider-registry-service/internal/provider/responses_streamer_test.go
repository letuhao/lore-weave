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

// LM Studio's /v1/responses emits NO function_call_arguments.delta events — it
// delivers the WHOLE argument string only on the batched `.done` (llama.cpp #20607).
// Before the fix the consumer got the tool NAME (from output_item.added) with EMPTY
// args, so a weaker local model "couldn't add entities". Assert the batched args
// are recovered as one fragment. Live-proven against gemma-4-26b-a4b-qat 2026-07-09.
func TestStreamResponsesSSE_LmStudioBatchedArgs(t *testing.T) {
	body := `data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"glossary_propose_entities","arguments":""}}

data: {"type":"response.function_call_arguments.done","output_index":0,"item_id":"fc_1","arguments":"{\"book_id\":\"b1\",\"items\":[{\"kind\":\"character\",\"name\":\"Lam Uyen\"}]}"}

data: {"type":"response.output_item.done","output_index":0,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"glossary_propose_entities","arguments":"{\"book_id\":\"b1\",\"items\":[{\"kind\":\"character\",\"name\":\"Lam Uyen\"}]}"}}

data: {"type":"response.completed","response":{"id":"resp_x","usage":{"input_tokens":10,"output_tokens":30}}}

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
	if first == nil || first.ToolCallID != "call_1" || first.ToolName != "glossary_propose_entities" {
		t.Fatalf("first tool_call must carry id+name from output_item.added, got %+v", first)
	}
	// output_item.done repeats the same args as function_call_arguments.done — the
	// argsSeen guard must emit them EXACTLY ONCE (no doubling across the two variants).
	if args.String() != `{"book_id":"b1","items":[{"kind":"character","name":"Lam Uyen"}]}` {
		t.Fatalf("batched args recovered once: got %q", args.String())
	}
}

// A compliant provider (OpenAI) streams `.delta` fragments AND repeats the full args
// on `.done`. The argsSeen guard must NOT re-append the batched copy — else the args
// double to invalid JSON. Regression companion to the LM Studio fallback above.
func TestStreamResponsesSSE_NoDoubleCountDeltasThenDone(t *testing.T) {
	body := `data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"glossary_search"}}

data: {"type":"response.function_call_arguments.delta","output_index":0,"delta":"{\"q\":"}

data: {"type":"response.function_call_arguments.delta","output_index":0,"delta":"\"elf\"}"}

data: {"type":"response.function_call_arguments.done","output_index":0,"arguments":"{\"q\":\"elf\"}"}

data: {"type":"response.completed","response":{"id":"resp_x","usage":{"input_tokens":10,"output_tokens":4}}}

`
	chunks := collectResponsesChunks(t, body)
	var args strings.Builder
	for i := range chunks {
		if chunks[i].Kind == StreamChunkToolCall {
			args.WriteString(chunks[i].ArgumentsDelta)
		}
	}
	if args.String() != `{"q":"elf"}` {
		t.Fatalf("streamed deltas + done must NOT double: got %q", args.String())
	}
}

// Case (c) isolation: a provider that delivers the full args ONLY on
// response.output_item.done (no function_call_arguments.done, no deltas). The
// output_item.done fallback must still recover them exactly once.
func TestStreamResponsesSSE_OutputItemDoneSoleArgsCarrier(t *testing.T) {
	body := `data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"book_get","arguments":""}}

data: {"type":"response.output_item.done","output_index":0,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"book_get","arguments":"{\"book_id\":\"b1\"}"}}

data: {"type":"response.completed","response":{"id":"resp_x","usage":{"input_tokens":5,"output_tokens":6}}}

`
	var args strings.Builder
	for _, c := range collectResponsesChunks(t, body) {
		if c.Kind == StreamChunkToolCall {
			args.WriteString(c.ArgumentsDelta)
		}
	}
	if args.String() != `{"book_id":"b1"}` {
		t.Fatalf("output_item.done as sole carrier: got %q", args.String())
	}
}

// Case (d): two PARALLEL function calls at different output_index. Args must be
// attributed to the correct call via the per-index argsSeen/toolStarted maps.
func TestStreamResponsesSSE_ParallelToolCallsByIndex(t *testing.T) {
	body := `data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","id":"fc_0","call_id":"call_0","name":"book_get"}}

data: {"type":"response.output_item.added","output_index":1,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"glossary_search"}}

data: {"type":"response.function_call_arguments.done","output_index":0,"arguments":"{\"book_id\":\"b0\"}"}

data: {"type":"response.function_call_arguments.done","output_index":1,"arguments":"{\"q\":\"elf\"}"}

data: {"type":"response.completed","response":{"id":"resp_x","usage":{"input_tokens":9,"output_tokens":8}}}

`
	byIndex := map[int]*strings.Builder{0: {}, 1: {}}
	name := map[int]string{}
	for _, c := range collectResponsesChunks(t, body) {
		if c.Kind == StreamChunkToolCall {
			byIndex[c.Index].WriteString(c.ArgumentsDelta)
			if c.ToolName != "" {
				name[c.Index] = c.ToolName
			}
		}
	}
	if name[0] != "book_get" || byIndex[0].String() != `{"book_id":"b0"}` {
		t.Fatalf("call 0 mis-attributed: name=%q args=%q", name[0], byIndex[0].String())
	}
	if name[1] != "glossary_search" || byIndex[1].String() != `{"q":"elf"}` {
		t.Fatalf("call 1 mis-attributed: name=%q args=%q", name[1], byIndex[1].String())
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
	// System is pulled OUT of input into instructions (§5), not a chained item.
	if body["instructions"] != "be terse" {
		t.Fatalf("system must become the instructions field, got %v", body["instructions"])
	}
	items, _ := body["input"].([]any)
	if len(items) != 2 {
		t.Fatalf("expected 2 input items (system moved to instructions), got %d", len(items))
	}
	// the tool message must become a function_call_output item
	last, _ := items[1].(map[string]any)
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

func TestStreamResponsesSSE_FinishReasonLengthAndToolCalls(t *testing.T) {
	// truncation → "length" (was hardcoded "stop", hiding the cap)
	trunc := `data: {"type":"response.incomplete","response":{"id":"r","status":"incomplete","incomplete_details":{"reason":"max_output_tokens"},"usage":{"input_tokens":5,"output_tokens":9}}}

`
	var done *StreamChunk
	for i, c := range collectResponsesChunks(t, trunc) {
		if c.Kind == StreamChunkDone {
			done = &collectResponsesChunks(t, trunc)[i]
		}
	}
	if done == nil || done.FinishReason != "length" {
		t.Fatalf("truncation must report finish_reason=length, got %+v", done)
	}
	// a turn that emitted a function_call → "tool_calls"
	tc := `data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","id":"fc","call_id":"c","name":"x"}}

data: {"type":"response.completed","response":{"id":"r","status":"completed","usage":{"input_tokens":1,"output_tokens":1}}}

`
	var d2 *StreamChunk
	ch := collectResponsesChunks(t, tc)
	for i := range ch {
		if ch[i].Kind == StreamChunkDone {
			d2 = &ch[i]
		}
	}
	if d2 == nil || d2.FinishReason != "tool_calls" {
		t.Fatalf("tool-call turn must report finish_reason=tool_calls, got %+v", d2)
	}
}

func TestMessagesToResponsesInput_AssistantToolCalls(t *testing.T) {
	// an assistant tool_calls message → function_call item(s) so a history replay isn't
	// an orphaned function_call_output (review H-t).
	msgs := []map[string]any{
		{"role": "assistant", "content": "", "tool_calls": []any{
			map[string]any{"id": "call_1", "type": "function", "function": map[string]any{
				"name": "glossary_search", "arguments": `{"q":"elf"}`,
			}},
		}},
		{"role": "tool", "tool_call_id": "call_1", "content": "result"},
	}
	items := messagesToResponsesInput(msgs)
	if len(items) != 2 {
		t.Fatalf("expected function_call + function_call_output, got %d: %+v", len(items), items)
	}
	fc, _ := items[0].(map[string]any)
	if fc["type"] != "function_call" || fc["call_id"] != "call_1" || fc["name"] != "glossary_search" {
		t.Fatalf("assistant tool_calls must become a function_call item, got %+v", fc)
	}
	fco, _ := items[1].(map[string]any)
	if fco["type"] != "function_call_output" || fco["call_id"] != "call_1" {
		t.Fatalf("tool result must reference the same call_id, got %+v", fco)
	}
}

func TestIsChainNotFound_MatchesOpenAIProse(t *testing.T) {
	// real OpenAI shape (prose, no machine code) must also classify.
	body := `{"error":{"message":"Previous response with id 'resp_abc' not found.","type":"invalid_request_error"}}`
	if !isChainNotFound(&ErrUpstreamPermanent{StatusCode: 404, Body: body}) {
		t.Fatal("must classify OpenAI's prose 'Previous response … not found'")
	}
}

func TestBuildResponsesBody_NestedReasoningEffort(t *testing.T) {
	// the Responses API needs NESTED reasoning.effort; the flat reasoning_effort is
	// ignored (live-verified). "off" → {"effort":"none"} disables thinking.
	b := buildResponsesBody("m", map[string]any{"messages": []any{}, "reasoning_effort": "off"})
	r, ok := b["reasoning"].(map[string]any)
	if !ok || r["effort"] != "none" {
		t.Fatalf("off must map to nested reasoning.effort=none, got %v", b["reasoning"])
	}
	if _, flat := b["reasoning_effort"]; flat {
		t.Fatal("must NOT send the flat reasoning_effort (ignored by /v1/responses)")
	}
	// "auto" → omit (model default), so no reasoning field forced.
	b2 := buildResponsesBody("m", map[string]any{"messages": []any{}, "reasoning_effort": "auto"})
	if _, has := b2["reasoning"]; has {
		t.Fatalf("auto must omit the reasoning field, got %v", b2["reasoning"])
	}
}

func TestMapResponsesEffort(t *testing.T) {
	cases := map[string]string{
		"off": "none", "none": "none", "low": "low", "fast": "low",
		"medium": "medium", "standard": "medium", "high": "high", "deep": "high",
		"minimal": "minimal", "auto": "", "": "", "weird": "",
	}
	for in, want := range cases {
		if got := mapResponsesEffort(in); got != want {
			t.Errorf("mapResponsesEffort(%q)=%q want %q", in, got, want)
		}
	}
}

func TestBuildResponsesBody_EnforcesOutputCeiling(t *testing.T) {
	// no caller max_tokens → the safety ceiling is applied (an always-reasoning local
	// model on /v1/responses can't be told to stop thinking, so it must be bounded).
	b := buildResponsesBody("m", map[string]any{"messages": []any{}})
	if b["max_output_tokens"] != 16384 {
		t.Fatalf("expected default output ceiling 16384, got %v", b["max_output_tokens"])
	}
	// a caller max_tokens wins.
	b2 := buildResponsesBody("m", map[string]any{"messages": []any{}, "max_tokens": 512})
	if toFloat(b2["max_output_tokens"]) != 512 {
		t.Fatalf("caller max_tokens must win, got %v", b2["max_output_tokens"])
	}
}

func TestIsChainNotFound_MatchesProbedLmStudioBody(t *testing.T) {
	// the EXACT body LM Studio returned for a bogus previous_response_id (probed 2026-07-06)
	body := `{"error":{"message":"Prediction history node with id 'x' not found while attempting to build chat history chain that includes this node.","type":"invalid_request_error","param":"previous_response_id","code":"previous_response_not_found"}}`
	if !isChainNotFound(&ErrUpstreamPermanent{StatusCode: 400, Body: body}) {
		t.Fatal("must classify the probed LM Studio previous_response_not_found body")
	}
	// a DIFFERENT 400 (real error) must NOT be mistaken for chain-not-found
	other := `{"error":{"message":"model not loaded","code":"model_not_found"}}`
	if isChainNotFound(&ErrUpstreamPermanent{StatusCode: 400, Body: other}) {
		t.Fatal("a non-chain 400 must NOT be classified as chain-not-found")
	}
	// a transient (5xx) is never chain-not-found
	if isChainNotFound(&ErrUpstreamTransient{StatusCode: 503}) {
		t.Fatal("5xx must not be chain-not-found")
	}
}

func TestSplitSystemInstructions(t *testing.T) {
	msgs := []map[string]any{
		{"role": "system", "content": "be terse"},
		{"role": "user", "content": "hi"},
		{"role": "system", "content": "and kind"},
	}
	instr, rest := splitSystemInstructions(msgs)
	if instr != "be terse\n\nand kind" {
		t.Fatalf("instructions join wrong: %q", instr)
	}
	if len(rest) != 1 || rest[0]["role"] != "user" {
		t.Fatalf("rest must be only non-system messages: %+v", rest)
	}
}

func TestIsStatefulRequest_GatedByFlag(t *testing.T) {
	in := map[string]any{"stateful": true}
	// default ON: marker present + flag unset → stateful
	t.Setenv("LLM_STATEFUL_CACHE", "")
	if !isStatefulRequest(in) {
		t.Fatal("stateful must be honored by default (flag unset) when the marker is set")
	}
	// explicit disable
	t.Setenv("LLM_STATEFUL_CACHE", "0")
	if isStatefulRequest(in) {
		t.Fatal("LLM_STATEFUL_CACHE=0 must disable stateful even with the marker set")
	}
	t.Setenv("LLM_STATEFUL_CACHE", "1")
	if isStatefulRequest(map[string]any{}) {
		t.Fatal("no marker → not stateful")
	}
}
