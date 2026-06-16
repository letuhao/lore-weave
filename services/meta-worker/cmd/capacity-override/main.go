// services/meta-worker/cmd/capacity-override — S13 (Inc-2) capacity-override I8 audit probe.
//
// L1.B capacity-override (Tier-2 break-glass, S5-D5): an admin lifts a shard's
// capacity cap for 24h. The write goes through contracts/meta.MetaWrite into
// scaling_events (event_type='override'), which lands ONE meta_write_audit row in
// the SAME TX (I8 — every meta write is audited). The 24h window is enforced by the
// scaling_events_override_expiry_within_24h CHECK at the DB.
//
// This probe drives the REAL MetaWrite path (mirrors admin-cli PgScalingEventWriter)
// against real Postgres and asserts the I8 audit + the 24h DB CHECK actually fire.
//
// Lives in the meta-worker module so it reuses the already-resolved contracts/meta +
// sdks/go/metapg deps (the metaworker-bench / lifecycle-race trick) — no new
// replace-directive module.
//
// Modes:
//
//	-mode override  Write a VALID 24h override via MetaWrite → assert scaling_events
//	                gained exactly 1 row AND meta_write_audit(table_name=scaling_events)
//	                gained exactly 1 row (I8, same write). Then attempt a 48h override
//	                → assert it is REJECTED by the 24h CHECK and nothing landed.
//	-mode bite      Insert a scaling_events row with a RAW INSERT (bypassing MetaWrite)
//	                → assert the row lands BUT meta_write_audit gains 0 rows → proves
//	                the I8 audit is produced by MetaWrite, not a DB-side trigger (so the
//	                "MetaWrite → meta_write_audit" check is non-vacuous).
package main

