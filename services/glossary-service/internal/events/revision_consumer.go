// Package events hosts glossary-service's downstream stream consumers.
//
// RevisionConsumer (D-GLOSSARY-VERSIONING, VG-1) materializes the entity
// versioning history. It is a Redis-Streams consumer group on
// loreweave:events:glossary — the same fan-out the relay already ships
// glossary.entity_updated to (knowledge/learning/translation also consume it).
// For each event it copies the entity's current whole-entity snapshot into the
// append-only entity_revisions table. This is a pure DOWNSTREAM projection: the
// hot glossary write path pays nothing for history.
//
// Actor-granularity (scale): a USER edit is always versioned (the precious,
// irreproducible recovery case); a pipeline/bulk write is versioned but pruned to
// a rolling last-N per entity (high-volume + reproducible). Idempotent on the
// source outbox_id, so an at-least-once redelivery never double-writes.
package events

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	revisionStream = "loreweave:events:glossary"
	revisionGroup  = "glossary-revisions"
	entityUpdated  = "glossary.entity_updated"
	// pipelineKeepN: how many of the most-recent PIPELINE revisions to keep per
	// entity. Machine writes are high-volume + reproducible → a small rolling
	// window is enough; USER revisions are never pruned.
	pipelineKeepN = 5
)

// RevisionConsumer reads glossary entity events and projects revisions.
type RevisionConsumer struct {
	pool     *pgxpool.Pool
	rdb      *redis.Client
	consumer string // per-instance name (hostname) so multiple replicas don't share identity
}

// NewRevisionConsumer builds a consumer from a redis URL. Returns (nil, nil) when
// redisURL is empty — the feature is simply disabled (dev/test boots without it).
func NewRevisionConsumer(pool *pgxpool.Pool, redisURL string) (*RevisionConsumer, error) {
	if redisURL == "" {
		return nil, nil
	}
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	// Stable per-instance consumer name: hostname is stable across restarts (so a
	// pod reclaims its own pending) yet distinct per replica (so two replicas in the
	// group don't share identity). NOTE (deferred): revision_num is assigned MAX+1,
	// which is safe for the single-consumer-per-entity-stream case; multi-replica
	// concurrent writes to ONE entity could race the (entity_id, revision_num)
	// unique key — add a retry/sequence when glossary-service runs >1 replica.
	name, _ := os.Hostname()
	if name == "" {
		name = "glossary-rev"
	}
	return &RevisionConsumer{pool: pool, rdb: redis.NewClient(opt), consumer: name}, nil
}

// Run blocks until ctx is cancelled, consuming the stream. Best-effort: transient
// errors are logged and the loop continues; a revision never affects entity data.
func (c *RevisionConsumer) Run(ctx context.Context) {
	if c == nil {
		return
	}
	// Create the group forward-only ("$") so a first deploy doesn't replay the
	// entire backlog + mass-snapshot every entity. BUSYGROUP (already exists) is OK.
	if err := c.rdb.XGroupCreateMkStream(ctx, revisionStream, revisionGroup, "$").Err(); err != nil &&
		err.Error() != "BUSYGROUP Consumer Group name already exists" {
		slog.Warn("revision-consumer: create group failed (will retry on read)", "err", err)
	}
	slog.Info("revision-consumer: started", "stream", revisionStream, "group", revisionGroup)

	// Drain this consumer's pending (un-acked) entries first (crash recovery),
	// then switch to new messages.
	c.drainPending(ctx)
	for {
		if ctx.Err() != nil {
			return
		}
		res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    revisionGroup,
			Consumer: c.consumer,
			Streams:  []string{revisionStream, ">"},
			Count:    32,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil || ctx.Err() != nil {
				continue // idle (no new messages) or shutting down
			}
			slog.Warn("revision-consumer: read failed", "err", err)
			time.Sleep(time.Second)
			continue
		}
		c.handleStreams(ctx, res)
	}
}

func (c *RevisionConsumer) drainPending(ctx context.Context) {
	res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    revisionGroup,
		Consumer: c.consumer,
		Streams:  []string{revisionStream, "0"},
		Count:    256,
	}).Result()
	if err == nil {
		c.handleStreams(ctx, res)
	}
}

