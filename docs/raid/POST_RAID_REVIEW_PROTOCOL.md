# Post-RAID Comprehensive Review Protocol (RAID v1.7)

> **Status:** MANDATORY phase for every RAID task. Runs ONCE, after all build
> cycles are DONE and **before** opening the PR to `main`.
> **Why it exists:** per-cycle review (RAID 12-phase) is scoped to a single
> cycle and a cold-start sub-agent. It structurally CANNOT see cross-cycle
> drift, "contract-complete but skeleton" gaps, escalation-log noise, missing
> CI, or invariant-enforcement that silently went NOTE-only. The foundation
> mega-task review (2026-05-30) found **45 such findings** — including a
> 64% projection-coverage gap, a forgeable admin auth, dead-at-runtime PII
> masking, an entire exit-0 worker fleet, and 24 spurious escalations — none
> of which any single per-cycle review surfaced. This protocol institutionalizes
> that review so future automated long-runs cannot drift into the same state.
>
> **Portability:** this doc is task-agnostic (lives in `docs/raid/`). Each task's
> `<plan_dir>` (from `.raid/active-task.yaml`) holds the run's output
> `POST_RAID_REVIEW_FINDINGS.md`.

---

## 1. Trigger

When `python scripts/raid/coordinator-helper.py next-cycle` reports `idle: true`
(all build cycles DONE), the Coordinator MUST run this review **instead of**
immediately reporting "ready to PR". The review is itself a single fan-out per
phase — the Coordinator stays in the loop between phases.

## 2. Three review passes (each multi-agent + adversarially verified)

Run as background `Workflow`s (or Agent fan-outs); every "clean/clear" verdict
MUST be checked by ≥1 adversarial skeptic that defaults to refuted.

### Pass A — Acceptance audit
- **Escalation reconciliation:** every `ESCALATIONS.md` entry classified
  `spurious_post_completion | real_unresolved`; cross-checked vs CYCLE_LOG
  status + AUDIT_LOG timeline + git feature commits. Skeptics hunt for a real
  unresolved cycle.
- **Artifact completeness:** sample artifacts per layer; confirm they EXIST on
  disk with REAL implementation, not hollow stubs the plan expected to be real.
- **Git integrity:** all cycle feature commits present + reachable; working tree
  clean; no stray worktrees; CYCLE_LOG schema sane.

### Pass B — Decisions audit
- Inventory every locked decision (CLARIFY + per-cycle LOCKED Q-IDs + the RAID
  methodology decisions) and classify `valid | superseded | drift | debt`
  against (a) `CLAUDE.md` + invariants and (b) the actual on-disk implementation.

### Pass C — Dimension review (the 4 mandatory dimensions)
1. **Architecture & invariant drift** — every invariant in
   `docs/03_planning/LLM_MMO_RPG/00_foundation/02_invariants.md` + `CLAUDE.md`
   (gateway, provider-gateway, language rule, per-service DB, no-hardcoded
   secrets/models, two-layer glossary↔knowledge).
2. **Contract conformance** — `contracts/api/**` OpenAPI specs + wire contracts
   (WS, RPC, service_acl) vs actual implementation.
3. **Security & GDPR** — auth/JWT, break-glass, tenant/reality isolation,
   secrets fail-closed, prompt/canon injection defense, GDPR Art.33 breach flow,
   PII masking + scrubbing. **Verify primitives are WIRED, not just present.**
4. **Test quality & cross-service live-smoke** — false-green probes
   (smoke that asserts nothing / dry-run "CLEARED"), mock-only coverage that
   hides cross-service bugs, outstanding `LIVE-SMOKE deferred` tokens, and
   projection/event coverage vs the registry.
- Plus an **integrated build** across all toolchains (compiling ≠ functional).

## 3. Output (REQUIRED artifacts)

- `<plan_dir>/POST_RAID_REVIEW_FINDINGS.md` — every finding with a stable
  `PRR-NN` id, severity (🔴 major / 🟠 medium / 🟡 low), evidence (`file:line`),
  and a Fix Log + a **Triage disposition** (each finding fixed-and-committed OR
  routed to a `DEFERRED.md` row with owner + target).
- Each deferral → a `docs/deferred/DEFERRED.md` row (defer means **tracked**,
  never forgotten).
- A machine-readable verdict line at the END of the findings doc, EXACTLY one of:
  - `POST-RAID-REVIEW: CLEAR (<one-line reason>)`
  - `POST-RAID-REVIEW: BLOCKED (<one-line reason>)`

## 4. Exit gate (enforced)

`scripts/raid/post-raid-review-gate.sh` (run before PR-to-main; also wired into
`foundation-ci.yml` is recommended) PASSES only when:
1. `<plan_dir>/POST_RAID_REVIEW_FINDINGS.md` exists,
2. it has a `Triage disposition` section (proves every finding was fixed or deferred),
3. its verdict line is `POST-RAID-REVIEW: CLEAR` (not BLOCKED / not missing).

**CLEAR criteria:** every 🔴 major finding is EITHER fixed+committed OR has a
tracked `DEFERRED.md` row with an explicit severity + target. A genuine
unresolved blocker (a major finding that is neither fixed nor tracked) → the
verdict MUST be `BLOCKED` and the gate fails. "CLEAR" does NOT mean
production-complete — it means "reviewed, and nothing is silently lost"; HIGH
deferred rows remain the explicit before-prod gate.

## 5. Coordinator integration

`.claude/commands/raid.md` "After completion": when the loop reaches idle, run
the three passes → write the findings doc + DEFERRED rows → run
`scripts/raid/post-raid-review-gate.sh` → only on PASS report "ready to PR";
on BLOCKED, halt and surface the blockers.

## 6. Cadence rule

Run ONCE per task at end-of-run. If new cycles are later appended to a task,
re-run the review (the findings doc is regenerated/extended; the verdict
re-stamped). The review is itself NOT a RAID cycle and does not get a CYCLE_LOG
row — it is the gate between "all cycles done" and "PR".
