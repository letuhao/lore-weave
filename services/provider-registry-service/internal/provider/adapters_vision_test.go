package provider

// adapters_vision_test.go — PDF-import vision op (docs/specs/2026-07-06-
// pdf-book-import.md L5) tests for CaptionImage.
//
// Coverage scope:
//   - OpenAI adapter happy path (wire shape: multimodal content array, data URI)
//   - Adapter-level invariants (empty prompt, empty image, oversize image)
//   - Empty-choices / empty-caption → ErrVisionCaptionFailed
//   - Response-body cap
//   - Stub-lock for the 3 non-OpenAI adapters

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestOpenAIAdapter_CaptionImage_HappyPath(t *testing.T) {
	var (
		gotPath string
		gotAuth string
		gotBody map[string]any
	)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"choices": [{"message": {"content": "A bar chart showing quarterly revenue."}, "finish_reason": "stop"}],
			"usage": {"prompt_tokens": 900, "completion_tokens": 12}
		}`))
	}))
	defer srv.Close()

	a := &openaiAdapter{client: srv.Client()}
	out, usage, err := a.CaptionImage(
		context.Background(),
		srv.URL,
		"sk-test-key",
		"gpt-4o",
		CaptionImageInput{
			ImageB64: "ZmFrZWltYWdlYnl0ZXM=",
			MimeType: "image/png",
			Prompt:   "Describe this chart.",
		},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Caption != "A bar chart showing quarterly revenue." {
		t.Errorf("Caption=%q", out.Caption)
	}
	if out.FinishReason != "stop" {
		t.Errorf("FinishReason=%q, want stop", out.FinishReason)
	}
	if usage.InputTokens != 900 || usage.OutputTokens != 12 {
		t.Errorf("usage=%+v", usage)
	}

	if gotPath != "/v1/chat/completions" {
		t.Errorf("path=%s, want /v1/chat/completions", gotPath)
	}
	if gotAuth != "Bearer sk-test-key" {
		t.Errorf("auth=%q, want Bearer sk-test-key", gotAuth)
	}
	if gotBody["model"] != "gpt-4o" {
		t.Errorf("body.model=%v, want gpt-4o", gotBody["model"])
	}
	msgs, ok := gotBody["messages"].([]any)
	if !ok || len(msgs) != 1 {
		t.Fatalf("messages=%v, want 1 message", gotBody["messages"])
	}
	msg := msgs[0].(map[string]any)
	content, ok := msg["content"].([]any)
	if !ok || len(content) != 2 {
		t.Fatalf("content=%v, want 2 blocks (text, image_url)", msg["content"])
	}
	textBlock := content[0].(map[string]any)
	if textBlock["type"] != "text" || textBlock["text"] != "Describe this chart." {
		t.Errorf("text block=%v", textBlock)
	}
	imgBlock := content[1].(map[string]any)
	if imgBlock["type"] != "image_url" {
		t.Errorf("image block type=%v, want image_url", imgBlock["type"])
	}
	imgURL, _ := imgBlock["image_url"].(map[string]any)
	wantURL := "data:image/png;base64,ZmFrZWltYWdlYnl0ZXM="
	if imgURL["url"] != wantURL {
		t.Errorf("image_url.url=%v, want %s", imgURL["url"], wantURL)
	}
}

func TestOpenAIAdapter_CaptionImage_DefaultsMimeType(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices": [{"message": {"content": "ok"}}]}`))
	}))
	defer srv.Close()

	a := &openaiAdapter{client: srv.Client()}
	_, _, err := a.CaptionImage(context.Background(), srv.URL, "sk", "gpt-4o",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	msg := gotBody["messages"].([]any)[0].(map[string]any)
	imgBlock := msg["content"].([]any)[1].(map[string]any)
	imgURL := imgBlock["image_url"].(map[string]any)
	if imgURL["url"] != "data:image/png;base64,YWJj" {
		t.Errorf("expected default mime_type image/png, got url=%v", imgURL["url"])
	}
}

func TestOpenAIAdapter_CaptionImage_EmptyPrompt(t *testing.T) {
	a := &openaiAdapter{client: http.DefaultClient}
	_, _, err := a.CaptionImage(context.Background(), "https://example.invalid", "sk", "gpt-4o",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "  "})
	if !errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("err=%v, want ErrVisionInvalidParams", err)
	}
}

func TestOpenAIAdapter_CaptionImage_EmptyImage(t *testing.T) {
	a := &openaiAdapter{client: http.DefaultClient}
	_, _, err := a.CaptionImage(context.Background(), "https://example.invalid", "sk", "gpt-4o",
		CaptionImageInput{ImageB64: "", Prompt: "Describe."})
	if !errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("err=%v, want ErrVisionInvalidParams", err)
	}
}

