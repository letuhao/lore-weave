package events

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// fakeExec is a minimal in-memory OutboxExecutor for unit tests. Captures
// every (query, args) pair + can be primed to fail on the Nth call to
// simulate DB error / partial-fail.
type fakeExec struct {
	calls       [][]any
	failOnCall  int // 1-based; 0 = never
	currentCall int
	rowsPerCall int64
}

type fakeResult struct{ n int64 }

func (r fakeResult) RowsAffected() (int64, error) { return r.n, nil }
func (r fakeResult) LastInsertId() (int64, error) { return 0, errors.New("not supported") }

func (e *fakeExec) ExecContext(_ context.Context, q string, args ...any) (sql.Result, error) {
	e.currentCall++
	e.calls = append(e.calls, append([]any{q}, args...))
	if e.failOnCall != 0 && e.currentCall == e.failOnCall {
		return nil, errors.New("simulated db error")
	}
	n := e.rowsPerCall
	if n == 0 {
		n = 1
	}
	return fakeResult{n: n}, nil
}

func sampleRow(t *testing.T) OutboxRow {
	t.Helper()
	eid, err := uuid.Parse("11111111-1111-1111-1111-111111111111")
	if err != nil {
		t.Fatalf("parse event_id: %v", err)
	}
	rid, err := uuid.Parse("22222222-2222-2222-2222-222222222222")
	if err != nil {
		t.Fatalf("parse reality_id: %v", err)
	}
	return OutboxRow{EventID: eid, RealityID: rid}
}

func TestOutboxWrite_HappyPath(t *testing.T) {
	exec := &fakeExec{}
	if err := OutboxWrite(context.Background(), exec, sampleRow(t)); err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if len(exec.calls) != 1 {
		t.Fatalf("expected 1 ExecContext call, got %d", len(exec.calls))
	}
	if !strings.Contains(exec.calls[0][0].(string), "INSERT INTO events_outbox") {
		t.Errorf("expected INSERT SQL, got %q", exec.calls[0][0])
	}
	if exec.calls[0][1] != sampleRow(t).EventID {
		t.Errorf("expected event_id arg, got %v", exec.calls[0][1])
	}
}

func TestOutboxWrite_RejectsNilEventID(t *testing.T) {
	exec := &fakeExec{}
	row := sampleRow(t)
	row.EventID = uuid.Nil
	err := OutboxWrite(context.Background(), exec, row)
	if err == nil {
		t.Fatal("expected error on nil event_id")
	}
	if !errors.Is(err, ErrInvalidOutboxRow) {
		t.Errorf("expected ErrInvalidOutboxRow, got %v", err)
	}
	if len(exec.calls) != 0 {
		t.Error("executor should NOT have been called on validation failure")
	}
}

func TestOutboxWrite_RejectsNilRealityID(t *testing.T) {
	exec := &fakeExec{}
	row := sampleRow(t)
	row.RealityID = uuid.Nil
	err := OutboxWrite(context.Background(), exec, row)
	if err == nil {
		t.Fatal("expected error on nil reality_id")
	}
	if !errors.Is(err, ErrInvalidOutboxRow) {
		t.Errorf("expected ErrInvalidOutboxRow, got %v", err)
	}
}

func TestOutboxWrite_ExecutorErrorPropagates(t *testing.T) {
	exec := &fakeExec{failOnCall: 1}
	err := OutboxWrite(context.Background(), exec, sampleRow(t))
	if err == nil {
		t.Fatal("expected propagated executor error")
	}
	if !strings.Contains(err.Error(), "simulated db error") {
		t.Errorf("expected wrapped error to contain 'simulated db error', got %v", err)
	}
}

func TestOutboxWrite_ZeroRowsAffectedReturnsErr(t *testing.T) {
	exec := &fakeExec{rowsPerCall: 0} // 0 = treated as default (1); override below
	exec.rowsPerCall = 0
	// Manually craft: simulate driver returning 0 rows.
	// We use a custom executor for this case.
	zeroExec := &zeroRowsExec{}
	err := OutboxWrite(context.Background(), zeroExec, sampleRow(t))
	if err == nil {
		t.Fatal("expected ErrOutboxNoRowsAffected")
	}
	if !errors.Is(err, ErrOutboxNoRowsAffected) {
		t.Errorf("expected ErrOutboxNoRowsAffected, got %v", err)
	}
}

type zeroRowsExec struct{}

func (zeroRowsExec) ExecContext(_ context.Context, _ string, _ ...any) (sql.Result, error) {
	return fakeResult{n: 0}, nil
}

// TestOutboxWrite_AtomicitySimulation mirrors the Rust-side unit test.
// Simulates an in-memory "TX" with two intents (event append + outbox
// write). If the outbox write fails, the caller MUST roll back and the
// simulated event row MUST be discarded.
func TestOutboxWrite_AtomicitySimulation(t *testing.T) {
	var eventsWritten []uuid.UUID

	exec := &fakeExec{failOnCall: 1}
	row := sampleRow(t)
	stagedEventID := row.EventID

	// "Begin TX" — stage event then attempt outbox.
	err := OutboxWrite(context.Background(), exec, row)
	if err == nil {
		// Would commit the event row.
		eventsWritten = append(eventsWritten, stagedEventID)
	}
	// On err, roll back: do NOT append.

	if len(eventsWritten) != 0 {
		t.Fatalf("atomicity violated: event should NOT be durable when outbox fails, got %v", eventsWritten)
	}
}

func TestOutboxInsertSQL_UsesTwoParams(t *testing.T) {
	if !strings.Contains(OutboxInsertSQL, "$1") {
		t.Error("OutboxInsertSQL missing $1")
	}
	if !strings.Contains(OutboxInsertSQL, "$2") {
		t.Error("OutboxInsertSQL missing $2")
	}
	if strings.Contains(OutboxInsertSQL, "$3") {
		t.Error("OutboxInsertSQL should bind exactly 2 params; $3 found")
	}
}

func TestOutboxRow_StringFormat(t *testing.T) {
	row := sampleRow(t)
	s := row.String()
	if !strings.Contains(s, row.EventID.String()) || !strings.Contains(s, row.RealityID.String()) {
		t.Errorf("OutboxRow.String() should embed both UUIDs, got %q", s)
	}
}
