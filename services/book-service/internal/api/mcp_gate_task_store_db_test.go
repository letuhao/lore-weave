package api

// M1b — the PERSISTENT durable-gate store (PgTaskStore), proven against real Postgres.
// The point of persistence is MULTI-REPLICA: a propose handled by one replica and its
// accept by ANOTHER (or after a restart) must resolve the SAME task exactly once. These
// tests use TWO PgTaskStore instances over one pool to stand in for two replicas.
//
// Gated by BOOK_TEST_DATABASE_URL like the sibling _DB tests (skips without a DB).

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

const gateTestDescriptor = "test.gate"

// recordingResolver captures the args it was reconstructed with and returns a result.
func recordingResolver(hits *[]map[string]any) lwmcp.TaskResolver {
	var mu sync.Mutex
	return func(_ context.Context, ownerUserID string, payload, inputs map[string]any) (any, error) {
		mu.Lock()
		*hits = append(*hits, map[string]any{"owner": ownerUserID, "payload": payload, "inputs": inputs})
		mu.Unlock()
		return map[string]any{"done": true, "chapter": payload["chapter_id"]}, nil
	}
}

func TestPgTaskStore_MultiReplica_ProposeOnA_AcceptOnB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	var hits []map[string]any
	reg := lwmcp.TaskResolverRegistry{gateTestDescriptor: recordingResolver(&hits)}
	// Two independent store instances over the same DB = two replicas.
	replicaA := NewPgTaskStore(pool, reg)
	replicaB := NewPgTaskStore(pool, reg)

	owner := uuid.New().String()
	task, err := replicaA.Create(gateTestDescriptor, owner,
		map[string]any{"chapter_id": "ch-42"}, map[string]any{"title": "Delete?"}, 0)
	if err != nil {
		t.Fatalf("Create on A: %v", err)
	}
	if task.Status != lwmcp.TaskInputRequired {
		t.Fatalf("created status = %q, want input_required", task.Status)
	}

	// Replica B (which never saw the Create) reads the durable row.
	gotB, err := replicaB.Get(task.TaskID, time.Time{})
	if err != nil || gotB.Status != lwmcp.TaskInputRequired {
		t.Fatalf("B.Get: err=%v status=%q", err, gotB.Status)
	}
	if gotB.OwnerUserID != owner || gotB.Payload["chapter_id"] != "ch-42" {
		t.Fatalf("B did not see the durable owner/payload: owner=%q payload=%v", gotB.OwnerUserID, gotB.Payload)
	}

	// Accept on B → the resolver runs on B (reconstructed from the row) → completed.
	done, err := replicaB.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": true, "note": "x"})
	if err != nil {
		t.Fatalf("B.ProvideInput accept: %v", err)
	}
	if done.Status != lwmcp.TaskCompleted {
		t.Fatalf("accept status = %q, want completed", done.Status)
	}
	res, _ := done.Result.(map[string]any)
	if res["chapter"] != "ch-42" {
		t.Fatalf("result did not carry payload: %v", done.Result)
	}
	if len(hits) != 1 || hits[0]["owner"] != owner {
		t.Fatalf("resolver ran %d times (want 1) with wrong args: %v", len(hits), hits)
	}

	// A sees the terminal state, and a double-accept on EITHER replica is refused
	// (single-winner across replicas) — the resolver must not run twice.
	gotA, _ := replicaA.Get(task.TaskID, time.Time{})
	if gotA.Status != lwmcp.TaskCompleted {
		t.Fatalf("A.Get after accept = %q, want completed", gotA.Status)
	}
	if _, err := replicaA.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": true}); err != lwmcp.ErrTaskNotWaiting {
		t.Fatalf("double-accept on A err = %v, want ErrTaskNotWaiting", err)
	}
	if len(hits) != 1 {
		t.Fatalf("resolver ran %d times total, want exactly 1", len(hits))
	}
}

