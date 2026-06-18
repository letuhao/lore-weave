package turn

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// TurnOutcomeRow is one row written into the meta `turn_outcomes` table
// at every terminal transition (Completed, Failed, Cancelled).
//
// `ErrorClass` + `ErrorCode` are populated for non-Completed terminals
// (zero values for Completed). See contracts/errors for canonical codes.
type TurnOutcomeRow struct {
	OutcomeID    uuid.UUID `json:"outcome_id"`
	TurnID       string    `json:"turn_id"`
	SessionID    string    `json:"session_id"`
	RealityID    string    `json:"reality_id"`
	ActorID      string    `json:"actor_id"`
	FinalState   TurnState `json:"final_state"`
	StartedAt    time.Time `json:"started_at"`
	EndedAt      time.Time `json:"ended_at"`
	DurationMs   int64     `json:"duration_ms"`
	ErrorClass   string    `json:"error_class,omitempty"` // see contracts/errors.ErrorClass
	ErrorCode    string    `json:"error_code,omitempty"`
	ErrorMessage string    `json:"error_message,omitempty"`
}

// Validate fail-fast on malformed rows. Most fields are required.
func (r TurnOutcomeRow) Validate() error {
	if r.OutcomeID == uuid.Nil {
		return errors.New("turn: outcome_id required")
	}
	if r.TurnID == "" {
		return errors.New("turn: turn_id required")
	}
	if !r.FinalState.IsValid() || !r.FinalState.IsTerminal() {
		return fmt.Errorf("turn: final_state must be terminal; got %q", r.FinalState)
	}
	if r.EndedAt.Before(r.StartedAt) {
		return errors.New("turn: ended_at < started_at")
	}
	return nil
}

// TurnOutcomeWriter persists one TurnOutcomeRow into the meta `turn_outcomes`
// table. Production wires this through contracts/meta MetaWrite (so the row
// gets the standard meta_write_audit trail); tests use a fake.
type TurnOutcomeWriter interface {
	Write(ctx context.Context, row TurnOutcomeRow) error
}

// CompleteOk is a convenience that builds a TurnOutcomeRow for a successful
// completion and writes it through the supplied writer.
func CompleteOk(ctx context.Context, w TurnOutcomeWriter, c *TurnContext, endedAt time.Time, idGen func() uuid.UUID) error {
	if c == nil || w == nil {
		return errors.New("turn: nil context or writer")
	}
	if err := c.Advance(StateCompleted); err != nil {
		return err
	}
	row := TurnOutcomeRow{
		OutcomeID:  idGen(),
		TurnID:     c.TurnID,
		SessionID:  c.SessionID,
		RealityID:  c.RealityID,
		ActorID:    c.ActorID,
		FinalState: StateCompleted,
		StartedAt:  c.StartedAt,
		EndedAt:    endedAt,
		DurationMs: endedAt.Sub(c.StartedAt).Milliseconds(),
	}
	return w.Write(ctx, row)
}

// FailWith advances the turn to StateFailed and writes the outcome with the
// supplied error envelope fields.
func FailWith(
	ctx context.Context,
	w TurnOutcomeWriter,
	c *TurnContext,
	endedAt time.Time,
	idGen func() uuid.UUID,
	errorClass, errorCode, errorMessage string,
) error {
	if c == nil || w == nil {
		return errors.New("turn: nil context or writer")
	}
	if err := c.Advance(StateFailed); err != nil {
		return err
	}
	row := TurnOutcomeRow{
		OutcomeID:    idGen(),
		TurnID:       c.TurnID,
		SessionID:    c.SessionID,
		RealityID:    c.RealityID,
		ActorID:      c.ActorID,
		FinalState:   StateFailed,
		StartedAt:    c.StartedAt,
		EndedAt:      endedAt,
		DurationMs:   endedAt.Sub(c.StartedAt).Milliseconds(),
		ErrorClass:   errorClass,
		ErrorCode:    errorCode,
		ErrorMessage: errorMessage,
	}
	return w.Write(ctx, row)
}
