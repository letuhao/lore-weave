package provider

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// C2 (BL-2) — rerank discovery: the inventory sync must tag rerank-capable models
// with the CANONICAL `rerank` token (capability_flags.rerank=true + _capability),
// across the OpenAI-shape, the Cohere-shape, and the LM Studio native parsers, so
// the RerankModelPicker filter (capability_flags @> {"rerank":true} OR
// _capability='rerank') discovers them without hand-registration.

func isRerank(m ModelInventory) bool {
	if v, _ := m.CapabilityFlags["rerank"].(bool); v {
		return true
	}
	return m.CapabilityFlags["_capability"] == "rerank"
}

func TestClassifyOpenAIModel_Rerank(t *testing.T) {
	cases := map[string]string{
		"rerank-v3.5":          "rerank",
		"rerank-english-v3.0":  "rerank",
		"bge-reranker-v2-m3":   "rerank",
		"text-embedding-3-small": "embedding",
		"gpt-4o":               "chat",
	}
	for id, want := range cases {
		if got := classifyOpenAIModel(id); got != want {
			t.Errorf("classifyOpenAIModel(%q) = %q, want %q", id, got, want)
		}
	}
}

// A live OpenAI /v1/models call never publishes context_length itself; the merge
// must fill it in from the preconfig-derived lookup by provider_model_name so a
// successful live sync doesn't regress a known model back to "unknown" window.
func TestParseOpenAIModels_MergesKnownContextLength(t *testing.T) {
	data := []any{
		map[string]any{"id": "gpt-4o"},
		map[string]any{"id": "some-brand-new-model-not-in-preconfig"},
	}
	known := map[string]int{"gpt-4o": 128000}
	got := parseOpenAIModels(data, known)
	if got[0].ContextLength == nil || *got[0].ContextLength != 128000 {
		t.Errorf("gpt-4o context_length not merged: %+v", got[0])
	}
	if got[1].ContextLength != nil {
		t.Errorf("unknown model should stay nil, got %+v", got[1])
	}
}

func TestParseOpenAIModels_TagsRerankCanonically(t *testing.T) {
	data := []any{
		map[string]any{"id": "rerank-english-v3.0"},
		map[string]any{"id": "gpt-4o"},
	}
	got := parseOpenAIModels(data, nil)
	if len(got) != 2 {
		t.Fatalf("want 2 models, got %d", len(got))
	}
	if !isRerank(got[0]) {
		t.Errorf("rerank model not tagged rerank: %+v", got[0].CapabilityFlags)
	}
	// canonical boolean flag present (NOT the divergent "reranker")
	if v, _ := got[0].CapabilityFlags["rerank"].(bool); !v {
		t.Errorf("rerank boolean flag missing: %+v", got[0].CapabilityFlags)
	}
	if got[0].CapabilityFlags["_capability"] == "reranker" {
		t.Errorf("divergent 'reranker' token reintroduced")
	}
	if isRerank(got[1]) {
		t.Errorf("chat model mis-tagged as rerank")
	}
}

func TestParseCohereModels_DetectsRerankViaEndpointsAndName(t *testing.T) {
	models := []any{
		map[string]any{"name": "rerank-v3.5", "endpoints": []any{"rerank"}, "context_length": float64(4096)},
		map[string]any{"name": "embed-english-v3.0", "endpoints": []any{"embed"}},
		map[string]any{"name": "command-r", "endpoints": []any{"chat"}},
		// no endpoints → fall back to name substring
		map[string]any{"name": "my-custom-reranker"},
		// multi-endpoint: rerank must win regardless of ordering with chat/embed
		map[string]any{"name": "multi-a", "endpoints": []any{"chat", "rerank"}},
		map[string]any{"name": "multi-b", "endpoints": []any{"rerank", "embed"}},
	}
	got := parseCohereModels(models)
	if len(got) != 6 {
		t.Fatalf("want 6 models, got %d", len(got))
	}
	if !isRerank(got[4]) {
		t.Errorf("multi-endpoint [chat,rerank] did not resolve to rerank: %+v", got[4].CapabilityFlags)
	}
	if !isRerank(got[5]) {
		t.Errorf("multi-endpoint [rerank,embed] did not resolve to rerank: %+v", got[5].CapabilityFlags)
	}
	if !isRerank(got[0]) || got[0].ContextLength == nil || *got[0].ContextLength != 4096 {
		t.Errorf("cohere rerank via endpoints not parsed: %+v ctx=%v", got[0].CapabilityFlags, got[0].ContextLength)
	}
	if got[1].CapabilityFlags["_capability"] != "embedding" {
		t.Errorf("cohere embed not tagged embedding: %+v", got[1].CapabilityFlags)
	}
	if isRerank(got[2]) {
		t.Errorf("cohere chat mis-tagged rerank")
	}
	if !isRerank(got[3]) {
		t.Errorf("cohere rerank via name fallback not detected: %+v", got[3].CapabilityFlags)
	}
}

