// services/meta-worker/cmd/relocate-drill — S13 (Inc-4) cross-shard reality
// relocation primitive: the REAL registry CAS transitions for a relocation.
//
// Relocation moves a reality's event DB from one shard to another. The registry
// flip is the crux: db_host must change ONLY via a CAS-guarded lifecycle transition
// (migrating→active) in the SAME write that sets status — so a half-done relocation
// can never leave the row both-live or status/host inconsistent. db_host is NOT the
// state column; it rides as a Payload override on the transition (the same
// AttemptStateTransition that CASes status).
//
// This harness exposes ONLY the two real transitions (everything else — seed, copy,
// content-checksum gate, decommission, fault ordering — is orchestrated by
// scripts/perf/l1-relocate.sh so the invariant logic lives in one place):
//
//	-mode to-migrating  AttemptStateTransition(active→migrating) [CAS]
//	-mode to-active     AttemptStateTransition(migrating→active) [CAS] carrying the
//	                    new db_host + db_name as Payload (set in the SAME UPDATE)
//
// Lives in the meta-worker module to reuse the resolved contracts/meta + sdks/go/metapg
// deps (the lifecycle-race / metaworker-bench trick).
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
)

type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

// relocator is a fixed system-actor UUID (actor_id is a UUID column).
const relocator = "00000000-0000-0000-0000-0000000000c2"

func main() {
	dsn := flag.String("meta-dsn", "", "meta Postgres DSN (reality_registry + lifecycle + meta_write_audit migrated)")
	transitions := flag.String("transitions", "contracts/meta/transitions.yaml", "path to transitions.yaml")
	allowlist := flag.String("allowlist", "contracts/meta/events_allowlist.yaml", "path to events_allowlist.yaml")
	reality := flag.String("reality", "", "reality_id (UUID)")
	mode := flag.String("mode", "", "to-migrating | to-active")
	dbHost := flag.String("db-host", "", "new db_host (to-active only)")
	dbName := flag.String("db-name", "", "new db_name (to-active only)")
	flag.Parse()
	if *dsn == "" || *reality == "" || *mode == "" {
		die("-meta-dsn, -reality and -mode are required")
	}
	os.Exit(run(*dsn, *transitions, *allowlist, *reality, *mode, *dbHost, *dbName))
}

func run(dsn, transitionsPath, allowlistPath, reality, mode, dbHost, dbName string) int {
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		die("pool: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		die("ping: %v", err)
	}

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

	switch mode {
	case "to-migrating":
		return transition(ctx, cfg, reality, "active", "migrating", nil)
	case "to-active":
		if dbHost == "" || dbName == "" {
			die("to-active requires -db-host and -db-name (the relocation target)")
		}
		// db_host + db_name ride as Payload on the CAS transition → set in the SAME
		// UPDATE as status, CAS-guarded on status=migrating.
		payload := map[string]any{"db_host": dbHost, "db_name": dbName}
		return transition(ctx, cfg, reality, "migrating", "active", payload)
	default:
		die("unknown mode %q", mode)
		return 2
	}
}

func transition(ctx context.Context, cfg *meta.Config, reality, from, to string, payload map[string]any) int {
	res, err := meta.AttemptStateTransition(ctx, cfg, meta.TransitionRequest{
		ResourceType: "reality",
		ResourceID:   reality,
		FromState:    from,
		ToState:      to,
		Reason:       "s13-inc4-relocation",
		Actor:        meta.Actor{Type: meta.ActorSystem, ID: relocator},
		Payload:      payload,
	})
	if err != nil {
		fmt.Printf(`{"mode":%q,"ok":false,"error":%q}`+"\n", from+"->"+to, err.Error())
		fmt.Fprintf(os.Stderr, "relocate-drill: transition %s->%s failed: %v\n", from, to, err)
		return 1
	}
	fmt.Printf(`{"mode":%q,"ok":true,"new_state":%q}`+"\n", from+"->"+to, res.NewState)
	return 0
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "relocate-drill: "+format+"\n", a...)
	os.Exit(2)
}