import (
	"context"
	"encoding/json"
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

// adminActor is a fixed admin UUID (actor_id / initiated_by are UUID-shaped).
const adminActor = "00000000-0000-0000-0000-0000000000ad"

// shardHost satisfies shard_utilization/scaling_events host conventions.
const shardHost = "pg-shard-0.internal"

func main() {
	dsn := flag.String("meta-dsn", "", "meta Postgres DSN (scaling_events + meta_write_audit migrated)")
	allowlist := flag.String("allowlist", "contracts/meta/events_allowlist.yaml", "path to events_allowlist.yaml")
	mode := flag.String("mode", "override", "override | bite")
	flag.Parse()
	if *dsn == "" {
		die("-meta-dsn required")
	}
	os.Exit(run(*dsn, *allowlist, *mode))
}

func run(dsn, allowlistPath, mode string) int {
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		die("pool: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		die("ping: %v", err)
	}

	switch mode {
	case "override":
		return override(ctx, pool, allowlistPath)
	case "bite":
		return bite(ctx, pool)
	default:
		die("unknown mode %q", mode)
		return 2
	}
}

// override drives the REAL MetaWrite override path and asserts I8 + the 24h CHECK.
func override(ctx context.Context, pool *pgxpool.Pool, allowlistPath string) int {
	allow, err := meta.LoadAllowlist(allowlistPath)
	if err != nil {
		die("load allowlist (%s): %v", allowlistPath, err)
	}
	cfg := &meta.Config{
		DB:           metapg.New(pool),
		Allowlist:    allow,
		QueryBuilder: meta.PostgresQueryBuilder{},
		Clock:        sysClock{},
		UUIDGen:      randUUID{},
		// Outbox intentionally nil: no capacity-event consumer in V1, so
		// scaling.event.recorded is dropped and the row is the SSOT (matches
		// admin-cli PgScalingEventWriter). The meta_write_audit row still lands.
	}

	seBefore := scalarInt(ctx, pool, `SELECT count(*) FROM scaling_events`)
	mwaBefore := scalarInt(ctx, pool, `SELECT count(*) FROM meta_write_audit WHERE table_name='scaling_events'`)

	// VALID override: expires exactly at created+24h (CHECK is <=, so allowed).
	created := time.Now().UTC()
	if err := writeOverride(ctx, cfg, created, created.Add(24*time.Hour)); err != nil {
		die("valid 24h override MetaWrite failed: %v", err)
	}

	seMid := scalarInt(ctx, pool, `SELECT count(*) FROM scaling_events`)
	mwaMid := scalarInt(ctx, pool, `SELECT count(*) FROM meta_write_audit WHERE table_name='scaling_events'`)

	// 48h override MUST be rejected by scaling_events_override_expiry_within_24h.
	err48 := writeOverride(ctx, cfg, created, created.Add(48*time.Hour))
	seAfter := scalarInt(ctx, pool, `SELECT count(*) FROM scaling_events`)
	mwaAfter := scalarInt(ctx, pool, `SELECT count(*) FROM meta_write_audit WHERE table_name='scaling_events'`)

	seDelta := seMid - seBefore
	mwaDelta := mwaMid - mwaBefore
	rejected48 := err48 != nil
	leaked48 := seAfter != seMid || mwaAfter != mwaMid

	fmt.Printf(`{"mode":"override","scaling_events_delta":%d,"meta_write_audit_delta":%d,"over_24h_rejected":%t,"over_24h_leaked":%t}`+"\n",
		seDelta, mwaDelta, rejected48, leaked48)

	if seDelta != 1 || mwaDelta != 1 {
		fmt.Fprintf(os.Stderr, "FAIL: I8 — valid override should add exactly 1 scaling_events row AND 1 meta_write_audit row (same write); got se=%d mwa=%d\n", seDelta, mwaDelta)
		return 1
	}
	if !rejected48 {
		fmt.Fprintf(os.Stderr, "FAIL: 48h override was NOT rejected — the scaling_events_override_expiry_within_24h CHECK is not enforcing the window\n")
		return 1
	}
	if leaked48 {
		fmt.Fprintf(os.Stderr, "FAIL: 48h override left a row behind despite the error (se/mwa moved after the rejected write)\n")
		return 1
	}
	fmt.Fprintf(os.Stderr, "PASS: valid 24h override → 1 scaling_events + 1 meta_write_audit (I8 same write); 48h override rejected by the 24h CHECK, nothing leaked\n")
	return 0
}

// writeOverride mirrors admin-cli PgScalingEventWriter.WriteOverride: one
// event_type='override' scaling_events INSERT via MetaWrite (audited in the same TX).
func writeOverride(ctx context.Context, cfg *meta.Config, created, expires time.Time) error {
	initiatedBy, err := uuid.Parse(adminActor)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(map[string]any{"hours": int(expires.Sub(created).Hours())})
	if err != nil {
		return err
	}
	intent := meta.MetaWriteIntent{
		Table:     "scaling_events",
		Operation: meta.OpInsert,
		PK:        map[string]any{"scaling_event_id": cfg.UUIDGen.New()},
		NewValues: map[string]any{
			"event_type":          "override",
			"shard_host":          shardHost,
			"initiated_by":        initiatedBy,
			"initiator_type":      "admin",
			"override_expires_at": expires,
			"payload":             payload,
			"reason":              "s13-inc2-capacity-override-probe",
			"created_at":          created,
		},
		Actor:  meta.Actor{Type: meta.ActorAdmin, ID: adminActor},
		Reason: "s13-inc2-capacity-override-probe",
	}
	_, err = meta.MetaWrite(ctx, cfg, intent)
	return err
}

// bite: a RAW INSERT into scaling_events bypassing MetaWrite. The row lands but NO
// meta_write_audit row appears → proves the I8 audit is produced by MetaWrite (the
// override-mode check is non-vacuous: nothing else writes the audit for us).
func bite(ctx context.Context, pool *pgxpool.Pool) int {
	mwaBefore := scalarInt(ctx, pool, `SELECT count(*) FROM meta_write_audit WHERE table_name='scaling_events'`)
	seBefore := scalarInt(ctx, pool, `SELECT count(*) FROM scaling_events`)

	created := time.Now().UTC()
	_, err := pool.Exec(ctx, `INSERT INTO scaling_events
		(scaling_event_id, event_type, shard_host, initiated_by, initiator_type,
		 override_expires_at, payload, reason, created_at)
		VALUES ($1,'override',$2,$3,'admin',$4,'{}'::jsonb,'s13-inc2-bite-raw-insert',$5)`,
		uuid.New(), shardHost, adminActor, created.Add(24*time.Hour), created)
	if err != nil {
		die("bite raw INSERT failed: %v", err)
	}

	mwaAfter := scalarInt(ctx, pool, `SELECT count(*) FROM meta_write_audit WHERE table_name='scaling_events'`)
	seAfter := scalarInt(ctx, pool, `SELECT count(*) FROM scaling_events`)
	seDelta := seAfter - seBefore
	mwaDelta := mwaAfter - mwaBefore

	fmt.Printf(`{"mode":"bite","scaling_events_delta":%d,"meta_write_audit_delta":%d}`+"\n", seDelta, mwaDelta)

	if seDelta != 1 {
		fmt.Fprintf(os.Stderr, "FAIL(bite): raw INSERT did not land exactly 1 scaling_events row (got %d) — bite setup broken\n", seDelta)
		return 1
	}
	if mwaDelta != 0 {
		fmt.Fprintf(os.Stderr, "FAIL(bite): a write bypassing MetaWrite still produced %d meta_write_audit row(s) — the I8 check is VACUOUS (a trigger audits regardless)\n", mwaDelta)
		return 1
	}
	fmt.Fprintf(os.Stderr, "PASS(bite): a scaling_events write that bypasses MetaWrite leaves 0 meta_write_audit rows — proving I8 audit is produced BY MetaWrite (override-mode check is non-vacuous)\n")
	return 0
}

func scalarInt(ctx context.Context, pool *pgxpool.Pool, q string, args ...any) int64 {
	var n int64
	_ = pool.QueryRow(ctx, q, args...).Scan(&n)
	return n
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "capacity-override: "+format+"\n", a...)
	os.Exit(2)
}
