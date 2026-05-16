package llmgw

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// testClient builds a Client pointed at the supplied test server.
func testClient(t *testing.T, server *httptest.Server, userID string) *Client {
	t.Helper()
	c, err := NewClient(Options{
		BaseURL:       server.URL,
		AuthMode:      AuthInternal,
		InternalToken: "test-token",
		UserID:        userID,
	})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	return c
}

func TestNewClient_BaseURLRequired(t *testing.T) {
	_, err := NewClient(Options{AuthMode: AuthInternal, InternalToken: "t"})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("missing BaseURL: got %v, want ErrInvalidRequest", err)
	}
}

func TestNewClient_AuthInternalRequiresInternalToken(t *testing.T) {
	_, err := NewClient(Options{BaseURL: "http://x", AuthMode: AuthInternal})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("got %v, want ErrInvalidRequest", err)
	}
}

func TestNewClient_AuthJWTRequiresBearerToken(t *testing.T) {
	_, err := NewClient(Options{BaseURL: "http://x", AuthMode: AuthJWT})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("got %v, want ErrInvalidRequest", err)
	}
}

func TestNewClient_UnknownAuthMode(t *testing.T) {
	_, err := NewClient(Options{BaseURL: "http://x", AuthMode: AuthMode("bogus"), InternalToken: "t"})
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("got %v, want ErrInvalidRequest", err)
	}
}

func TestSubmitJob_OK(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/llm/jobs" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("user_id") != "user-1" {
			t.Errorf("missing user_id query: %s", r.URL.RawQuery)
		}
		if r.Header.Get("X-Internal-Token") != "test-token" {
			t.Errorf("missing X-Internal-Token header")
		}
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(submitJobResponse{
			JobID:       "job-123",
			Status:      "pending",
			SubmittedAt: "2026-05-14T00:00:00Z",
		})
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	resp, err := c.submitJob(context.Background(), map[string]any{"operation": "image_gen"}, "")
	if err != nil {
		t.Fatalf("submitJob: %v", err)
	}
	if resp.JobID != "job-123" {
		t.Errorf("JobID = %q, want job-123", resp.JobID)
	}
}

func TestSubmitJob_400_InvalidRequest_PopulatesInner(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":    "LLM_INVALID_REQUEST",
			"message": "model_ref invalid",
		})
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	_, err := c.submitJob(context.Background(), map[string]any{}, "")
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("errors.Is(err, ErrInvalidRequest) = false; got %v", err)
	}
	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatal("errors.As failed")
	}
	if llmErr.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", llmErr.StatusCode)
	}
}

func TestSubmitJob_429_PopulatesRetryAfter(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":          "LLM_RATE_LIMITED",
			"message":       "slow down",
			"retry_after_s": 7.5,
		})
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	_, err := c.submitJob(context.Background(), map[string]any{}, "")
	if !errors.Is(err, ErrRateLimited) {
		t.Errorf("not RateLimited: %v", err)
	}
	var llmErr *Error
	if !errors.As(err, &llmErr) {
		t.Fatal("errors.As failed")
	}
	if llmErr.RetryAfterS != 7.5 {
		t.Errorf("RetryAfterS = %v, want 7.5", llmErr.RetryAfterS)
	}
}

func TestSubmitJob_TransportError_ReturnsHTTPError(t *testing.T) {
	c := &Client{
		baseURL:       "http://127.0.0.1:1", // RFC2606 — guaranteed unreachable
		authMode:      AuthInternal,
		internalToken: "t",
		userID:        "u",
		http:          &http.Client{Transport: http.DefaultTransport},
	}
	_, err := c.submitJob(context.Background(), map[string]any{}, "")
	if !errors.Is(err, ErrHTTPTransport) {
		t.Errorf("expected ErrHTTPTransport, got %v", err)
	}
}

func TestGetJob_NotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	_, err := c.getJob(context.Background(), "missing-job", "")
	if !errors.Is(err, ErrJobNotFound) {
		t.Errorf("expected ErrJobNotFound, got %v", err)
	}
}

