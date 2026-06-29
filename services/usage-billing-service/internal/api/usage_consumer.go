package api

// S4c — usage audit stream consumer. Consumes the S4b `loreweave:events:usage`
// Redis stream (every completed job's usage, emitted by provider-registry's relay)
// and writes one usage_logs audit row per event with the REAL per-model cost_usd.
// This restores the audit that S4b's removal of the jobs-path RecordUsage left as a
// gap. The USD spend ENFORCEMENT already happened via the Phase-6a guardrail
// reconcile — this path is audit-only (token-quota deduction is retired).
//
// Mirrors the Go stream-consumer pattern used by statistics-service /
// glossary-service. At-least-once delivery; idempotent on request_id via
// writeUsageLog's ON CONFLICT DO NOTHING; XAck only after the durable write.

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/redis/go-redis/v9"
)

// pgxBeginner is the slice of *pgxpool.Pool the consumer needs — an interface so
// tests inject pgxmock. writeUsageLog itself operates on the returned tx.
type pgxBeginner interface {
	Begin(ctx context.Context) (pgx.Tx, error)
}

// UsageConsumer drains loreweave:events:usage → usage_logs audit rows.
type UsageConsumer struct {
	rdb    *redis.Client
	pool   pgxBeginner
	srv    *Server // for writeUsageLog (uses the passed tx + s.secretKey)
	stream string
	group  string
	name   string
	logger *slog.Logger
}

func NewUsageConsumer(rdb *redis.Client, pool pgxBeginner, srv *Server, stream, group, name string, logger *slog.Logger) *UsageConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	if stream == "" {
		stream = "loreweave:events:usage"
	}
	if group == "" {
		group = "usage-biller"
	}
	if name == "" {
		name = "usage-biller-1"
	}
	return &UsageConsumer{rdb: rdb, pool: pool, srv: srv, stream: stream, group: group, name: name, logger: logger}
}

// Run loops until ctx is cancelled, processing the usage stream via a consumer group.
func (c *UsageConsumer) Run(ctx context.Context) {
	// Create the group at the stream tail-from-start ("0"); idempotent (BUSYGROUP).
	if err := c.rdb.XGroupCreateMkStream(ctx, c.stream, c.group, "0").Err(); err != nil &&
		!strings.Contains(err.Error(), "BUSYGROUP") {
		c.logger.Warn("usage consumer group create failed", "err", err)
	}
	c.logger.Info("usage consumer started", "stream", c.stream, "group", c.group)
	// Recover entries left PENDING by a prior run (transient failures that were
	// deliberately not acked — see processMessages). Restores their audit rows.
	c.drainPending(ctx)
	for {
		if ctx.Err() != nil {
			c.logger.Info("usage consumer stopped")
			return
		}
		res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    c.group,
			Consumer: c.name,
			Streams:  []string{c.stream, ">"},
			Count:    50,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			if err == redis.Nil {
				// Idle — a good moment to retry any entries left pending by a
				// transient failure (so they don't wait for a restart).
				c.drainPending(ctx)
				continue
			}
			c.logger.Warn("usage consumer XREADGROUP failed", "err", err)
			select { // brief backoff so a persistent error doesn't hot-loop
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
			continue
		}
		for _, st := range res {
			c.processMessages(ctx, st.Messages)
		}
	}
}

// drainPending does ONE pass over this consumer's already-delivered-but-unacked
// entries (id "0") and reprocesses them. A single pass (no inner loop) avoids
// spinning on an entry that keeps failing transiently — it's retried on the next
// idle drain instead.
func (c *UsageConsumer) drainPending(ctx context.Context) {
	res, err := c.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    c.group,
		Consumer: c.name,
		Streams:  []string{c.stream, "0"},
		Count:    50,
	}).Result()
	if err != nil || len(res) == 0 {
		return
	}
	for _, st := range res {
		c.processMessages(ctx, st.Messages)
	}
}

