// Package scheduler is the per-user tick driver (WS-3.1, spec 11 Q3). It is the one thing the platform
// lacked: a time trigger. It does NOT execute jobs — it CLAIMS due `scheduled_agent_runs` rows under a
// lease and hands each to the existing consumer (WS-3.2 posts to the chat distill HTTP trigger, which
// resolves the headless context via WS-3.0). Lease/claim/breaker mirror usage-billing's sweeper.
package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Enqueuer hands a claimed job to its consumer. Returns an error to fail the claim (→ breaker++).
type Enqueuer interface {
	Enqueue(ctx context.Context, ownerUserID uuid.UUID, jobKind string) error
}

// Driver owns the tick loop.
type Driver struct {
	pool     *pgxpool.Pool
	enq      Enqueuer
	name     string        // this replica's consumer name (audit + lease owner)
	lease    time.Duration // how long a claim is held before another replica may re-claim
	maxFails int           // breaker: after this many consecutive failures, back off
	backoff  time.Duration // breaker back-off window
}

func NewDriver(pool *pgxpool.Pool, enq Enqueuer, name string) *Driver {
	return &Driver{pool: pool, enq: enq, name: name, lease: 5 * time.Minute, maxFails: 5, backoff: time.Hour}
}

// Run ticks every `interval` until ctx is cancelled. Restart-safe: a crashed tick's lease expires and
// another driver re-claims; SKIP LOCKED prevents two replicas claiming the same row at once.
func (d *Driver) Run(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if n, err := d.tickOnce(ctx); err != nil {
				slog.Error("scheduler tick failed", "error", err)
			} else if n > 0 {
				slog.Info("scheduler fired", "count", n)
			}
		}
	}
}

type claimedRow struct {
	id    uuid.UUID
	owner uuid.UUID
	kind  string
	tz    string
}

// tickOnce claims every due row (enabled, armed, due, not paused) under a fresh lease, enqueues each,
// then re-arms (success → advance next_fire_at + reset breaker; failure → breaker++ / back off).
func (d *Driver) tickOnce(ctx context.Context) (int, error) {
	tx, err := d.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	now := time.Now().UTC()
	rows, err := tx.Query(ctx, `
SELECT id, owner_user_id, job_kind, timezone
FROM scheduled_agent_runs
WHERE enabled
  AND next_fire_at IS NOT NULL AND next_fire_at <= $1
  AND (paused_until IS NULL OR paused_until <= $1)
  AND (lease_until IS NULL OR lease_until <= $1)
ORDER BY next_fire_at
FOR UPDATE SKIP LOCKED
LIMIT 100`, now)
	if err != nil {
		return 0, err
	}
	var claimed []claimedRow
	for rows.Next() {
		var c claimedRow
		if err := rows.Scan(&c.id, &c.owner, &c.kind, &c.tz); err != nil {
			rows.Close()
			return 0, err
		}
		claimed = append(claimed, c)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}
	if len(claimed) == 0 {
		return 0, nil
	}

	// Stamp the lease on all claimed rows inside the same tx so a concurrent replica can't re-claim.
	leaseUntil := now.Add(d.lease)
	ids := make([]uuid.UUID, len(claimed))
	for i, c := range claimed {
		ids[i] = c.id
	}
	if _, err := tx.Exec(ctx,
		`UPDATE scheduled_agent_runs SET lease_until=$1, locked_by=$2, updated_at=now() WHERE id = ANY($3)`,
		leaseUntil, d.name, ids); err != nil {
		return 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}

	// Enqueue OUTSIDE the claim tx (the lease covers this window). Re-arm each row by its own result.
	fired := 0
	for _, c := range claimed {
		// WS-3.4 (spec 11 Q7) — a NUDGE must never fire on a declared away day (don't scold someone on
		// holiday). Suppress it as a successful no-op: re-arm for the next day, don't send. eod_distill
		// is NOT away-gated (a returning user still wants their days journaled — that's the catch-up).
		if c.kind == "nudge" {
			// M3 — check the user's LOCAL calendar day, not the tick's UTC day (near a tz boundary they
			// differ, so a UTC-day check could suppress/allow a nudge on the wrong day).
			localNow := now
			if loc, err := time.LoadLocation(c.tz); err == nil && c.tz != "" {
				localNow = now.In(loc)
			}
			// cold-review #5 — fail CLOSED: if the away-check errors we SUPPRESS the nudge (a
			// best-effort reminder should not scold someone on holiday precisely when the DB is
			// flaky). Only send when we affirmatively know they're NOT away.
			away, err := IsAway(ctx, d.pool, c.owner, localNow)
			if err != nil || away {
				if err != nil {
					slog.Warn("scheduler: away-check failed; suppressing nudge (fail-closed)", "id", c.id, "error", err)
				}
				d.recordSuccess(ctx, c.id, now) // re-arm, don't notify
				continue
			}
		}
		if err := d.enq.Enqueue(ctx, c.owner, c.kind); err != nil {
			slog.Warn("scheduler enqueue failed; breaker++", "owner", c.owner, "kind", c.kind, "error", err)
			d.recordFailure(ctx, c.id)
			continue
		}
		d.recordSuccess(ctx, c.id, now)
		fired++
	}
	return fired, nil
}