func (c *RevisionConsumer) handleStreams(ctx context.Context, streams []redis.XStream) {
	for _, st := range streams {
		for _, msg := range st.Messages {
			// processMessage returns nil for success AND for poison (a malformed /
			// non-matching event it intentionally skips), and a non-nil error ONLY
			// for a transient DB failure. So: ack on nil (don't re-process poison),
			// but on a transient error LEAVE the message pending — drainPending
			// reclaims it on the next restart rather than dropping a revision
			// (history is recovery-critical, not throwaway).
			if err := c.processMessage(ctx, msg); err != nil {
				slog.Warn("revision-consumer: transient process error — leaving pending for retry",
					"id", msg.ID, "err", err)
				continue
			}
			if err := c.rdb.XAck(ctx, revisionStream, revisionGroup, msg.ID).Err(); err != nil {
				slog.Warn("revision-consumer: ack failed", "id", msg.ID, "err", err)
			}
		}
	}
}

// eventEnvelope is the subset of the glossary.entity_updated payload the
// revision projection needs (actor + op). The full state is read from the
// entity's current snapshot, not the event's lightweight before/after.
type eventEnvelope struct {
	ActorType string `json:"actor_type"`
	ActorID   string `json:"actor_id"`
	Op        string `json:"op"`
}

func (c *RevisionConsumer) processMessage(ctx context.Context, msg redis.XMessage) error {
	if str(msg.Values["event_type"]) != entityUpdated {
		return nil // not our event — ack + skip
	}
	entityID, err := uuid.Parse(str(msg.Values["aggregate_id"]))
	if err != nil {
		return nil // malformed id — skip
	}
	eventID, err := uuid.Parse(str(msg.Values["outbox_id"]))
	if err != nil {
		return nil // no stable idempotency key — skip
	}
	var env eventEnvelope
	_ = json.Unmarshal([]byte(str(msg.Values["payload"])), &env)
	actorType := env.ActorType
	if actorType != "user" && actorType != "pipeline" {
		actorType = "system"
	}
	op := env.Op
	if op == "" {
		op = "updated"
	}
	_, err = recordRevision(ctx, c.pool, entityID, eventID, op, actorType, env.ActorID)
	return err
}

// recordRevision copies the entity's current whole-entity snapshot into
// entity_revisions (idempotent on event_id), pruning pipeline revisions to a
// rolling last-N. Returns (inserted, err). Factored out (DB-only, no Redis) so it
// is unit-testable against a real DB. Returns (false, nil) on a duplicate event or
// a vanished entity.
func recordRevision(
	ctx context.Context, pool *pgxpool.Pool,
	entityID, eventID uuid.UUID, op, actorType, actorID string,
) (bool, error) {
	var snapshot string
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT COALESCE(entity_snapshot::text, '{}'), book_id
		   FROM glossary_entities WHERE entity_id = $1`,
		entityID,
	).Scan(&snapshot, &bookID); err != nil {
		if err == pgx.ErrNoRows {
			return false, nil // entity gone — nothing to version
		}
		return false, err
	}

	var actorUUID *uuid.UUID
	if actorID != "" {
		if u, e := uuid.Parse(actorID); e == nil {
			actorUUID = &u
		}
	}

	var revNum int
	err := pool.QueryRow(ctx, `
		INSERT INTO entity_revisions
		  (entity_id, book_id, revision_num, snapshot, op, actor_type, actor_id, event_id)
		VALUES (
		  $1, $2,
		  (SELECT COALESCE(MAX(revision_num),0)+1 FROM entity_revisions WHERE entity_id = $1),
		  $3::jsonb, $4, $5, $6, $7)
		ON CONFLICT (entity_id, event_id) DO NOTHING
		RETURNING revision_num`,
		entityID, bookID, snapshot, op, actorType, actorUUID, eventID,
	).Scan(&revNum)
	if err == pgx.ErrNoRows {
		return false, nil // duplicate event (redelivery) — idempotent no-op
	}
	if err != nil {
		return false, err
	}

	// Rolling last-N: keep only the most recent pipeline revisions; USER revisions
	// are never pruned (they are the precious recovery case).
	if actorType == "pipeline" {
		if _, err := pool.Exec(ctx, `
			DELETE FROM entity_revisions
			WHERE entity_id = $1 AND actor_type = 'pipeline'
			  AND revision_num NOT IN (
			    SELECT revision_num FROM entity_revisions
			    WHERE entity_id = $1 AND actor_type = 'pipeline'
			    ORDER BY revision_num DESC LIMIT $2)`,
			entityID, pipelineKeepN,
		); err != nil {
			return true, err
		}
	}
	return true, nil
}

// str coerces a redis stream field (interface{}) to string.
func str(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