func TestGetJob_OK(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/job-abc") {
			t.Errorf("path missing job_id: %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(job{
			JobID:     "job-abc",
			Operation: "image_gen",
			Status:    JobCompleted,
			Result:    map[string]any{"created": 1, "data": []map[string]any{{"url": "http://x/img.png"}}},
		})
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	j, err := c.getJob(context.Background(), "job-abc", "")
	if err != nil {
		t.Fatalf("getJob: %v", err)
	}
	if j.Status != JobCompleted {
		t.Errorf("Status = %q, want completed", j.Status)
	}
}

func TestCancelJob_204_NoError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()
	c := testClient(t, server, "user-1")
	if err := c.cancelJob(context.Background(), "job-1", ""); err != nil {
		t.Errorf("cancelJob 204: %v", err)
	}
}

func TestCancelJob_409_NoError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusConflict)
	}))
	defer server.Close()
	c := testClient(t, server, "user-1")
	if err := c.cancelJob(context.Background(), "job-1", ""); err != nil {
		t.Errorf("cancelJob 409: %v", err)
	}
}

func TestCancelJob_404_ErrJobNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()
	c := testClient(t, server, "user-1")
	err := c.cancelJob(context.Background(), "job-1", "")
	if !errors.Is(err, ErrJobNotFound) {
		t.Errorf("expected ErrJobNotFound, got %v", err)
	}
}

func TestWaitTerminal_CompletesQuickly(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := calls.Add(1)
		status := JobPending
		if n >= 3 {
			status = JobCompleted
		}
		_ = json.NewEncoder(w).Encode(job{
			JobID:  "job-1",
			Status: status,
		})
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	start := time.Now()
	j, err := c.waitTerminal(context.Background(), "job-1", "", pollOptions{
		pollInterval:    10 * time.Millisecond,
		maxPollInterval: 100 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("waitTerminal: %v", err)
	}
	if j.Status != JobCompleted {
		t.Errorf("Status = %q, want completed", j.Status)
	}
	if elapsed := time.Since(start); elapsed > 5*time.Second {
		t.Errorf("waitTerminal took too long: %v", elapsed)
	}
	if calls.Load() != 3 {
		t.Errorf("expected 3 polls, got %d", calls.Load())
	}
}

func TestWaitTerminal_TerminalStatuses(t *testing.T) {
	for _, status := range []JobStatus{JobCompleted, JobFailed, JobCancelled} {
		t.Run(string(status), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_ = json.NewEncoder(w).Encode(job{
					JobID:  "job-1",
					Status: status,
				})
			}))
			defer server.Close()
			c := testClient(t, server, "user-1")
			j, err := c.waitTerminal(context.Background(), "job-1", "", pollOptions{
				pollInterval:    1 * time.Millisecond,
				maxPollInterval: 10 * time.Millisecond,
			})
			if err != nil {
				t.Fatalf("waitTerminal: %v", err)
			}
			if j.Status != status {
				t.Errorf("Status = %q, want %q", j.Status, status)
			}
		})
	}
}

func TestWaitTerminal_TransientHTTPFailure_Budget0_RaisesImmediately(t *testing.T) {
	// Server doesn't respond — transport error.
	c := &Client{
		baseURL:       "http://127.0.0.1:1",
		authMode:      AuthInternal,
		internalToken: "t",
		userID:        "u",
		http:          &http.Client{Transport: http.DefaultTransport},
	}
	_, err := c.waitTerminal(context.Background(), "job-1", "", pollOptions{
		pollInterval:         1 * time.Millisecond,
		maxPollInterval:      10 * time.Millisecond,
		transientRetryBudget: 0,
	})
	if !errors.Is(err, ErrHTTPTransport) {
		t.Errorf("expected ErrHTTPTransport, got %v", err)
	}
}

