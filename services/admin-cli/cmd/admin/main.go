// admin — single-binary admin CLI for the LoreWeave platform.
//
// LOCKED Q-IDs honored (RAID cycle 36):
//   - Q-L7A-1: registry loaded from contracts/admin/registry/*.yaml,
//     auto-merged by framework.LoadRegistry.
//   - Q-L7A-2: ONE binary; sub-commands dispatched as `<domain> <verb>`.
//
// Usage:
//
//	admin                       — show help (all domains + commands)
//	admin --list                — JSON dump of registry (CI consumption)
//	admin <domain>              — list verbs under a domain
//	admin <domain> <verb> --help — show parameters
//	admin <domain> <verb> [params...] --token <jwt> [--reason …] [--dry-run | --confirm] [--second-actor …]
//
// Distribution: a single Go binary (Q-L7A-2). All ~30 commands ship in one
// build; the registry YAML decides which sub-commands are visible.
//
// Audit: every invocation is audited via framework.Run() → admin_action_audit
// (cycle 4 L1.A-3 table; allowlist confirms events: []).
//
// AV note: this binary links AWS-KMS + AES-GCM crypto-shred (PII erasure), which
// some desktop AVs (Bitdefender Gen:Variant.Tedy.*) flag as a FALSE POSITIVE on
// unsigned static Go binaries. It is not malware — see docs/SECURITY-FALSEPOSITIVE.md.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/contracts/pii"
	"github.com/loreweave/foundation/sdks/go/metaoutbox"
	"github.com/loreweave/foundation/sdks/go/metapg"
	"github.com/loreweave/foundation/sdks/go/piikms"
	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
	"github.com/loreweave/foundation/services/admin-cli/internal/commands"
	"github.com/loreweave/foundation/services/admin-cli/internal/commands/miniofetch"
	"github.com/loreweave/foundation/services/admin-cli/internal/framework"
)

// sysClock / randUUID are the production Clock/UUIDGen for MetaWrite.
type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

// buildAuditSink selects the audit Sink. With META_DATABASE_URL set it persists
// to admin_action_audit via MetaWrite (metapg + Slice-A scrubber); without it,
// the dev stdout/in-memory sink. Guards: dev tokens are incompatible with a
// real audit DB (non-UUID subjects break the UUID actor_id), and running a
// destructive command unaudited (no DB) requires an explicit opt-in.
func buildAuditSink(stderr *os.File, impact framework.ImpactClass, dryRun, confirm bool) (audit_emitter.Sink, func(), error) {
	_ = confirm // retained for signature symmetry; the guard keys on !dryRun (below)
	dsn := os.Getenv("META_DATABASE_URL")
	destructive := impact == framework.Tier1Destructive || impact == framework.Tier2Griefing

	if dsn == "" {
		// Any REAL (non-dry-run) destructive command must be audited. Keying on
		// !dryRun (NOT confirm) closes the tier-2 hole: tier-2-griefing has no
		// DryRunRequired gate, so a flagless tier-2 run would otherwise escape.
		if destructive && !dryRun && os.Getenv("ADMIN_CLI_ALLOW_UNAUDITED") != "1" {
			return nil, nil, fmt.Errorf("META_DATABASE_URL unset: refusing to run destructive command unaudited (set ADMIN_CLI_ALLOW_UNAUDITED=1 to override for local dev)")
		}
		mem := audit_emitter.NewMemorySink()
		return stdoutSink{stdout: stderr, mem: mem}, func() {}, nil
	}

	if os.Getenv("ADMIN_CLI_ALLOW_DEV_TOKENS") == "1" {
		return nil, nil, fmt.Errorf("ADMIN_CLI_ALLOW_DEV_TOKENS=1 is incompatible with META_DATABASE_URL (a dev-token non-UUID subject cannot be the admin_action_audit.actor_id); unset one")
	}
	allowPath := os.Getenv("META_ALLOWLIST_PATH")
	if allowPath == "" {
		return nil, nil, fmt.Errorf("META_ALLOWLIST_PATH is required when META_DATABASE_URL is set (path to events_allowlist.yaml)")
	}
	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return nil, nil, fmt.Errorf("load allowlist: %w", err)
	}
	// Fail-fast: the audit path writes admin_action_audit AND its same-TX
	// meta_write_audit row. A misconfigured allowlist missing either would
	// otherwise fail-closed only at the first command's audit write.
	for _, tbl := range []string{"admin_action_audit", "meta_write_audit"} {
		if !allow.AllowsTable(tbl) {
			return nil, nil, fmt.Errorf("allowlist %s missing required table %q (audit path needs it)", allowPath, tbl)
		}
	}
	// NO Outbox here (P2/101 /review-impl #1): the audit Sink writes ONLY
	// admin_action_audit, which is allowlisted events: [] (emits nothing). Wiring
	// cfg.Outbox + probing meta_outbox here would be dead weight that needlessly
	// couples EVERY admin-cli command to migration 030. The meta-outbox emit path
	// lives where events actually emit — the erasure handler (buildErasureHandler).
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, nil, fmt.Errorf("meta DB connect: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{}, Scrubber: meta.NewRegexScrubber(nil),
	}
	return audit_emitter.NewMetaWriteSink(cfg), pool.Close, nil
}

// buildMetaOutbox constructs the production meta.OutboxAppender (P2/101) from
// the allowlist's xreality_topic bindings, so MetaWrite emits allowlisted events
// into the meta_outbox table (drained by meta-outbox-relay). Shared by the
// audit-sink + erasure Config builders. A malformed xreality mapping fails fast.
func buildMetaOutbox(allowPath string) (meta.OutboxAppender, error) {
	topics, err := meta.LoadXRealityTopics(allowPath)
	if err != nil {
		return nil, fmt.Errorf("load xreality topics: %w", err)
	}
	return metaoutbox.New(topics), nil
}

