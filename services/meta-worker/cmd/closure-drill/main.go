// services/meta-worker/cmd/closure-drill — W1.3 closure-drain live drill.
//
// Drives the REAL closure.Orchestrator (MetaTransitioner over contracts/meta
// AttemptStateTransition + PgOutboxReader over a per-reality events_outbox)
// against the scale rig. reality_registry lives on meta-pg; events_outbox on a
// shard DB.
//
// Modes:
//
//	drain    Seed N unpublished outbox rows; a stub publisher marks them
//	         published over ~100ms. The orchestrator polls the backlog → 0 and
//	         ONLY THEN flips →frozen. Asserts: final status=frozen, backlog 0,
//	         and it actually polled while draining (Polls > 1).
//	timeout  Seed N; NO publisher. The drain times out → the orchestrator ABORTS
//	         (pending_close→active), never forces →frozen. Asserts: status=active
//	         (restored), backlog preserved (still N), not frozen.
//	bite     Naive close (active→pending_close→frozen with NO drain gate) while
//	         the backlog is non-empty → status=frozen WITH undrained rows =
//	         stranded undelivered events. Proves the drain gate is non-vacuous.
//	smoke    drain → timeout → bite.
//
// Verdict: 0 PASS · 1 FAIL · 2 NOTRUN(setup). Re-runnable.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
	"github.com/loreweave/foundation/services/meta-worker/pkg/closure"
)

type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

const (
	closer    = "00000000-0000-0000-0000-0000000000c3"
	shardHost = "pg-shard-0.internal"
	realityDB = "w1c_reality"
	backlog   = 8
)

var (
	metaDSN     = "postgres://foundation:foundation@127.0.0.1:55510/w1_closure?sslmode=disable"
	realityDSN  = "postgres://foundation:foundation@127.0.0.1:55511/w1c_reality?sslmode=disable"
	transitions = "contracts/meta/transitions.yaml"
	allowlist   = "contracts/meta/events_allowlist.yaml"
)

func main() {
	mode := flag.String("mode", "smoke", "drain | timeout | bite | smoke")
	flag.StringVar(&metaDSN, "meta-dsn", metaDSN, "meta DB DSN")
	flag.StringVar(&realityDSN, "reality-dsn", realityDSN, "per-reality DB DSN (events_outbox)")
	flag.Parse()
	os.Exit(run(*mode))
}

