package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

// #286 / plan 2026-09-19 T12 — /v1/llm/stream bypasses the jobs worker's Guard, so it takes the
// model lease itself. A streamed draft on one GPU collides with a job for another model exactly
// like two jobs do.

const leaseEP = "http://host.docker.internal:1234"

func leaseServer(t *testing.T, wait time.Duration) (*Server, *ratelimit.ModelLease) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	l := ratelimit.NewModelLease(rdb, ratelimit.ModelLeaseConfig{WaitTimeout: wait, PollInterval: 10 * time.Millisecond})
	return &Server{modelLease: l}, l
}

func streamOnce(s *Server, model string, optedIn bool) (string, *fakeStreamAdapter) {
	adapter := &fakeStreamAdapter{chunks: []provider.StreamChunk{{Kind: provider.StreamChunkToken, Delta: "PROSE"}}}
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/llm/stream", nil)
	s.streamChat(req, rr, rr, adapter, leaseEP, "", model, streamRequest{}, &streamGuard{op: "chat"}, optedIn)
	return rr.Body.String(), adapter
}

func TestStreamChat_OptedIn_WaitsForAnotherModel_ThenReportsBusy(t *testing.T) {
	s, l := leaseServer(t, 80*time.Millisecond)
	release, err := l.Acquire(context.Background(), leaseEP, "gemma-26b") // a job holds the GPU
	if err != nil {
		t.Fatal(err)
	}
	defer release()

	body, _ := streamOnce(s, "gemma-12b", true)
	if !strings.Contains(body, "LLM_MODEL_BUSY") {
		t.Fatalf("a stream for another model must wait and then say the model is busy; body=%q", body)
	}
	if strings.Contains(body, "PROSE") {
		t.Fatal("the provider was called while another model held the endpoint — the collision #286 is about")
	}
}

func TestStreamChat_OptedIn_SameModelRunsAlongside(t *testing.T) {
	s, l := leaseServer(t, 80*time.Millisecond)
	release, _ := l.Acquire(context.Background(), leaseEP, "gemma-12b")
	defer release()
	if body, _ := streamOnce(s, "gemma-12b", true); !strings.Contains(body, "PROSE") {
		t.Fatalf("the same model must not wait; body=%q", body)
	}
}

func TestStreamChat_NotOptedIn_IsUntouched(t *testing.T) {
	s, l := leaseServer(t, 80*time.Millisecond)
	release, _ := l.Acquire(context.Background(), leaseEP, "gemma-26b")
	defer release()
	if body, _ := streamOnce(s, "gemma-12b", false); !strings.Contains(body, "PROSE") {
		t.Fatalf("without the opt-in the stream path must behave exactly as before; body=%q", body)
	}
}
