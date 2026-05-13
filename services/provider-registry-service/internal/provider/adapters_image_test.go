package provider

// adapters_image_test.go — Phase 5c-α tests for GenerateImage.
//
// Coverage scope:
//   - OpenAI adapter happy path (url mode, b64 mode, n>1, revised_prompt)
//   - Content-policy detection (JSON-first per /review-impl(DESIGN) MED#3)
//   - Adapter-level invariants (Prompt empty, N>cap, bad ResponseFormat
//     — all per /review-impl(DESIGN) MED#5)
//   - Response-body cap (/review-impl(DESIGN) LOW#6)
//   - Stub-lock for the 3 non-OpenAI adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ── OpenAI GenerateImage ──────────────────────────────────────────────

func TestOpenAIAdapter_GenerateImage_HappyPath_URLMode(t *testing.T) {
	var (
		gotMethod      string
		gotPath        string
		gotAuth        string
		gotContentType string
		gotBody        map[string]any
	)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotContentType = r.Header.Get("Content-Type")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"created": 1700000000,
			"data": [{"url": "https://cdn.example/img/abc.png"}]
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	out, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test-key",
		"noobai-xl-v1.1",
		GenerateImageInput{
			Prompt: "cinematic landscape at golden hour",
			Size:   "1024x1024",
			N:      1,
		},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Output assertions
	if out.Created != 1700000000 {
		t.Errorf("Created=%d, want 1700000000", out.Created)
	}
	if len(out.Data) != 1 {
		t.Fatalf("len(Data)=%d, want 1", len(out.Data))
	}
	if out.Data[0].URL != "https://cdn.example/img/abc.png" {
		t.Errorf("URL=%q, want https://cdn.example/img/abc.png", out.Data[0].URL)
	}

	// Wire-shape assertions
	if gotMethod != http.MethodPost {
		t.Errorf("method=%s, want POST", gotMethod)
	}
	if gotPath != "/v1/images/generations" {
		t.Errorf("path=%s, want /v1/images/generations", gotPath)
	}
	if gotAuth != "Bearer sk-test-key" {
		t.Errorf("auth=%q, want Bearer sk-test-key", gotAuth)
	}
	if gotContentType != "application/json" {
		t.Errorf("content-type=%q, want application/json", gotContentType)
	}
	if gotBody["model"] != "noobai-xl-v1.1" {
		t.Errorf("body.model=%v, want noobai-xl-v1.1", gotBody["model"])
	}
	if gotBody["prompt"] != "cinematic landscape at golden hour" {
		t.Errorf("body.prompt=%v", gotBody["prompt"])
	}
	if gotBody["size"] != "1024x1024" {
		t.Errorf("body.size=%v, want 1024x1024", gotBody["size"])
	}
	// n=1 should be present (json.Marshal treats int 1 as 1.0 via map[string]any)
	if v, ok := gotBody["n"]; !ok || (v != float64(1) && v != 1) {
		t.Errorf("body.n=%v (type %T), want 1", v, v)
	}
}

func TestOpenAIAdapter_GenerateImage_MultiImage_N2(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"created": 1700000001,
			"data": [
				{"url": "https://cdn.example/img/a.png"},
				{"url": "https://cdn.example/img/b.png"}
			]
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	out, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-2",
		GenerateImageInput{Prompt: "two cats", N: 2},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out.Data) != 2 {
		t.Fatalf("len(Data)=%d, want 2", len(out.Data))
	}
	if out.Data[0].URL == "" || out.Data[1].URL == "" {
		t.Errorf("Data[0].URL=%q Data[1].URL=%q", out.Data[0].URL, out.Data[1].URL)
	}
}

func TestOpenAIAdapter_GenerateImage_B64Mode(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		var body map[string]any
		_ = json.Unmarshal(raw, &body)
		if body["response_format"] != "b64_json" {
			t.Errorf("body.response_format=%v, want b64_json", body["response_format"])
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"created": 1700000002,
			"data": [{"b64_json": "iVBORw0KGgoAAAANSUhEUg=="}]
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	out, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "a forest", ResponseFormat: "b64_json"},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Data[0].B64JSON != "iVBORw0KGgoAAAANSUhEUg==" {
		t.Errorf("B64JSON=%q", out.Data[0].B64JSON)
	}
	if out.Data[0].URL != "" {
		t.Errorf("URL should be empty in b64 mode, got %q", out.Data[0].URL)
	}
}

