package api

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

// present reports whether a CancelFunc is still registered (without removing it).
func present(s *Server, id uuid.UUID) bool { _, ok := s.jobCancels.m.Load(id); return ok }

func TestJobCancelRegistry_CancelInvokesAndRemoves(t *testing.T) {
	var r jobCancelRegistry
	id := uuid.New()
	ctx, cancel := context.WithCancel(context.Background())
	r.register(id, cancel)

	if !r.cancel(id) {
		t.Fatal("cancel should return true for a registered job")
	}
	select {
	case <-ctx.Done():
	default:
		t.Fatal("cancel must invoke the CancelFunc (ctx not cancelled)")
	}
	if r.cancel(id) {
		t.Fatal("cancel after delete must be a no-op (false)")
	}
}

func TestJobCancelRegistry_RemoveDoesNotCancel(t *testing.T) {
	var r jobCancelRegistry
	id := uuid.New()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	r.register(id, cancel)
	r.remove(id)

	if r.cancel(id) {
		t.Fatal("cancel after remove must be false")
	}
	select {
	case <-ctx.Done():
		t.Fatal("remove must NOT cancel the context")
	default:
	}
}

func TestJobCancelRegistry_CancelUnknownIsFalse(t *testing.T) {
	var r jobCancelRegistry
	if r.cancel(uuid.New()) {
		t.Fatal("cancel of an unregistered id must be false")
	}
}

// The incident regression: DELETE must abort the in-flight worker. spawnJob
// registers a cancellable ctx; jobCancels.cancel(jobID) must propagate Done()
// to the worker (which mirrors the streamer/governor honoring ctx.Done()).
func TestSpawnJob_CancelAbortsInFlight(t *testing.T) {
	s := &Server{}
	jobID := uuid.New()
	started := make(chan struct{})
	aborted := make(chan struct{})

	s.spawnJob(context.Background(), jobID, func(ctx context.Context) {
		close(started)
		<-ctx.Done() // streamer/governor honor this → frees the slot
		close(aborted)
	})

	<-started
	if !present(s, jobID) {
		t.Fatal("spawnJob must register the job's CancelFunc")
	}
	if !s.jobCancels.cancel(jobID) {
		t.Fatal("cancel returned false for an in-flight job")
	}
	select {
	case <-aborted:
	case <-time.After(2 * time.Second):
		t.Fatal("worker not aborted within 2s of cancel")
	}
	if s.jobCancels.cancel(jobID) {
		t.Fatal("a second cancel must be a no-op")
	}
}

func TestSpawnJob_DeregistersOnCompletion(t *testing.T) {
	s := &Server{}
	jobID := uuid.New()
	done := make(chan struct{})

	s.spawnJob(context.Background(), jobID, func(ctx context.Context) {
		close(done) // completes immediately
	})
	<-done

	// The goroutine's deferred remove runs after fn returns — poll for it.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if !present(s, jobID) {
			return // deregistered — correct
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("completed job left a stale CancelFunc in the registry")
}

func TestSpawnJob_WallclockSelfCancels(t *testing.T) {
	s := &Server{jobWallclock: 50 * time.Millisecond}
	jobID := uuid.New()
	aborted := make(chan struct{})

	s.spawnJob(context.Background(), jobID, func(ctx context.Context) {
		<-ctx.Done() // no explicit DELETE — the wall-clock backstop must fire
		close(aborted)
	})

	select {
	case <-aborted:
	case <-time.After(2 * time.Second):
		t.Fatal("wall-clock backstop did not self-cancel the runaway job")
	}
}
