package api

// Phase 6a — leaked-reservation sweeper. A held reservation whose job never
// reached a terminal state (gateway crash, lost worker) would inflate
// reserved_usd forever and permanently shrink the user's budget. The sweeper
// releases held reservations past expires_at, marking them 'swept' (a state
// distinct from 'released' so a late reconcile still records the spend —
// see settleReservation / review-impl HIGH#2). ADR §3.

import (
	"context"
	"log/slog"
	"time"

	"github.com/google/uuid"
)

// StartSweeper runs the sweeper loop until ctx is cancelled. Call in a goroutine.
func (s *Server) StartSweeper(ctx context.Context, interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			if n, err := s.sweepExpiredReservations(ctx); err != nil {
				slog.Error("guardrail sweeper failed", "err", err)
			} else if n > 0 {
				slog.Info("guardrail sweeper released expired holds", "count", n)
			}
		}
	}
}

// sweepExpiredReservations releases every held reservation past expires_at.
func (s *Server) sweepExpiredReservations(ctx context.Context) (int, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	rows, err := tx.Query(ctx, `
SELECT reservation_id, owner_user_id, estimated_usd FROM token_reservations
WHERE status = 'held' AND expires_at < now()
FOR UPDATE SKIP LOCKED`)
	if err != nil {
		return 0, err
	}
	type expired struct {
		id, owner uuid.UUID
		est       float64
	}
	var list []expired
	for rows.Next() {
		var e expired
		if err := rows.Scan(&e.id, &e.owner, &e.est); err != nil {
			rows.Close()
			return 0, err
		}
		list = append(list, e)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	for _, e := range list {
		if _, err := tx.Exec(ctx, `
UPDATE spend_guardrails SET reserved_usd = reserved_usd - $2, updated_at = now()
WHERE owner_user_id = $1`, e.owner, e.est); err != nil {
			return 0, err
		}
		if _, err := tx.Exec(ctx, `
UPDATE token_reservations SET status = 'swept', updated_at = now()
WHERE reservation_id = $1`, e.id); err != nil {
			return 0, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return len(list), nil
}