func TestOpenAIAdapter_GenerateImage_RevisedPrompt(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"created": 1700000003,
			"data": [{
				"url": "https://cdn.example/img.png",
				"revised_prompt": "a cinematic landscape at golden hour with volumetric light"
			}]
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	out, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "landscape"},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out.Data[0].RevisedPrompt, "volumetric light") {
		t.Errorf("RevisedPrompt=%q (expected upstream's rewrite)", out.Data[0].RevisedPrompt)
	}
}

// ── Content-policy detection (Fix #3) ─────────────────────────────────

func TestOpenAIAdapter_GenerateImage_ContentPolicy_JSONErrorCode(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(400)
		_, _ = w.Write([]byte(`{
			"error": {
				"code": "content_policy_violation",
				"message": "Your request was rejected as a result of our safety system",
				"type": "image_generation_user_error"
			}
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "anything"},
	)
	if !errors.Is(err, ErrImageContentPolicy) {
		t.Fatalf("expected ErrImageContentPolicy, got %v", err)
	}
}

// TestOpenAIAdapter_GenerateImage_ContentPolicy_PromptEchoNotMisclassified
// pins Fix #3 — if upstream echoes the user's prompt back inside the
// error message (e.g., "your prompt 'X content_policy_violation Y'
// was rejected"), the JSON-first check must reject this as NOT a
// content-policy rejection (because `error.code` is something else).
func TestOpenAIAdapter_GenerateImage_ContentPolicy_PromptEchoNotMisclassified(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(400)
		// error.code is something else; message contains the substring
		// but JSON-first MUST trust the structural code field.
		_, _ = w.Write([]byte(`{
			"error": {
				"code": "invalid_request_error",
				"message": "Your prompt 'discussing content_policy_violation in poetry' is too long",
				"type": "invalid_request_error"
			}
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "anything"},
	)
	if errors.Is(err, ErrImageContentPolicy) {
		t.Errorf("JSON-first check failed — prompt echo wrongly classified as content-policy: %v", err)
	}
	// Should classify as upstream permanent (400)
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Errorf("expected *ErrUpstreamPermanent for non-policy 400, got %T: %v", err, err)
	}
}

// TestOpenAIAdapter_GenerateImage_ContentPolicy_NonJSONSubstringFallback
// pins the substring fallback for non-JSON error bodies (HTML error
// pages from misconfigured upstreams).
func TestOpenAIAdapter_GenerateImage_ContentPolicy_NonJSONSubstringFallback(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(400)
		_, _ = w.Write([]byte(`<html><body>safety_system blocked this request</body></html>`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "anything"},
	)
	if !errors.Is(err, ErrImageContentPolicy) {
		t.Errorf("expected ErrImageContentPolicy via substring fallback, got %v", err)
	}
}

// ── Adapter-level invariants (Fix #5) ─────────────────────────────────

func TestOpenAIAdapter_GenerateImage_RejectsEmptyPrompt(t *testing.T) {
	upstreamCalled := false
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: ""},
	)
	if !errors.Is(err, ErrImageInvalidParams) {
		t.Fatalf("expected ErrImageInvalidParams for empty prompt, got %v", err)
	}
	if upstreamCalled {
		t.Error("upstream MUST NOT be called when adapter pre-check fires")
	}
}

func TestOpenAIAdapter_GenerateImage_RejectsNOverCap(t *testing.T) {
	upstreamCalled := false
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-2",
		GenerateImageInput{Prompt: "a cat", N: MaxImagesPerJob + 1},
	)
	if !errors.Is(err, ErrImageInvalidParams) {
		t.Fatalf("expected ErrImageInvalidParams for N>cap, got %v", err)
	}
	if !strings.Contains(err.Error(), "exceeds cap") {
		t.Errorf("error should mention 'exceeds cap': %v", err)
	}
	if upstreamCalled {
		t.Error("upstream MUST NOT be called when adapter N-cap fires")
	}
}

