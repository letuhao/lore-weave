// GrantRevokeConsumer (D-GRANT-INSTANT-REVOKE) tails book-service's grant-revoke
// stream and drops the matching cached (user, book) grant from this process's
// grantclient cache — so a revoke/downgrade takes effect at once instead of after
// the 45s positive-cache TTL.
//
// Unlike the staleness consumer this uses a PLAIN XRead (no consumer group): cache
// invalidation must fan out to EVERY replica (a group would deliver each event to
// only one). Each instance tails from "$" independently; a missed event simply
// degrades to the TTL (fail-safe). Pure cache-side-effect — never touches data.
package events

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/grantclient"
)

const grantRevokeStream = "loreweave:events:grant_revoke"

// GrantRevokeConsumer tails the grant-revoke stream and invalidates the local cache.
type GrantRevokeConsumer struct {
	rdb    *redis.Client
	grants *grantclient.Client
}

// NewGrantRevokeConsumer builds a consumer from a redis URL + the process's grant
// client. Returns (nil, nil) when redisURL is empty or grants is nil — the feature
// is simply disabled (the cache then relies on the TTL only).
func NewGrantRevokeConsumer(redisURL string, grants *grantclient.Client) (*GrantRevokeConsumer, error) {
	if redisURL == "" || grants == nil {
		return nil, nil
	}
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &GrantRevokeConsumer{rdb: redis.NewClient(opt), grants: grants}, nil
}

// Run blocks until ctx is cancelled, tailing the stream and invalidating on each
// event. Best-effort: transient read errors are logged and the loop continues.
func (c *GrantRevokeConsumer) Run(ctx context.Context) {
	if c == nil {
		return
	}
	slog.Info("grant-revoke-consumer: started", "stream", grantRevokeStream)
	lastID := "$" // forward-only — a cache only cares about NEW revokes
	for {
		if ctx.Err() != nil {
			return
		}
		res, err := c.rdb.XRead(ctx, &redis.XReadArgs{
			Streams: []string{grantRevokeStream, lastID},
			Count:   64,
			Block:   5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || ctx.Err() != nil {
				continue
			}
			slog.Warn("grant-revoke-consumer: read failed", "err", err)
			time.Sleep(time.Second)
			continue
		}
		for _, st := range res {
			for _, msg := range st.Messages {
				lastID = msg.ID
				c.apply(msg)
			}
		}
	}
}

func (c *GrantRevokeConsumer) apply(msg redis.XMessage) {
	raw := str(msg.Values["payload"])
	if raw == "" {
		return
	}
	var body struct {
		UserID string `json:"user_id"`
		BookID string `json:"book_id"`
	}
	if err := json.Unmarshal([]byte(raw), &body); err != nil {
		return
	}
	bookID, err1 := uuid.Parse(body.BookID)
	userID, err2 := uuid.Parse(body.UserID)
	if err1 != nil || err2 != nil {
		return
	}
	c.grants.Invalidate(bookID, userID)
}
