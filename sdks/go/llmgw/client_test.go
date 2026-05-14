package llmgw

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

const testModelRef = "0192f5ad-3c4d-7890-a000-000000000001"

// imageGatewayMux builds an httptest.Mux that simulates the unified
// gateway's submit + poll behavior. submitBody captures the wire shape
// for wire-level assertions.
type imageGatewayMux struct {
	mu             sync.Mutex
	submitBody     map[string]any
	pollsBeforeOK  int32
	pollsSeen      atomic.Int32
	terminalStatus JobStatus
	terminalError  *jobError
	terminalResult map[string]any
}

func newImageGateway() *imageGatewayMux {
	return &imageGatewayMux{
		terminalStatus: JobCompleted,
		terminalResult: map[string]any{
			"created": 1.0,
			"data": []map[string]any{
				{"url": "https://upstream/img.png"},
			},
		},
	}
}

func (g *imageGatewayMux) handler(t *testing.T) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/internal/llm/jobs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("submit must be POST, got %s", r.Method)
		}
		raw, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("read body: %v", err)
		}
		g.mu.Lock()
		g.submitBody = nil
		_ = json.Unmarshal(raw, &g.submitBody)
		g.mu.Unlock()
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(submitJobResponse{
			JobID:       "job-test",
			Status:      "pending",
			SubmittedAt: "2026-05-14T00:00:00Z",
		})
	})
	mux.HandleFunc("/internal/llm/jobs/job-test", func(w http.ResponseWriter, r *http.Request) {
		n := g.pollsSeen.Add(1)
		status := JobPending
		var result map[string]any
		var errBody *jobError
		if n > g.pollsBeforeOK {
			status = g.terminalStatus
			result = g.terminalResult
			errBody = g.terminalError
		}
		_ = json.NewEncoder(w).Encode(job{
			JobID:     "job-test",
			Operation: "image_gen",
			Status:    status,
			Result:    result,
			Error:     errBody,
		})
	})
	return mux
}

func newClientFor(t *testing.T, server *httptest.Server) *Client {
	t.Helper()
	c, err := NewClient(Options{
		BaseURL:       server.URL,
		AuthMode:      AuthInternal,
		InternalToken: "test-token",
		UserID:        "user-1",
	})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	return c
}

func TestGenerateImage_HappyPath(t *testing.T) {
	g := newImageGateway()
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	size := "1024x1024"
	result, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "a sunset",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		Size:            &size,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("GenerateImage: %v", err)
	}
	if len(result.Data) != 1 || result.Data[0].URL != "https://upstream/img.png" {
		t.Errorf("unexpected result: %+v", result)
	}

	// /review-impl(BUILD) MED#4 — assert top-level wire fields. Without
	// this, a future refactor could spell `image-gen` (hyphen) or omit
	// `operation` entirely and the test would still pass because the
	// mock blindly echoes back JobCompleted. Gateway would 400 in prod.
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.submitBody["operation"] != "image_gen" {
		t.Errorf("wire body operation = %v, want %q", g.submitBody["operation"], "image_gen")
	}
	if g.submitBody["model_source"] != "user_model" {
		t.Errorf("wire body model_source = %v, want %q", g.submitBody["model_source"], "user_model")
	}
	if g.submitBody["model_ref"] != testModelRef {
		t.Errorf("wire body model_ref = %v, want %q", g.submitBody["model_ref"], testModelRef)
	}
}

// HIGH#6 — non-default size MUST reach the wire (not gateway default).
//
// Gateway default for size is "1024x1024" per openapi.yaml. This test
// uses "1792x1024" which IS NOT the default; if a future refactor
// hardcodes "1024x1024" or silently drops size from the wire payload,
// this test fails because the wire body's input.size won't match.
func TestGenerateImage_NonDefaultSize_ReachesWire(t *testing.T) {
	g := newImageGateway()
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	size := "1792x1024"
	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "wide sunset",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		Size:            &size,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("GenerateImage: %v", err)
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	input, ok := g.submitBody["input"].(map[string]any)
	if !ok {
		t.Fatalf("submit body has no input map: %+v", g.submitBody)
	}
	if input["size"] != "1792x1024" {
		t.Errorf("wire body input.size = %v, want 1792x1024", input["size"])
	}
}

// HIGH#6 companion — when Size is nil, the wire payload must NOT
// contain the size key (so gateway/upstream picks its default).
func TestGenerateImage_OmittedSize_NotInWire(t *testing.T) {
	g := newImageGateway()
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "sunset",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("GenerateImage: %v", err)
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	input, ok := g.submitBody["input"].(map[string]any)
	if !ok {
		t.Fatalf("submit body has no input map: %+v", g.submitBody)
	}
	if _, present := input["size"]; present {
		t.Errorf("wire body input contains size key when SDK caller omitted it: %+v", input)
	}
}

