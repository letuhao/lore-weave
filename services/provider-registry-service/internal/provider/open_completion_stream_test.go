package provider

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

// /review-impl LOW#6 — pin the openCompletionStream → typed-error mapping
// at the wire boundary. Earlier streamWithRetry tests use a fakeAdapter
// that returns typed errors directly; this suite proves the streamer
// itself emits the right typed shape from real HTTP responses, so a
// future regression that drops to fmt.Errorf("provider %d", ...) would
// break these tests instead of silently disabling worker.streamWithRetry.

func TestOpenCompletionStream_429MapsToRateLimitedWithRetryAfter(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "5")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":"rate limit exceeded"}`))
	}))
	defer srv.Close()

	_, err := openCompletionStream(context.Background(), srv.Client(), srv.URL, nil, map[string]any{})
	if err == nil {
		t.Fatal("expected error")
	}
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %T: %v", err, err)
	}
	if rl.StatusCode != 429 {
		t.Errorf("status=%d, want 429", rl.StatusCode)
	}
	if rl.RetryAfterS == nil || *rl.RetryAfterS != 5.0 {
		t.Errorf("retry_after_s=%v, want 5.0", rl.RetryAfterS)
	}
}

func TestOpenCompletionStream_502MapsToTransient(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte("upstream blip"))
	}))
	defer srv.Close()

	_, err := openCompletionStream(context.Background(), srv.Client(), srv.URL, nil, map[string]any{})
	var trans *ErrUpstreamTransient
	if !errors.As(err, &trans) {
		t.Fatalf("expected *ErrUpstreamTransient, got %T: %v", err, err)
	}
	if trans.StatusCode != 502 {
		t.Errorf("status=%d, want 502", trans.StatusCode)
	}
}

func TestOpenCompletionStream_400MapsToPermanent(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("invalid model"))
	}))
	defer srv.Close()

	_, err := openCompletionStream(context.Background(), srv.Client(), srv.URL, nil, map[string]any{})
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Fatalf("expected *ErrUpstreamPermanent, got %T: %v", err, err)
	}
	// Permanent errors must NOT be classified as transient (worker would
	// otherwise retry forever on bad auth / wrong model / malformed input).
	if IsTransientUpstreamError(err) {
		t.Errorf("permanent error misclassified as transient")
	}
}

func TestOpenCompletionStream_429WithoutRetryAfterParsesNil(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	_, err := openCompletionStream(context.Background(), srv.Client(), srv.URL, nil, map[string]any{})
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %T", err)
	}
	if rl.RetryAfterS != nil {
		t.Errorf("expected nil RetryAfterS without header, got %v", *rl.RetryAfterS)
	}
}

func TestOpenCompletionStream_429MalformedRetryAfterParsesNil(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// HTTP-date form is intentionally not parsed (only delta-seconds).
		w.Header().Set("Retry-After", "Wed, 21 Oct 2026 07:28:00 GMT")
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	_, err := openCompletionStream(context.Background(), srv.Client(), srv.URL, nil, map[string]any{})
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %T", err)
	}
	if rl.RetryAfterS != nil {
		t.Errorf("HTTP-date Retry-After must parse to nil, got %v", *rl.RetryAfterS)
	}
}

func TestOpenCompletionStream_503And504AlsoTransient(t *testing.T) {
	for _, code := range []int{503, 504} {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(code)
		}))
		_, err := openCompletionStream(context.Background(), srv.Client(), srv.URL, nil, map[string]any{})
		srv.Close()
		var trans *ErrUpstreamTransient
		if !errors.As(err, &trans) || trans.StatusCode != code {
			t.Errorf("status %d: expected ErrUpstreamTransient with that code, got %T %+v", code, err, err)
		}
	}
}

func TestIsTransientUpstreamError_RejectsGenericError(t *testing.T) {
	// Default-deny: any non-typed error MUST NOT be treated as transient.
	// Otherwise a future regression to fmt.Errorf would silently stop
	// worker.streamWithRetry from working without a test failing.
	if IsTransientUpstreamError(errors.New("something went wrong")) {
		t.Error("generic error wrongly classified as transient")
	}
	if IsTransientUpstreamError(nil) {
		t.Error("nil error wrongly classified as transient")
	}
}
