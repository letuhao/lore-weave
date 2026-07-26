package push

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Querier is the minimal pgx surface the gate needs (satisfied by *pgxpool.Pool).
type Querier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// PushEnabled decides whether to BUZZ the device for a stored notification's (category, message_key).
// It FAILS CLOSED (§8-H2): unlike the in-app prefs.Suppressed() — which fails OPEN so a prefs hiccup
// never drops a stored notification — a lookup error here returns (false, err) so the caller does NOT
// push. That's the safe default for a lock-screen: the in-app row is already persisted, so suppressing
// the buzz on error loses nothing, whereas pushing on a bad read could buzz a topic the user muted.
//
// Resolution: category+message_key → push_topic (H3); the user's push_preferences row for that topic,
// or the topic's code default (TopicDefaults) when the user has no row. A missing row is NOT an error
// (it's the default path); only a real query/scan failure fails closed.
func PushEnabled(ctx context.Context, q Querier, userID uuid.UUID, category, messageKey string) (bool, error) {
	topic := ResolveTopic(category, messageKey)
	var enabled bool
	err := q.QueryRow(ctx,
		`SELECT push_enabled FROM push_preferences WHERE user_id=$1 AND push_topic=$2`,
		userID, string(topic),
	).Scan(&enabled)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return TopicDefaults[topic], nil // no row → the topic's default (not an error)
		}
		return false, err // real error → fail CLOSED: do not push
	}
	return enabled, nil
}
