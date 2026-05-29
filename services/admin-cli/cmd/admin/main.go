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
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
	"github.com/loreweave/foundation/services/admin-cli/internal/framework"
)

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

	// Audit emitter: V1 stdout sink (writes to admin_action_audit
	// wires via meta-worker MetaWrite adapter in a follow-up cycle).
	mem := audit_emitter.NewMemorySink()
	emitter := audit_emitter.New(stdoutSink{stdout: stderr, mem: mem}, nil)

	handler := defaultHandlers().Resolve(c)
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
			"command":    c.Name,
			"dry_run":    *fDryRun,
			"output":     out,
			"audit_rows": mem.Count(),
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
