// Package prefs is the per-user notification opt-out layer. Both ingress paths
// (HTTP createNotification/batch + the AMQP terminal-event consumer) call
// Suppressed() before persisting a notification, so a category the user disabled
// is never stored or pushed. The public API (GET/PUT preferences) uses List/Set.
//
// Scope: per-user (user_id is the row's scope key). A user only ever reads/writes
// their own rows — there is no cross-user surface here. Default is DELIVER: a
// category with no row is enabled, so opting IN is the absence of an opt-out row.
package prefs

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// Querier is the minimal DB surface prefs needs; *pgxpool.Pool satisfies it, and a
// pgxmock pool satisfies it in tests.
type Querier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
}

// Suppressed reports whether the user has DISABLED this category (a row with
// enabled=false). Default (no row) = not suppressed (delivered). A NULL/absent row
// therefore fails OPEN — a missing preference never silently drops a notification.
func Suppressed(ctx context.Context, q Querier, userID uuid.UUID, category string) (bool, error) {
	var enabled bool
	err := q.QueryRow(ctx,
		`SELECT enabled FROM notification_preferences WHERE user_id=$1 AND category=$2`,
		userID, category).Scan(&enabled)
	if err == pgx.ErrNoRows {
		return false, nil // no preference row → deliver
	}
	if err != nil {
		return false, err
	}
	return !enabled, nil
}

// Set upserts one category preference for a user (idempotent on the PK).
func Set(ctx context.Context, q Querier, userID uuid.UUID, category string, enabled bool) error {
	_, err := q.Exec(ctx, `
INSERT INTO notification_preferences (user_id, category, enabled, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (user_id, category) DO UPDATE SET enabled=EXCLUDED.enabled, updated_at=now()
`, userID, category, enabled)
	return err
}

// List returns the user's EXPLICIT preference rows as category→enabled. Categories
// with no row are omitted (the caller merges them against the default-enabled set,
// so the response always describes every category without persisting defaults).
func List(ctx context.Context, q Querier, userID uuid.UUID) (map[string]bool, error) {
	rows, err := q.Query(ctx,
		`SELECT category, enabled FROM notification_preferences WHERE user_id=$1`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]bool{}
	for rows.Next() {
		var cat string
		var enabled bool
		if err := rows.Scan(&cat, &enabled); err != nil {
			return nil, err
		}
		out[cat] = enabled
	}
	return out, rows.Err()
}
