package provider

// adapters_video_test.go — Phase 5d tests for GenerateVideo.
//
// Coverage scope:
//   - Path dispatch (text-to-video vs image-to-video based on InitImage)
//   - Happy paths (txt2vid, img2vid)
//   - Adapter-level invariants (empty prompt, n<0, n>1, bad response_format,
//     oversize init_image)
//   - Content-policy detection (via shared helper from openai_content_policy.go)
//   - Response body cap
//   - Typed upstream errors
//   - Stub-locks for the 3 non-OpenAI adapters

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

// ── OpenAI GenerateVideo — path dispatch ─────────────────────────────

func TestOpenAIAdapter_GenerateVideo_HappyPath_TextToVideo(t *testing.T) {
	var (
		gotPath string
		gotBody map[string]any
	)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"created": 1700000000,
			"data": [{"url": "https://cdn.example/video.mp4"}]
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	out, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"wan-14b",
		GenerateVideoInput{
			Prompt:   "a cinematic landscape pan at dawn",
			Size:     "1920x1080",
			Duration: 5,
			N:        1,
		},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Data[0].URL != "https://cdn.example/video.mp4" {
		t.Errorf("URL=%q", out.Data[0].URL)
	}
	// /review-impl(DESIGN) HIGH#1 — path dispatch verification
	if gotPath != "/v1/videos/generations/text-to-video" {
		t.Errorf("path=%s, want /v1/videos/generations/text-to-video (NOT singular)", gotPath)
	}
	if gotBody["n"] != float64(1) {
		t.Errorf("body.n=%v, want 1", gotBody["n"])
	}
	if _, ok := gotBody["init_image"]; ok {
		t.Errorf("body.init_image should be absent for txt2vid; got %v", gotBody["init_image"])
	}
	if _, ok := gotBody["mode"]; ok {
		t.Errorf("body.mode should be absent (sync upstream default); got %v", gotBody["mode"])
	}
}

func TestOpenAIAdapter_GenerateVideo_HappyPath_Img2Vid_PathDispatch(t *testing.T) {
	var (
		gotPath string
		gotBody map[string]any
	)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"created": 1700000001,
			"data": [{"url": "https://cdn.example/i2v.mp4"}]
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"ltx-video",
		GenerateVideoInput{
			Prompt:    "animate this scene with a slow camera pan",
			InitImage: "iVBORw0KGgo...",
			N:         1,
		},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// /review-impl(DESIGN) HIGH#1 — init_image presence flips path to image-to-video
	if gotPath != "/v1/videos/generations/image-to-video" {
		t.Errorf("path=%s, want /v1/videos/generations/image-to-video", gotPath)
	}
	// Field name is `init_image`, NOT `image` (HIGH#1 fix)
	if gotBody["init_image"] != "iVBORw0KGgo..." {
		t.Errorf("body.init_image=%v, want iVBORw0KGgo...", gotBody["init_image"])
	}
	if _, ok := gotBody["image"]; ok {
		t.Errorf("body.image should NOT exist (use init_image per HIGH#1); got %v", gotBody["image"])
	}
}

// TestOpenAIAdapter_GenerateVideo_WhitespaceInitImage_RoutesAsTxt2Vid pins
// /review-impl(BUILD) LOW#2 — whitespace-only init_image (" " or "\n")
// must NOT route to image-to-video. The adapter trims before dispatch
// so confused callers get text-to-video (their actual intent) rather
// than a confusing upstream parse error.
func TestOpenAIAdapter_GenerateVideo_WhitespaceInitImage_RoutesAsTxt2Vid(t *testing.T) {
	var gotPath string
	var gotBody map[string]any
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"created":1700000000,"data":[{"url":"https://cdn.example/v.mp4"}]}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	for _, ws := range []string{" ", "\t", "\n", "  \t\n  "} {
		t.Run(fmt.Sprintf("ws=%q", ws), func(t *testing.T) {
			_, _, err := a.GenerateVideo(
				context.Background(),
				openaiSrv.URL,
				"sk-test",
				"wan-14b",
				GenerateVideoInput{
					Prompt:    "a cat",
					InitImage: ws,
				},
			)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if gotPath != "/v1/videos/generations/text-to-video" {
				t.Errorf("whitespace init_image routed to %s; want text-to-video", gotPath)
			}
			if _, hasInit := gotBody["init_image"]; hasInit {
				t.Errorf("body.init_image should be absent for whitespace-only input; got %v", gotBody["init_image"])
			}
		})
	}
}

// ── Adapter-level invariants ─────────────────────────────────────────

func TestOpenAIAdapter_GenerateVideo_RejectsEmptyPrompt(t *testing.T) {
	upstreamCalled := false
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"wan-14b",
		GenerateVideoInput{Prompt: ""},
	)
	if !errors.Is(err, ErrVideoInvalidParams) {
		t.Fatalf("expected ErrVideoInvalidParams, got %v", err)
	}
	if upstreamCalled {
		t.Error("upstream MUST NOT be called when adapter pre-check fires")
	}
}

func TestOpenAIAdapter_GenerateVideo_RejectsNegativeN(t *testing.T) {
	a := &openaiAdapter{client: &http.Client{}}
	_, _, err := a.GenerateVideo(
		context.Background(),
		"http://example.invalid",
		"sk-test",
		"wan-14b",
		GenerateVideoInput{Prompt: "a cat", N: -1},
	)
	if !errors.Is(err, ErrVideoInvalidParams) {
		t.Fatalf("expected ErrVideoInvalidParams for N<0, got %v", err)
	}
	if !strings.Contains(err.Error(), "must be >= 0") {
		t.Errorf("expected 'must be >= 0' phrasing, got %v", err)
	}
}

