// StalenessConsumer (wiki-llm Phase-2, §5.2 DEFER) is glossary-service's
// wiki-change-control capture. It is a Redis-Streams consumer group on BOTH
// loreweave:events:glossary AND loreweave:events:chapter — the same fan-out the
// outbox relay already ships to. When a knowledge source an AI wiki article was
// built from changes, it records a wiki_staleness row + flips
// wiki_articles.is_knowledge_stale — and does ZERO LLM work (regeneration is the
// user-gated §5.3 DECIDE step). Pure DOWNSTREAM projection: the hot wiki write
// path pays nothing.
//
// Capture is idempotent via the ledger's partial-unique (article, reason, source)
// index, so an at-least-once redelivery never piles duplicate staleness rows.
package events

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	glossaryStream = "loreweave:events:glossary"
	chapterStream  = "loreweave:events:chapter"
	stalenessGroup = "wiki-staleness"

	evEntityUpdated   = "glossary.entity_updated"
	evEntityMerged    = "glossary.entity_merged"
	evChapterPub      = "chapter.published"
	evChapterDeleted  = "chapter.deleted"
	evChapterTrashed  = "chapter.trashed"
	// A chapter's prose came BACK — a bulk book RESTORE un-trashes its chapters (spec §4.6). The
	// articles were hard-broken on the trash; the ground truth returning is a re-grounding trigger
	// (content severity, like a re-publish), not another hard break. Closed-set, so it must be named.
	evChapterRestored = "chapter.restored"
	// WS-0.6 (spec 2026-07-11-publish-independent-kg-indexing): a chapter can now enter
	// the knowledge graph WITHOUT being published ("add to knowledge" on a draft), which
	// re-parses its scenes. stalenessRule below is a CLOSED SET — an event it doesn't
	// name is dropped — so without this the wiki would never re-ground on a re-indexed
	// chapter and its articles would silently rot against prose that has moved.
	evChapterKGIndexed = "chapter.kg_indexed"
	// review-impl: the RETRACTION event. stalenessRule is a closed set, so without this
	// the event was silently ACKed and dropped — wiki articles grounded on a chapter the
	// user REMOVED from their knowledge graph were never flagged stale, and kept citing
	// prose the user asked us to forget. It is a hard break, like a deletion: the ground
	// truth is gone, not merely changed.
	evChapterKGExcluded = "chapter.kg_excluded"
)

// StalenessConsumer reads glossary + chapter events and records wiki staleness.
type StalenessConsumer struct {
	pool     *pgxpool.Pool
	rdb      *redis.Client
	consumer string // per-instance name (hostname) — replicas don't share identity
}

// NewStalenessConsumer builds a consumer from a redis URL. Returns (nil, nil) when
// redisURL is empty — the feature is simply disabled (dev/test boots without it).
func NewStalenessConsumer(pool *pgxpool.Pool, redisURL string) (*StalenessConsumer, error) {
	if redisURL == "" {
		return nil, nil
	}
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	name, _ := os.Hostname()
	if name == "" {
		name = "wiki-staleness"
	}
	return &StalenessConsumer{pool: pool, rdb: redis.NewClient(opt), consumer: name}, nil
}

// Run blocks until ctx is cancelled, consuming BOTH streams (one read-loop per
// stream, since a consumer group is per-stream). Best-effort: transient errors are
// logged and the loop continues; staleness never affects article data.
func (c *StalenessConsumer) Run(ctx context.Context) {
	if c == nil {
		return
	}
	go c.runStream(ctx, glossaryStream)
	c.runStream(ctx, chapterStream)
}

func (c *StalenessConsumer) runStream(ctx context.Context, stream string) {
	// Forward-only ("$") so a first deploy doesn't replay the entire backlog and
	// mass-flag every article. BUSYGROUP (already exists) is fine.
	if err := c.rdb.XGroupCreateMkStream(ctx, stream, stalenessGroup, "$").Err(); err != nil &&
		err.Error() != "BUSYGROUP Consumer Group name already exists" {
		slog.Warn("staleness-consumer: create group failed (will retry on read)", "stream", stream, "err", err)
	}
	slog.Info("staleness-consumer: started", "stream", stream, "group", stalenessGroup)
	c.drainPending(ctx, stream)
	for {
		if ctx.Err() != nil {
			return
		}
		res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    stalenessGroup,
			Consumer: c.consumer,
			Streams:  []string{stream, ">"},
			Count:    32,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || ctx.Err() != nil {
				continue
			}
			slog.Warn("staleness-consumer: read failed", "stream", stream, "err", err)
			time.Sleep(time.Second)
			continue
		}
		c.handleStreams(ctx, stream, res)
	}
}

