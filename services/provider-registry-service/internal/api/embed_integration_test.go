package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
)

func postEmbedForTest(t *testing.T, srv *Server, userID, modelID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(map[string]any{
		"model_source": "user_model",
		"model_ref":    modelID.String(),
		"texts":        []string{"safe test input"},
	})
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/embed?user_id="+userID.String(),
		bytes.NewReader(body),
	)
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	srv.internalEmbed(rr, req)
	return rr
}

func TestInternalEmbedPreservesProvider429(t *testing.T) {
	srv, pool := integrationServer(t)
	srv.guardrail = nil // avoid recording usage to a live service in this test
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Retry-After", "4")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":{"message":"provider concurrency limit"}}`))
	}))
	defer upstream.Close()

	userID, modelID := seedUserModel(t, srv, pool, upstream.URL, "embed-test-model", "test-key")
	rr := postEmbedForTest(t, srv, userID, modelID)
	if rr.Code != http.StatusTooManyRequests {
		t.Fatalf("status = %d, want 429; body=%s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("Retry-After"); got != "4" {
		t.Fatalf("Retry-After = %q, want 4", got)
	}
	var body errorBody
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if body.Code != "EMBED_PROVIDER_RATE_LIMITED" {
		t.Fatalf("code = %q, want EMBED_PROVIDER_RATE_LIMITED", body.Code)
	}
	if body.Message == "" {
		t.Fatal("rate-limit response must keep the provider message")
	}
}

func TestInternalEmbedAppliesDefaultConcurrencyLimit(t *testing.T) {
	srv, pool := integrationServer(t)
	srv.guardrail = nil // avoid recording usage to a live service in this test
	srv.providerDefaultMax = 1
	srv.providerAcquireTimeout = 50 * time.Millisecond
	started := make(chan struct{}, 2)
	release := make(chan struct{})
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started <- struct{}{}
		<-release
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[{"embedding":[0.1,0.2]}],"model":"embed-test-model"}`))
	}))
	defer upstream.Close()

	userID, modelID := seedUserModel(t, srv, pool, upstream.URL, "embed-test-model", "test-key")
	firstDone := make(chan *httptest.ResponseRecorder, 1)
	go func() { firstDone <- postEmbedForTest(t, srv, userID, modelID) }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("first provider request did not start")
	}

	secondDone := make(chan *httptest.ResponseRecorder, 1)
	go func() { secondDone <- postEmbedForTest(t, srv, userID, modelID) }()
	var second *httptest.ResponseRecorder
	select {
	case second = <-secondDone:
	case <-time.After(time.Second):
		close(release)
		t.Fatal("second request did not respect the bounded acquire timeout")
	}
	if second.Code != http.StatusServiceUnavailable {
		t.Fatalf("second status = %d, want 503; body=%s", second.Code, second.Body.String())
	}
	if got := second.Header().Get("Retry-After"); got == "" {
		t.Fatal("busy response must include Retry-After")
	}
	var busy errorBody
	if err := json.Unmarshal(second.Body.Bytes(), &busy); err != nil {
		t.Fatalf("decode busy response: %v", err)
	}
	if busy.Code != "EMBED_PROVIDER_BUSY" {
		t.Fatalf("busy code = %q, want EMBED_PROVIDER_BUSY", busy.Code)
	}

	close(release)
	select {
	case first := <-firstDone:
		if first.Code != http.StatusOK {
			t.Fatalf("first status = %d, want 200; body=%s", first.Code, first.Body.String())
		}
	case <-time.After(time.Second):
		t.Fatal("first request did not complete after provider was released")
	}

	// The acquired slot is released on completion, so a later request can run.
	// release is already closed at this point, so the third request's upstream
	// handler passes through it without another close.
	thirdDone := make(chan *httptest.ResponseRecorder, 1)
	go func() { thirdDone <- postEmbedForTest(t, srv, userID, modelID) }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("third provider request did not start after slot release")
	}
	select {
	case third := <-thirdDone:
		if third.Code != http.StatusOK {
			t.Fatalf("third status = %d, want 200; body=%s", third.Code, third.Body.String())
		}
	case <-time.After(time.Second):
		t.Fatal("third request did not finish")
	}
}
