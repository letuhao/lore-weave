package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PgDeliveryStore is the Postgres DeliveryStore (breach-notifier's own DB).
type PgDeliveryStore struct{ pool *pgxpool.Pool }

// NewPgDeliveryStore binds a pool (caller-owned).
func NewPgDeliveryStore(pool *pgxpool.Pool) *PgDeliveryStore { return &PgDeliveryStore{pool: pool} }

var _ DeliveryStore = (*PgDeliveryStore)(nil)

// AlreadyDelivered reports whether the incident's notice was already delivered.
func (s *PgDeliveryStore) AlreadyDelivered(ctx context.Context, incidentID string) (bool, error) {
	var status string
	err := s.pool.QueryRow(ctx,
		`SELECT status FROM breach_dpo_delivery WHERE incident_id = $1`, incidentID).Scan(&status)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return false, nil
		}
		return false, fmt.Errorf("store: query delivery %s: %w", incidentID, err)
	}
	return status == StatusDelivered, nil
}

// RecordAttempt upserts the delivery row. attempts increments on every attempt;
// delivered_at is set on success and RETAINED across later rows (COALESCE), so a
// confirmed delivery's timestamp is never lost; last_error reflects the latest attempt.
func (s *PgDeliveryStore) RecordAttempt(ctx context.Context, d Delivery, at time.Time) error {
	var deliveredAt *time.Time
	if d.Status == StatusDelivered {
		deliveredAt = &at
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO breach_dpo_delivery
		  (incident_id, subject, deadline, channel, status, attempts, last_error, delivered_at, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, 1, $6, $7, $8, $8)
		ON CONFLICT (incident_id) DO UPDATE SET
		  subject      = EXCLUDED.subject,
		  deadline     = EXCLUDED.deadline,
		  channel      = EXCLUDED.channel,
		  status       = EXCLUDED.status,
		  attempts     = breach_dpo_delivery.attempts + 1,
		  last_error   = EXCLUDED.last_error,
		  delivered_at = COALESCE(breach_dpo_delivery.delivered_at, EXCLUDED.delivered_at),
		  updated_at   = EXCLUDED.updated_at`,
		d.IncidentID, d.Subject, d.Deadline, d.Channel, d.Status, d.LastError, deliveredAt, at)
	if err != nil {
		return fmt.Errorf("store: upsert delivery %s: %w", d.IncidentID, err)
	}
	return nil
}
