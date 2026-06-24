package turn

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
)

type recordingWriter struct {
	mu   sync.Mutex
	rows []TurnOutcomeRow
}

func (w *recordingWriter) Write(_ context.Context, row TurnOutcomeRow) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.rows = append(w.rows, row)
	return nil
}

func TestOutcomeRowValidation(t *testing.T) {
	r := TurnOutcomeRow{
		OutcomeID:  uuid.New(),
		TurnID:     "t1",
		FinalState: StateCompleted,
		StartedAt:  time.Now(),
		EndedAt:    time.Now().Add(time.Second),
	}
	if err := r.Validate(); err != nil {
		t.Fatalf("valid row: %v", err)
	}
	r2 := r
	r2.FinalState = StateExecuting
	if err := r2.Validate(); err == nil {
		t.Fatal("non-terminal must error")
	}
	r3 := r
	r3.EndedAt = r.StartedAt.Add(-time.Second)
	if err := r3.Validate(); err == nil {
		t.Fatal("ended_at < started_at must error")
	}
}

func TestCompleteOkAdvancesAndWrites(t *testing.T) {
	c := sampleCtx()
	// Advance to executing first (otherwise Pending->Completed is invalid).
	for _, to := range []TurnState{StateValidating, StateRouting, StateExecuting} {
		if err := c.Advance(to); err != nil {
			t.Fatal(err)
		}
	}
	w := &recordingWriter{}
	idGen := func() uuid.UUID { return uuid.MustParse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") }
	endedAt := c.StartedAt.Add(500 * time.Millisecond)
	if err := CompleteOk(context.Background(), w, c, endedAt, idGen); err != nil {
		t.Fatal(err)
	}
	if c.State() != StateCompleted {
		t.Fatalf("state=%q", c.State())
	}
	if len(w.rows) != 1 {
		t.Fatalf("rows=%d", len(w.rows))
	}
	row := w.rows[0]
	if row.FinalState != StateCompleted {
		t.Fatalf("final=%q", row.FinalState)
	}
	if row.DurationMs != 500 {
		t.Fatalf("duration=%d", row.DurationMs)
	}
}

func TestFailWithPopulatesErrorEnvelopeFields(t *testing.T) {
	c := sampleCtx()
	for _, to := range []TurnState{StateValidating, StateRouting, StateExecuting} {
		if err := c.Advance(to); err != nil {
			t.Fatal(err)
		}
	}
	w := &recordingWriter{}
	idGen := func() uuid.UUID { return uuid.MustParse("11111111-2222-3333-4444-555555555555") }
	endedAt := c.StartedAt.Add(time.Second)
	if err := FailWith(context.Background(), w, c, endedAt, idGen, "user_error", "auth_required", "JWT expired"); err != nil {
		t.Fatal(err)
	}
	if c.State() != StateFailed {
		t.Fatalf("state=%q", c.State())
	}
	if len(w.rows) != 1 {
		t.Fatalf("rows=%d", len(w.rows))
	}
	row := w.rows[0]
	if row.ErrorClass != "user_error" || row.ErrorCode != "auth_required" {
		t.Fatalf("error fields wrong: %+v", row)
	}
}

func TestCompleteOk_RejectsNil(t *testing.T) {
	if err := CompleteOk(context.Background(), nil, sampleCtx(), time.Now(), uuid.New); err == nil {
		t.Fatal("nil writer must error")
	}
	if err := CompleteOk(context.Background(), &recordingWriter{}, nil, time.Now(), uuid.New); err == nil {
		t.Fatal("nil ctx must error")
	}
}
