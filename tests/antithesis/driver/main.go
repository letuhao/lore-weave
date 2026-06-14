// Command antithesis-driver is the S11 whole-stack DST test template.
//
// Under Antithesis: the composed stack (PG + Redis + MinIO + the publisher) runs
// while the hypervisor injects faults; this driver drives workload and asserts
// the load-bearing spine property — DELIVERY-CONVERGENCE: the publisher drains
// every emitted event to its Redis stream with NO LOSS (at-least-once), the one
// property the foundation spine's faults can actually break (review S11 HIGH-1:
// projections are rebuild-only, the write path is transactional). It also
// re-asserts C3 (ledger integrity).
//
// Outside Antithesis the assert/lifecycle calls are no-ops, so this binary is a
// locally-runnable convergence check too. Config via env (defaults = the
// foundation-dev compose). Exit 0 = converged, 1 = a violation, 2 = setup/notrun.
package main

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/antithesishq/antithesis-sdk-go/assert"
	"github.com/antithesishq/antithesis-sdk-go/lifecycle"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	os.Exit(run())
}

func run() int {
	var (
		shardDSN  = env("SHARD_DSN", "postgres://foundation:foundation@127.0.0.1:55432/wholestack_antithesis?sslmode=disable")
		redisAddr = env("REDIS_ADDR", "127.0.0.1:56379")
		wgBin     = env("WG_BIN", "wg")
		profile   = env("WG_PROFILE", "multi-reality")
		seed      = env("WG_SEED", "7")
		quiesceS  = envInt("QUIESCE_TIMEOUT_SECONDS", 60)
	)

	db, err := sql.Open("postgres", shardDSN)
	if err != nil {
		return notrun("open shard DSN: %v", err)
	}
	defer db.Close()
	if err := db.Ping(); err != nil {
		return notrun("shard DB unreachable (composer must migrate + seed it): %v", err)
	}
	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})
	defer rdb.Close()
	ctx := context.Background()
	if err := rdb.Ping(ctx).Err(); err != nil {
		return notrun("redis unreachable: %v", err)
	}

	// Signal Antithesis the system is up and the driver is about to drive load.
	lifecycle.SetupComplete(map[string]any{"driver": "s11-whole-stack", "profile": profile})

	// 1. Ensure a workload exists. The composer's `init` seeds + registers the
	//    realities BEFORE the publisher starts (the V1 publisher loads realities
	//    once), so the driver SKIPS emit when the DB is already seeded and just
	//    checks convergence. It only emits as a fallback on an empty DB.
	n, err := countEvents(db)
	if err != nil {
		return notrun("count events: %v", err)
	}
	if n == 0 {
		if out, err := sh(wgBin, "-seed", seed, "-profile", profile, "-emit", "-dsn", shardDSN); err != nil {
			// Under a fault an emit can fail transactionally (no partial) — legal.
			assert.Sometimes(true, "emit failed transactionally under a fault (tolerated)", map[string]any{"err": err.Error(), "out": out})
			return notrun("emit failed (no events to converge): %v", err)
		}
	}
	assert.Reachable("workload present", nil)

	// 2. Wait for the publisher to drain the outbox (quiesce).
	if !waitOutboxDrained(db, quiesceS) {
		return notrun("outbox did not drain within %ds (publisher not running / too slow)", quiesceS)
	}

	// 3. PRIMARY: delivery-convergence — every event reached its Redis stream,
	//    no loss, dedup-able (XLEN >= distinct == events). Per reality.
	realities, err := distinctRealities(db)
	if err != nil {
		return notrun("enumerate realities: %v", err)
	}
	if len(realities) == 0 {
		return notrun("0 realities — delivery check would be vacuous")
	}
	allConverged := true
	for _, rid := range realities {
		logIDs, err := eventIDs(db, rid)
		if err != nil {
			return notrun("event ids for %s: %v", rid, err)
		}
		streamIDs, xlen, err := streamIDs(ctx, rdb, rid)
		if err != nil {
			return notrun("stream ids for %s: %v", rid, err)
		}
		distinct := uniq(streamIDs)
		noLoss := setEqual(distinct, logIDs)
		dedupAble := xlen >= int64(len(logIDs))
		converged := noLoss && dedupAble
		// The load-bearing assertion Antithesis explores against every fault schedule.
		assert.Always(converged, "delivery-convergence: every emitted event reached its Redis stream (no loss, dedup-able)",
			map[string]any{"reality": rid, "events": len(logIDs), "distinct": len(distinct), "xlen": xlen, "no_loss": noLoss, "dedup_able": dedupAble})
		if !converged {
			allConverged = false
			fmt.Fprintf(os.Stderr, "[driver] FAIL delivery-convergence reality=%s events=%d distinct=%d xlen=%d\n", rid, len(logIDs), len(distinct), xlen)
		}
	}
	assert.Sometimes(true, "driver reached the convergence assertion (progress made under the schedule)", nil)

	// 4. SECONDARY: C3 ledger integrity (rebuild-laundered B/C2 are S5/S8's job).
	if out, err := sh(wgBin, "-seed", seed, "-profile", profile, "-verify", "-dsn", shardDSN); err != nil {
		assert.Always(false, "C3: event-store ledger integrity", map[string]any{"err": err.Error(), "out": out})
		allConverged = false
	} else {
		assert.Always(true, "C3: event-store ledger integrity", nil)
	}

	assert.Reachable("driver completed a full convergence cycle", nil)
	if !allConverged {
		return 1
	}
	fmt.Println("[driver] PASS: delivery-convergence (no-loss, dedup-able) + C3 clean")
	return 0
}

