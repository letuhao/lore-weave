// Package closure is the W1.3 R09 safe-closure drain orchestrator.
//
// Closing a reality must not strand undelivered events. The orchestrator:
//
//  1. active → pending_close (CAS). This freezes NEW appends immediately — the
//     W1.4 kernel guard reads reality_registry.status UNCACHED, so the instant
//     pending_close commits, appends are rejected. Without that freeze the
//     outbox could never reach 0 (new writes keep arriving), so W1.3 depends on
//     W1.4 (the increment order).
//  2. freeze-settle: a brief wait so any append that passed the guard just
//     BEFORE the flip commits its outbox row before we start counting.
//  3. drain: poll the reality's events_outbox unpublished (and not dead-lettered)
//     count down to 0 — the publisher high-water — bounded by DrainTimeout.
//  4. pending_close → frozen (CAS) — reached ONLY when the count hit 0.
//
// If the drain times out (e.g. the publisher is down) the orchestrator does NOT
// hang and does NOT force →frozen — it ABORTS (pending_close → active), which
// restores the reality and preserves the outbox, and surfaces drain_timeout for
// SRE. Abort is also the manual escape hatch (an operator can re-open any time).
//
// Collaborators are interfaces so the drain/abort logic is unit-tested without a
// DB; the production impls (MetaTransitioner, PgOutboxReader) wrap
// contracts/meta AttemptStateTransition + a pgx count.
package closure

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// Transitioner performs one CAS lifecycle transition for a reality.
type Transitioner interface {
	Transition(ctx context.Context, realityID, from, to string) error
}

// OutboxReader reports the reality's drainable (unpublished, not dead-lettered)
// outbox backlog — the publisher high-water.
type OutboxReader interface {
	UnpublishedCount(ctx context.Context, realityID string) (int64, error)
}

// Result reports how the close ended.
type Result struct {
	FinalState      string // "frozen" (drained) or "active" (aborted)
	Aborted         bool
	AbortReason     string
	Polls           int
	LastUnpublished int64
}

// Orchestrator drives the safe-closure drain. Zero PollInterval/DrainTimeout =>
// a single drain check (no looping).
type Orchestrator struct {
	Tr           Transitioner
	Outbox       OutboxReader
	PollInterval time.Duration
	DrainTimeout time.Duration
	SettleDelay  time.Duration
	// Sleep is injectable so tests run instantly; nil => real time.Sleep.
	Sleep func(ctx context.Context, d time.Duration)
}

func (o *Orchestrator) sleep(ctx context.Context, d time.Duration) {
	if d <= 0 {
		return
	}
	if o.Sleep != nil {
		o.Sleep(ctx, d)
		return
	}
	select {
	case <-ctx.Done():
	case <-time.After(d):
	}
}

// Close runs the full close-drain for one reality.
func (o *Orchestrator) Close(ctx context.Context, realityID string) (*Result, error) {
	// 1. active → pending_close (freezes new appends via W1.4).
	if err := o.Tr.Transition(ctx, realityID, "active", "pending_close"); err != nil {
		return nil, fmt.Errorf("closure: enter pending_close: %w", err)
	}
	// 2. freeze-settle: let any pre-flip in-flight append commit its outbox row.
	o.sleep(ctx, o.SettleDelay)

	// 3. drain: poll unpublished → 0, bounded by DrainTimeout/PollInterval.
	maxPolls := 1
	if o.PollInterval > 0 && o.DrainTimeout > 0 {
		maxPolls = max(int(o.DrainTimeout/o.PollInterval), 1)
	}
	res := &Result{}
	for {
		n, err := o.Outbox.UnpublishedCount(ctx, realityID)
		if err != nil {
			return nil, fmt.Errorf("closure: outbox count: %w", err)
		}
		res.Polls++
		res.LastUnpublished = n
		if n == 0 {
			break
		}
		if res.Polls >= maxPolls {
			// Timeout — abort + restore, never force →frozen (that would strand
			// the undrained events behind a frozen reality).
			if err := o.Tr.Transition(ctx, realityID, "pending_close", "active"); err != nil {
				return nil, fmt.Errorf("closure: abort-restore after drain timeout: %w", err)
			}
			res.FinalState = "active"
			res.Aborted = true
			res.AbortReason = "drain_timeout"
			return res, nil
		}
		o.sleep(ctx, o.PollInterval)
	}

	// 4. pending_close → frozen (only when drained to 0).
	if err := o.Tr.Transition(ctx, realityID, "pending_close", "frozen"); err != nil {
		return nil, fmt.Errorf("closure: freeze: %w", err)
	}
	res.FinalState = "frozen"
	return res, nil
}

// ─── production collaborators ────────────────────────────────────────────────

// MetaTransitioner wraps contracts/meta.AttemptStateTransition (CAS + I9 audit).
type MetaTransitioner struct {
	Cfg   *meta.Config
	Actor meta.Actor
}

// Transition runs a CAS reality transition with the closure reason.
func (m MetaTransitioner) Transition(ctx context.Context, realityID, from, to string) error {
	_, err := meta.AttemptStateTransition(ctx, m.Cfg, meta.TransitionRequest{
		ResourceType: "reality",
		ResourceID:   realityID,
		FromState:    from,
		ToState:      to,
		Reason:       "w1.3-closure-drain",
		Actor:        m.Actor,
	})
	return err
}

// PgOutboxReader counts drainable outbox rows in a per-reality DB pool. The
// pool IS the reality scope (one DB per reality), so the count is the table's
// pending-scan predicate — unpublished AND not dead-lettered (a dead-lettered
// row can never be published, so it must NOT block the drain; SRE triages it).
type PgOutboxReader struct {
	Pool *pgxpool.Pool
}

// UnpublishedCount returns the drainable backlog (realityID is informational —
// the pool is already the reality's DB).
func (r PgOutboxReader) UnpublishedCount(ctx context.Context, _ string) (int64, error) {
	var n int64
	err := r.Pool.QueryRow(ctx,
		`SELECT count(*) FROM events_outbox WHERE published = false AND dead_lettered_at IS NULL`,
	).Scan(&n)
	return n, err
}
