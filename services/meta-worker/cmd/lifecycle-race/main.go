// services/meta-worker/cmd/lifecycle-race — S13 (Inc-1) I9 lifecycle CAS race probe.
//
// I9: every reality_registry.status change goes through AttemptStateTransition,
// which is MetaWrite with ExpectedBefore={status:FromState} — a compare-and-swap.
// S9 model-checked this logic; S13 proves it at RUNTIME against real Postgres
// under concurrent racers.
//
// Lives in the meta-worker module so it reuses the already-resolved contracts/meta
// + sdks/go/metapg deps (the metaworker-bench trick), no new replace-directive
// module.
//
// Modes:
//
//	-mode race   N goroutines call the REAL AttemptStateTransition(active→migrating)
//	             on ONE reality → assert EXACTLY ONE wins, N-1 get
//	             ErrConcurrentStateTransition, and lifecycle_transition_audit has
//	             exactly one succeeded=true row.
//	-mode bite   N goroutines do a RAW `UPDATE … SET status='migrating'` WITHOUT the
//	             CAS WHERE-guard (bypassing AttemptStateTransition) → MANY "win" →
//	             proves the CAS is what limits the transition to a single winner.
//	             (You cannot feed a stale expected to the API — the guard derives
//	             from req.FromState — so the bite must bypass the API entirely.)
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
)

type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

func main() {
	dsn := flag.String("meta-dsn", "", "meta Postgres DSN (reality_registry + lifecycle_transition_audit + meta_write_audit migrated)")
	transitions := flag.String("transitions", "contracts/meta/transitions.yaml", "path to transitions.yaml")
	allowlist := flag.String("allowlist", "contracts/meta/events_allowlist.yaml", "path to events_allowlist.yaml")
	racers := flag.Int("racers", 16, "concurrent racers")
	mode := flag.String("mode", "race", "race | bite")
	flag.Parse()
	if *dsn == "" {
		die("-meta-dsn required")
	}
	os.Exit(run(*dsn, *transitions, *allowlist, *racers, *mode))
}

func run(dsn, transitionsPath, allowlistPath string, racers int, mode string) int {
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		die("pool: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		die("ping: %v", err)
	}

	// Fresh reality in 'active' (setup bypasses lifecycle — we test the transition,
	// not provisioning).
	rid := uuid.New().String()
	if _, err := pool.Exec(ctx, `INSERT INTO reality_registry
		(reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
		VALUES ($1,'pg-shard-0.internal','l1_shard','active','en',10,10,20,5)`, rid); err != nil {
		die("seed reality: %v", err)
	}

	switch mode {
	case "race":
		return race(ctx, pool, transitionsPath, allowlistPath, racers, rid)
	case "bite":
		return bite(ctx, pool, racers, rid)
	default:
		die("unknown mode %q", mode)
		return 2
	}
}

// race: N racers via the REAL AttemptStateTransition. Exactly one must win.
func race(ctx context.Context, pool *pgxpool.Pool, transitionsPath, allowlistPath string, racers int, rid string) int {
	graph, err := meta.LoadTransitions(transitionsPath)
	if err != nil {
		die("load transitions (%s): %v", transitionsPath, err)
	}
	allow, err := meta.LoadAllowlist(allowlistPath)
	if err != nil {
		die("load allowlist (%s): %v", allowlistPath, err)
	}
	cfg := &meta.Config{
		DB:           metapg.New(pool),
		Allowlist:    allow,
		Transitions:  graph,
		QueryBuilder: meta.PostgresQueryBuilder{},
		Clock:        sysClock{},
		UUIDGen:      randUUID{},
	}

	var wins, conflicts, other int64
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < racers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start // release all racers together to maximise the race
			_, err := meta.AttemptStateTransition(ctx, cfg, meta.TransitionRequest{
				ResourceType: "reality", ResourceID: rid,
				FromState: "active", ToState: "migrating",
				// actor_id is a UUID column — system actors carry a fixed UUID.
				Reason: "s13-lifecycle-race", Actor: meta.Actor{Type: meta.ActorSystem, ID: "00000000-0000-0000-0000-0000000000aa"},
			})
			switch {
			case err == nil:
				atomic.AddInt64(&wins, 1)
			case isConcurrent(err):
				atomic.AddInt64(&conflicts, 1)
			default:
				atomic.AddInt64(&other, 1)
				fmt.Fprintf(os.Stderr, "racer non-CAS error: %v\n", err)
			}
		}()
	}
	close(start)
	wg.Wait()

	// Cross-check against the audit ledger: exactly one succeeded row.
	auditWins := scalarInt(ctx, pool, `SELECT count(*) FROM lifecycle_transition_audit WHERE reality_id=$1 AND to_status='migrating' AND succeeded=true`, rid)
	finalStatus := scalarStr(ctx, pool, `SELECT status FROM reality_registry WHERE reality_id=$1`, rid)

	fmt.Printf(`{"mode":"race","racers":%d,"wins":%d,"conflicts":%d,"other":%d,"audit_success_rows":%d,"final_status":%q}`+"\n",
		racers, wins, conflicts, other, auditWins, finalStatus)

	if other > 0 {
		fmt.Fprintf(os.Stderr, "NOTRUN: %d non-CAS errors (infra) — re-run\n", other)
		return 2
	}
	if wins != 1 || conflicts != int64(racers-1) || auditWins != 1 || finalStatus != "migrating" {
		fmt.Fprintf(os.Stderr, "FAIL: I9 CAS broken — expected exactly 1 win + %d conflicts + 1 audit row + status=migrating\n", racers-1)
		return 1
	}
	fmt.Fprintf(os.Stderr, "PASS: %d racers → exactly 1 won the active→migrating transition (CAS); %d got concurrent_modification; 1 audit success row\n", racers, conflicts)
	return 0
}

// bite: N racers do a RAW status UPDATE with NO CAS guard → many "win".
func bite(ctx context.Context, pool *pgxpool.Pool, racers int, rid string) int {
	var wins int64
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < racers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			// NO `AND status='active'` guard — this is the missing-CAS bug.
			tag, err := pool.Exec(ctx, `UPDATE reality_registry SET status='migrating' WHERE reality_id=$1`, rid)
			if err == nil && tag.RowsAffected() >= 1 {
				atomic.AddInt64(&wins, 1)
			}
		}()
	}
	close(start)
	wg.Wait()
	fmt.Printf(`{"mode":"bite","racers":%d,"raw_wins":%d}`+"\n", racers, wins)
	if wins > 1 {
		fmt.Fprintf(os.Stderr, "PASS(bite): %d racers ALL won the single transition via raw UPDATE (no CAS) — the CAS guard is what holds correctness\n", wins)
		return 0
	}
	fmt.Fprintf(os.Stderr, "FAIL(bite): raw no-CAS UPDATE produced only %d winner(s) — bite is vacuous\n", wins)
	return 1
}

func isConcurrent(err error) bool {
	// ErrConcurrentStateTransition is the CAS-mismatch sentinel (status changed
	// under us — another racer won).
	return errors.Is(err, meta.ErrConcurrentStateTransition)
}

func scalarInt(ctx context.Context, pool *pgxpool.Pool, q string, args ...any) int64 {
	var n int64
	_ = pool.QueryRow(ctx, q, args...).Scan(&n)
	return n
}

func scalarStr(ctx context.Context, pool *pgxpool.Pool, q string, args ...any) string {
	var s string
	_ = pool.QueryRow(ctx, q, args...).Scan(&s)
	return s
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "lifecycle-race: "+format+"\n", a...)
	os.Exit(2)
}
