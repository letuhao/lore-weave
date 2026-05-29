# Admin Command Catalog (R13 §12L.5)

> Generated reference for the LoreWeave admin CLI. Source of truth = `contracts/admin/registry/*.yaml`. To list machine-readable: `admin --list`.
>
> **Cycle:** 36 (L7.A) · **LOCKED:** Q-L7A-1 per-domain YAML · Q-L7A-2 single binary.

## At a glance

| Domain | Commands | Notes |
|---|---|---|
| reality | 8 | Reality lifecycle: freeze, thaw, force-close, rebuild-projection, catastrophic-rebuild, capacity-override (consolidated cycle 7), stats, cancel-close |
| erasure | 3 | GDPR Art.15/17 flows: user-erasure, kek-rotate, pii-export |
| canon | 3 | DMCA decanonize, force-propagate, conflict-list |
| projection | 1 | drift-check (read-only) |
| backup | 3 | trigger, restore-drill, list |
| archive | 3 | list, fetch, replay (consolidated cycle 11 archive-restore CLI) |
| migration | 3 | up, down, status (consolidated cycle 6 migration-orchestrator CLI) |
| incident | 2 | declare, statuspage-update |
| ops | 6 | drain-replica, set-service-mode, deploy-freeze, deploy-thaw, canary-advance, chaos-run |
| **TOTAL** | **32** | Within cycle 36 target (28-32) |

## Distribution (Q-L7A-2)

ONE binary — `services/admin-cli/cmd/admin`. Build:

```bash
cd services/admin-cli && go build -o ./bin/admin ./cmd/admin
```

Invocation pattern:

```bash
admin                                  # overview (all domains + commands)
admin <domain>                         # list verbs in a domain
admin <domain> <verb> --help           # parameters for one command
admin <domain> <verb> [flags] --token …
admin --list                           # JSON dump for CI / lint
```

## Registry layout (Q-L7A-1)

Per-domain YAML under `contracts/admin/registry/`:

```
contracts/admin/registry/
├── reality.yaml
├── erasure.yaml
├── canon.yaml
├── projection.yaml
├── backup.yaml
├── archive.yaml
├── migration.yaml
├── incident.yaml
└── ops.yaml
```

Framework loader `services/admin-cli/internal/framework.LoadRegistry()` walks the directory and auto-merges. Domain collisions across files are rejected at load time (one domain per file).

## Audit (R13 §12L.3 + S08 §12X.5)

Every command — even dry-runs and failures — writes TWO `admin_action_audit` rows (cycle 4 table): one on `Before` (outcome=started) and one on `After` (outcome=succeeded) or `Failure` (outcome=failed, error_detail hash).

The audit hook lives at the FRAMEWORK level (`framework.Run()`) — individual command handlers never call the audit writer themselves. This guarantees no command can ship without auditing.

Audit fields per row:

| field | description |
|---|---|
| `command_name` | full name (e.g. `reality force-close`) |
| `actor` | from JWT subject |
| `actor_role` | from JWT role claim |
| `reason` | operator-supplied --reason (>=10 chars for tier-1/2) |
| `params_hash` | SHA-256 of normalised params (never raw PII) |
| `impact_class` | tier-1-destructive / tier-2-griefing / tier-3-informational |
| `dry_run` | bool |
| `second_actor` | tier-1 dual-approval ref |
| `outcome` | started / succeeded / failed |
| `error_detail_hash` | SHA-256(err) on failure (scrubbed via S08 §12X.5) |
| `started_at` / `finished_at` | timestamps |

## Tier classification (S5-D5)

| Tier | dry_run_required | double_approval_required | typed_confirm | scope needed |
|---|---|---|---|---|
| tier-1-destructive | true | true | true | admin:destructive |
| tier-2-griefing | false | false | false | admin:write |
| tier-3-informational | false | false | false | admin:read |

LoadRegistry REJECTS tier-1 commands whose YAML sets `dry_run_required: false` or `double_approval_required: false` — caught at startup, not at first invocation.

## Consolidation (Q-L7A-2 — single binary)

Prior cycles shipped standalone CLIs that are NOW dispatched through the unified `admin` binary:

| Prior cycle | What shipped | Where it lives now |
|---|---|---|
| **6** | `services/migration-orchestrator/cmd/migrate` | `admin migration up | down | status` |
| **7** | `services/admin-cli/commands/capacity_override.go` (library) | `admin reality capacity-override` |
| **11** | `services/archive-worker/cmd/archive-restore` | `admin archive list | fetch | replay` |
| **14** | `services/admin-cli/commands/rebuild_projection.go` + `catastrophic_rebuild.go` (libraries) | `admin reality rebuild-projection`, `admin reality catastrophic-rebuild` |

The underlying packages still live in their original locations; the unified CLI re-uses them as handlers (cycle 36 ships the framework + NotWiredHandler skeletons; later carry-forward cycles wire each consolidated command's real body via `commands.Register("reality capacity-override", commands.Apply)` etc.). The standalone `cmd/` binaries remain for backwards compatibility but new operators should use `admin`.

## Break-glass (S11-D10)

`break_glass` package validates dual-actor + 100+ char reason + incident ticket + ≤24h TTL requests. Actual JWT issuance wires to auth-service in cycle 18+ — V1 ships the policy CHECKS so we cannot later forget them.

## Authoring a new command

1. Pick the domain (one of the 9 above) or add a new YAML file in `contracts/admin/registry/`.
2. Add an entry following the schema in `reality.yaml` header.
3. Tier-1 destructive? `dry_run_required: true` + `double_approval_required: true` are MANDATORY.
4. Run `scripts/admin-command-registry-lint.sh` to catch ad-hoc SQL/RPC outside the framework.
5. Run `cd services/admin-cli && go test ./...` — registry_test.go validates load + dispatch + audit.
6. Run `cd tests/integration && go test -tags=integration -run TestAdminCLI ./...` — cross-module smoke.

## Open follow-ups (carry-forward beyond cycle 36)

- **D-ADMIN-CLI-LIVE-WIRING** — `defaultHandlers()` in `cmd/admin/main.go` is empty; consolidated cycle-7/11/14 handlers wire via `commands.Register(...)` in follow-up cycles per `carry_forward_cycle`.
- **D-ADMIN-CLI-METAWRITE-WIRING** — V1 stdout sink for audit rows; production swap to a `contracts/meta` MetaWrite adapter targeting `admin_action_audit` table (cycle 4 already declared events_allowlist: events: []).
- **D-ADMIN-CLI-JWT-WIRING** — `internal/auth.Validate()` is V1 skeleton accepting `dev:` tokens; auth-service cycle 18+ ships real RS256/JWS verifier.
- **D-ADMIN-CLI-BREAK-GLASS-ENDPOINT** — `internal/break_glass` ships POLICY only; the `POST /admin/break-glass` HTTP endpoint that issues the 24h JWT wires to auth-service when the admin JWT path goes live.