// Feedback memory `feedback_sdk_default_arg_dropped_from_wire` — explicit
// optional values must reach the wire even when they could be confused
// for defaults.
func TestGenerateImage_ExplicitN_ReachesWire(t *testing.T) {
	g := newImageGateway()
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	n := 1 // explicit; gateway might also default to 1 for some backends
	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		N:               &n,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("GenerateImage: %v", err)
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	input := g.submitBody["input"].(map[string]any)
	got, present := input["n"]
	if !present {
		t.Errorf("explicit N not in wire body: %+v", input)
	}
	// JSON unmarshals integers as float64
	if got != float64(1) {
		t.Errorf("wire body input.n = %v, want 1", got)
	}
}

func TestGenerateImage_EmptyPrompt_ReturnsInvalidRequest(t *testing.T) {
	c, _ := NewClient(Options{
		BaseURL:       "http://x",
		AuthMode:      AuthInternal,
		InternalToken: "t",
		UserID:        "u",
	})
	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:      "   ",
		ModelSource: ModelSourceUser,
		ModelRef:    testModelRef,
	})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("expected ErrInvalidRequest, got %v", err)
	}
}

func TestGenerateImage_NonUUIDModelRef_ReturnsInvalidRequest(t *testing.T) {
	c, _ := NewClient(Options{
		BaseURL:       "http://x",
		AuthMode:      AuthInternal,
		InternalToken: "t",
		UserID:        "u",
	})
	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:      "p",
		ModelSource: ModelSourceUser,
		ModelRef:    "not-a-uuid",
	})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("expected ErrInvalidRequest, got %v", err)
	}
}

func TestGenerateImage_InvalidModelSource_ReturnsInvalidRequest(t *testing.T) {
	c, _ := NewClient(Options{
		BaseURL:       "http://x",
		AuthMode:      AuthInternal,
		InternalToken: "t",
		UserID:        "u",
	})
	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:      "p",
		ModelSource: ModelSource("bogus"),
		ModelRef:    testModelRef,
	})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("expected ErrInvalidRequest, got %v", err)
	}
}

func TestGenerateImage_ContextCancellation(t *testing.T) {
	g := newImageGateway()
	g.pollsBeforeOK = 1000 // never reach terminal
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()
	_, err := c.GenerateImage(ctx, GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    10 * time.Millisecond,
		MaxPollInterval: 50 * time.Millisecond,
	})
	if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled, got %v", err)
	}
}

func TestGenerateImage_JobFailedWithContentPolicy_ReturnsTypedError(t *testing.T) {
	g := newImageGateway()
	g.terminalStatus = JobFailed
	g.terminalResult = nil
	g.terminalError = &jobError{
		Code:    "LLM_IMAGE_CONTENT_POLICY_VIOLATION",
		Message: "rephrase your prompt",
	}
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if !errors.Is(err, ErrImageContentPolicy) {
		t.Errorf("expected ErrImageContentPolicy, got %v", err)
	}
	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatal("errors.As failed")
	}
	if !strings.Contains(llmErr.Message, "rephrase") {
		t.Errorf("Message = %q, want substring 'rephrase'", llmErr.Message)
	}
}

func TestGenerateImage_JobFailedWithQuotaExceeded_ReturnsTypedError(t *testing.T) {
	g := newImageGateway()
	g.terminalStatus = JobFailed
	g.terminalResult = nil
	g.terminalError = &jobError{
		Code:    "LLM_QUOTA_EXCEEDED",
		Message: "no credits left",
	}
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if !errors.Is(err, ErrQuotaExceeded) {
		t.Errorf("expected ErrQuotaExceeded, got %v", err)
	}
}

func TestGenerateImage_JobCancelled_ReturnsJobTerminalError(t *testing.T) {
	g := newImageGateway()
	g.terminalStatus = JobCancelled
	g.terminalResult = nil
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if !errors.Is(err, ErrJobTerminal) {
		t.Errorf("expected ErrJobTerminal, got %v", err)
	}
}

func TestGenerateImage_RateLimited_PropagatesRetryAfter(t *testing.T) {
	g := newImageGateway()
	g.terminalStatus = JobFailed
	g.terminalResult = nil
	g.terminalError = &jobError{
		Code:        "LLM_RATE_LIMITED",
		Message:     "slow down",
		RetryAfterS: 30,
	}
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if !errors.Is(err, ErrRateLimited) {
		t.Errorf("expected ErrRateLimited, got %v", err)
	}
	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatal("errors.As failed")
	}
	if llmErr.RetryAfterS != 30 {
		t.Errorf("RetryAfterS = %v, want 30", llmErr.RetryAfterS)
	}
}

func TestGenerateImage_EmptyResultData_Returns502(t *testing.T) {
	g := newImageGateway()
	g.terminalStatus = JobCompleted
	g.terminalResult = map[string]any{
		"created": 1.0,
		"data":    []map[string]any{},
	}
	server := httptest.NewServer(g.handler(t))
	defer server.Close()
	c := newClientFor(t, server)

	_, err := c.GenerateImage(context.Background(), GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     ModelSourceUser,
		ModelRef:        testModelRef,
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if !errors.Is(err, ErrUpstream) {
		t.Errorf("expected ErrUpstream (empty data), got %v", err)
	}
}
