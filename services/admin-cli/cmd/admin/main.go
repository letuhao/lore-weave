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
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/contracts/pii"
	"github.com/loreweave/foundation/sdks/go/metapg"
	"github.com/loreweave/foundation/sdks/go/piikms"
	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
	"github.com/loreweave/foundation/services/admin-cli/internal/commands"
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
	// Fail-fast: step 7 writes user_consent_ledger via MetaWrite.
	if !allow.AllowsTable("user_consent_ledger") {
		return nil, noop, fmt.Errorf("allowlist %s missing user_consent_ledger (erasure step 7 needs it)", allowPath)
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		return nil, noop, fmt.Errorf("erasure meta DB connect: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{}, Scrubber: meta.NewRegexScrubber(nil),
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
			KEKManager:  piikms.NewPgKEKManager(pool, kmsClient, 30),
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
	// Wire the erasure orchestrator (076 Slice C) only for its own command, so
	// unrelated commands never open the PII pool. Falls back to NotWired on a
	// wiring error.
	closeErasure := func() {}
	if c.Name == "erasure user-erasure" {
		erasureH, ce, eerr := buildErasureHandler()
		closeErasure = ce
		if eerr != nil {
			fmt.Fprintf(stderr, "admin: erasure handler not wired: %v\n", eerr)
		} else if erasureH != nil {
			handlers.Register("erasure user-erasure", erasureH)
		}
	}
	defer closeErasure()

	// Read-only `reality stats` (073) — wired only for its own command.
	closeReality := func() {}
	if c.Name == "reality stats" {
		rsH, rc, rerr := buildRealityStatsHandler()
		closeReality = rc
		if rerr != nil {
			fmt.Fprintf(stderr, "admin: reality-stats handler not wired: %v\n", rerr)
		} else if rsH != nil {
			handlers.Register("reality stats", rsH)
		}
	}
	defer closeReality()

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
