package push

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// Execer is the minimal write surface (satisfied by *pgxpool.Pool).
type Execer interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
}

// UpsertSubscription registers (or refreshes) a device subscription. Idempotent on the device key
// (owner_user_id, endpoint) — re-registering the same device updates its keys/ua and resets the
// fail_count rather than inserting a duplicate (§8-S1). Owner is the JWT `sub`, never a body field
// (§8-H4) — the caller passes the server-derived id.
func UpsertSubscription(ctx context.Context, q Execer, ownerID uuid.UUID, endpoint, p256dh, auth, ua string) error {
	_, err := q.Exec(ctx, `
INSERT INTO push_subscriptions (owner_user_id, endpoint, p256dh, auth, ua)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (owner_user_id, endpoint)
DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth, ua = EXCLUDED.ua, fail_count = 0
`, ownerID, endpoint, p256dh, auth, nullIfEmpty(ua))
	return err
}

// DeleteSubscription removes one device by (owner, endpoint) — the sign-out teardown (§8-B2). Returns
// the rows deleted (0 if the endpoint wasn't registered — idempotent).
func DeleteSubscription(ctx context.Context, q Execer, ownerID uuid.UUID, endpoint string) (int64, error) {
	tag, err := q.Exec(ctx, `DELETE FROM push_subscriptions WHERE owner_user_id=$1 AND endpoint=$2`, ownerID, endpoint)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

// DeleteAllForOwner removes every subscription for a user — the account-deletion teardown primitive
// (§8-B2). NOTE: it is NOT yet wired to a caller — account erasure is admin-cli-driven and there is no
// account-deletion event for this service to consume (tracked: D-PUSH-ACCOUNT-TEARDOWN). Wire it to an
// erasure-event consumer, or add push_subscriptions to the admin erasure purge, when that lands. The
// sign-out DELETE path (DeleteSubscription) IS wired and covers the common single-device case. Idempotent.
func DeleteAllForOwner(ctx context.Context, q Execer, ownerID uuid.UUID) (int64, error) {
	tag, err := q.Exec(ctx, `DELETE FROM push_subscriptions WHERE owner_user_id=$1`, ownerID)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}