// probeMetaOutbox fails fast at startup if the meta_outbox table is absent
// (P2/101 /review-impl #1). Once cfg.Outbox is wired, a missing meta_outbox
// makes EVERY allowlisted MetaWrite roll back (the outbox INSERT shares the
// write TX) — which would otherwise surface mid-erasure-flow as "relation
// meta_outbox does not exist" instead of at deploy. Mirrors buildAuditSink's
// allow-table fail-fast. Cheap: a single to_regclass lookup.
func probeMetaOutbox(ctx context.Context, pool *pgxpool.Pool) error {
	var reg *string
	if err := pool.QueryRow(ctx, `SELECT to_regclass('meta_outbox')::text`).Scan(&reg); err != nil {
		return fmt.Errorf("probe meta_outbox: %w", err)
	}
	if reg == nil {
		return fmt.Errorf("meta_outbox table missing — apply migrations/meta/030_meta_outbox.up.sql before running with Outbox wired (P2/101)")
	}
	return nil
}

// buildErasureHandler wires `erasure user-erasure` to the full PII SDK +
// MetaWrite consent path (076 Slice C). It owns its OWN meta pool — isolated
// from buildAuditSink's pool so the security-critical audit guards stay
// untouched; both pools are short-lived for a single CLI invocation. Returns a
// no-op closer (never nil) so the caller can always defer it. On a hard wiring
// error it returns a nil handler + the error; the caller logs and the registry's
// NotWired handler refuses the command.
//
// The PII SDK is built PER-INVOCATION inside the closure so meta_read_audit gets
// the LIVE admin subject (inv.Actor) as actor_id and the enum-valid "admin" as
// actor_type (migration-014 CHECK) — never the doc's suggested "admin-cli",
// which would fail the actor_type CHECK after the KEK is already shredded.
func buildErasureHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil // no DB → leave NotWired (dispatcher refuses real runs)
	}
	allowPath := os.Getenv("META_ALLOWLIST_PATH")
	if allowPath == "" {
		return nil, noop, fmt.Errorf("META_ALLOWLIST_PATH required for erasure consent-revoke")
	}
	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return nil, noop, fmt.Errorf("load allowlist: %w", err)
	}
	// Fail-fast: step 7 writes user_consent_ledger + step 3's crypto-shred writes
	// pii_kek, both via MetaWrite (P2/113). A missing allowlist row would
	// otherwise fail mid-erasure (ErrTableNotAllowlisted) instead of at startup.
	for _, tbl := range []string{"user_consent_ledger", "pii_kek"} {
		if !allow.AllowsTable(tbl) {
			return nil, noop, fmt.Errorf("allowlist %s missing %q (erasure needs it)", allowPath, tbl)
		}
	}
	// Outbox (P2/101): wire the meta-outbox appender so step 7's
	// user_consent_ledger UPDATE emits user.consent.revoked into meta_outbox
	// (the relay drains it). Before 101 this was Outbox=nil → the event was
	// silently dropped (revoked_at was the only SSOT). Fail-fast before the pool.
	outbox, err := buildMetaOutbox(allowPath)
	if err != nil {
		return nil, noop, err
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("erasure meta DB connect: %w", err)
	}
	if err := probeMetaOutbox(context.Background(), pool); err != nil {
		pool.Close()
		return nil, noop, err
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{}, Scrubber: meta.NewRegexScrubber(nil),
		Outbox: outbox,
	}
	// Real AWS KMS (KMS_ENDPOINT overrides BaseEndpoint for LocalStack).
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = "us-east-1"
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(context.Background(), awsconfig.WithRegion(region))
	if err != nil {
		pool.Close()
		return nil, noop, fmt.Errorf("aws config: %w", err)
	}
	endpoint := os.Getenv("KMS_ENDPOINT")
	kmsClient := awskms.NewFromConfig(awsCfg, func(o *awskms.Options) {
		if endpoint != "" {
			o.BaseEndpoint = &endpoint
		}
	})

	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		sdk, err := pii.NewSDK(pii.Config{
			KMS:         piikms.NewAWSKMSClient(kmsClient),
			DB:          piikms.NewPgPIIReader(pool),
			KEKManager:  piikms.NewPgKEKManager(pool, kmsClient, 30, cfg, inv.Actor),
			AuditWriter: piikms.NewPgReadAuditWriter(pool),
			ActorID:     inv.Actor,               // live admin subject (meta_read_audit.actor_id is TEXT)
			ActorType:   string(meta.ActorAdmin), // enum-valid "admin" (migration-014); typed const, NOT a magic "admin-cli"
		})
		if err != nil {
			return "", fmt.Errorf("build PII SDK: %w", err)
		}
		uid, err := uuid.Parse(inv.Params["user_ref_id"])
		if err != nil {
			return "", fmt.Errorf("invalid user_ref_id %q: %w", inv.Params["user_ref_id"], err)
		}
		req := commands.ErasureRequest{
			UserRefID:  uid,
			TicketID:   inv.Params["ticket_id"],
			Reason:     inv.Reason,
			LegalBasis: inv.Params["legal_basis"],
			DryRun:     inv.DryRun,
		}
		reader := piikms.NewPgPIIReader(pool)
		deps := commands.ErasureDeps{
			Eraser:  sdk,
			Consent: commands.NewPgConsentRevoker(pool, cfg, inv.Actor, time.Now),
			Balance: commands.NewPgBalanceReader(pool),
			// Existence guard: refuse to shred a non-existent user_ref_id.
			Existence: commands.ExistenceCheckerFunc(func(c context.Context, u uuid.UUID) (bool, error) {
				if _, rerr := reader.ReadPIIRow(c, u); rerr != nil {
					if errors.Is(rerr, meta.ErrPIINotFound) {
						return false, nil
					}
					return false, rerr
				}
				return true, nil
			}),
			Clock: time.Now,
		}
		return commands.RunUserErasure(ctx, req, deps)
	}
	return h, pool.Close, nil
}

