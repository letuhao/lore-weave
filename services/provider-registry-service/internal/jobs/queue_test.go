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
	q := &JobQueue{sems: map[string]*queueSlot{}, logger: slog.Default()}

	// Effective limits are positive; a non-positive cap does not create a slot.
	if s := q.semFor("cred-B", 0); s != nil {
		t.Fatalf("limit 0 must yield a nil slot; got cap=%d", s.limit)
	}
	if s := q.semFor("cred-B", -1); s != nil {
		t.Fatalf("negative limit must yield a nil slot; got cap=%d", s.limit)
	}
	if len(q.sems) != 0 {
		t.Fatalf("non-positive caps must not retain slots: %d", len(q.sems))
	}
	// Same credential → same slot; the effective limit is fixed while the slot
	// has active references, and idle slots are reclaimed after release.
	a := q.semFor("cred-A", 4)
	b := q.semFor("cred-A", 9)
	if a != b {
		t.Fatalf("semFor returned a different slot for the same credential")
	}
	if b.limit != 4 {
		t.Fatalf("active slot cap must stay 4; got %d", b.limit)
	}
	q.semMu.Lock()
	a.waiters -= 2
	q.deleteSlotIfIdleLocked("cred-A", a)
	q.semMu.Unlock()
	if len(q.sems) != 0 {
		t.Fatalf("idle slots should be reclaimed after their waiters leave: %d", len(q.sems))
	}

	if len(q.sems) != 0 {
		t.Fatalf("idle slot retained: %d", len(q.sems))
	}
}

func TestResolveConcurrency_UserModelCapAndUnlimited(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}
	owner, modelRef := uuid.New(), uuid.New()

	cred := uuid.New()
	cap4 := 4
	mock.ExpectQuery("FROM user_models").WithArgs(modelRef, owner).
		WillReturnRows(pgxmock.NewRows([]string{"provider_credential_id", "max_concurrency"}).AddRow(cred, &cap4))
	key, limit, ok, err := repo.EffectiveConcurrency(context.Background(), "user_model", owner, modelRef, 8)
	if err != nil || !ok || key != cred.String() || limit != 4 {
		t.Fatalf("explicit cap: key=%q limit=%d ok=%v err=%v want %s,4,true,nil", key, limit, ok, err, cred)
	}

	// NULL max_concurrency → the shared positive default, not unlimited.
	modelRef = uuid.New()
	mock.ExpectQuery("FROM user_models").WithArgs(modelRef, owner).
		WillReturnRows(pgxmock.NewRows([]string{"provider_credential_id", "max_concurrency"}).AddRow(cred, (*int)(nil)))
	key2, limit2, ok2, err2 := repo.EffectiveConcurrency(context.Background(), "user_model", owner, modelRef, 8)
	if err2 != nil || !ok2 || key2 != cred.String() || limit2 != 8 {
		t.Fatalf("null cap: key=%q limit=%d ok=%v err=%v want %s,8,true,nil", key2, limit2, ok2, err2, cred)
	}

	// Gone model → ok=false, no error (consumer acks+drops).
	modelRef = uuid.New()
	mock.ExpectQuery("FROM user_models").WithArgs(modelRef, owner).
		WillReturnRows(pgxmock.NewRows([]string{"provider_credential_id", "max_concurrency"}))
	_, _, ok3, err3 := repo.EffectiveConcurrency(context.Background(), "user_model", owner, modelRef, 8)
	if ok3 || err3 != nil {
		t.Fatalf("not-found: ok=%v err=%v want false,nil", ok3, err3)
	}

	pmRef := uuid.New()
	pKey, pLimit, pOK, pErr := repo.EffectiveConcurrency(context.Background(), "platform_model", owner, pmRef, 8)
	if pErr != nil || !pOK || pLimit != 8 || pKey != "platform:"+pmRef.String() {
		t.Fatalf("platform: key=%q limit=%d ok=%v err=%v want default cap 8", pKey, pLimit, pOK, pErr)
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