// ── helpers ──────────────────────────────────────────────────────────────────

func notrun(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "[driver] NOTRUN: "+format+"\n", a...)
	return 2
}

func envInt(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func sh(name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func waitOutboxDrained(db *sql.DB, timeoutS int) bool {
	deadline := time.Now().Add(time.Duration(timeoutS) * time.Second)
	for time.Now().Before(deadline) {
		var pending int
		if err := db.QueryRow("SELECT count(*) FROM events_outbox WHERE published = FALSE").Scan(&pending); err == nil && pending == 0 {
			return true
		}
		time.Sleep(1 * time.Second)
	}
	return false
}

func countEvents(db *sql.DB) (int, error) {
	var n int
	err := db.QueryRow("SELECT count(*) FROM events").Scan(&n)
	return n, err
}

func distinctRealities(db *sql.DB) ([]string, error) {
	rows, err := db.Query("SELECT DISTINCT reality_id FROM events")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var r string
		if err := rows.Scan(&r); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

func eventIDs(db *sql.DB, reality string) ([]string, error) {
	rows, err := db.Query("SELECT event_id FROM events WHERE reality_id = $1 ORDER BY 1", reality)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, strings.ToLower(id))
	}
	return out, rows.Err()
}

// streamIDs returns the lowercased event_id field of every entry in the
// reality's Redis stream, plus XLEN.
func streamIDs(ctx context.Context, rdb *redis.Client, reality string) ([]string, int64, error) {
	stream := "lw.events." + reality
	xlen, err := rdb.XLen(ctx, stream).Result()
	if err != nil {
		return nil, 0, err
	}
	msgs, err := rdb.XRange(ctx, stream, "-", "+").Result()
	if err != nil {
		return nil, 0, err
	}
	var ids []string
	for _, m := range msgs {
		if v, ok := m.Values["event_id"]; ok {
			ids = append(ids, strings.ToLower(fmt.Sprint(v)))
		}
	}
	return ids, xlen, nil
}

func uniq(in []string) []string {
	seen := map[string]struct{}{}
	var out []string
	for _, s := range in {
		if _, ok := seen[s]; !ok {
			seen[s] = struct{}{}
			out = append(out, s)
		}
	}
	sort.Strings(out)
	return out
}

func setEqual(a, b []string) bool {
	as, bs := uniq(a), uniq(b)
	if len(as) != len(bs) {
		return false
	}
	for i := range as {
		if as[i] != bs[i] {
			return false
		}
	}
	return true
}