// buildRealityStatsHandler wires the read-only `reality stats` command (073) to
// a reality_registry SELECT. Owns its own meta pool (read-only; no allowlist /
// scrubber / KMS needed). Returns a no-op closer (never nil); without
// META_DATABASE_URL it leaves the command NotWired.
func buildRealityStatsHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("reality-stats meta DB connect: %w", err)
	}
	reader := commands.NewPgRealityStatsReader(pool)
	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		rid, err := uuid.Parse(inv.Params["reality_id"])
		if err != nil {
			return "", fmt.Errorf("invalid reality_id %q: %w", inv.Params["reality_id"], err)
		}
		return commands.RunRealityStats(ctx, rid, reader)
	}
	return h, pool.Close, nil
}

// buildMigrationStatusHandler wires the read-only `migration status` command
// (073) to a single-meta-table aggregation read of instance_schema_migrations
// (the orchestrator's central per-reality migration ledger). Own read-only pool.
func buildMigrationStatusHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("migration-status meta DB connect: %w", err)
	}
	reader := commands.NewPgMigrationStatusReader(pool)
	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		return commands.RunMigrationStatus(ctx, inv.Params["scope"], reader)
	}
	return h, pool.Close, nil
}

// buildShardDSN builds a per-reality DB DSN from the SHARD_DB_* env + the
// reality's resolved host/name. Kept inline so admin-cli stays self-contained
// (no publisher dep); mirrors the shard DSN config publisher/meta-worker use.
// SHARD_DB_HOST_OVERRIDE routes every reality to a local host for dev.
func buildShardDSN(host, dbname string) (string, error) {
	user := os.Getenv("SHARD_DB_USER")
	pass := os.Getenv("SHARD_DB_PASSWORD")
	if user == "" || pass == "" {
		return "", fmt.Errorf("SHARD_DB_USER + SHARD_DB_PASSWORD required for per-reality reads")
	}
	if ov := os.Getenv("SHARD_DB_HOST_OVERRIDE"); ov != "" {
		host = ov
	}
	port := os.Getenv("SHARD_DB_PORT")
	if port == "" {
		port = "5432"
	}
	sslmode := os.Getenv("SHARD_DB_SSLMODE")
	if sslmode == "" {
		sslmode = "require"
	}
	return fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=%s", user, pass, host, port, dbname, sslmode), nil
}

// perRealityDSN resolves a reality's per-reality DB DSN: look up db_host/db_name
// from reality_registry (meta pool) → build the shard DSN. ErrRealityNotFound on
// a missing reality.
func perRealityDSN(ctx context.Context, metaPool *pgxpool.Pool, realityID uuid.UUID) (string, error) {
	var host, name string
	err := metaPool.QueryRow(ctx,
		`SELECT db_host, db_name FROM reality_registry WHERE reality_id = $1`, realityID).Scan(&host, &name)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", commands.ErrRealityNotFound
		}
		return "", fmt.Errorf("resolve reality %s DSN: %w", realityID, err)
	}
	return buildShardDSN(host, name)
}

// perRealityPool resolves a reality's per-reality DB pool. The caller closes it
// (per-invocation for a CLI command).
func perRealityPool(ctx context.Context, metaPool *pgxpool.Pool, realityID uuid.UUID) (*pgxpool.Pool, error) {
	dsn, err := perRealityDSN(ctx, metaPool, realityID)
	if err != nil {
		return nil, err
	}
	return pgxpool.New(ctx, dsn)
}

// buildArchiveListHandler wires the read-only `archive list` command (073) to a
// PER-REALITY archive_state SELECT. Owns the meta pool (DSN resolution); opens
// the reality's per-reality pool PER-INVOCATION (a CLI read). NotWired without
// META_DATABASE_URL; per-reality reads also need the SHARD_DB_* env at run time.
func buildArchiveListHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	metaPool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("archive-list meta DB connect: %w", err)
	}
	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		rid, err := uuid.Parse(inv.Params["reality_id"])
		if err != nil {
			return "", fmt.Errorf("invalid reality_id %q: %w", inv.Params["reality_id"], err)
		}
		rpool, err := perRealityPool(ctx, metaPool, rid)
		if err != nil {
			return "", err
		}
		defer rpool.Close()
		return commands.RunArchiveList(ctx, rid, commands.NewPgArchiveListReader(rpool))
	}
	return h, metaPool.Close, nil
}

// buildProjectionDriftCheckHandler wires the read-only `projection drift-check`
// command (073) to a FLEET-WIDE read of projection_drift_state (the registry entry
// has no reality_id → all realities; D1). Owns the meta pool (reality enumeration);
// the reader opens each reality's shard pool per-read via buildShardDSN. NotWired
// without META_DATABASE_URL; per-reality reads also need SHARD_DB_* at run time.
func buildProjectionDriftCheckHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	metaPool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("projection-drift-check meta DB connect: %w", err)
	}
	reader := commands.NewPgProjectionDriftReader(metaPool, buildShardDSN)
	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		sampleSize := 100 // registry default
		if raw := strings.TrimSpace(inv.Params["sample_size"]); raw != "" {
			n, perr := strconv.Atoi(raw)
			if perr != nil {
				return "", fmt.Errorf("invalid --sample_size %q: %w", raw, perr)
			}
			sampleSize = n
		}
		return commands.RunProjectionDriftCheck(ctx, inv.Params["projection_name"], sampleSize, reader)
	}
	return h, metaPool.Close, nil
}