func TestWaitTerminal_ContextCancellation(t *testing.T) {
	// Server always returns pending.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(job{
			JobID:  "job-1",
			Status: JobPending,
		})
	}))
	defer server.Close()

	c := testClient(t, server, "user-1")
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()
	_, err := c.waitTerminal(ctx, "job-1", "", pollOptions{
		pollInterval:    10 * time.Millisecond,
		maxPollInterval: 100 * time.Millisecond,
	})
	if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled, got %v", err)
	}
}

func TestJobsEndpoint_InternalAuth_RequiresUserID(t *testing.T) {
	c := &Client{
		baseURL:       "http://x",
		authMode:      AuthInternal,
		internalToken: "t",
		// userID intentionally empty
	}
	_, _, _, err := c.jobsEndpoint("submit", "", "")
	if !errors.Is(err, ErrInvalidRequest) {
		t.Errorf("expected ErrInvalidRequest, got %v", err)
	}
}

func TestJobsEndpoint_InternalAuth_PerCallOverrideWins(t *testing.T) {
	c := &Client{
		baseURL:       "http://x",
		authMode:      AuthInternal,
		internalToken: "t",
		userID:        "ctor-user",
	}
	_, params, _, err := c.jobsEndpoint("submit", "", "per-call-user")
	if err != nil {
		t.Fatalf("jobsEndpoint: %v", err)
	}
	if params.Get("user_id") != "per-call-user" {
		t.Errorf("user_id = %q, want per-call-user", params.Get("user_id"))
	}
}

// /review-impl(BUILD) MED#6 — verify waitTerminal applies the 500ms
// default when caller passes zero PollInterval. A regression to zero
// would busy-loop on CPU.
func TestWaitTerminal_ZeroIntervalDefaultsToHalfSecond(t *testing.T) {
	var calls atomic.Int32
	var firstPollAt time.Time
	var secondPollAt time.Time
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := calls.Add(1)
		now := time.Now()
		if n == 1 {
			firstPollAt = now
		} else if n == 2 {
			secondPollAt = now
		}
		status := JobPending
		if n >= 2 {
			status = JobCompleted
		}
		_ = json.NewEncoder(w).Encode(job{
			JobID:  "job-1",
			Status: status,
		})
	}))
	defer server.Close()
	c := testClient(t, server, "user-1")
	// Caller passes ZERO pollInterval — SDK must default to 500ms.
	_, err := c.waitTerminal(context.Background(), "job-1", "", pollOptions{})
	if err != nil {
		t.Fatalf("waitTerminal: %v", err)
	}
	if firstPollAt.IsZero() || secondPollAt.IsZero() {
		t.Fatalf("did not capture two polls (calls=%d)", calls.Load())
	}
	gap := secondPollAt.Sub(firstPollAt)
	// Defaulted to 500ms; allow ±150ms wall-clock jitter on CI.
	if gap < 350*time.Millisecond || gap > 700*time.Millisecond {
		t.Errorf("default poll gap = %v, want ~500ms (±150ms); zero default did NOT apply", gap)
	}
}

func TestNextInterval_Backoff(t *testing.T) {
	got := nextInterval(100*time.Millisecond, 1*time.Second)
	want := 150 * time.Millisecond
	if got != want {
		t.Errorf("got %v, want %v", got, want)
	}
}

func TestNextInterval_CapAtMax(t *testing.T) {
	got := nextInterval(800*time.Millisecond, 1*time.Second)
	want := 1 * time.Second
	if got != want {
		t.Errorf("got %v, want %v", got, want)
	}
}

func TestErrorsAs_FindsErrorThroughWrap(t *testing.T) {
	orig := newErrorFromCode("LLM_AUTH_FAILED", "msg", 401)
	wrapped := fmt.Errorf("outer: %w", orig)
	var target *Error
	if !errors.As(wrapped, &target) {
		t.Fatal("errors.As failed to find *Error in chain")
	}
	if target.Code != "LLM_AUTH_FAILED" {
		t.Errorf("found wrong error: %v", target)
	}
}
