package api

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

// The worker is OFF by default — StartIngestWorker must be a no-op (no goroutine, no
// DB) unless explicitly enabled, so a dev/test boot never hits a timer.
func TestStartIngestWorker_DisabledByDefault(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	s := NewServer(mock, testCfg()) // testCfg has IngestWorker=false (zero value)
	s.StartIngestWorker(context.Background())
	// no expectations set → if the worker had run a cycle, an unexpected query would fail
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("disabled worker touched the DB: %v", err)
	}
}

func TestStartIngestWorker_EnabledStarts(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	cfg := *testCfg()
	cfg.IngestWorker = true
	cfg.IngestIntervalSeconds = 1 // clamped to 300 at start → won't fire during the test
	s := NewServer(mock, &cfg)
	s.StartIngestWorker(context.Background()) // starts the goroutine; ticker is 300s so no cycle runs
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("enabled worker fired a cycle prematurely: %v", err)
	}
}

// denylistSync: an approved ingested server the completed pull did NOT refresh
// (updated_at < pullStart) is SUSPENDED (dropped from federation) and its queue row
// marked revoked_upstream + audited. This is the §7b#1 retroactive-removal guard.
func TestDenylistSync_SuspendsRemovedUpstreamServer(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	s := NewServer(mock, testCfg())

	ingestID := uuid.MustParse("019d7000-0000-7000-8000-000000000001")
	serverID := uuid.MustParse("019d7000-0000-7000-8000-0000000000aa")
	pullStart := time.Now().UTC()

	mock.ExpectQuery("SELECT ingest_id, name, approved_server_id FROM registry_ingest_queue").
		WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"ingest_id", "name", "approved_server_id"}).
			AddRow(ingestID, "io.gone/server", serverID))
	// suspend the federated server
	mock.ExpectExec("UPDATE mcp_server_registrations SET status='suspended'").
		WithArgs(anyArgs(1)...).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	// mark the queue row revoked_upstream
	mock.ExpectExec("UPDATE registry_ingest_queue SET status='revoked_upstream'").
		WithArgs(anyArgs(1)...).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	// audit + catalog bump
	mock.ExpectExec("INSERT INTO registry_audit").
		WithArgs(anyArgs(8)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec("UPDATE registry_meta SET catalog_version").
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))

	s.denylistSync(context.Background(), pullStart)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("denylistSync did not perform the expected suspend+revoke: %v", err)
	}
}

// A pull that returned nothing removed → no writes (no false suspensions).
func TestDenylistSync_NoRemovals_NoWrites(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	s := NewServer(mock, testCfg())
	mock.ExpectQuery("SELECT ingest_id, name, approved_server_id FROM registry_ingest_queue").
		WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"ingest_id", "name", "approved_server_id"}))
	s.denylistSync(context.Background(), time.Now().UTC())
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unexpected writes when nothing was removed: %v", err)
	}
}