// buildArchiveFetchHandler wires the read-only `archive fetch` command (073): resolve
// the object key from the per-reality archive_state manifest, then GET the blob from
// the lw-event-archive MinIO bucket + verify the LWP1 header. Owns the meta pool (DSN
// resolution) + a minio fetcher (admin-cli's own wrapper; D4). NotWired without
// META_DATABASE_URL; the blob fetch also needs MINIO_* env. A MinIO wiring error
// leaves the command NotWired (the meta pool still closes).
func buildArchiveFetchHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	metaPool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("archive-fetch meta DB connect: %w", err)
	}
	ep, ak, sk := os.Getenv("MINIO_ENDPOINT"), os.Getenv("MINIO_ACCESS_KEY"), os.Getenv("MINIO_SECRET_KEY")
	if ep == "" || ak == "" || sk == "" {
		metaPool.Close()
		return nil, noop, fmt.Errorf("archive fetch needs MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY")
	}
	fetcher, err := miniofetch.New(context.Background(), miniofetch.Config{
		Endpoint: ep, AccessKey: ak, SecretKey: sk, UseSSL: os.Getenv("MINIO_USE_SSL") == "true",
	})
	if err != nil {
		metaPool.Close()
		return nil, noop, fmt.Errorf("archive-fetch minio connect: %w", err)
	}
	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		rid, err := uuid.Parse(inv.Params["reality_id"])
		if err != nil {
			return "", fmt.Errorf("invalid reality_id %q: %w", inv.Params["reality_id"], err)
		}
		rpool, err := perRealityPool(ctx, metaPool, rid)
		if err != nil {
			return "", err
		}
		defer rpool.Close()
		return commands.RunArchiveFetch(ctx, rid, inv.Params["month"], inv.Params["out_path"], inv.DryRun,
			commands.NewPgArchiveMetaReader(rpool), fetcher)
	}
	return h, metaPool.Close, nil
}

// buildCapacityOverrideHandler wires `reality capacity-override` (073) to a
// scaling_events INSERT via MetaWrite (Tier-2 griefing; 24h auto-expire). Owns
// its OWN meta pool + allowlist (write path needs the allowlist + scrubber),
// isolated from buildAuditSink's pool. Outbox is nil: scaling_events emits
// scaling.event.recorded but no V1 consumer reads it (mirrors PgConsentRevoker).
// NotWired without META_DATABASE_URL; dev tokens are rejected on the audited path.
func buildCapacityOverrideHandler() (framework.Handler, func(), error) {
	noop := func() {}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil // no DB → leave NotWired (dispatcher refuses real runs)
	}
	if os.Getenv("ADMIN_CLI_ALLOW_DEV_TOKENS") == "1" {
		return nil, noop, fmt.Errorf("ADMIN_CLI_ALLOW_DEV_TOKENS=1 is incompatible with META_DATABASE_URL (a dev-token non-UUID subject cannot be scaling_events.initiated_by)")
	}
	allowPath := os.Getenv("META_ALLOWLIST_PATH")
	if allowPath == "" {
		return nil, noop, fmt.Errorf("META_ALLOWLIST_PATH required for capacity-override (scaling_events write)")
	}
	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return nil, noop, fmt.Errorf("load allowlist: %w", err)
	}
	if !allow.AllowsTable("scaling_events") {
		return nil, noop, fmt.Errorf("allowlist %s missing scaling_events (capacity-override needs it)", allowPath)
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("capacity-override meta DB connect: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{}, Scrubber: meta.NewRegexScrubber(nil),
	}
	writer := commands.NewPgScalingEventWriter(cfg)
	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		hours, err := strconv.Atoi(strings.TrimSpace(inv.Params["hours"]))
		if err != nil {
			return "", fmt.Errorf("invalid --hours %q: %w", inv.Params["hours"], err)
		}
		req := commands.CapacityOverrideRequest{
			ShardHost: inv.Params["shard_host"],
			Reason:    inv.Reason,
			Hours:     hours,
			Actor:     inv.Actor,
			DryRun:    inv.DryRun,
		}
		return commands.RunCapacityOverride(ctx, req, writer, time.Now)
	}
	return h, pool.Close, nil
}

// enableUnprovenRebuildEnv gates the Tier-1 destructive rebuild commands
// (rebuild-projection + catastrophic-rebuild). Their worker (the world-service
// `rebuilder`) is the FIRST live projection-apply path and is NOT yet validated
// against real events by the L3.E/F integrity checker — so wiring a catastrophic
// recovery tool to it is unproven. Until L3.E/F lands the commands stay fail-
// closed NotWired unless an operator consciously sets this to "1".
// See docs/plans/2026-06-03-073-destructive-admin-commands.md + DEFERRED.md.
const enableUnprovenRebuildEnv = "ADMIN_CLI_ENABLE_UNPROVEN_REBUILD"

// defaultTransitionsPath discovers contracts/meta/transitions.yaml (the reality
// state-machine graph AttemptStateTransition needs), overridable via
// META_TRANSITIONS_PATH.
func defaultTransitionsPath() string {
	if p := os.Getenv("META_TRANSITIONS_PATH"); p != "" {
		return p
	}
	for _, c := range []string{
		"contracts/meta/transitions.yaml",
		"../../contracts/meta/transitions.yaml",
		"../../../contracts/meta/transitions.yaml",
	} {
		if abs, err := filepath.Abs(c); err == nil {
			if _, serr := os.Stat(abs); serr == nil {
				return abs
			}
		}
	}
	return "contracts/meta/transitions.yaml"
}

