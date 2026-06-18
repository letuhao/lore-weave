package jobs

// M3 (chat disconnect-cancel) — unit coverage for the billing-neutral streaming
// finalize. The 'running' guard is the load-bearing property: it must NOT clobber
// a 'cancelled' status that an explicit DELETE (Cancel) already wrote.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

func TestFinalizeStreamStatus_RunningRowUpdates(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectExec("UPDATE llm_jobs").
		WithArgs(anyArgs(3)...).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))

	rows, err := repo.FinalizeStreamStatus(context.Background(), uuid.New(), "completed", "stop")
	if err != nil || rows != 1 {
		t.Fatalf("got rows=%d err=%v want 1,nil", rows, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestFinalizeStreamStatus_GuardSkipsNonRunning(t *testing.T) {
	// A row already 'cancelled' by an explicit DELETE (Cancel) → the
	// status='running' guard makes this a no-op (rows==0), NOT a clobber.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectExec("UPDATE llm_jobs").
		WithArgs(anyArgs(3)...).
		WillReturnResult(pgxmock.NewResult("UPDATE", 0))

	rows, err := repo.FinalizeStreamStatus(context.Background(), uuid.New(), "cancelled", "client_cancelled")
	if err != nil || rows != 0 {
		t.Fatalf("got rows=%d err=%v want 0,nil", rows, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}