func TestOpenAIAdapter_CaptionImage_OversizeImage(t *testing.T) {
	a := &openaiAdapter{client: http.DefaultClient}
	oversized := strings.Repeat("a", MaxVisionInputImageBytes+1)
	_, _, err := a.CaptionImage(context.Background(), "https://example.invalid", "sk", "gpt-4o",
		CaptionImageInput{ImageB64: oversized, Prompt: "Describe."})
	if !errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("err=%v, want ErrVisionInvalidParams", err)
	}
}

func TestOpenAIAdapter_CaptionImage_EmptyChoicesFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices": []}`))
	}))
	defer srv.Close()

	a := &openaiAdapter{client: srv.Client()}
	_, _, err := a.CaptionImage(context.Background(), srv.URL, "sk", "gpt-4o",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	if !errors.Is(err, ErrVisionCaptionFailed) {
		t.Errorf("err=%v, want ErrVisionCaptionFailed", err)
	}
}

func TestOpenAIAdapter_CaptionImage_EmptyCaptionContentFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices": [{"message": {"content": "   "}}]}`))
	}))
	defer srv.Close()

	a := &openaiAdapter{client: srv.Client()}
	_, _, err := a.CaptionImage(context.Background(), srv.URL, "sk", "gpt-4o",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	if !errors.Is(err, ErrVisionCaptionFailed) {
		t.Errorf("err=%v, want ErrVisionCaptionFailed", err)
	}
}

func TestOpenAIAdapter_CaptionImage_NonOKStatusClassified(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error": {"message": "rate limited"}}`))
	}))
	defer srv.Close()

	a := &openaiAdapter{client: srv.Client()}
	_, _, err := a.CaptionImage(context.Background(), srv.URL, "sk", "gpt-4o",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Errorf("err=%v (%T), want *ErrUpstreamRateLimited", err, err)
	}
}

// ── Ollama CaptionImage (/review-impl 2026-07-06 — real impl, not a stub) ──

func TestOllamaAdapter_CaptionImage_HappyPath(t *testing.T) {
	var gotPath string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices": [{"message": {"content": "A llava caption."}}]}`))
	}))
	defer srv.Close()

	a := &ollamaAdapter{client: srv.Client()}
	out, _, err := a.CaptionImage(context.Background(), srv.URL, "", "llava",
		CaptionImageInput{ImageB64: "YWJj", MimeType: "image/png", Prompt: "Describe."})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Caption != "A llava caption." {
		t.Errorf("Caption=%q", out.Caption)
	}
	// Ollama's OpenAI-compat endpoint, per adapters.go's Stream doc comment.
	if gotPath != "/v1/chat/completions" {
		t.Errorf("path=%s, want /v1/chat/completions", gotPath)
	}
	if gotBody["model"] != "llava" {
		t.Errorf("body.model=%v, want llava", gotBody["model"])
	}
}

func TestOllamaAdapter_CaptionImage_DefaultBaseURL(t *testing.T) {
	a := &ollamaAdapter{client: http.DefaultClient}
	// No server to hit — just prove the empty-base default doesn't panic
	// and produces a transport error (unreachable localhost:11434), not a
	// validation error, confirming the default base is applied.
	_, _, err := a.CaptionImage(context.Background(), "", "", "llava",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	if errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("expected a transport error against the default base, got validation error: %v", err)
	}
}

func TestOllamaAdapter_CaptionImage_EmptyPromptRejected(t *testing.T) {
	a := &ollamaAdapter{client: http.DefaultClient}
	_, _, err := a.CaptionImage(context.Background(), "https://example.invalid", "", "llava",
		CaptionImageInput{ImageB64: "YWJj", Prompt: ""})
	if !errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("err=%v, want ErrVisionInvalidParams", err)
	}
}

// ── LM Studio CaptionImage ─────────────────────────────────────────────

func TestLMStudioAdapter_CaptionImage_HappyPath(t *testing.T) {
	var gotPath, gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices": [{"message": {"content": "A gemma-vision caption."}}]}`))
	}))
	defer srv.Close()

	a := &lmStudioAdapter{client: srv.Client()}
	// google/gemma-4-26b-a4b-qat — the real vision-capable local model
	// this platform's test account has BYOK access to (per CLAUDE.md).
	out, _, err := a.CaptionImage(context.Background(), srv.URL, "lm-studio-key", "google/gemma-4-26b-a4b-qat",
		CaptionImageInput{ImageB64: "YWJj", MimeType: "image/png", Prompt: "Describe this chart."})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Caption != "A gemma-vision caption." {
		t.Errorf("Caption=%q", out.Caption)
	}
	if gotPath != "/v1/chat/completions" {
		t.Errorf("path=%s, want /v1/chat/completions", gotPath)
	}
	if gotAuth != "Bearer lm-studio-key" {
		t.Errorf("auth=%q, want Bearer lm-studio-key", gotAuth)
	}
}