// buildRebuildProjectionHandler wires `reality rebuild-projection` (073, L3.G) —
// Tier-1 destructive freeze-truncate-rebuild-thaw. GATED: registered only when
// enableUnprovenRebuildEnv=1 (else returns a nil handler → the command stays
// fail-closed NotWired). Owns the meta pool (lifecycle gate + DSN resolution);
// the per-reality truncator pool + rebuilder subprocess DSN are resolved PER
// INVOCATION inside the closure (reality_id is a runtime param).
func buildRebuildProjectionHandler() (framework.Handler, func(), error) {
	noop := func() {}
	if os.Getenv(enableUnprovenRebuildEnv) != "1" {
		return nil, noop, nil // gated off → leave NotWired (fail-closed)
	}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	if os.Getenv("ADMIN_CLI_ALLOW_DEV_TOKENS") == "1" {
		return nil, noop, fmt.Errorf("ADMIN_CLI_ALLOW_DEV_TOKENS=1 is incompatible with META_DATABASE_URL (a dev-token non-UUID subject cannot be lifecycle_transition_audit.actor_id)")
	}
	allowPath := os.Getenv("META_ALLOWLIST_PATH")
	if allowPath == "" {
		return nil, noop, fmt.Errorf("META_ALLOWLIST_PATH required for rebuild-projection (reality_registry state transition)")
	}
	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return nil, noop, fmt.Errorf("load allowlist: %w", err)
	}
	if !allow.AllowsTable("reality_registry") {
		return nil, noop, fmt.Errorf("allowlist %s missing reality_registry (freeze/thaw needs it)", allowPath)
	}
	graph, err := meta.LoadTransitions(defaultTransitionsPath())
	if err != nil {
		return nil, noop, fmt.Errorf("load transitions graph: %w", err)
	}
	metaPool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("rebuild-projection meta DB connect: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(metaPool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{}, Scrubber: meta.NewRegexScrubber(nil),
		Transitions: graph,
	}
	lifecycle := commands.NewPgLifecycleGate(cfg)
	binPath := os.Getenv("REBUILDER_BIN_PATH")
	if binPath == "" {
		binPath = "rebuilder"
	}

	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		rid, err := uuid.Parse(inv.Params["reality_id"])
		if err != nil {
			return "", fmt.Errorf("invalid reality_id %q: %w", inv.Params["reality_id"], err)
		}
		// Dry-run needs no shard wiring (the orchestrator short-circuits).
		if inv.DryRun {
			return commands.RunRebuildProjection(ctx, commands.RebuildProjectionRequest{
				RealityID: rid, ProjectionName: inv.Params["projection_name"],
				Actor: inv.Actor, Reason: inv.Reason, DryRun: true,
			}, commands.RebuildProjectionDeps{})
		}
		rdsn, err := perRealityDSN(ctx, metaPool, rid)
		if err != nil {
			return "", err
		}
		rpool, err := pgxpool.New(ctx, rdsn)
		if err != nil {
			return "", fmt.Errorf("rebuild-projection per-reality DB connect: %w", err)
		}
		defer rpool.Close()
		deps := commands.RebuildProjectionDeps{
			Lifecycle: lifecycle,
			Truncator: commands.NewPgProjectionTruncator(rpool),
			Invoker:   commands.NewSubprocessRebuildInvoker(binPath, rdsn),
		}
		return commands.RunRebuildProjection(ctx, commands.RebuildProjectionRequest{
			RealityID: rid, ProjectionName: inv.Params["projection_name"],
			Actor: inv.Actor, Reason: inv.Reason, Confirm: inv.Confirm, DryRun: inv.DryRun,
		}, deps)
	}
	return h, metaPool.Close, nil
}

// resolveCatastrophicRealities turns --scope into a concrete reality-id list:
// reality (--reality_ids comma/space-separated), all-realities (every ACTIVE
// reality_registry row — only active realities can be frozen), or aggregate-list
// (--aggregate_file, one UUID per line; '#' comments + blanks skipped).
func resolveCatastrophicRealities(ctx context.Context, metaPool *pgxpool.Pool, scope string, params map[string]string) ([]string, error) {
	switch scope {
	case "reality":
		return splitIDs(params["reality_ids"]), nil
	case "aggregate-list":
		path := strings.TrimSpace(params["aggregate_file"])
		if path == "" {
			return nil, fmt.Errorf("scope=aggregate-list requires --aggregate_file")
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read aggregate_file %q: %w", path, err)
		}
		var ids []string
		for _, line := range strings.Split(string(raw), "\n") {
			line = strings.TrimSpace(line)
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			ids = append(ids, line)
		}
		return ids, nil
	case "all-realities":
		rows, err := metaPool.Query(ctx, `SELECT reality_id::text FROM reality_registry WHERE status = 'active'`)
		if err != nil {
			return nil, fmt.Errorf("enumerate active realities: %w", err)
		}
		defer rows.Close()
		var ids []string
		for rows.Next() {
			var id string
			if err := rows.Scan(&id); err != nil {
				return nil, fmt.Errorf("scan reality_id: %w", err)
			}
			ids = append(ids, id)
		}
		return ids, rows.Err()
	default:
		return nil, fmt.Errorf("unknown scope %q (reality|all-realities|aggregate-list)", scope)
	}
}

// splitIDs splits a comma/whitespace-separated id list, dropping empties.
func splitIDs(s string) []string {
	fields := strings.FieldsFunc(s, func(r rune) bool { return r == ',' || r == ' ' || r == '\t' || r == '\n' })
	out := make([]string, 0, len(fields))
	for _, f := range fields {
		if f = strings.TrimSpace(f); f != "" {
			out = append(out, f)
		}
	}
	return out
}

