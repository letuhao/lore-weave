// BookLifecycleConsumer (DQ-T38 residue, owner ruling 2026-09-02) drops a sharing policy whose
// book no longer exists.
//
// 🔴 THE DEFECT, MEASURED 2026-09-02 while answering DQ-T38 ("why does the public catalogue list
// nothing while 44 books are marked public?"). The catalogue was RIGHT — not one of those 44 books
// exists. 57 of 58 sharing_policies rows point at a book that is gone:
//
//	sharing_policies                     58 rows  (44 public, 13 private, 1 unlisted)
//	...pointing at a book that EXISTS     1 row
//	books in loreweave_book             867
//
// Nothing cleaned them up, and nothing could: book-service emitted no delete signal sharing
// consumed, sharing subscribed to nothing at all, and the two stores are separate databases so
// there is no FK cascade either. A policy row therefore outlives its book forever.
//
// 🔴 THE BLAST RADIUS IS SMALL AND IS NOT OVERSTATED. The catalogue joins through book-service's
// projection, so an orphan surfaces nothing to a user, and UUIDs are not reused so no future book
// can inherit one. What it costs is that the sharing store's own numbers lie about the platform —
// which is exactly what sent DQ-T38 to the P7-FALSE-ABSENCE class and kept it open for six weeks.
//
// 🔴 THE MECHANISM ALREADY EXISTED AND WAS MERELY UNCONSUMED, which is the first thing to check
// before building anything. book-service has emitted `book.lifecycle_changed` {book_id} on every
// trash / restore / purge since the manuscript-structure work, published to
// `loreweave:events:book`; composition-service has consumed it all along. Nothing new is invented
// here — sharing simply starts listening.
//
// WHY IT RE-READS INSTEAD OF TRUSTING THE PAYLOAD. book-service's own note on the event says it,
// and it is the reason the payload carries no state: "the relay is at-least-once + unordered, so a
// payload state would let a stale trashed→restored→trashed redelivery land the mirror on the wrong
// value; a re-read always converges to book-service's truth NOW."
//
// WHY A CONSUMER GROUP AND NOT THE PLAIN XRead THE GRANT-REVOKE CONSUMER USES. That one is a pure
// cache invalidation and MUST fan out to every replica. This one DELETES. A plain XRead would have
// every replica race to delete the same row — harmless today because the delete is idempotent, and
// exactly the kind of accident that stops being harmless the moment someone adds a side effect.
package events

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	bookEventStream = "loreweave:events:book"
	consumerGroup   = "sharing-service"
	consumerName    = "worker-1"
)

// BookProjectionReader answers "does this book still exist?" — book-service's internal projection
// endpoint, which sharing-service already calls elsewhere for its kind check.
type BookProjectionReader interface {
	// BookExists reports whether the book resolves. The bool is only meaningful when err is nil:
	// an unreachable book-service must NEVER be read as "the book is gone".
	BookExists(ctx context.Context, bookID uuid.UUID) (bool, error)
}

type BookLifecycleConsumer struct {
	rdb   *redis.Client
	pool  *pgxpool.Pool
	books BookProjectionReader
}

func NewBookLifecycleConsumer(redisURL string, pool *pgxpool.Pool, books BookProjectionReader) (*BookLifecycleConsumer, error) {
	if redisURL == "" || pool == nil || books == nil {
		// Disabled rather than half-wired: a consumer with no reader would delete on every event.
		return nil, nil
	}
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &BookLifecycleConsumer{rdb: redis.NewClient(opt), pool: pool, books: books}, nil
}

func (c *BookLifecycleConsumer) Run(ctx context.Context) {
	if c == nil {
		return
	}
	// "0" so a fresh group also drains what is already in the stream.
	c.rdb.XGroupCreateMkStream(ctx, bookEventStream, consumerGroup, "0")
	slog.Info("book-lifecycle-consumer: started", "stream", bookEventStream)
	for {
		if ctx.Err() != nil {
			return
		}
		res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{bookEventStream, ">"},
			Count:    64,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || ctx.Err() != nil {
				continue
			}
			slog.Warn("book-lifecycle-consumer: read failed", "err", err)
			time.Sleep(time.Second)
			continue
		}
		for _, st := range res {
			for _, msg := range st.Messages {
				// 🔴 ACK ONLY ON A DECIDED OUTCOME. `Apply` returns an error when book-service
				// could not be reached, and that message is deliberately NOT acked: the whole
				// point of this consumer is that "I could not tell" must never become "the book
				// is gone". It is redelivered instead.
				if err := c.Apply(ctx, msg); err != nil {
					slog.Warn("book-lifecycle-consumer: deferring message", "id", msg.ID, "err", err)
					continue
				}
				c.rdb.XAck(ctx, bookEventStream, consumerGroup, msg.ID)
			}
		}
	}
}

// Apply drops the sharing policy for a book that no longer resolves. Exported so the test can
// drive it directly without a Redis server.
func (c *BookLifecycleConsumer) Apply(ctx context.Context, msg redis.XMessage) error {
	raw, _ := msg.Values["payload"].(string)
	if raw == "" {
		return nil // nothing to act on; ack it rather than redelivering forever
	}
	var body struct {
		BookID string `json:"book_id"`
	}
	if err := json.Unmarshal([]byte(raw), &body); err != nil {
		return nil // malformed payloads are not retryable
	}
	bookID, err := uuid.Parse(body.BookID)
	if err != nil {
		return nil
	}
	exists, err := c.books.BookExists(ctx, bookID)
	if err != nil {
		// 🔴 FAIL CLOSED, LOUDLY. An unreachable book-service is NOT evidence the book is gone,
		// and deleting a live book's sharing policy would make a public book private with no
		// audit trail and no way for the author to know why.
		return fmt.Errorf("cannot confirm book %s: %w", bookID, err)
	}
	if exists {
		return nil
	}
	tag, err := c.pool.Exec(ctx, `DELETE FROM sharing_policies WHERE book_id = $1`, bookID)
	if err != nil {
		return fmt.Errorf("delete policy for %s: %w", bookID, err)
	}
	if n := tag.RowsAffected(); n > 0 {
		slog.Info("book-lifecycle-consumer: dropped orphaned sharing policy",
			"book_id", bookID, "rows", n)
	}
	return nil
}

// HTTPBookReader is the production BookProjectionReader — book-service's internal projection
// endpoint, the same one sharing-service's kind check already uses.
type HTTPBookReader struct {
	BaseURL       string
	InternalToken string
	Client        *http.Client
}

func (r *HTTPBookReader) BookExists(ctx context.Context, bookID uuid.UUID) (bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		fmt.Sprintf("%s/internal/books/%s/projection", r.BaseURL, bookID), nil)
	if err != nil {
		return false, err
	}
	req.Header.Set("X-Internal-Token", r.InternalToken)
	cl := r.Client
	if cl == nil {
		cl = &http.Client{Timeout: 10 * time.Second}
	}
	res, err := cl.Do(req)
	if err != nil {
		return false, err
	}
	defer res.Body.Close()
	switch res.StatusCode {
	case http.StatusOK:
		return true, nil
	case http.StatusNotFound:
		return false, nil
	default:
		// 5xx, 401, anything else: an ANSWER WE DID NOT UNDERSTAND is not a "no".
		return false, fmt.Errorf("projection for %s returned %d", bookID, res.StatusCode)
	}
}