func run(mode string) int {
	ctx := context.Background()
	metaPool, err := pgxpool.New(ctx, metaDSN)
	if err != nil {
		return notrun("meta pool: %v", err)
	}
	defer metaPool.Close()
	realityPool, err := pgxpool.New(ctx, realityDSN)
	if err != nil {
		return notrun("reality pool: %v", err)
	}
	defer realityPool.Close()
	if err := metaPool.Ping(ctx); err != nil {
		return notrun("meta ping: %v", err)
	}
	if err := realityPool.Ping(ctx); err != nil {
		return notrun("reality ping: %v", err)
	}

	graph, err := meta.LoadTransitions(transitions)
	if err != nil {
		return notrun("load transitions: %v", err)
	}
	allow, err := meta.LoadAllowlist(allowlist)
	if err != nil {
		return notrun("load allowlist: %v", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(metaPool), Allowlist: allow, Transitions: graph,
		QueryBuilder: meta.PostgresQueryBuilder{}, Clock: sysClock{}, UUIDGen: randUUID{},
	}
	tr := closure.MetaTransitioner{Cfg: cfg, Actor: meta.Actor{Type: meta.ActorSystem, ID: closer}}
	outbox := closure.PgOutboxReader{Pool: realityPool}

	switch mode {
	case "drain":
		return cmdDrain(ctx, metaPool, realityPool, tr, outbox)
	case "timeout":
		return cmdTimeout(ctx, metaPool, realityPool, tr, outbox)
	case "bite":
		return cmdBite(ctx, metaPool, realityPool, tr)
	case "smoke":
		if c := cmdDrain(ctx, metaPool, realityPool, tr, outbox); c != 0 {
			return c
		}
		if c := cmdTimeout(ctx, metaPool, realityPool, tr, outbox); c != 0 {
			return c
		}
		return cmdBite(ctx, metaPool, realityPool, tr)
	default:
		return notrun("unknown mode %q", mode)
	}
}

// drain: publisher catches up → frozen only after backlog hits 0.
func cmdDrain(ctx context.Context, metaPool, realityPool *pgxpool.Pool, tr closure.Transitioner, outbox closure.OutboxReader) int {
	rid := mustReset(ctx, metaPool, realityPool)

	// Stub publisher: mark the backlog published in two batches over ~120ms so
	// the orchestrator genuinely polls a non-zero backlog before it reaches 0.
	go func() {
		time.Sleep(40 * time.Millisecond)
		markPublished(ctx, realityPool, backlog/2)
		time.Sleep(80 * time.Millisecond)
		markPublished(ctx, realityPool, backlog) // the rest
	}()

	o := &closure.Orchestrator{
		Tr: tr, Outbox: outbox,
		PollInterval: 20 * time.Millisecond, DrainTimeout: 10 * time.Second,
		SettleDelay: 10 * time.Millisecond,
	}
	res, err := o.Close(ctx, rid)
	if err != nil {
		return fail("drain: Close: %v", err)
	}
	status := realityStatus(ctx, metaPool, rid)
	left := unpublished(ctx, realityPool)
	fmt.Printf(`{"mode":"drain","final":%q,"db_status":%q,"backlog_left":%d,"polls":%d}`+"\n",
		res.FinalState, status, left, res.Polls)
	if res.FinalState != "frozen" || status != "frozen" {
		return fail("drain: expected frozen, got result=%s db=%s", res.FinalState, status)
	}
	if left != 0 {
		return fail("drain: froze with %d undrained rows", left)
	}
	if res.Polls < 2 {
		return fail("drain: only %d poll(s) — the backlog drained instantly, not a real drain (re-run)", res.Polls)
	}
	return pass("drain: backlog drained to 0 over %d polls, THEN →frozen; no events stranded", res.Polls)
}

// timeout: no publisher → abort + restore, never frozen.
func cmdTimeout(ctx context.Context, metaPool, realityPool *pgxpool.Pool, tr closure.Transitioner, outbox closure.OutboxReader) int {
	rid := mustReset(ctx, metaPool, realityPool)
	o := &closure.Orchestrator{
		Tr: tr, Outbox: outbox,
		PollInterval: 10 * time.Millisecond, DrainTimeout: 60 * time.Millisecond, // ~6 polls
		SettleDelay: 5 * time.Millisecond,
	}
	res, err := o.Close(ctx, rid)
	if err != nil {
		return fail("timeout: Close: %v", err)
	}
	status := realityStatus(ctx, metaPool, rid)
	left := unpublished(ctx, realityPool)
	fmt.Printf(`{"mode":"timeout","final":%q,"db_status":%q,"backlog_left":%d,"aborted":%t,"reason":%q}`+"\n",
		res.FinalState, status, left, res.Aborted, res.AbortReason)
	if !res.Aborted || res.AbortReason != "drain_timeout" {
		return fail("timeout: expected drain_timeout abort, got %+v", res)
	}
	if status != "active" {
		return fail("timeout: expected restore to active, db status=%s", status)
	}
	if left != backlog {
		return fail("timeout: backlog should be preserved (%d), got %d", backlog, left)
	}
	return pass("timeout: drain timed out → aborted to active, %d events preserved (NOT stranded behind frozen)", left)
}

// bite: naive close with NO drain gate → frozen WITH undrained outbox = stranded.
func cmdBite(ctx context.Context, metaPool, realityPool *pgxpool.Pool, tr closure.Transitioner) int {
	rid := mustReset(ctx, metaPool, realityPool)
	// The bug: close straight through without draining.
	if err := tr.Transition(ctx, rid, "active", "pending_close"); err != nil {
		return notrun("bite: pending_close: %v", err)
	}
	if err := tr.Transition(ctx, rid, "pending_close", "frozen"); err != nil {
		return notrun("bite: frozen: %v", err)
	}
	status := realityStatus(ctx, metaPool, rid)
	left := unpublished(ctx, realityPool)
	fmt.Printf(`{"mode":"bite","db_status":%q,"backlog_left":%d}`+"\n", status, left)
	if status != "frozen" || left == 0 {
		return fail("bite VACUOUS: naive close did not strand events (status=%s left=%d) — the drain gate's check cannot fail", status, left)
	}
	return pass("bite: closing WITHOUT the drain gate froze the reality with %d undelivered events stranded — the gate (drain mode) is non-vacuous", left)
}

// ── setup helpers ────────────────────────────────────────────────────────────

func mustReset(ctx context.Context, metaPool, realityPool *pgxpool.Pool) string {
	rid := uuid.New().String()
	if _, err := metaPool.Exec(ctx, "DELETE FROM reality_registry WHERE db_name=$1", realityDB); err != nil {
		die("reset registry: %v", err)
	}
	if _, err := metaPool.Exec(ctx, `INSERT INTO reality_registry
		(reality_id, db_host, db_name, status, locale,
		 session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		VALUES ($1, $2, $3, 'active', 'en', 10, 10, 20, 0)`,
		rid, shardHost, realityDB); err != nil {
		die("seed registry: %v", err)
	}
	if _, err := realityPool.Exec(ctx, "TRUNCATE events_outbox"); err != nil {
		die("truncate outbox: %v", err)
	}
	for range backlog {
		if _, err := realityPool.Exec(ctx,
			`INSERT INTO events_outbox (event_id, reality_id, published) VALUES ($1, $2, false)`,
			uuid.New(), rid); err != nil {
			die("seed outbox: %v", err)
		}
	}
	return rid
}

// markPublished marks up to `upTo` rows published (respecting the consistency
// CHECK: published rows need attempts>=1 + last_attempt_at).
func markPublished(ctx context.Context, realityPool *pgxpool.Pool, upTo int) {
	_, _ = realityPool.Exec(ctx, `
		UPDATE events_outbox SET published=true, attempts=attempts+1, last_attempt_at=now()
		WHERE event_id IN (
			SELECT event_id FROM events_outbox WHERE published=false ORDER BY enqueued_at LIMIT $1
		)`, upTo)
}

func unpublished(ctx context.Context, realityPool *pgxpool.Pool) int64 {
	var n int64
	_ = realityPool.QueryRow(ctx,
		`SELECT count(*) FROM events_outbox WHERE published=false AND dead_lettered_at IS NULL`).Scan(&n)
	return n
}

func realityStatus(ctx context.Context, metaPool *pgxpool.Pool, rid string) string {
	var s string
	_ = metaPool.QueryRow(ctx, "SELECT status FROM reality_registry WHERE reality_id=$1", rid).Scan(&s)
	return s
}

func pass(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "PASS: "+format+"\n", a...)
	return 0
}
func fail(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "FAIL: "+format+"\n", a...)
	return 1
}
func notrun(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "NOTRUN(setup): "+format+"\n", a...)
	return 2
}
func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "closure-drill: "+format+"\n", a...)
	os.Exit(2)
}