// buildCatastrophicRebuildHandler wires `reality catastrophic-rebuild` (073,
// L3.H) — Tier-1 destructive rolling rebuild across N realities. Same gate as
// rebuild-projection (ADMIN_CLI_ENABLE_UNPROVEN_REBUILD=1 → else NotWired). Owns
// the meta pool (lifecycle gate + reality enumeration + DSN resolution); each
// reality's truncator pool + rebuilder DSN are resolved by the PerRealityResolver
// inside the rolling orchestrator's worker.
func buildCatastrophicRebuildHandler() (framework.Handler, func(), error) {
	noop := func() {}
	if os.Getenv(enableUnprovenRebuildEnv) != "1" {
		return nil, noop, nil
	}
	dsn := os.Getenv("META_DATABASE_URL")
	if dsn == "" {
		return nil, noop, nil
	}
	if os.Getenv("ADMIN_CLI_ALLOW_DEV_TOKENS") == "1" {
		return nil, noop, fmt.Errorf("ADMIN_CLI_ALLOW_DEV_TOKENS=1 is incompatible with META_DATABASE_URL")
	}
	allowPath := os.Getenv("META_ALLOWLIST_PATH")
	if allowPath == "" {
		return nil, noop, fmt.Errorf("META_ALLOWLIST_PATH required for catastrophic-rebuild")
	}
	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return nil, noop, fmt.Errorf("load allowlist: %w", err)
	}
	if !allow.AllowsTable("reality_registry") {
		return nil, noop, fmt.Errorf("allowlist %s missing reality_registry", allowPath)
	}
	graph, err := meta.LoadTransitions(defaultTransitionsPath())
	if err != nil {
		return nil, noop, fmt.Errorf("load transitions graph: %w", err)
	}
	metaPool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("catastrophic-rebuild meta DB connect: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(metaPool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{}, Scrubber: meta.NewRegexScrubber(nil),
		Transitions: graph,
	}
	lifecycle := commands.NewPgLifecycleGate(cfg)
	binPath := os.Getenv("REBUILDER_BIN_PATH")
	if binPath == "" {
		binPath = "rebuilder"
	}

	// Per-reality resolver: DSN → its own pool (truncator) + DSN (subprocess).
	resolve := func(ctx context.Context, realityID uuid.UUID) (commands.ProjectionTruncator, commands.RebuildInvoker, func(), error) {
		rdsn, err := perRealityDSN(ctx, metaPool, realityID)
		if err != nil {
			return nil, nil, func() {}, err
		}
		rpool, err := pgxpool.New(ctx, rdsn)
		if err != nil {
			return nil, nil, func() {}, fmt.Errorf("per-reality DB connect: %w", err)
		}
		return commands.NewPgProjectionTruncator(rpool),
			commands.NewSubprocessRebuildInvoker(binPath, rdsn),
			rpool.Close, nil
	}

	h := func(ctx context.Context, inv framework.Invocation) (string, error) {
		scope := inv.Params["scope"]
		concurrency := 10
		if raw := strings.TrimSpace(inv.Params["rolling_concurrency"]); raw != "" {
			n, perr := strconv.Atoi(raw)
			if perr != nil {
				return "", fmt.Errorf("invalid --rolling_concurrency %q: %w", raw, perr)
			}
			concurrency = n
		}
		timeout := 30 * time.Minute
		if raw := strings.TrimSpace(inv.Params["per_reality_timeout"]); raw != "" {
			d, perr := time.ParseDuration(raw)
			if perr != nil {
				return "", fmt.Errorf("invalid --per_reality_timeout %q: %w", raw, perr)
			}
			timeout = d
		}
		// Resolution is read-only (SELECT / file read), so it runs for dry-run too
		// — the preview then reports the real reality count.
		realityIDs, rerr := resolveCatastrophicRealities(ctx, metaPool, scope, inv.Params)
		if rerr != nil {
			return "", rerr
		}
		req := commands.CatastrophicRebuildRequest{
			Scope: scope, RealityIDs: realityIDs, Actor: inv.Actor, Reason: inv.Reason,
			Confirm: inv.Confirm, DryRun: inv.DryRun,
			RollingConcurrency: concurrency, PerRealityTimeout: timeout,
		}
		rebuilder := &commands.MultiProjectionRebuilder{
			Lifecycle: lifecycle, Resolve: commands.PerRealityResolver(resolve),
			Projections: commands.AllProjectionTables(),
		}
		return commands.RunCatastrophicRebuild(ctx, req, rebuilder)
	}
	return h, metaPool.Close, nil
}

