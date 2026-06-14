// services/meta-worker/cmd/connpool-stress — S14 (D3) connection-pool exhaustion.
//
// S12 hit the max_connections=300 wall. This probe proves that a BOUNDED pool
// (pgxpool with MaxConns ≤ the server's max_connections) keeps a large fan-out of
// callers SAFE — they queue on the pool and all complete, the server is never
// exhausted — while the BITE (unbounded: a fresh raw connection per caller, no pool)
// blows past max_connections and the server rejects with FATAL 53300
// "too many clients already".
//
//	-mode pooled      N workers × OPS ops through a MaxConns-bounded pgxpool →
//	                  all complete, 0 connection-refused, pool drains after (recovers)
//	-mode unbounded   N concurrent RAW connections held at once (no pool) →
//	                  the server rejects the overflow with 53300 (BITE / self-saturation)
//
// Drive both against a DEDICATED throwaway PG with a low max_connections (the cap is
// not runtime-settable — must not restart the shared rig).
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
	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	dsn := flag.String("dsn", "", "Postgres DSN")
	mode := flag.String("mode", "pooled", "pooled | unbounded")
	workers := flag.Int("workers", 50, "concurrent callers (>> max_connections)")
	maxconns := flag.Int("maxconns", 10, "pgxpool MaxConns (pooled mode; <= server max_connections)")
	ops := flag.Int("ops", 20, "ops per worker (pooled mode)")
	flag.Parse()
	if *dsn == "" {
		die("-dsn required")
	}
	switch *mode {
	case "pooled":
		os.Exit(pooled(*dsn, *workers, *maxconns, *ops))
	case "unbounded":
		os.Exit(unbounded(*dsn, *workers))
	default:
		die("unknown mode %q", *mode)
	}
}

// pooled: a MaxConns-bounded pool absorbs N>>MaxConns callers by queueing. All ops
// complete, nothing is connection-refused, and the pool drains after (recovery).
func pooled(dsn string, workers, maxconns, ops int) int {
	ctx := context.Background()
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		die("parse dsn: %v", err)
	}
	cfg.MaxConns = int32(maxconns)
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		die("pool: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		die("ping: %v", err)
	}

	var done, connRefused, otherErr int64
	var wg sync.WaitGroup
	start := make(chan struct{})
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for range ops {
				_, e := pool.Exec(ctx, "SELECT 1")
				switch {
				case e == nil:
					atomic.AddInt64(&done, 1)
				case isTooManyClients(e):
					atomic.AddInt64(&connRefused, 1)
				default:
					atomic.AddInt64(&otherErr, 1)
				}
			}
		}()
	}
	close(start)
	wg.Wait()

	// recovery: the pool drained back to 0 in-use connections.
	acquired := pool.Stat().AcquiredConns()
	total := int64(workers * ops)
	fmt.Printf(`{"mode":"pooled","workers":%d,"maxconns":%d,"ops_total":%d,"completed":%d,"conn_refused":%d,"other_err":%d,"acquired_after":%d}`+"\n",
		workers, maxconns, total, done, connRefused, otherErr, acquired)

	if connRefused > 0 {
		fmt.Fprintf(os.Stderr, "FAIL: bounded pool still got %d 'too many clients' — pool did not cap server connections\n", connRefused)
		return 1
	}
	if done != total {
		fmt.Fprintf(os.Stderr, "FAIL: only %d/%d ops completed (other_err=%d) — pool did not absorb the fan-out gracefully\n", done, total, otherErr)
		return 1
	}
	if acquired != 0 {
		fmt.Fprintf(os.Stderr, "FAIL: pool left %d connections acquired after drain — no recovery\n", acquired)
		return 1
	}
	fmt.Fprintf(os.Stderr, "PASS(pooled): %d workers × %d ops all completed through a %d-conn pool; 0 connection-refused; pool drained to 0 (recovered)\n", workers, ops, maxconns)
	return 0
}

// unbounded (BITE): N raw connections opened and HELD simultaneously (no pool). Past
// the server's max_connections the overflow is rejected with FATAL 53300.
func unbounded(dsn string, workers int) int {
	ctx := context.Background()
	var ok, refused, otherErr int64
	var mu sync.Mutex
	held := make([]*pgx.Conn, 0, workers)
	var wg sync.WaitGroup
	start := make(chan struct{})
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			c, e := pgx.Connect(ctx, dsn) // raw, no pool
			switch {
			case e == nil:
				atomic.AddInt64(&ok, 1)
				mu.Lock()
				held = append(held, c) // HOLD it open so all successes overlap
				mu.Unlock()
			case isTooManyClients(e):
				atomic.AddInt64(&refused, 1)
			default:
				atomic.AddInt64(&otherErr, 1)
				fmt.Fprintf(os.Stderr, "unbounded non-53300 error: %v\n", e)
			}
		}()
	}
	close(start)
	wg.Wait()
	for _, c := range held { // release the held connections
		_ = c.Close(ctx)
	}

	fmt.Printf(`{"mode":"unbounded","workers":%d,"connected":%d,"refused_53300":%d,"other_err":%d}`+"\n",
		workers, ok, refused, otherErr)
	if refused <= 0 {
		fmt.Fprintf(os.Stderr, "NOTRUN: 0 connections were refused (server max_connections not exceeded by %d raw conns) — raise -workers / lower the server cap\n", workers)
		return 2
	}
	fmt.Fprintf(os.Stderr, "PASS(bite): %d raw connections exhausted the server — %d rejected with FATAL 53300 'too many clients'; proves the bounded pool is what prevents exhaustion\n", workers, refused)
	return 0
}

func isTooManyClients(err error) bool {
	var pg *pgconn.PgError
	if errors.As(err, &pg) {
		return pg.Code == "53300" // too_many_connections
	}
	return false
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "connpool-stress: "+format+"\n", a...)
	os.Exit(2)
}
