// services/meta-worker/cmd/deadlock-probe — S14 (D4) deadlock / lock-contention.
//
// Validates the ORDERING PRINCIPLE I6 relies on (consistent global lock order ⇒ no
// deadlock). roleplay-service is `missing` — the shipped one-processor-per-session
// command processor does not exist yet — so this drives the principle directly against
// real Postgres, NOT the shipped processor (labeled as such).
//
// Two transactions each lock two rows (A=id 1, B=id 2):
//
//	-mode ordered  both lock in the SAME order (A then B) → one serializes behind the
//	               other → 0 deadlocks, both commit (the I6 principle holds).
//	-mode bite     OPPOSING orders (T1 A→B, T2 B→A) with a BARRIER (both hold their
//	               FIRST lock before either grabs the second) → real PG deadlock
//	               (SQLSTATE 40P01) → proves consistent ordering is what prevents it.
//
// The barrier is essential: PG's detector only fires in hold-and-wait, so "fire both
// and hope" is racy. Each conn sets a short deadlock_timeout so the bite is fast.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"sync"
	"sync/atomic"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

func main() {
	dsn := flag.String("dsn", "", "Postgres DSN")
	mode := flag.String("mode", "ordered", "ordered | bite")
	rounds := flag.Int("rounds", 5, "contention rounds")
	flag.Parse()
	if *dsn == "" {
		die("-dsn required")
	}
	os.Exit(run(*dsn, *mode, *rounds))
}

func run(dsn, mode string, rounds int) int {
	ctx := context.Background()
	setup(ctx, dsn)

	// The barrier (force both txns into hold-and-wait) is needed ONLY for the bite:
	// opposing first-locks (1 and 2) CAN both be held at once. In ordered mode both
	// want row 1, so the second BLOCKS at its first lock — no barrier (it would never
	// open) and no deadlock (pure serialization).
	useBarrier := mode == "bite"

	var deadlocks, committed, other int64
	for range rounds {
		var lockFirst1, lockSecond1, lockFirst2, lockSecond2 int
		if mode == "ordered" {
			lockFirst1, lockSecond1 = 1, 2 // both lock A(1) then B(2) — consistent order
			lockFirst2, lockSecond2 = 1, 2
		} else {
			lockFirst1, lockSecond1 = 1, 2 // opposing: T1 A->B, T2 B->A
			lockFirst2, lockSecond2 = 2, 1
		}

		var firstHeld sync.WaitGroup
		firstHeld.Add(2)
		release := make(chan struct{})

		classifyErr := func(err error) {
			if isDeadlock(err) {
				atomic.AddInt64(&deadlocks, 1)
			} else {
				atomic.AddInt64(&other, 1)
			}
		}

		runTxn := func(first, second int) {
			c, err := pgx.Connect(ctx, dsn)
			if err != nil {
				atomic.AddInt64(&other, 1)
				firstHeld.Done()
				return
			}
			defer c.Close(ctx)
			_, _ = c.Exec(ctx, "SET deadlock_timeout = '200ms'")
			tx, err := c.Begin(ctx)
			if err != nil {
				atomic.AddInt64(&other, 1)
				firstHeld.Done()
				return
			}
			// grab FIRST lock. In bite mode this always succeeds immediately (distinct
			// rows); signal the barrier. In ordered mode the SECOND txn blocks HERE
			// until the first commits — exactly the serialization we want (no deadlock).
			if useBarrier {
				if _, err := tx.Exec(ctx, "SELECT v FROM s14_lock WHERE id=$1 FOR UPDATE", first); err != nil {
					_ = tx.Rollback(ctx)
					classifyErr(err)
					firstHeld.Done()
					return
				}
				firstHeld.Done()
				<-release // both hold their first lock → deterministic hold-and-wait
			} else {
				if _, err := tx.Exec(ctx, "SELECT v FROM s14_lock WHERE id=$1 FOR UPDATE", first); err != nil {
					_ = tx.Rollback(ctx)
					classifyErr(err)
					return
				}
			}
			// grab SECOND lock — opposing order deadlocks here (or in the UPDATE/commit).
			if _, err := tx.Exec(ctx, "SELECT v FROM s14_lock WHERE id=$1 FOR UPDATE", second); err != nil {
				_ = tx.Rollback(ctx)
				classifyErr(err)
				return
			}
			if _, err := tx.Exec(ctx, "UPDATE s14_lock SET v=v+1 WHERE id IN (1,2)"); err != nil {
				_ = tx.Rollback(ctx)
				classifyErr(err)
				return
			}
			if err := tx.Commit(ctx); err != nil {
				classifyErr(err)
				return
			}
			atomic.AddInt64(&committed, 1)
		}

		var wg sync.WaitGroup
		wg.Add(2)
		go func() { defer wg.Done(); runTxn(lockFirst1, lockSecond1) }()
		go func() { defer wg.Done(); runTxn(lockFirst2, lockSecond2) }()
		if useBarrier {
			go func() { firstHeld.Wait(); close(release) }() // open once both hold first lock
		}
		wg.Wait()
	}

	fmt.Printf(`{"mode":%q,"rounds":%d,"deadlocks":%d,"committed":%d,"other_err":%d}`+"\n",
		mode, rounds, deadlocks, committed, other)

	if mode == "ordered" {
		if other > 0 {
			fmt.Fprintf(os.Stderr, "NOTRUN: %d infra errors in the ordered run — re-run\n", other)
			return 2
		}
		if deadlocks != 0 {
			fmt.Fprintf(os.Stderr, "FAIL: consistent lock order still deadlocked %d× — the I6 ordering principle does NOT hold\n", deadlocks)
			return 1
		}
		fmt.Fprintf(os.Stderr, "PASS(ordered): %d rounds of consistent-order contention → 0 deadlocks, %d commits — the I6 ordering principle holds\n", rounds, committed)
		return 0
	}
	// bite: opposing order MUST produce at least one real deadlock (else vacuous).
	if deadlocks < 1 {
		fmt.Fprintf(os.Stderr, "NOTRUN(bite): opposing-order contention produced 0 deadlocks (race missed the hold-and-wait window?) — re-run\n")
		return 2
	}
	fmt.Fprintf(os.Stderr, "PASS(bite): opposing lock order produced %d real PG deadlock(s) (40P01) — proves consistent ordering (I6) is what prevents the deadlock\n", deadlocks)
	return 0
}

func setup(ctx context.Context, dsn string) {
	c, err := pgx.Connect(ctx, dsn)
	if err != nil {
		die("connect: %v", err)
	}
	defer c.Close(ctx)
	if _, err := c.Exec(ctx, `CREATE TABLE IF NOT EXISTS s14_lock (id int PRIMARY KEY, v int NOT NULL)`); err != nil {
		die("create table: %v", err)
	}
	if _, err := c.Exec(ctx, `INSERT INTO s14_lock (id, v) VALUES (1,0),(2,0) ON CONFLICT (id) DO UPDATE SET v=0`); err != nil {
		die("seed: %v", err)
	}
}

func isDeadlock(err error) bool {
	var pg *pgconn.PgError
	if errors.As(err, &pg) {
		return pg.Code == "40P01" // deadlock_detected
	}
	return false
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "deadlock-probe: "+format+"\n", a...)
	os.Exit(2)
}