func TestParseLMStudioNativeModels_RerankIsCanonical(t *testing.T) {
	mList := []any{
		map[string]any{"key": "bge-reranker-v2-m3", "type": "rerank", "display_name": "BGE Reranker"},
		map[string]any{"key": "some-chat", "type": "llm"},
	}
	got := parseLMStudioNativeModels(mList)
	if len(got) != 2 {
		t.Fatalf("want 2 models, got %d", len(got))
	}
	if got[0].CapabilityFlags["_capability"] != "rerank" {
		t.Errorf("LM Studio rerank not canonical (got %v, want rerank)", got[0].CapabilityFlags["_capability"])
	}
	if v, _ := got[0].CapabilityFlags["rerank"].(bool); !v {
		t.Errorf("LM Studio rerank boolean flag missing: %+v", got[0].CapabilityFlags)
	}
	if got[0].CapabilityFlags["_capability"] == "reranker" {
		t.Errorf("divergent 'reranker' token reintroduced in LM Studio parser")
	}
}

// ListModels routes a Cohere-shape /v1/models (no "data", has "models") through
// the Cohere parser — the local-rerank backend path.
func TestOpenAIAdapter_ListModels_CohereShape(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"models": []any{
				map[string]any{"name": "rerank-v3.5", "endpoints": []any{"rerank"}},
			},
		})
	}))
	defer srv.Close()
	a := &openaiAdapter{client: srv.Client(), staticInventory: []ModelInventory{}}
	got, err := a.ListModels(context.Background(), srv.URL, "")
	if err != nil {
		t.Fatalf("ListModels: %v", err)
	}
	if len(got) != 1 || !isRerank(got[0]) {
		t.Fatalf("Cohere-shape rerank not discovered: %+v", got)
	}
}

// parseLMStudioNativeIDModels parses the LM-Studio-native id-keyed /v1/models
// shape `{"models":[{"id":...,"state":...}]}` — entries carry `id`/`state`, no
// `name`/`endpoints`. Each id is classified via classifyOpenAIModel so a
// `*rerank*` id (bge-reranker-v2-m3) is canonically tagged rerank while a chat
// id (qwen2.5-7b) stays chat.
func TestParseLMStudioNativeIDModels_TagsRerankOnlyForReranker(t *testing.T) {
	models := []any{
		map[string]any{"id": "bge-reranker-v2-m3", "state": "loaded"},
		map[string]any{"id": "qwen2.5-7b", "state": "not-loaded"},
	}
	got := parseLMStudioNativeIDModels(models)
	if len(got) != 2 {
		t.Fatalf("want 2 models, got %d", len(got))
	}
	if got[0].ProviderModelName != "bge-reranker-v2-m3" {
		t.Errorf("first id mis-parsed: %+v", got[0])
	}
	if !isRerank(got[0]) {
		t.Errorf("reranker id not tagged rerank: %+v", got[0].CapabilityFlags)
	}
	if v, _ := got[0].CapabilityFlags["rerank"].(bool); !v {
		t.Errorf("reranker boolean flag missing: %+v", got[0].CapabilityFlags)
	}
	if isRerank(got[1]) {
		t.Errorf("non-rerank id (qwen2.5-7b) mis-tagged rerank: %+v", got[1].CapabilityFlags)
	}
}

// ListModels routes the LM-Studio-native id-keyed /v1/models shape (the REAL
// :28417 local-rerank backend response — `models` array whose entries carry
// `id`/`state`, no `name`/`endpoints`) to the id parser so the reranker is
// discovered + tagged. This is the C2 live-smoke-found bug: previously this
// shape fell through parseCohereModels (which keys on `name`) → 0 models.
func TestOpenAIAdapter_ListModels_LMStudioNativeIDShape(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// Verbatim shape captured from the real backend on :28417.
		_ = json.NewEncoder(w).Encode(map[string]any{
			"models": []any{
				map[string]any{
					"id": "bge-reranker-v2-m3", "state": "loaded",
					"vram_mb": 1, "ttl_seconds": 600, "keep_warm": false,
				},
				map[string]any{"id": "qwen2.5-7b", "state": "not-loaded"},
			},
		})
	}))
	defer srv.Close()
	a := &openaiAdapter{client: srv.Client(), staticInventory: []ModelInventory{}}
	got, err := a.ListModels(context.Background(), srv.URL, "")
	if err != nil {
		t.Fatalf("ListModels: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("want 2 models from id-keyed shape, got %d: %+v", len(got), got)
	}
	var reranker *ModelInventory
	for i := range got {
		if got[i].ProviderModelName == "bge-reranker-v2-m3" {
			reranker = &got[i]
		} else if isRerank(got[i]) {
			t.Errorf("non-rerank id mis-tagged rerank: %+v", got[i])
		}
	}
	if reranker == nil {
		t.Fatalf("bge-reranker-v2-m3 NOT discovered from id-keyed shape: %+v", got)
	}
	if !isRerank(*reranker) {
		t.Errorf("discovered reranker not tagged rerank: %+v", reranker.CapabilityFlags)
	}
}