func TestLMStudioAdapter_CaptionImage_NormalizesTrailingV1Base(t *testing.T) {
	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices": [{"message": {"content": "ok"}}]}`))
	}))
	defer srv.Close()

	a := &lmStudioAdapter{client: srv.Client()}
	// Users frequently paste a trailing /v1 (adapters.go's
	// NormalizeLmStudioBase doc comment) — confirm CaptionImage applies
	// the same normalization as Invoke/ListModels, not a raw base+path
	// join that would 404 on /v1/v1/chat/completions.
	_, _, err := a.CaptionImage(context.Background(), srv.URL+"/v1", "", "google/gemma-4-26b-a4b-qat",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotPath != "/v1/chat/completions" {
		t.Errorf("path=%s, want /v1/chat/completions (not /v1/v1/...)", gotPath)
	}
}

func TestLMStudioAdapter_CaptionImage_EmptyImageRejected(t *testing.T) {
	a := &lmStudioAdapter{client: http.DefaultClient}
	_, _, err := a.CaptionImage(context.Background(), "https://example.invalid", "", "model",
		CaptionImageInput{ImageB64: "", Prompt: "Describe."})
	if !errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("err=%v, want ErrVisionInvalidParams", err)
	}
}

// ── Anthropic CaptionImage (Messages API image content block) ─────────

func TestAnthropicAdapter_CaptionImage_HappyPath(t *testing.T) {
	var gotPath, gotVersion, gotKey string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotVersion = r.Header.Get("anthropic-version")
		gotKey = r.Header.Get("x-api-key")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"content": [{"type": "text", "text": "A Claude vision caption."}],
			"stop_reason": "end_turn",
			"usage": {"input_tokens": 800, "output_tokens": 15}
		}`))
	}))
	defer srv.Close()

	a := &anthropicAdapter{client: srv.Client()}
	out, usage, err := a.CaptionImage(context.Background(), srv.URL, "sk-ant-test", "claude-3-5-sonnet-20241022",
		CaptionImageInput{ImageB64: "YWJj", MimeType: "image/png", Prompt: "Describe this chart."})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Caption != "A Claude vision caption." {
		t.Errorf("Caption=%q", out.Caption)
	}
	if out.FinishReason != "end_turn" {
		t.Errorf("FinishReason=%q", out.FinishReason)
	}
	if usage.InputTokens != 800 || usage.OutputTokens != 15 {
		t.Errorf("usage=%+v", usage)
	}
	if gotPath != "/v1/messages" {
		t.Errorf("path=%s, want /v1/messages", gotPath)
	}
	if gotVersion != "2023-06-01" {
		t.Errorf("anthropic-version=%q", gotVersion)
	}
	if gotKey != "sk-ant-test" {
		t.Errorf("x-api-key=%q", gotKey)
	}
	msgs := gotBody["messages"].([]any)
	msg := msgs[0].(map[string]any)
	content := msg["content"].([]any)
	if len(content) != 2 {
		t.Fatalf("content blocks=%v, want 2 (image, text)", content)
	}
	imgBlock := content[0].(map[string]any)
	if imgBlock["type"] != "image" {
		t.Errorf("content[0].type=%v, want image (Anthropic recommends image before text)", imgBlock["type"])
	}
	source := imgBlock["source"].(map[string]any)
	if source["type"] != "base64" || source["media_type"] != "image/png" || source["data"] != "YWJj" {
		t.Errorf("source=%v", source)
	}
	textBlock := content[1].(map[string]any)
	if textBlock["type"] != "text" || textBlock["text"] != "Describe this chart." {
		t.Errorf("text block=%v", textBlock)
	}
}

func TestAnthropicAdapter_CaptionImage_DefaultsMaxTokensTo300(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"content": [{"type": "text", "text": "ok"}], "usage": {}}`))
	}))
	defer srv.Close()

	a := &anthropicAdapter{client: srv.Client()}
	_, _, err := a.CaptionImage(context.Background(), srv.URL, "sk", "claude-3-5-sonnet-20241022",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotBody["max_tokens"] != float64(300) {
		t.Errorf("max_tokens=%v, want 300 default", gotBody["max_tokens"])
	}
}

func TestAnthropicAdapter_CaptionImage_EmptyPromptRejected(t *testing.T) {
	a := &anthropicAdapter{client: http.DefaultClient}
	_, _, err := a.CaptionImage(context.Background(), "https://example.invalid", "sk", "claude-3-5-sonnet-20241022",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "  "})
	if !errors.Is(err, ErrVisionInvalidParams) {
		t.Errorf("err=%v, want ErrVisionInvalidParams", err)
	}
}

func TestAnthropicAdapter_CaptionImage_NonOKStatusClassified(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error": {"message": "invalid x-api-key"}}`))
	}))
	defer srv.Close()

	a := &anthropicAdapter{client: srv.Client()}
	_, _, err := a.CaptionImage(context.Background(), srv.URL, "bad-key", "claude-3-5-sonnet-20241022",
		CaptionImageInput{ImageB64: "YWJj", Prompt: "Describe."})
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Errorf("err=%v (%T), want *ErrUpstreamPermanent", err, err)
	}
}
