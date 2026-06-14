// Command workload-gen produces seeded foundation event streams (slice S3).
//
//	workload-gen -seed 1 -profile single-reality            # JSONL to stdout (dry-run)
//	workload-gen -seed 1 -profile single-reality -emit -dsn …    # write via the real outbox path
//	workload-gen -seed 1 -profile single-reality -verify -dsn …  # C3 ledger check vs the same seed
//	workload-gen -check-projections -dsn …                       # C structural no-orphan sweep
//
// The stream is ALWAYS validated (referential + causal + monotonic) before
// anything is printed or written — a generator bug must never reach a DB.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	_ "github.com/lib/pq"

	"github.com/loreweave/foundation/tests/workload-gen/internal/emit"
	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
	"github.com/loreweave/foundation/tests/workload-gen/internal/ledger"
	"github.com/loreweave/foundation/tests/workload-gen/internal/projcheck"
)

func main() {
	seed := flag.Int64("seed", 1, "RNG seed (a given seed+profile is byte-deterministic)")
	profile := flag.String("profile", "single-reality", "micro | single-reality | multi-reality | multi-user-session")
	doEmit := flag.Bool("emit", false, "write the stream via the real outbox path (requires -dsn); default is dry-run JSONL")
	doVerify := flag.Bool("verify", false, "C3 ledger check: read -dsn and reconcile against this seed+profile (requires -dsn)")
	doCheckProj := flag.Bool("check-projections", false, "C structural no-orphan sweep: every projection row's event_id must resolve to a real event (requires -dsn)")
	doCheckHistory := flag.Bool("check-history", false, "W2.2 history-ordering: per-aggregate version monotonicity over the recorded stream (requires -dsn)")
	dsn := flag.String("dsn", "", "Postgres DSN for -emit / -verify / -check-projections (a per-reality DB with the events + outbox + projection migrations applied)")
	// W2.1 sustained-workload mode: a steady-rate loop (NOT a single burst) so a
	// fault/soak has a workload that keeps running while the fault is injected.
	duration := flag.Duration("duration", 0, "sustained mode: run a steady-rate emit loop for this long (e.g. 30s); 0 = one-shot")
	rate := flag.Float64("rate", 0, "sustained mode: target events/sec (paced); 0 = as fast as possible")
	flag.Parse()

	os.Exit(run(os.Stdout, *seed, *profile, *doEmit, *doVerify, *doCheckProj, *doCheckHistory, *dsn, *duration, *rate))
}

func run(out io.Writer, seed int64, profileName string, doEmit, doVerify, doCheckProj, doCheckHistory bool, dsn string, duration time.Duration, rate float64) int {
	p, ok := gen.Profiles[profileName]
	if !ok {
		fmt.Fprintf(os.Stderr, "workload-gen: unknown profile %q (have: micro, single-reality, multi-reality, multi-user-session)\n", profileName)
		return 2
	}

	// W2.1 — sustained loop short-circuits the one-shot paths.
	if duration > 0 {
		return runSustained(out, seed, p, dsn, duration, rate)
	}

	stream := gen.New(seed).Generate(p)

	// Validate before printing OR writing — never let a generator bug reach a DB.
	if err := gen.Validate(stream); err != nil {
		fmt.Fprintf(os.Stderr, "workload-gen: generated stream failed validation: %v\n", err)
		return 1
	}

	if doVerify {
		if dsn == "" {
			fmt.Fprintln(os.Stderr, "workload-gen: -verify requires -dsn")
			return 2
		}
		db, err := sql.Open("postgres", dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: open db: %v\n", err)
			return 1
		}
		defer db.Close()
		log, err := ledger.LoadLog(context.Background(), db)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: %v\n", err)
			return 1
		}
		rep := ledger.CheckSelfConsistency(log)
		rep.Merge(ledger.CheckAgainstExpected(log, stream))
		fmt.Fprint(out, rep.String())
		if !rep.OK() {
			return 1
		}
		fmt.Fprintf(os.Stderr, "workload-gen: ledger verified — %d events clean (seed=%d profile=%s)\n", len(stream), seed, profileName)
		return 0
	}

	if doCheckProj {
		if dsn == "" {
			fmt.Fprintln(os.Stderr, "workload-gen: -check-projections requires -dsn")
			return 2
		}
		db, err := sql.Open("postgres", dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: open db: %v\n", err)
			return 1
		}
		defer db.Close()
		ctx := context.Background()
		eventIDs, err := projcheck.LoadEventIDs(ctx, db)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: %v\n", err)
			return 1
		}
		rows, err := projcheck.LoadProjections(ctx, db)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: %v\n", err)
			return 1
		}
		orphans := projcheck.CheckNoOrphan(eventIDs, rows)
		fmt.Fprint(out, projcheck.Render(orphans))
		if len(orphans) > 0 {
			return 1
		}
		fmt.Fprintf(os.Stderr, "workload-gen: no-orphan clean — %d projection rows over %d events\n", len(rows), len(eventIDs))
		return 0
	}

	if doCheckHistory {
		if dsn == "" {
			fmt.Fprintln(os.Stderr, "workload-gen: -check-history requires -dsn")
			return 2
		}
		db, err := sql.Open("postgres", dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: open db: %v\n", err)
			return 1
		}
		defer db.Close()
		log, err := ledger.LoadLog(context.Background(), db)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: %v\n", err)
			return 1
		}
		rep := ledger.CheckAggregateMonotonicity(log)
		fmt.Fprint(out, rep.String())
		if !rep.OK() {
			return 1
		}
		fmt.Fprintf(os.Stderr, "workload-gen: history monotonic — %d events, per-aggregate version strictly ordered\n", len(log.Events))
		return 0
	}

	if doEmit {
		if dsn == "" {
			fmt.Fprintln(os.Stderr, "workload-gen: -emit requires -dsn")
			return 2
		}
		db, err := sql.Open("postgres", dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: open db: %v\n", err)
			return 1
		}
		defer db.Close()
		if err := emit.Stream(context.Background(), db, stream); err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: emit: %v\n", err)
			return 1
		}
		fmt.Fprintf(os.Stderr, "workload-gen: emitted %d events (seed=%d profile=%s)\n", len(stream), seed, profileName)
		return 0
	}

	enc := json.NewEncoder(out)
	for _, e := range stream {
		if err := enc.Encode(e); err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: encode: %v\n", err)
			return 1
		}
	}
	fmt.Fprintf(os.Stderr, "workload-gen: %d events (seed=%d profile=%s, dry-run)\n", len(stream), seed, profileName)
	return 0
}