func TestPgTaskStore_DeclineCancelsWithoutResolver(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	var hits []map[string]any
	store := NewPgTaskStore(pool, lwmcp.TaskResolverRegistry{gateTestDescriptor: recordingResolver(&hits)})

	task, _ := store.Create(gateTestDescriptor, uuid.New().String(), map[string]any{"chapter_id": "c"}, nil, 0)
	res, err := store.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": false})
	if err != nil || res.Status != lwmcp.TaskCancelled {
		t.Fatalf("decline: err=%v status=%q", err, res.Status)
	}
	if len(hits) != 0 {
		t.Fatalf("resolver ran on decline (%d hits)", len(hits))
	}
	// A post-decline accept is refused.
	if _, err := store.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": true}); err != lwmcp.ErrTaskNotWaiting {
		t.Fatalf("accept after decline err = %v, want ErrTaskNotWaiting", err)
	}
}

func TestPgTaskStore_TTLExpiryLapsesToFailed(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	store := NewPgTaskStore(pool, lwmcp.TaskResolverRegistry{gateTestDescriptor: recordingResolver(new([]map[string]any))})

	task, _ := store.Create(gateTestDescriptor, uuid.New().String(), nil, nil, 1) // 1ms TTL
	// A Get with `now` past the TTL lapses the row to failed/task_expired and persists it.
	got, err := store.Get(task.TaskID, task.CreatedAt.Add(time.Hour))
	if err != nil {
		t.Fatalf("Get(future): %v", err)
	}
	if got.Status != lwmcp.TaskFailed || got.ErrorMsg != "task_expired" {
		t.Fatalf("status=%q err=%q, want failed/task_expired", got.Status, got.ErrorMsg)
	}
	// The lapse is durable → a later accept is refused.
	if _, err := store.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": true}); err != lwmcp.ErrTaskNotWaiting {
		t.Fatalf("accept after expiry err = %v, want ErrTaskNotWaiting", err)
	}
}

func TestPgTaskStore_CancelIdempotentThenReject(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	store := NewPgTaskStore(pool, lwmcp.TaskResolverRegistry{gateTestDescriptor: recordingResolver(new([]map[string]any))})

	task, _ := store.Create(gateTestDescriptor, uuid.New().String(), nil, nil, 0)
	c, err := store.Cancel(task.TaskID)
	if err != nil || c.Status != lwmcp.TaskCancelled {
		t.Fatalf("cancel: err=%v status=%q", err, c.Status)
	}
	c2, err := store.Cancel(task.TaskID) // idempotent on a terminal task
	if err != nil || c2.Status != lwmcp.TaskCancelled {
		t.Fatalf("second cancel: err=%v status=%q", err, c2.Status)
	}
	if _, err := store.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": true}); err != lwmcp.ErrTaskNotWaiting {
		t.Fatalf("accept after cancel err = %v, want ErrTaskNotWaiting", err)
	}
}

func TestPgTaskStore_ConcurrentAccept_SingleWinner(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	var hits []map[string]any
	store := NewPgTaskStore(pool, lwmcp.TaskResolverRegistry{gateTestDescriptor: recordingResolver(&hits)})

	task, _ := store.Create(gateTestDescriptor, uuid.New().String(), map[string]any{"chapter_id": "z"}, nil, 0)

	// Two concurrent accepts (two replicas racing) → the atomic input_required→working
	// claim makes exactly one win; the resolver runs once.
	var wg sync.WaitGroup
	results := make([]error, 2)
	completed := make([]bool, 2)
	for i := range 2 {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			res, err := store.ProvideInput(ctx, task.TaskID, map[string]any{"accepted": true})
			results[idx] = err
			if err == nil && res.Status == lwmcp.TaskCompleted {
				completed[idx] = true
			}
		}(i)
	}
	wg.Wait()

	wins, notWaiting := 0, 0
	for i := range 2 {
		if results[i] == nil && completed[i] {
			wins++
		} else if results[i] == lwmcp.ErrTaskNotWaiting {
			notWaiting++
		} else {
			t.Fatalf("unexpected result[%d]: err=%v completed=%v", i, results[i], completed[i])
		}
	}
	if wins != 1 || notWaiting != 1 {
		t.Fatalf("wins=%d notWaiting=%d, want 1/1 (single-winner)", wins, notWaiting)
	}
	if len(hits) != 1 {
		t.Fatalf("resolver ran %d times, want exactly 1", len(hits))
	}
}