// recordSuccess re-arms next_fire_at to the NEXT LOCAL fire time (review H1: a raw +1d/+7d interval add
// drifts by up to one tick/day and shifts ±1h across DST). Re-reads the row's fire_local_time/timezone/
// cadence and recomputes via ComputeNextFireAt in the user's zone; clears the lease + breaker.
func (d *Driver) recordSuccess(ctx context.Context, id uuid.UUID, firedAt time.Time) {
	var fireLocalTime, tz, cadence string
	if err := d.pool.QueryRow(ctx,
		`SELECT fire_local_time, timezone, cadence FROM scheduled_agent_runs WHERE id=$1`, id).
		Scan(&fireLocalTime, &tz, &cadence); err != nil {
		slog.Error("scheduler recordSuccess: read row failed", "id", id, "error", err)
		return
	}
	// daily → the next local fire after firedAt (tomorrow). weekly → the next local fire after firedAt+6d
	// (~7 days out at the same wall-clock time), so DST changes the UTC instant but not the local time.
	anchor := firedAt
	if cadence == "weekly" {
		anchor = firedAt.AddDate(0, 0, 6)
	}
	next, err := ComputeNextFireAt(fireLocalTime, tz, anchor)
	if err != nil {
		slog.Error("scheduler recordSuccess: compute next failed", "id", id, "error", err)
		return
	}
	// cold-review #3 — guard on `locked_by = d.name`: under a degraded downstream a batch can
	// outrun the 5-min lease, another replica re-claims the row, and this (now lease-less)
	// driver must NOT overwrite the new holder's fresh lease + next_fire_at.
	if _, err := d.pool.Exec(ctx, `
UPDATE scheduled_agent_runs
SET last_fired_at = $2, next_fire_at = $3,
    lease_until = NULL, locked_by = NULL, consecutive_failures = 0, paused_until = NULL, updated_at = now()
WHERE id = $1 AND locked_by = $4`, id, firedAt, next, d.name); err != nil {
		slog.Error("scheduler recordSuccess: update failed", "id", id, "error", err)
	}
}

// recordFailure bumps the breaker; at maxFails it backs the row off (paused_until) instead of hot-looping.
func (d *Driver) recordFailure(ctx context.Context, id uuid.UUID) {
	_, err := d.pool.Exec(ctx, fmt.Sprintf(`
UPDATE scheduled_agent_runs
SET consecutive_failures = consecutive_failures + 1,
    lease_until = NULL, locked_by = NULL,
    paused_until = CASE WHEN consecutive_failures + 1 >= %d THEN now() + interval '%d seconds' ELSE paused_until END,
    updated_at = now()
WHERE id = $1 AND locked_by = $2`, d.maxFails, int(d.backoff.Seconds())), id, d.name)
	if err != nil {
		slog.Error("scheduler recordFailure failed", "id", id, "error", err)
	}
}

