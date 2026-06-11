package jobs

// Phase 1 Commit 3 — unit coverage for the parts of the work queue that don't
// need a live broker: the per-kind semaphore sizing, the kind resolver, the
// dispatch loader, and ProcessJob's redelivery-safe skip. The amqp publish /
// consume round-trip is the live-smoke (D-PHASE1-QUEUE-LIVE-SMOKE).

import (
	"context"
	"log/slog"
	"testing"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

func TestSemFor_PerKindSizing(t *testing.T) {
	q := &JobQueue{cloudMax: 8, sems: map[string]chan struct{}{}, logger: slog.Default()}

	// Local kinds serialize to 1 (the single GPU).
	if got := cap(q.semFor("lm_studio")); got != 1 {
		t.Fatalf("lm_studio sem cap=%d want 1", got)
	}
	if got := cap(q.semFor("ollama")); got != 1 {
		t.Fatalf("ollama sem cap=%d want 1", got)
	}
	// Cloud kinds get cloudMax.
	if got := cap(q.semFor("openai")); got != 8 {
		t.Fatalf("openai sem cap=%d want 8", got)
	}
	// Same kind → same semaphore instance (stable bound, not a fresh one each call).
	a := q.semFor("lm_studio")
	b := q.semFor("lm_studio")
	if a != b {
		t.Fatalf("semFor returned a different semaphore for the same kind")
	}
}

func TestResolveKind_UserModelAndNotFound(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectQuery("SELECT provider_kind FROM user_models").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"provider_kind"}).AddRow("lm_studio"))
	kind, ok, err := repo.ResolveKind(context.Background(), "user_model", uuid.New(), uuid.New())
	if err != nil || !ok || kind != "lm_studio" {
		t.Fatalf("got kind=%q ok=%v err=%v want lm_studio,true,nil", kind, ok, err)
	}

	// Not found → ok=false, no error (caller 404s).
	mock.ExpectQuery("SELECT provider_kind FROM user_models").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"provider_kind"})) // empty → ErrNoRows
	_, ok2, err2 := repo.ResolveKind(context.Background(), "user_model", uuid.New(), uuid.New())
	if ok2 || err2 != nil {
		t.Fatalf("not-found: ok=%v err=%v want false,nil", ok2, err2)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestLoadForProcess_ReturnsDispatch(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	owner, modelRef := uuid.New(), uuid.New()
	mock.ExpectQuery("SELECT owner_user_id, operation, model_source, model_ref, input, chunking, status").
		WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"owner_user_id", "operation", "model_source", "model_ref", "input", "chunking", "status"}).
			AddRow(owner, "entity_extraction", "user_model", modelRef, []byte(`{"messages":[]}`), []byte(nil), "pending"))

	d, err := repo.LoadForProcess(context.Background(), uuid.New())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if d.Operation != "entity_extraction" || d.ModelSource != "user_model" || d.Status != "pending" {
		t.Fatalf("bad dispatch: %+v", d)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestProcessJob_NotPendingSkips(t *testing.T) {
	// Redelivery of an already-cancelled job → ProcessJob loads it, sees status
	// != pending, and returns WITHOUT running Process (no MarkRunning, no
	// finalize). The only DB call is the load SELECT.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	w := &Worker{repo: &Repo{pool: mock}, logger: slog.Default()}

	mock.ExpectQuery("SELECT owner_user_id, operation, model_source, model_ref, input, chunking, status").
		WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"owner_user_id", "operation", "model_source", "model_ref", "input", "chunking", "status"}).
			AddRow(uuid.New(), "chat", "user_model", uuid.New(), []byte(`{}`), []byte(nil), "cancelled"))

	w.ProcessJob(context.Background(), uuid.New())

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestProcessJob_GoneRowDrops(t *testing.T) {
	// A vanished row (ErrNoRows) → load fails → ProcessJob logs + returns (the
	// consumer acks + drops). No further DB calls.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	w := &Worker{repo: &Repo{pool: mock}, logger: slog.Default()}

	mock.ExpectQuery("SELECT owner_user_id, operation, model_source, model_ref, input, chunking, status").
		WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"owner_user_id", "operation", "model_source", "model_ref", "input", "chunking", "status"})) // empty → ErrNoRows

	w.ProcessJob(context.Background(), uuid.New())

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}
