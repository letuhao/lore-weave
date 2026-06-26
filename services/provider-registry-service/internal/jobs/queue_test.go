package jobs

// Phase 1 Commit 3 — unit coverage for the parts of the work queue that don't
// need a live broker: the per-kind semaphore sizing, the kind resolver, the
// dispatch loader, and ProcessJob's redelivery-safe skip. The amqp publish /
// consume round-trip is the live-smoke (D-PHASE1-QUEUE-LIVE-SMOKE).

import (
	"context"
	"log/slog"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

func TestSemFor_PerCredentialSizing(t *testing.T) {
	q := &JobQueue{sems: map[string]chan struct{}{}, logger: slog.Default()}

	// A credential with a cap → a semaphore of exactly that cap.
	if got := cap(q.semFor("cred-A", 4)); got != 4 {
		t.Fatalf("cred-A sem cap=%d want 4", got)
	}
	// Unlimited (≤0) → nil semaphore (no gate; the caller runs straight through).
	if s := q.semFor("cred-B", 0); s != nil {
		t.Fatalf("limit 0 must yield a nil (unlimited) semaphore; got cap=%d", cap(s))
	}
	if s := q.semFor("cred-B", -1); s != nil {
		t.Fatalf("negative limit must yield a nil semaphore; got cap=%d", cap(s))
	}
	// Same credential → same semaphore instance (stable bound, cached on the cap
	// seen first — a later cap change is ignored until process restart).
	a := q.semFor("cred-A", 4)
	b := q.semFor("cred-A", 9)
	if a != b {
		t.Fatalf("semFor returned a different semaphore for the same credential")
	}
	if cap(b) != 4 {
		t.Fatalf("cached sem cap must stay 4 (first-seen wins); got %d", cap(b))
	}
}

func TestResolveConcurrency_UserModelCapAndUnlimited(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	cred := uuid.New()
	cap4 := 4
	// A credential with max_concurrency=4 → key=credential id, limit=4.
	mock.ExpectQuery("FROM user_models").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"provider_credential_id", "max_concurrency"}).AddRow(cred, &cap4))
	key, limit, ok, err := repo.ResolveConcurrency(context.Background(), "user_model", uuid.New(), uuid.New())
	if err != nil || !ok || key != cred.String() || limit != 4 {
		t.Fatalf("got key=%q limit=%d ok=%v err=%v want %s,4,true,nil", key, limit, ok, err, cred)
	}

	// NULL max_concurrency → limit 0 (unlimited).
	mock.ExpectQuery("FROM user_models").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"provider_credential_id", "max_concurrency"}).AddRow(cred, (*int)(nil)))
	_, limit2, ok2, err2 := repo.ResolveConcurrency(context.Background(), "user_model", uuid.New(), uuid.New())
	if err2 != nil || !ok2 || limit2 != 0 {
		t.Fatalf("null cap: limit=%d ok=%v err=%v want 0,true,nil", limit2, ok2, err2)
	}

	// Gone model → ok=false, no error (consumer acks+drops).
	mock.ExpectQuery("FROM user_models").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"provider_credential_id", "max_concurrency"})) // ErrNoRows
	_, _, ok3, err3 := repo.ResolveConcurrency(context.Background(), "user_model", uuid.New(), uuid.New())
	if ok3 || err3 != nil {
		t.Fatalf("not-found: ok=%v err=%v want false,nil", ok3, err3)
	}

	// Platform models are unlimited without a DB hit.
	pmRef := uuid.New()
	pKey, pLimit, pOK, pErr := repo.ResolveConcurrency(context.Background(), "platform_model", uuid.New(), pmRef)
	if pErr != nil || !pOK || pLimit != 0 || pKey != "platform:"+pmRef.String() {
		t.Fatalf("platform: key=%q limit=%d ok=%v err=%v", pKey, pLimit, pOK, pErr)
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

func TestSweepStuckRunning_FailsAndEmits(t *testing.T) {
	// Two stalled `running` jobs → bulk UPDATE…RETURNING → a job_event_outbox
	// INSERT per swept job → commit, returns 2.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_id", "owner_user_id", "operation", "job_meta"}).
			AddRow(uuid.New(), uuid.New(), "entity_extraction", []byte(`{}`)).
			AddRow(uuid.New(), uuid.New(), "chat", []byte(`{}`)))
	mock.ExpectExec("INSERT INTO job_event_outbox").WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec("INSERT INTO job_event_outbox").WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	n, err := repo.SweepStuckRunning(context.Background(), 30*time.Minute)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if n != 2 {
		t.Fatalf("swept=%d want 2", n)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestSweepStuckRunning_NoneSwept(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_id", "owner_user_id", "operation", "job_meta"})) // none
	mock.ExpectCommit()

	n, err := repo.SweepStuckRunning(context.Background(), 30*time.Minute)
	if err != nil || n != 0 {
		t.Fatalf("got n=%d err=%v want 0,nil", n, err)
	}
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
