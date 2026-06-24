package jobs

// S4b (Auto-Draft Factory, decision C) — usage outbox relay. Polls the
// transactional `usage_outbox` (written in the finalize tx by
// FinalizeWithUsageOutbox) and publishes each row to two Redis streams:
//
//   loreweave:events:usage           — EVERY job's usage (usage-billing consumes
//                                       this in S4c for the quota/credit deduction)
//   loreweave:events:campaign_usage  — only campaign-tagged usage (G8, bounded;
//                                       campaign-service consumes this in S4d to
//                                       sum per-campaign spend + pause at cap)
//
// Delivery is at-least-once (XADD is a side-effect outside the DB commit); every
// consumer dedups on request_id (= job_id). FOR UPDATE SKIP LOCKED makes the
// poll safe across >1 provider-registry replica (disjoint batches; locks held
// across XADD+mark so no double-publish in the normal case).

import (
	"context"
	"log/slog"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

// RelayConfig tunes the usage relay. Stream names + MAXLEN come from
// provider-registry config; the poll/batch defaults are applied in NewUsageRelay.
type RelayConfig struct {
	UsageStream         string
	CampaignUsageStream string
	UsageMaxLen         int64
	CampaignMaxLen      int64
	// LLM re-arch Phase 1 — the durable, per-job terminal-event stream
	// (job_event_outbox → here). A caller (SDK adapter / future service consumer)
	// resumes on it, keyed by job_id.
	TerminalStream string
	TerminalMaxLen int64
	PollInterval   time.Duration
	BatchSize      int
	// DrainTimeout bounds ONE drain batch (SELECT…FOR UPDATE SKIP LOCKED held
	// across the XADD network calls + mark-published). Caps how long a batch can
	// hold its row locks + a pool connection if Redis is slow/hung — independent
	// of the go-redis client's own per-op timeouts. On timeout the in-flight op
	// errors → tx rollback → rows stay unpublished → retried next tick.
	DrainTimeout time.Duration
}

// UsageRelay drains usage_outbox → Redis streams. Single-purpose background loop.
type UsageRelay struct {
	rdb    *redis.Client
	pool   PgxPool
	cfg    RelayConfig
	logger *slog.Logger
}

func NewUsageRelay(rdb *redis.Client, pool PgxPool, cfg RelayConfig, logger *slog.Logger) *UsageRelay {
	if logger == nil {
		logger = slog.Default()
	}
	if cfg.BatchSize <= 0 {
		cfg.BatchSize = 100
	}
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 500 * time.Millisecond
	}
	if cfg.DrainTimeout <= 0 {
		cfg.DrainTimeout = 15 * time.Second
	}
	if cfg.UsageStream == "" {
		cfg.UsageStream = "loreweave:events:usage"
	}
	if cfg.CampaignUsageStream == "" {
		cfg.CampaignUsageStream = "loreweave:events:campaign_usage"
	}
	if cfg.TerminalStream == "" {
		cfg.TerminalStream = "loreweave:events:llm_job_terminal"
	}
	return &UsageRelay{rdb: rdb, pool: pool, cfg: cfg, logger: logger}
}

// Run loops until ctx is cancelled, draining a batch each PollInterval.
func (r *UsageRelay) Run(ctx context.Context) {
	t := time.NewTicker(r.cfg.PollInterval)
	defer t.Stop()
	r.logger.Info("usage relay started",
		"usage_stream", r.cfg.UsageStream, "campaign_stream", r.cfg.CampaignUsageStream,
		"poll_ms", r.cfg.PollInterval.Milliseconds(), "batch", r.cfg.BatchSize)
	for {
		select {
		case <-ctx.Done():
			r.logger.Info("usage relay stopped")
			return
		case <-t.C:
			if n, err := r.drainOnce(ctx); err != nil {
				r.logger.Warn("usage relay drain failed", "err", err)
			} else if n > 0 {
				r.logger.Debug("usage relay published", "rows", n)
			}
			// LLM re-arch Phase 1 — drain the terminal-event outbox in the same
			// tick. Independent tx/stream from usage; a failure of one doesn't
			// block the other (both retry next tick).
			if n, err := r.drainTerminalOnce(ctx); err != nil {
				r.logger.Warn("terminal relay drain failed", "err", err)
			} else if n > 0 {
				r.logger.Debug("terminal relay published", "rows", n)
			}
		}
	}
}

type usageRow struct {
	id       int64
	campaign string // "" when not campaign-tagged
	fields   map[string]any
}

// buildUsageFields produces the Redis-stream field map for one usage event.
// This is the wire contract S4c (usage-billing) + S4d (campaign) consume — every
// key is here, all values string-encoded (stream values are strings); empty
// string for a null campaign_id / cost_usd. Pure + unit-tested so a key rename
// or a dropped field is caught without a live stack.
func buildUsageFields(requestID, ownerID, campaign, modelSource, modelRef, operation, cost string, inTok, outTok int) map[string]any {
	return map[string]any{
		"request_id":     requestID,
		"owner_user_id":  ownerID,
		"campaign_id":    campaign,
		"model_source":   modelSource,
		"model_ref":      modelRef,
		"operation":      operation,
		"input_tokens":   strconv.Itoa(inTok),
		"output_tokens":  strconv.Itoa(outTok),
		"cost_usd":       cost,
		"request_status": "success",
	}
}