// processMessages handles a batch, acking only on success or a PERMANENT failure.
// A TRANSIENT failure (DB blip) is left UNACKED so it stays pending and is retried
// by drainPending — the audit row is not silently lost. A permanent failure (a
// malformed event) is acked (dropped) so it can't wedge the group.
func (c *UsageConsumer) processMessages(ctx context.Context, msgs []redis.XMessage) {
	for _, msg := range msgs {
		permanent, err := c.handleMessage(ctx, msg.Values)
		switch {
		case err == nil:
			c.ack(ctx, msg.ID)
		case permanent:
			c.logger.Warn("usage consumer dropping unprocessable event", "id", msg.ID, "err", err)
			c.ack(ctx, msg.ID)
		default:
			// Transient — leave pending; drainPending retries it. No ack.
			c.logger.Warn("usage consumer transient failure (will retry)", "id", msg.ID, "err", err)
		}
	}
}

func (c *UsageConsumer) ack(ctx context.Context, id string) {
	if err := c.rdb.XAck(ctx, c.stream, c.group, id).Err(); err != nil {
		c.logger.Warn("usage consumer XACK failed", "id", id, "err", err)
	}
}

// handleMessage parses one stream event and writes its audit row in a tx. The
// bool reports whether a non-nil error is PERMANENT (a malformed event — never
// reprocessable) vs TRANSIENT (a DB/tx failure — worth retrying).
func (c *UsageConsumer) handleMessage(ctx context.Context, values map[string]any) (permanent bool, err error) {
	p, perr := parseUsageEvent(values)
	if perr != nil {
		return true, perr // malformed event — dropping is correct
	}
	tx, terr := c.pool.Begin(ctx)
	if terr != nil {
		return false, fmt.Errorf("begin: %w", terr)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, _, _, werr := c.srv.writeUsageLog(ctx, tx, p); werr != nil {
		return false, werr
	}
	if cerr := tx.Commit(ctx); cerr != nil {
		return false, fmt.Errorf("commit: %w", cerr)
	}
	return false, nil
}

// parseUsageEvent maps a Redis-stream field map (all string values, per S4b
// buildUsageFields) to usageLogParams. cost_usd empty/unparseable → flat fallback
// (rare: unpriced model). provider_kind + payloads are absent on the jobs path.
func parseUsageEvent(v map[string]any) (usageLogParams, error) {
	get := func(k string) string {
		s, _ := v[k].(string)
		return s
	}
	reqID, err := uuid.Parse(get("request_id"))
	if err != nil {
		return usageLogParams{}, fmt.Errorf("request_id: %w", err)
	}
	owner, err := uuid.Parse(get("owner_user_id"))
	if err != nil {
		return usageLogParams{}, fmt.Errorf("owner_user_id: %w", err)
	}
	modelRef, err := uuid.Parse(get("model_ref"))
	if err != nil {
		return usageLogParams{}, fmt.Errorf("model_ref: %w", err)
	}
	inTok, _ := strconv.Atoi(get("input_tokens"))
	outTok, _ := strconv.Atoi(get("output_tokens"))
	// mcp_key_id (H-C/PUB-11) — present only when the job originated at the public
	// MCP edge. Empty/unparseable → nil (un-attributed), never a parse failure: a
	// malformed tag must not drop a billing-critical usage row.
	var mcpKeyID *uuid.UUID
	if mk := get("mcp_key_id"); mk != "" {
		if id, e := uuid.Parse(mk); e == nil {
			mcpKeyID = &id
		}
	}
	// Authoritative stream cost_usd (when present + parseable) overrides the flat
	// fallback; recordCostUSD applies the verbatim/zero/negative-reject contract.
	var override *float64
	if cs := get("cost_usd"); cs != "" {
		if f, e := strconv.ParseFloat(cs, 64); e == nil {
			override = &f
		}
	}
	cost := recordCostUSD(inTok+outTok, override)
	return usageLogParams{
		RequestID:     reqID,
		OwnerUserID:   owner,
		ModelSource:   get("model_source"),
		ModelRef:      modelRef,
		InputTokens:   inTok,
		OutputTokens:  outTok,
		CostUSD:       cost,
		RequestStatus: get("request_status"),
		Purpose:       get("operation"),
		McpKeyID:      mcpKeyID,
	}, nil
}
