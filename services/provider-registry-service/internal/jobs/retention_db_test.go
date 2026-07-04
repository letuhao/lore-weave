package jobs

// P2·B2 — DB-mock coverage for the plaintext retention sweeper (PurgeExpiredJobs).
// The DELETE's WHERE clause is the load-bearing correctness: it MUST purge only
// terminal (completed/failed/cancelled) rows past expires_at, never a running/
// pending job (that would drop live work). pgxmock matches the ExpectExec regex
// against the actual SQL, so the status filter + expires_at guard + bounded LIMIT
// are asserted statically here — a future edit that drops the status filter reds
// this test. Runtime row-selection semantics (which rows now() actually matches)
// remain a live-PG concern → D-B2-RETENTION-LIVE-SMOKE.

import (
	"context"
	"errors"
	"testing"

	"github.com/pashagolub/pgxmock/v4"
)

func TestPurgeExpiredJobs_DeletesTerminalPastExpiryBounded(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	defer mock.Close()
	repo := &Repo{pool: mock}

	// The matcher encodes the retention contract: DELETE from llm_jobs, scoped to
	// the 3 terminal statuses, guarded by expires_at < now(), bounded by a LIMIT $1.
	mock.ExpectExec(`(?s)DELETE FROM llm_jobs.*status IN \('completed','failed','cancelled'\).*expires_at < now\(\).*LIMIT \$1`).
		WithArgs(1000).
		WillReturnResult(pgxmock.NewResult("DELETE", 3))

	n, err := repo.PurgeExpiredJobs(context.Background(), 1000)
	if err != nil {
		t.Fatalf("purge: %v", err)
	}
	if n != 3 {
		t.Fatalf("deleted=%d want 3", n)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestPurgeExpiredJobs_PropagatesError(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	sentinel := errors.New("boom")
	mock.ExpectExec(`DELETE FROM llm_jobs`).WithArgs(500).WillReturnError(sentinel)

	n, err := repo.PurgeExpiredJobs(context.Background(), 500)
	if err == nil {
		t.Fatal("want error, got nil")
	}
	if n != 0 {
		t.Fatalf("deleted=%d want 0 on error", n)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}