func (c *StalenessConsumer) drainPending(ctx context.Context, stream string) {
	res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    stalenessGroup,
		Consumer: c.consumer,
		Streams:  []string{stream, "0"},
		Count:    256,
	}).Result()
	if err == nil {
		c.handleStreams(ctx, stream, res)
	}
}

func (c *StalenessConsumer) handleStreams(ctx context.Context, stream string, streams []redis.XStream) {
	for _, st := range streams {
		for _, msg := range st.Messages {
			// ack on nil (success OR intentionally-skipped poison); on a transient DB
			// error LEAVE pending so drainPending reclaims it on the next restart.
			if err := c.processMessage(ctx, msg); err != nil {
				slog.Warn("staleness-consumer: transient error — leaving pending", "id", msg.ID, "err", err)
				continue
			}
			if err := c.rdb.XAck(ctx, stream, stalenessGroup, msg.ID).Err(); err != nil {
				slog.Warn("staleness-consumer: ack failed", "id", msg.ID, "err", err)
			}
		}
	}
}

// stalenessRule maps an event to (reason_code, severity, source_type). The
// affected articles are found by joining wiki_article_source_usage on
// (source_type, source_id=aggregate_id).
func stalenessRule(eventType string) (reason, severity, sourceType string, ok bool) {
	switch eventType {
	case evEntityUpdated:
		return "entity_changed", "content", "entity", true
	case evEntityMerged:
		// aggregate_id is the WINNER (the surviving canon, which now covers both).
		return "merged", "structural", "entity", true
	case evChapterPub, evChapterKGIndexed, evChapterRestored:
		// Same reason code for all three: the chapter's prose (and the scene index the wiki's
		// citations hang off) has been re-pinned, so the articles grounded on it need re-grounding.
		// Publishing and indexing are independent acts, and a RESTORE (prose returns after a book
		// trash) is a third — EACH moves the ground truth back into place.
		return "chapter_regrounded", "content", "block", true
	case evChapterDeleted, evChapterTrashed, evChapterKGExcluded:
		// kg_excluded joins the HARD break class: the user retracted the chapter from
		// their knowledge graph, so any article grounded on it is citing a source that no
		// longer exists for them. Same severity as a deletion — the citation is broken,
		// not merely stale.
		return "citation_broken", "hard", "block", true
	}
	return "", "", "", false
}

func (c *StalenessConsumer) processMessage(ctx context.Context, msg redis.XMessage) error {
	reason, severity, sourceType, ok := stalenessRule(str(msg.Values["event_type"]))
	if !ok {
		return nil // not our event — ack + skip
	}
	sourceID := str(msg.Values["aggregate_id"]) // entity_id or chapter_id
	if sourceID == "" {
		return nil // malformed — skip
	}
	eventID := str(msg.Values["outbox_id"])
	_, err := markArticlesStale(ctx, c.pool, sourceType, sourceID, reason, severity, eventID)
	return err
}

// markArticlesStale records a pending staleness row for every article that used
// (sourceType, sourceID) and flips is_knowledge_stale on them. Idempotent on the
// ledger's partial-unique (article, reason, source) index. Returns the number of
// staleness rows inserted. Factored out (DB-only, no Redis) so it is unit-testable
// against a real DB.
func markArticlesStale(
	ctx context.Context, pool *pgxpool.Pool,
	sourceType, sourceID, reason, severity, eventID string,
) (int, error) {
	srcRef, _ := json.Marshal(map[string]string{
		"source_type": sourceType, "source_id": sourceID, "event_id": eventID,
	})
	tag, err := pool.Exec(ctx, `
		INSERT INTO wiki_staleness (article_id, reason_code, source_ref, severity)
		SELECT DISTINCT wasu.article_id, $3, $5::jsonb, $4
		  FROM wiki_article_source_usage wasu
		 WHERE wasu.source_type = $1 AND wasu.source_id = $2
		ON CONFLICT (article_id, reason_code, (source_ref->>'source_id'))
		  WHERE status = 'pending' DO NOTHING`,
		sourceType, sourceID, reason, severity, string(srcRef),
	)
	if err != nil {
		return 0, err
	}
	inserted := int(tag.RowsAffected())
	if _, err := pool.Exec(ctx, `
		UPDATE wiki_articles SET is_knowledge_stale = true
		 WHERE article_id IN (
		   SELECT article_id FROM wiki_article_source_usage
		    WHERE source_type = $1 AND source_id = $2)
		   AND is_knowledge_stale = false`,
		sourceType, sourceID,
	); err != nil {
		return inserted, err
	}
	return inserted, nil
}