// drainOnce publishes one batch of unpublished rows. Returns the count published.
func (r *UsageRelay) drainOnce(ctx context.Context) (int, error) {
	// Bound the whole batch (locks held across XADD) — see RelayConfig.DrainTimeout.
	ctx, cancel := context.WithTimeout(ctx, r.cfg.DrainTimeout)
	defer cancel()

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// uuid + numeric columns cast to ::text so they scan cleanly into string.
	rows, err := tx.Query(ctx, `
SELECT id, request_id::text, owner_user_id::text, campaign_id::text,
       model_source, model_ref::text, operation,
       input_tokens, output_tokens, cost_usd::text
FROM usage_outbox
WHERE published_at IS NULL
ORDER BY id
LIMIT $1
FOR UPDATE SKIP LOCKED
`, r.cfg.BatchSize)
	if err != nil {
		return 0, err
	}

	var batch []usageRow
	for rows.Next() {
		var id int64
		var requestID, ownerID, modelSource, modelRef, operation string
		var campaignID, costUSD *string // nullable
		var inTok, outTok int
		if err := rows.Scan(&id, &requestID, &ownerID, &campaignID, &modelSource,
			&modelRef, &operation, &inTok, &outTok, &costUSD); err != nil {
			rows.Close()
			return 0, err
		}
		camp := ""
		if campaignID != nil {
			camp = *campaignID
		}
		cost := ""
		if costUSD != nil {
			cost = *costUSD
		}
		batch = append(batch, usageRow{
			id:       id,
			campaign: camp,
			fields:   buildUsageFields(requestID, ownerID, camp, modelSource, modelRef, operation, cost, inTok, outTok),
		})
	}
	// Must drain+close the cursor BEFORE issuing further queries on this tx.
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}
	if len(batch) == 0 {
		return 0, tx.Commit(ctx)
	}

	for _, b := range batch {
		if err := r.rdb.XAdd(ctx, &redis.XAddArgs{
			Stream: r.cfg.UsageStream,
			MaxLen: r.cfg.UsageMaxLen,
			Approx: true,
			Values: b.fields,
		}).Err(); err != nil {
			// Abort: row stays unpublished (lock released on rollback) → retried
			// next tick. Already-XADDed rows in this batch are deduped downstream.
			return 0, err
		}
		if b.campaign != "" {
			if err := r.rdb.XAdd(ctx, &redis.XAddArgs{
				Stream: r.cfg.CampaignUsageStream,
				MaxLen: r.cfg.CampaignMaxLen,
				Approx: true,
				Values: b.fields,
			}).Err(); err != nil {
				return 0, err
			}
		}
		if _, err := tx.Exec(ctx, `UPDATE usage_outbox SET published_at=now() WHERE id=$1`, b.id); err != nil {
			return 0, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return len(batch), nil
}

// buildTerminalFields produces the Redis-stream field map for one terminal
// event. This is the wire contract the SDK event adapter + future service
// consumers read (every value string-encoded; empty string for a null). Pure +
// unit-tested so a key rename / dropped field is caught without a live stack.
// result_ref = job_id — the consumer fetches the full result via
// GET /internal/llm/jobs/{id}; the event carries only correlation + summary.
func buildTerminalFields(jobID, ownerID, operation, status, kind, cost, errCode, errMsg, campaign, correlation string) map[string]any {
	return map[string]any{
		"job_id":         jobID,
		"owner_user_id":  ownerID,
		"operation":      operation,
		"status":         status,
		"kind":           kind,
		"result_ref":     jobID,
		"cost_usd":       cost,
		"error_code":     errCode,
		"error_message":  errMsg,
		"campaign_id":    campaign,
		"correlation_id": correlation,
	}
}

type terminalRow struct {
	id     int64
	fields map[string]any
}

// drainTerminalOnce publishes one batch of unpublished job_event_outbox rows to
// the terminal stream. Same FOR UPDATE SKIP LOCKED + lock-across-XADD shape as
// drainOnce (multi-replica-safe, at-least-once; consumers dedup on job_id).
func (r *UsageRelay) drainTerminalOnce(ctx context.Context) (int, error) {
	ctx, cancel := context.WithTimeout(ctx, r.cfg.DrainTimeout)
	defer cancel()

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	rows, err := tx.Query(ctx, `
SELECT id, job_id::text, owner_user_id::text, operation, status, kind,
       cost_usd::text, error_code, error_message, campaign_id::text, correlation_id
FROM job_event_outbox
WHERE published_at IS NULL
ORDER BY id
LIMIT $1
FOR UPDATE SKIP LOCKED
`, r.cfg.BatchSize)
	if err != nil {
		return 0, err
	}

	var batch []terminalRow
	for rows.Next() {
		var id int64
		var jobID, ownerID, operation, status, kind string
		var cost, errCode, errMsg, campaign, correlation *string // nullable
		if err := rows.Scan(&id, &jobID, &ownerID, &operation, &status, &kind,
			&cost, &errCode, &errMsg, &campaign, &correlation); err != nil {
			rows.Close()
			return 0, err
		}
		batch = append(batch, terminalRow{
			id: id,
			fields: buildTerminalFields(jobID, ownerID, operation, status, kind,
				deref(cost), deref(errCode), deref(errMsg), deref(campaign), deref(correlation)),
		})
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}
	if len(batch) == 0 {
		return 0, tx.Commit(ctx)
	}

	for _, b := range batch {
		if err := r.rdb.XAdd(ctx, &redis.XAddArgs{
			Stream: r.cfg.TerminalStream,
			MaxLen: r.cfg.TerminalMaxLen,
			Approx: true,
			Values: b.fields,
		}).Err(); err != nil {
			// Row stays unpublished (rollback releases the lock) → retried next
			// tick. Already-XADDed rows are deduped downstream on job_id.
			return 0, err
		}
		if _, err := tx.Exec(ctx, `UPDATE job_event_outbox SET published_at=now() WHERE id=$1`, b.id); err != nil {
			return 0, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return len(batch), nil
}

// deref returns the pointed-to string or "" for a nil (null column) pointer.
func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