// runSustained drives a steady-rate emit loop for `duration`, so a soak/fault
// has a workload that keeps running. Each iteration uses seed = base+iter, which
// builds a FRESH seed-derived world (gen.New) → disjoint reality/aggregate ids
// per iteration, so versions never collide across iterations. With a -dsn it
// emits through the real outbox path; without one it dry-runs (counts only),
// which keeps the non-vacuity bite runnable with no DB. Emits a machine-readable
// JSON summary so a drill can assert the run actually sustained ~rate×duration.
func runSustained(out io.Writer, baseSeed int64, p gen.Profile, dsn string, duration time.Duration, rate float64) int {
	var db *sql.DB
	if dsn != "" {
		var err error
		db, err = sql.Open("postgres", dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: open db: %v\n", err)
			return 1
		}
		defer db.Close()
	}
	ctx := context.Background()
	start := time.Now()
	var emitted int
	var iters int64
	for iter := int64(0); ; iter++ {
		if time.Since(start) >= duration {
			break
		}
		stream := gen.New(baseSeed + iter).Generate(p)
		if err := gen.Validate(stream); err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: sustained iter %d failed validation: %v\n", iter, err)
			return 1
		}
		if db != nil {
			if err := emit.Stream(ctx, db, stream); err != nil {
				fmt.Fprintf(os.Stderr, "workload-gen: sustained emit (iter %d): %v\n", iter, err)
				return 1
			}
		}
		emitted += len(stream)
		iters++
		if sleep := paceSleep(emitted, rate, time.Since(start)); sleep > 0 {
			time.Sleep(sleep)
		}
	}
	elapsed := time.Since(start)
	target := 0
	if rate > 0 {
		target = int(rate * duration.Seconds())
	}
	fmt.Fprintf(out, `{"mode":"sustained","emitted":%d,"iters":%d,"elapsed_s":%.2f,"rate":%.1f,"target":%d}`+"\n",
		emitted, iters, elapsed.Seconds(), rate, target)
	fmt.Fprintf(os.Stderr, "workload-gen: sustained %d events over %.1fs (~%.0f eps, target rate %.0f)\n",
		emitted, elapsed.Seconds(), float64(emitted)/elapsed.Seconds(), rate)
	return 0
}

// paceSleep returns how long to sleep so cumulative `emitted` tracks `rate`
// events/sec given `elapsed` so far. Zero rate = no pacing (as fast as possible);
// already-behind = no sleep. Pure (no clock) so it is unit-testable.
func paceSleep(emitted int, rate float64, elapsed time.Duration) time.Duration {
	if rate <= 0 {
		return 0
	}
	targetElapsed := time.Duration(float64(emitted) / rate * float64(time.Second))
	if d := targetElapsed - elapsed; d > 0 {
		return d
	}
	return 0
}
