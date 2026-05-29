# Foundation Lint Catalog (L1.K)

> Source of truth for the 15 CI lints that enforce L1 invariants. Each lint
> has a corresponding shell script in `scripts/` and is wired into
> `.github/workflows/lint-foundation.yml`.
>
> Source: `docs/plans/2026-05-29-foundation-mega-task/L1C_to_L_infrastructure.md` §9
> LOCKED Q-IDs: Q-L1K-1 (mix tool choice) + Q-L1K-2 (I3 amendment same commit)

## Catalog

| ID | Script | Invariant | Source |
|---|---|---|---|
| L1.K.1 | `meta-write-discipline-lint.sh` | Direct INSERT/UPDATE/DELETE on meta tables outside `contracts/meta/` is forbidden | I8 / S04 §12T.6 |
| L1.K.2 | `pii-classify-lint.sh` | Every migration carries `@pii_sensitivity`, `@retention_class`, `@retention_hot`, `@erasure_method`, `@legal_basis` | S08 §12X.3 |
| L1.K.3 | `transitions-validation-lint.sh` | `transitions.yaml` graph is well-formed | C05 §12Q.6 |
| L1.K.4 | `shard-allocation-validation.sh` | Capacity thresholds present and warning < full | R04 §12D.6 |
| L1.K.5 | `migration-idempotency-validator.sh` | All per-reality migrations use `IF [NOT] EXISTS` | R04 §12D.2 — **shipped cycle 6** |
| L1.K.6 | `observability-inventory-lint.sh` | Every `lw_*` metric appears in `contracts/observability/inventory.yaml` | SR12 I19 |
| L1.K.7 | `capacity-budget-lint.sh` | Every service has an entry in `contracts/capacity/budgets.yaml` | SR08 I17 |
| L1.K.8 | `dep-pinning-lint.sh` | Every toolchain has lockfiles; Dockerfile `FROM` should use digest pin | SR10 I18 |
| L1.K.9 | `timeout-discipline-lint.sh` | No bare `http.Get` / `db.Query` (use Context variants); no `reqwest::get` | SR06 I16 |
| L1.K.10 | `language-rule-lint.sh` | Services in correct language per `contracts/language-rule.yaml` (amended I3) | I3 / Q-L1K-2 |
| L1.K.11 | `role-grant-validator.sh` | ACL matrix references only declared tables; audit tables append-only | S04-D6 / §12T.7 |
| L1.K.12 | `outbox-event-emit-lint.sh` | Direct `redis.XAdd` outside `services/publisher/` is forbidden | I13 |
| L1.K.13 | `service-acl-matrix-lint.sh` | Every service that imports `contracts/meta` has a matrix entry | I11 / S11 §12AA |
| L1.K.14 | `prompt-assembly-discipline-lint.sh` | Direct LLM SDK use outside `contracts/prompt/` and allowed services | I2 / I10 / S09 §12Y |
| L1.K.15 | `meta-sensitive-read-bypass-lint.sh` | Sensitive-table reads must flow through `contracts/meta/read_audit.go` | S04 §12T.6 |

## Conformance

- **CI:** `.github/workflows/lint-foundation.yml` matrix-runs all 15 in parallel; PR check.
- **Local:** `make lint` runs all 15 sequentially.
- **Code review:** lint catalog is the second-pass review checklist (see CLAUDE.md `Phase 7 REVIEW` §2 Code quality).

## Adding a lint

1. Create `scripts/<lint-name>-lint.sh` — must `set -euo pipefail` and exit 0 = PASS, 1 = FAIL, 2 = misuse.
2. Add a test fixture: a deliberately-bad file under `tests/lint-fixtures/<lint>/bad.<ext>` and `tests/lint-fixtures/<lint>/good.<ext>`.
3. Append to the matrix list in `.github/workflows/lint-foundation.yml`.
4. Append to `LINTS :=` in `Makefile`.
5. Update this catalog row.

## Tooling discipline (Q-L1K-1)

The catalog is intentionally a **mix** of tooling per Q-L1K-1 LOCKED 2026-05-29:

- **Pure shell + grep:** simple regex-friendly patterns (most lints today).
- **go vet extensions / staticcheck:** Go-specific patterns (none yet; planned for cycle 22+).
- **semgrep:** cross-language semantic patterns (none yet; planned for cycle 22+ when pattern complexity justifies the infra overhead).

V1 ships all-shell; semgrep upgrades land per-lint as the catalog matures.