// registryDirEnv lets ops override the registry path (defaults to the
// canonical contracts/admin/registry relative to repo root).
const registryDirEnv = "ADMIN_CLI_REGISTRY_DIR"

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr *os.File) int {
	dir := os.Getenv(registryDirEnv)
	if dir == "" {
		dir = defaultRegistryDir()
	}
	reg, err := framework.LoadRegistry(dir)
	if err != nil {
		fmt.Fprintf(stderr, "admin: load registry: %v\n", err)
		return 2
	}

	if len(args) == 0 {
		printOverview(stdout, reg)
		return 0
	}

	// Top-level meta flags first.
	switch args[0] {
	case "--help", "-h", "help":
		printOverview(stdout, reg)
		return 0
	case "--list":
		return dumpRegistryJSON(stdout, reg)
	case "--version":
		fmt.Fprintln(stdout, "admin-cli v1.0.0 (cycle 36)")
		return 0
	}

	domain := args[0]
	domainCmds := reg.ByDomain(domain)
	if len(domainCmds) == 0 {
		fmt.Fprintf(stderr, "admin: unknown domain %q. Known: %s\n", domain, strings.Join(reg.Domains, ", "))
		return 2
	}

	if len(args) == 1 {
		printDomain(stdout, domain, domainCmds)
		return 0
	}

	verb := args[1]
	full := domain + " " + verb
	c, ok := reg.Commands[full]
	if !ok {
		fmt.Fprintf(stderr, "admin: unknown verb %q under %q. Known: %s\n",
			verb, domain, joinVerbs(domainCmds))
		return 2
	}

	// Sub-command flag parsing (one fs per command keeps name collisions out).
	fs := flag.NewFlagSet(full, flag.ContinueOnError)
	fs.SetOutput(stderr)
	var (
		fToken            = fs.String("token", "", "admin JWT (dev:user:role:scopes[:break-glass])")
		fReason           = fs.String("reason", "", "audit reason (>=10 chars for tier-1/2)")
		fSecondActor      = fs.String("second-actor", "", "tier-1 dual-approval secondary actor (must differ from caller)")
		fSecondActorToken = fs.String("second-actor-token", "", "tier-1 dual-approval: the second actor's OWN signed token")
		fConfirmToken     = fs.String("confirm-token", "", "tier-1 typed-confirmation: re-type the target resource id")
		fDryRun           = fs.Bool("dry-run", false, "preview-only; no side effects")
		fConfirm          = fs.Bool("confirm", false, "proceed with destructive run (mutually exclusive with --dry-run)")
		fHelp             = fs.Bool("help", false, "show this command's parameters")
		fJSON             = fs.Bool("json", false, "machine-readable output")
	)
	// Dynamic per-param flags so each registry parameter gets a CLI flag.
	// Skip names that collide with reserved framework flags — the
	// framework-level flag absorbs them (e.g., `reason`, `dry_run`).
	reserved := map[string]bool{
		"token": true, "reason": true, "second-actor": true,
		"second-actor-token": true, "confirm-token": true,
		"dry-run": true, "confirm": true, "help": true, "json": true,
		// Underscore variants in registry → take the framework flag.
		"dry_run": true, "second_actor": true,
		"second_actor_token": true, "confirm_token": true,
	}
	dynParams := make(map[string]*string)
	for _, p := range c.Params {
		if reserved[p.Name] {
			continue
		}
		dynParams[p.Name] = fs.String(p.Name, "", p.Description)
	}
	if err := fs.Parse(args[2:]); err != nil {
		return 2
	}
	if *fHelp {
		printCommand(stdout, c)
		return 0
	}
	if *fDryRun && *fConfirm {
		fmt.Fprintln(stderr, "admin: --dry-run and --confirm are mutually exclusive")
		return 2
	}

	// Validate required params.
	params := make(map[string]string, len(c.Params))
	for _, p := range c.Params {
		var v string
		switch p.Name {
		case "reason":
			v = *fReason
		default:
			if ptr, ok := dynParams[p.Name]; ok {
				v = *ptr
			}
		}
		if p.Required && strings.TrimSpace(v) == "" {
			fmt.Fprintf(stderr, "admin: missing required --%s\n", p.Name)
			return 2
		}
		params[p.Name] = v
	}

	// Audit emitter: MetaWriteSink (admin_action_audit via MetaWrite) when
	// META_DATABASE_URL is set, else the dev stdout sink. 073 prerequisite.
	sink, closeSink, serr := buildAuditSink(stderr, c.ImpactClass, *fDryRun, *fConfirm)
	if serr != nil {
		fmt.Fprintf(stderr, "admin: %v\n", serr)
		return 2
	}
	defer closeSink()
	emitter := audit_emitter.New(sink, nil)

	handlers := defaultHandlers()

	// Per-command live-wiring: build the real handler ONLY for the invoked
	// command, so unrelated commands never open a DB / KMS / MinIO connection.
	// The builders are uniform: (nil handler, nil err) when the command is
	// intentionally left NotWired (no META_DATABASE_URL, or the rebuild gate is
	// off), a real handler on success, or a non-nil err when config is present
	// but invalid. See each build* func for the per-command doc.
	builders := map[string]func() (framework.Handler, func(), error){
		"erasure user-erasure":         buildErasureHandler,
		"reality stats":                buildRealityStatsHandler,
		"migration status":             buildMigrationStatusHandler,
		"archive list":                 buildArchiveListHandler,
		"projection drift-check":       buildProjectionDriftCheckHandler,
		"archive fetch":                buildArchiveFetchHandler,
		"reality capacity-override":    buildCapacityOverrideHandler,
		"reality rebuild-projection":   buildRebuildProjectionHandler,
		"reality catastrophic-rebuild": buildCatastrophicRebuildHandler,
	}
	if build, ok := builders[c.Name]; ok {
		closeHandler, fatal := wireCommandHandler(stderr, handlers, c.Name, build)
		defer closeHandler()
		if fatal {
			// D-ADMIN-NOTWIRED-EXIT (121): a wiring-builder error means config is
			// present but invalid — exit non-zero instead of falling through to the
			// tier-3 NotWiredHandler (a calm "recognised but not wired" + exit 0).
			return 2
		}
	}

	handler := handlers.Resolve(c)
	inv := framework.Invocation{
		Command:          c,
		Params:           params,
		DryRun:           *fDryRun,
		Confirm:          *fConfirm,
		Reason:           *fReason,
		SecondActor:      *fSecondActor,
		SecondActorToken: *fSecondActorToken,
		ConfirmToken:     *fConfirmToken,
	}
	ctx := context.Background()
	out, rerr := framework.Run(ctx, c, inv, *fToken, handler, emitter)
	if rerr != nil {
		fmt.Fprintf(stderr, "admin: %v\n", rerr)
		return 3
	}
	if *fJSON {
		_ = json.NewEncoder(stdout).Encode(map[string]any{
			"command": c.Name,
			"dry_run": *fDryRun,
			"output":  out,
			"audited": os.Getenv("META_DATABASE_URL") != "",
		})
	} else {
		fmt.Fprintln(stdout, out)
	}
	return 0
}

// ─── output helpers ──────────────────────────────────────────────────────────

func printOverview(w *os.File, reg *framework.Registry) {
	fmt.Fprintln(w, "admin — LoreWeave admin CLI (single binary; Q-L7A-2)")
	fmt.Fprintln(w, "")
	fmt.Fprintln(w, "Domains:")
	for _, d := range reg.Domains {
		cmds := reg.ByDomain(d)
		fmt.Fprintf(w, "  %-12s  %d command(s)\n", d, len(cmds))
	}
	fmt.Fprintln(w, "")
	fmt.Fprintln(w, "All commands:")
	for _, c := range reg.List() {
		fmt.Fprintf(w, "  %-40s  [%s]  %s\n", c.Name, c.ImpactClass, c.Summary)
	}
	fmt.Fprintln(w, "")
	fmt.Fprintln(w, "Help:")
	fmt.Fprintln(w, "  admin <domain>              list verbs in a domain")
	fmt.Fprintln(w, "  admin <domain> <verb> --help show parameters")
	fmt.Fprintln(w, "  admin --list                JSON dump (CI / lint)")
}

func printDomain(w *os.File, domain string, cmds []*framework.Command) {
	fmt.Fprintf(w, "admin %s — %d command(s):\n", domain, len(cmds))
	for _, c := range cmds {
		fmt.Fprintf(w, "  %-30s  [%s]  %s\n", c.Verb, c.ImpactClass, c.Summary)
	}
}

