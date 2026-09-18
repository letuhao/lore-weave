package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/loreweave/book-service/internal/config"
)

// T6 (plan 2026-09-18) — the best-effort call that asks composition for a book's Work with the
// CALLER'S OWN bearer (OQ-1: nothing is minted, nobody else's token is ever sent).

func provisionServer(t *testing.T, h http.HandlerFunc) *Server {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return &Server{cfg: &config.Config{CompositionServiceURL: srv.URL}}
}

func TestProvisionCompositionWork_ForwardsTheCallersBearerUnchanged(t *testing.T) {
	var gotAuth, gotPath, gotMethod string
	s := provisionServer(t, func(w http.ResponseWriter, r *http.Request) {
		gotAuth, gotPath, gotMethod = r.Header.Get("Authorization"), r.URL.Path, r.Method
		w.WriteHeader(http.StatusCreated)
	})
	status, err := s.provisionCompositionWork(context.Background(), "b-1", "Bearer caller-token")
	if err != nil || status != http.StatusCreated {
		t.Fatalf("status=%d err=%v, want 201 nil", status, err)
	}
	if gotMethod != http.MethodPost || gotPath != "/v1/composition/books/b-1/work" {
		t.Fatalf("called %s %s, want POST /v1/composition/books/b-1/work", gotMethod, gotPath)
	}
	if gotAuth != "Bearer caller-token" {
		t.Fatalf("Authorization %q — the caller's own bearer must arrive unchanged", gotAuth)
	}
}

func TestProvisionCompositionWork_AnExistingWorkIsSuccess(t *testing.T) {
	s := provisionServer(t, func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	if _, err := s.provisionCompositionWork(context.Background(), "b-1", "Bearer x"); err != nil {
		t.Fatalf("200 (already a Work) must be success: %v", err)
	}
}

func TestProvisionCompositionWork_ADownstreamFailureIsReturnedNotPanicked(t *testing.T) {
	s := provisionServer(t, func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusBadGateway) })
	status, err := s.provisionCompositionWork(context.Background(), "b-1", "Bearer x")
	if err == nil || status != http.StatusBadGateway {
		t.Fatalf("status=%d err=%v, want 502 + error", status, err)
	}
}

func TestProvisionCompositionWork_NoBearerMeansNoCall(t *testing.T) {
	var calls int32
	s := provisionServer(t, func(w http.ResponseWriter, _ *http.Request) { atomic.AddInt32(&calls, 1) })
	if _, err := s.provisionCompositionWork(context.Background(), "b-1", ""); err == nil {
		t.Fatal("an empty bearer must be refused")
	}
	if atomic.LoadInt32(&calls) != 0 {
		t.Fatal("a call went out with no bearer — the only identity allowed here is the caller's")
	}
}

func TestProvisionCompositionWork_AHungComposition_IsBounded(t *testing.T) {
	release := make(chan struct{})
	s := provisionServer(t, func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-release:
		case <-r.Context().Done():
		}
	})
	defer close(release)
	if provisionClient.Timeout <= 0 || provisionClient == http.DefaultClient {
		t.Fatal("the provision client must carry its own timeout; http.DefaultClient has none")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	start := time.Now()
	if _, err := s.provisionCompositionWork(ctx, "b-1", "Bearer x"); err == nil {
		t.Fatal("a hung composition must surface as an error")
	}
	if time.Since(start) > 2*time.Second {
		t.Fatalf("waited %s on a hung composition", time.Since(start))
	}
}