func TestOpenAIAdapter_GenerateVideo_RejectsNGreaterThan1(t *testing.T) {
	a := &openaiAdapter{client: &http.Client{}}
	_, _, err := a.GenerateVideo(
		context.Background(),
		"http://example.invalid",
		"sk-test",
		"wan-14b",
		GenerateVideoInput{Prompt: "a cat", N: 2},
	)
	if !errors.Is(err, ErrVideoInvalidParams) {
		t.Fatalf("expected ErrVideoInvalidParams for N>1, got %v", err)
	}
	if !strings.Contains(err.Error(), "only n=1 supported") {
		t.Errorf("expected 'only n=1 supported' phrasing, got %v", err)
	}
}

func TestOpenAIAdapter_GenerateVideo_RejectsBadResponseFormat(t *testing.T) {
	a := &openaiAdapter{client: &http.Client{}}
	for _, rf := range []string{"b64_json", "mp4"} {
		_, _, err := a.GenerateVideo(
			context.Background(),
			"http://example.invalid",
			"sk-test",
			"wan-14b",
			GenerateVideoInput{Prompt: "a cat", ResponseFormat: rf},
		)
		if !errors.Is(err, ErrVideoInvalidParams) {
			t.Errorf("response_format=%q → expected ErrVideoInvalidParams, got %v", rf, err)
		}
	}
}

func TestOpenAIAdapter_GenerateVideo_RejectsOversizeInitImage(t *testing.T) {
	upstreamCalled := false
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
	}))
	defer openaiSrv.Close()

	oversize := strings.Repeat("A", MaxImg2VidInputBytes+1)
	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"ltx-video",
		GenerateVideoInput{
			Prompt:    "animate",
			InitImage: oversize,
		},
	)
	if !errors.Is(err, ErrVideoInvalidParams) {
		t.Fatalf("expected ErrVideoInvalidParams for oversize init_image, got %v", err)
	}
	if !strings.Contains(err.Error(), "exceeds") {
		t.Errorf("expected 'exceeds' phrasing, got %v", err)
	}
	if upstreamCalled {
		t.Error("upstream MUST NOT be called when adapter cap fires")
	}
}

// ── Content-policy detection (shared helper test) ────────────────────

func TestOpenAIAdapter_GenerateVideo_ContentPolicy_JSONErrorCode(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(400)
		_, _ = w.Write([]byte(`{
			"error": {
				"code": "content_policy_violation",
				"message": "rejected",
				"type": "image_generation_user_error"
			}
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"sora",
		GenerateVideoInput{Prompt: "anything"},
	)
	if !errors.Is(err, ErrVideoContentPolicy) {
		t.Fatalf("expected ErrVideoContentPolicy, got %v", err)
	}
}

// ── Response body cap ────────────────────────────────────────────────

func TestOpenAIAdapter_GenerateVideo_OversizeResponseRejected(t *testing.T) {
	huge := bytes.Repeat([]byte("A"), MaxImageResponseBytes+1024)
	body := fmt.Sprintf(`{"created":1700000000,"data":[{"url":"%s"}]}`, huge)

	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"wan-14b",
		GenerateVideoInput{Prompt: "anything"},
	)
	if !errors.Is(err, ErrVideoGenerationFailed) {
		t.Fatalf("expected ErrVideoGenerationFailed for oversize, got %v", err)
	}
}

// ── Typed upstream errors ────────────────────────────────────────────

func TestOpenAIAdapter_GenerateVideo_RateLimit429(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "5")
		w.WriteHeader(429)
		_, _ = w.Write([]byte(`{"error":{"code":"rate_limit_exceeded","message":"slow down"}}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"sora",
		GenerateVideoInput{Prompt: "anything"},
	)
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %v", err)
	}
	if rl.RetryAfterS == nil || *rl.RetryAfterS != 5.0 {
		t.Errorf("RetryAfterS=%v, want 5.0", rl.RetryAfterS)
	}
}

func TestOpenAIAdapter_GenerateVideo_AuthFailed401(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(401)
		_, _ = w.Write([]byte(`{"error":{"code":"invalid_api_key"}}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.GenerateVideo(
		context.Background(),
		openaiSrv.URL,
		"sk-test",
		"sora",
		GenerateVideoInput{Prompt: "anything"},
	)
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Fatalf("expected *ErrUpstreamPermanent for 401, got %v", err)
	}
	if perm.StatusCode != 401 {
		t.Errorf("StatusCode=%d, want 401", perm.StatusCode)
	}
}

// ── Stub adapters MUST return ErrOperationNotSupported ───────────────

func TestNonOpenAIAdapters_GenerateVideo_Unsupported(t *testing.T) {
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
			_, _, err := tc.adapter.GenerateVideo(
				context.Background(),
				"https://upstream.example",
				"sk-test",
				"some-model",
				GenerateVideoInput{Prompt: "anything"},
			)
			if !errors.Is(err, ErrOperationNotSupported) {
				t.Fatalf("expected ErrOperationNotSupported, got %v", err)
			}
		})
	}
}