func printCommand(w *os.File, c *framework.Command) {
	fmt.Fprintf(w, "admin %s — v%s\n", c.Name, c.Version)
	fmt.Fprintf(w, "  %s\n", c.Summary)
	fmt.Fprintf(w, "  impact: %s | dry_run_required: %v | double_approval_required: %v\n",
		c.ImpactClass, c.DryRunRequired, c.DoubleApprovalRequired)
	if c.CarryForwardCycle != "" {
		fmt.Fprintf(w, "  carry-forward cycle: %s\n", c.CarryForwardCycle)
	}
	if len(c.LockedQsConsumed) > 0 {
		fmt.Fprintf(w, "  locked Q-IDs:      %s\n", strings.Join(c.LockedQsConsumed, ", "))
	}
	if len(c.Params) > 0 {
		fmt.Fprintln(w, "  params:")
		ps := append([]framework.Param(nil), c.Params...)
		sort.Slice(ps, func(i, j int) bool { return ps[i].Name < ps[j].Name })
		for _, p := range ps {
			req := ""
			if p.Required {
				req = " (required)"
			}
			fmt.Fprintf(w, "    --%-22s %s%s — %s\n", p.Name, p.Type, req, p.Description)
		}
	}
	fmt.Fprintln(w, "")
	fmt.Fprintln(w, "Common flags:")
	fmt.Fprintln(w, "  --token <jwt>            required for every invocation")
	fmt.Fprintln(w, "  --reason <text>          required for tier-1/2 (>=10 chars)")
	fmt.Fprintln(w, "  --dry-run                preview only (tier-1: mandatory before --confirm)")
	fmt.Fprintln(w, "  --confirm                proceed with destructive run")
	fmt.Fprintln(w, "  --second-actor <user>    tier-1 dual approval")
	fmt.Fprintln(w, "  --json                   machine-readable output")
}

func dumpRegistryJSON(w *os.File, reg *framework.Registry) int {
	out := make([]map[string]any, 0, len(reg.Commands))
	for _, c := range reg.List() {
		out = append(out, map[string]any{
			"name":                     c.Name,
			"domain":                   c.Domain,
			"verb":                     c.Verb,
			"version":                  c.Version,
			"summary":                  c.Summary,
			"impact_class":             c.ImpactClass,
			"dry_run_required":         c.DryRunRequired,
			"double_approval_required": c.DoubleApprovalRequired,
			"carry_forward_cycle":      c.CarryForwardCycle,
			"params_count":             len(c.Params),
			"locked_qs":                c.LockedQsConsumed,
		})
	}
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	if err := enc.Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	return 0
}

func joinVerbs(cmds []*framework.Command) string {
	out := make([]string, 0, len(cmds))
	for _, c := range cmds {
		out = append(out, c.Verb)
	}
	sort.Strings(out)
	return strings.Join(out, ", ")
}

// defaultRegistryDir walks up from the binary's cwd looking for
// contracts/admin/registry. Fallback: relative path that works from repo root.
func defaultRegistryDir() string {
	candidates := []string{
		"contracts/admin/registry",
		"../../contracts/admin/registry",
		"../../../contracts/admin/registry",
	}
	for _, c := range candidates {
		abs, _ := filepath.Abs(c)
		if st, err := os.Stat(abs); err == nil && st.IsDir() {
			return abs
		}
	}
	return "contracts/admin/registry"
}

// defaultHandlers seeds the per-command registry. Cycle 36 ships every
// command as NotWiredHandler (audited skeleton); real bodies wire via
// commands.Register("<name>", real-fn) in subsequent cycles. The consolidated
// cycle 7/14 commands stay in services/admin-cli/commands/ and are invoked
// from this map when their cycle's wire-in cycle ships (e.g., cycle 14b
// would call h.Register("reality rebuild-projection", commands.RealityRebuildProjection)).
func defaultHandlers() *framework.HandlerRegistry {
	h := framework.NewHandlerRegistry()
	// (Intentionally empty — NotWiredHandler is the default. CONSOLIDATION
	// follow-ups land wiring per carry_forward_cycle.)
	return h
}

// wireCommandHandler invokes a per-command wiring builder and applies the
// uniform NotWired-vs-error policy (D-ADMIN-NOTWIRED-EXIT / 121).
//
//   - build returns a non-nil ERROR → config is present but invalid (e.g.
//     MINIO_* unset for `archive fetch`, SHARD_DB_* missing, allowlist load
//     fail). This is FATAL: report it and signal a non-zero exit, so an operator
//     who gave valid args but forgot config sees the real error — NOT the calm
//     tier-3 NotWiredHandler "recognised but not wired" message with exit 0.
//   - build returns (nil handler, nil err) → the command is intentionally left
//     NotWired (no META_DATABASE_URL, or the rebuild gate is off). NOT fatal: the
//     dispatcher's fail-closed tier policy decides (tier-3 informs; tier-1/2
//     error). Mirrors buildAuditSink's own config errors, which already exit 2.
//   - build returns (handler, _, nil) → register it.
//
// The returned closer is always non-nil (the builders return a no-op closer on
// every error path), so the caller can unconditionally defer it.
func wireCommandHandler(
	stderr io.Writer,
	handlers *framework.HandlerRegistry,
	name string,
	build func() (framework.Handler, func(), error),
) (closer func(), fatal bool) {
	h, closer, err := build()
	if err != nil {
		fmt.Fprintf(stderr, "admin: %s handler not wired: %v\n", name, err)
		return closer, true
	}
	if h != nil {
		handlers.Register(name, h)
	}
	return closer, false
}

// ─── audit sink ──────────────────────────────────────────────────────────────

// stdoutSink writes one JSON-line per audit row to a writer (typically
// stderr) AND mirrors to an in-memory MemorySink so --json output can include
// audit_rows count. Production swaps to a contracts/meta MetaWrite adapter.
type stdoutSink struct {
	stdout *os.File
	mem    *audit_emitter.MemorySink
}

func (s stdoutSink) Write(ctx context.Context, a audit_emitter.Action) error {
	if err := s.mem.Write(ctx, a); err != nil {
		return err
	}
	enc := json.NewEncoder(s.stdout)
	return enc.Encode(map[string]any{
		"audit":        "admin_action",
		"command":      a.CommandName,
		"actor":        a.Actor,
		"actor_role":   a.ActorRole,
		"reason":       a.Reason,
		"params_hash":  a.ParamsHash,
		"impact":       a.ImpactClass,
		"dry_run":      a.DryRun,
		"second_actor": a.DoubleApprovalRef,
		"outcome":      a.Outcome,
		"err_hash":     a.ErrorDetailHash,
		"started_at":   a.StartedAt.UTC(),
		"finished_at":  a.FinishedAt.UTC(),
	})
}