// ── HTTPEnqueuer — the default Enqueuer: POST the job to its consumer's HTTP trigger ──

// HTTPEnqueuer posts an 'eod_distill' claim to the chat distill trigger (WS-3.2), which resolves the
// headless distill context server-side (WS-3.0). Other job_kinds are added as their consumers land.
type HTTPEnqueuer struct {
	ChatInternalURL string
	NotificationURL string // WS-3.6 content-free nudge sink; "" → nudges are no-ops
	InternalToken   string
	Client          *http.Client
}

func (e *HTTPEnqueuer) Enqueue(ctx context.Context, ownerUserID uuid.UUID, jobKind string) error {
	switch jobKind {
	case "eod_distill":
		// WS-3.3 — the daily fire also sweeps a small catch-up window (a returning user's last few days
		// get journaled; kept days 409-skip, so it's cheap + idempotent + spend-capped by the distiller).
		return e.postAssistant(ctx, ownerUserID, "/internal/chat/assistant/distill", `,"catchup_days":3`)
	case "weekly_rollup":
		return e.postAssistant(ctx, ownerUserID, "/internal/chat/assistant/weekly-rollup", "")
	case "nudge":
		return e.postNudge(ctx, ownerUserID)
	default:
		return fmt.Errorf("scheduler: unknown job_kind %q", jobKind)
	}
}

// postNudge (WS-3.6, spec 11 Q6/T26) — a CONTENT-FREE reminder. The body carries the user_id + a
// content-free `kind` ONLY — never any diary text (a nudge lands on a lock screen / an employer inbox;
// the content lives behind auth). The notification-service content-free path (locked + tested) renders
// it as "You have an unfinished entry." A missing/unconfigured notification URL degrades to a no-op
// (nudges are best-effort; never a breaker trip for a reminder).
func (e *HTTPEnqueuer) postNudge(ctx context.Context, ownerUserID uuid.UUID) error {
	if e.NotificationURL == "" {
		return nil // nudges best-effort; no notification sink configured → skip quietly
	}
	url := strings.TrimRight(e.NotificationURL, "/") + "/internal/notifications/assistant-nudge"
	body := fmt.Sprintf(`{"user_id":%q,"kind":"unfinished_entry"}`, ownerUserID.String()) // NO content (T26)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", e.InternalToken)
	resp, err := e.Client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return nil
	}
	return fmt.Errorf("nudge notification returned %d", resp.StatusCode)
}

// postAssistant posts {user_id[, extra]} to an assistant trigger `path` (distill or weekly-rollup).
// Both resolve book/model/tz server-side (WS-3.0), so the scheduler carries only the identity (+ an
// optional trailing JSON fragment like `,"catchup_days":3`).
func (e *HTTPEnqueuer) postAssistant(ctx context.Context, ownerUserID uuid.UUID, path, extra string) error {
	url := strings.TrimRight(e.ChatInternalURL, "/") + path
	body := fmt.Sprintf(`{"user_id":%q%s}`, ownerUserID.String(), extra) // WS-3.0 resolves book/model/tz
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", e.InternalToken)
	resp, err := e.Client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	// 202 = enqueued. 422 = the user has no diary/model (WS-3.0) — a permanent skip, NOT a transient
	// failure that should trip the breaker; treat it as "handled" so the row re-arms (the user may
	// configure a model later). Any 5xx / transport error is a real failure (breaker++).
	if resp.StatusCode == http.StatusAccepted || resp.StatusCode == http.StatusUnprocessableEntity {
		return nil
	}
	return fmt.Errorf("distill trigger returned %d", resp.StatusCode)
}

// compile-time assertion
var _ Enqueuer = (*HTTPEnqueuer)(nil)