func TestOpenAIAdapter_GenerateImage_RejectsNegativeN(t *testing.T) {
	a := &openaiAdapter{client: &http.Client{}}
	_, _, err := a.GenerateImage(
		context.Background(),
		"http://example.invalid",
		"sk-test",
		"dall-e-2",
		GenerateImageInput{Prompt: "a cat", N: -1},
	)
	if !errors.Is(err, ErrImageInvalidParams) {
		t.Fatalf("expected ErrImageInvalidParams for N<0, got %v", err)
	}
}

func TestOpenAIAdapter_GenerateImage_RejectsBadResponseFormat(t *testing.T) {
	upstreamCalled := false
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "a cat", ResponseFormat: "jpeg"},
	)
	if !errors.Is(err, ErrImageInvalidParams) {
		t.Fatalf("expected ErrImageInvalidParams for bad response_format, got %v", err)
	}
	if upstreamCalled {
		t.Error("upstream MUST NOT be called when adapter response_format check fires")
	}
}

// ── Response body cap (Fix #6) ────────────────────────────────────────

func TestOpenAIAdapter_GenerateImage_OversizeResponseRejected(t *testing.T) {
	// Build an oversized JSON response (>MaxImageResponseBytes).
	huge := bytes.Repeat([]byte("A"), MaxImageResponseBytes+1024)
	body := fmt.Sprintf(`{"created":1700000000,"data":[{"b64_json":"%s"}]}`, huge)

	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-2",
		GenerateImageInput{Prompt: "a cat", ResponseFormat: "b64_json"},
	)
	if !errors.Is(err, ErrImageGenerationFailed) {
		t.Fatalf("expected ErrImageGenerationFailed for oversize response, got %v", err)
	}
	if !strings.Contains(err.Error(), "exceeds") {
		t.Errorf("error should mention 'exceeds': %v", err)
	}
}

// ── Upstream typed-error classification (reuses Phase 5a helpers) ─────

func TestOpenAIAdapter_GenerateImage_RateLimit429(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "5")
		w.WriteHeader(429)
		_, _ = w.Write([]byte(`{"error":{"code":"rate_limit_exceeded","message":"slow down"}}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "anything"},
	)
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %v", err)
	}
	if rl.RetryAfterS == nil || *rl.RetryAfterS != 5.0 {
		t.Errorf("RetryAfterS=%v, want 5.0", rl.RetryAfterS)
	}
}

func TestOpenAIAdapter_GenerateImage_AuthFailed401(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(401)
		_, _ = w.Write([]byte(`{"error":{"code":"invalid_api_key","message":"bad key"}}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "anything"},
	)
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Fatalf("expected *ErrUpstreamPermanent for 401, got %v", err)
	}
	if perm.StatusCode != 401 {
		t.Errorf("StatusCode=%d, want 401", perm.StatusCode)
	}
}

// ── Empty-data rejection ──────────────────────────────────────────────

func TestOpenAIAdapter_GenerateImage_EmptyDataArrayRejected(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"created":1700000000,"data":[]}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateImage(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"dall-e-3",
		GenerateImageInput{Prompt: "anything"},
	)
	if !errors.Is(err, ErrImageGenerationFailed) {
		t.Fatalf("expected ErrImageGenerationFailed for empty data, got %v", err)
	}
}

// ── Stub adapters MUST return ErrOperationNotSupported ────────────────

func TestNonOpenAIAdapters_GenerateImage_Unsupported(t *testing.T) {
	cases := []struct {
		name    string
		adapter Adapter
	}{
		{name: "anthropic", adapter: &anthropicAdapter{}},
		{name: "ollama", adapter: &ollamaAdapter{}},
		{name: "lmStudio", adapter: &lmStudioAdapter{}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, _, err := tc.adapter.GenerateImage(
				context.Background(),
				"https://upstream.example",
				"sk-test",
				"some-model",
				GenerateImageInput{Prompt: "anything"},
			)
			if !errors.Is(err, ErrOperationNotSupported) {
				t.Fatalf("expected ErrOperationNotSupported, got %v", err)
			}
		})
	}
}
