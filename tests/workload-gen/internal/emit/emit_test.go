package emit

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	events "github.com/loreweave/foundation/contracts/events"
)

type recordedCall struct {
	sql  string
	args []any
}

// fakeExec records ExecContext calls and reports a configurable RowsAffected
// (so events.OutboxWrite's 0-rows check can be exercised).
type fakeExec struct {
	calls []recordedCall
	err   error
	rows  int64
}

func (f *fakeExec) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	f.calls = append(f.calls, recordedCall{query, args})
	if f.err != nil {
		return nil, f.err
	}
	return fakeResult{f.rows}, nil
}

type fakeResult struct{ n int64 }

func (r fakeResult) LastInsertId() (int64, error) { return 0, nil }
func (r fakeResult) RowsAffected() (int64, error) { return r.n, nil }

func sampleEvent(metadata map[string]any) events.Envelope {
	return events.Envelope{
		EventID:          uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		EventType:        "npc.said",
		EventVersion:     1,
		AggregateID:      "npc-1",
		AggregateType:    "npc",
		AggregateVersion: 2,
		RealityID:        uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		OccurredAt:       time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC),
		RecordedAt:       time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC),
		Payload:          map[string]any{"text": "hi"},
		Metadata:         metadata,
	}
}

func TestWriteEventInsertsEventThenOutboxSameExecutor(t *testing.T) {
	ex := &fakeExec{rows: 1}
	if err := writeEvent(context.Background(), ex, sampleEvent(nil)); err != nil {
		t.Fatalf("writeEvent: %v", err)
	}
	if len(ex.calls) != 2 {
		t.Fatalf("want 2 ExecContext calls (event + outbox), got %d", len(ex.calls))
	}
	if !strings.Contains(ex.calls[0].sql, "INSERT INTO events") {
		t.Errorf("first call should insert the event, got %q", ex.calls[0].sql)
	}
	if ex.calls[1].sql != events.OutboxInsertSQL {
		t.Errorf("second call should be the canonical outbox INSERT, got %q", ex.calls[1].sql)
	}
	// event id is arg[0] on both; reality id is arg[1] on both
	if ex.calls[0].args[0] != ex.calls[1].args[0] {
		t.Error("event INSERT and outbox INSERT must carry the same event_id")
	}
	if ex.calls[1].args[1] != sampleEvent(nil).RealityID {
		t.Error("outbox row must carry the event's reality_id")
	}
}

func TestWriteEventInsertArgVector(t *testing.T) {
	// Pin the events INSERT's positional contract ($1..$11) so a column/arg
	// reorder or a wrong int cast fails fast in unit tests, not only live.
	ex := &fakeExec{rows: 1}
	e := sampleEvent(map[string]any{"session_id": "s-1"})
	if err := writeEvent(context.Background(), ex, e); err != nil {
		t.Fatalf("writeEvent: %v", err)
	}
	args := ex.calls[0].args
	if len(args) != 11 {
		t.Fatalf("events INSERT must bind 11 args, got %d", len(args))
	}
	checks := []struct {
		i    int
		want any
	}{
		{0, e.EventID},
		{1, e.RealityID},
		{2, e.AggregateType},
		{3, e.AggregateID},
		{4, int64(e.AggregateVersion)}, // BIGINT
		{5, e.EventType},
		{6, int32(e.EventVersion)}, // INTEGER
		{9, e.OccurredAt},
		{10, e.RecordedAt},
	}
	for _, c := range checks {
		if args[c.i] != c.want {
			t.Errorf("arg[%d] = %v, want %v", c.i, args[c.i], c.want)
		}
	}
	if _, ok := args[7].([]byte); !ok {
		t.Errorf("arg[7] payload must be []byte JSON, got %T", args[7])
	}
	if _, ok := args[8].([]byte); !ok {
		t.Errorf("arg[8] metadata must be []byte JSON when present, got %T", args[8])
	}
}

func TestWriteEventMetadataNullWhenAbsent(t *testing.T) {
	// metadata is arg index 8 (1-based $9) in the events INSERT.
	ex := &fakeExec{rows: 1}
	_ = writeEvent(context.Background(), ex, sampleEvent(nil))
	if ex.calls[0].args[8] != nil {
		t.Errorf("absent metadata must bind NULL, got %v", ex.calls[0].args[8])
	}

	ex2 := &fakeExec{rows: 1}
	_ = writeEvent(context.Background(), ex2, sampleEvent(map[string]any{"session_id": "s-1"}))
	if ex2.calls[0].args[8] == nil {
		t.Error("present metadata must bind non-NULL JSON")
	}
}

func TestWriteEventPropagatesInsertError(t *testing.T) {
	ex := &fakeExec{err: errors.New("boom")}
	if err := writeEvent(context.Background(), ex, sampleEvent(nil)); err == nil {
		t.Error("writeEvent must propagate the event INSERT error")
	}
}

func TestWriteEventOutboxZeroRowsIsError(t *testing.T) {
	// rows=0 → events.OutboxWrite returns ErrOutboxNoRowsAffected (a PK collision
	// would surface this) → writeEvent must fail so the caller rolls back.
	ex := &fakeExec{rows: 0}
	if err := writeEvent(context.Background(), ex, sampleEvent(nil)); err == nil {
		t.Error("writeEvent must fail when the outbox INSERT affects 0 rows")
	}
}
