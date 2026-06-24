# Cycle 25: Packer override-merge (composition)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** **CROSS-SERVICE.** Make the composition packer assemble a derivative's grounding from **two knowledge projects**: `base(source project_id, ≤ branch_point)` → **apply `entity_override`** → merge `delta(derivative project_id)` (G2: the derivative owns its own partition). The **`before_order` branch-filter + the override-application seam in packer `assemble` already exist** — this cycle adds the **two-project (source+delta) merge** + the **override mutation** on top. Override-at-retrieve is **self-syncing**: re-read + re-apply every pack, no stale cache. Verify a generated derivative keeps an overridden entity overridden across chapters.
- **Acceptance gate:** `scripts/raid/verify-cycle-25.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G2 (two-project partition merge), override-at-retrieve self-syncing, GUARD (packer asserts project-scoping for derivatives)
- **DPS count:** 2
- **Estimated wall time:** 4–5h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C23, C8
- Files expected to exist (grep-able paths): the composition packer `assemble` path with the existing `before_order` branch-filter + override seam; `composition_work.source_work_id`/`branch_point`/`entity_override` (C23); the C8 entities semantic-layer read (status/anchor) the base/delta reads draw from.

## Scope (IN)
- **Two-project merge in packer `assemble`:** for a derivative Work, read **base** grounding from the **source `project_id`** filtered to `≤ branch_point` (existing `before_order` filter), then merge **delta** grounding from the **derivative's own `project_id`** (full). Delta entities/relations take precedence over inherited base on collision.
- **Override mutation:** after assembling base, **apply `entity_override[]`** — mutate the inherited entity's overridden fields (entity-field + added canon-rule scope) before they reach the prompt window. Re-read + re-apply **every pack** (self-syncing; no override cache).
- **GUARD assertion:** the packer **asserts project-scoping for derivatives** — a derivative pack must use the derivative's own project_id for delta and the source's for base; refuse to proceed if `project_id` is null/missing (defends the cross-project leak the C23 NOT-NULL guard prevents).
- `scripts/raid/verify-cycle-25.sh` (acceptance gate) — asserts a derivative pack merges base+delta, applies overrides, and override survives across chapters.

## Scope (OUT — explicitly)
- **NO schema/migration** — `entity_override`/`source_work_id`/`branch_point` are C23. This cycle only reads + applies them.
- **NO new override TYPES** — entity-field + added canon-rule only (M0; relationship/event overrides deferred).
- **NO critic enforcement** (C26 enforces overrides at critique time — separate dimension).
- **NO delta flywheel / what-if promotion** (C27), **NO living-world FE** (C28), **NO wizard/studio FE** (C24).
- **NO knowledge schema change** — base/delta are two existing project partitions; no shared-graph plumbing (LOCKED COW).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: packer merge + override-application unit tests (`services/composition-service/.../test_packer_override*.py`) — base+delta merge, delta precedence, override mutation, project-scoping assertion.
- Lints pass: composition linter; provider-gate green (composition has no AI imports — keep it).
- Integration smoke: **live smoke (REQUIRED — cross-service)** — on a stacked-up composition + knowledge, **generate in a derivative → the overridden entity stays overridden across chapters** (the override is re-applied every pack, and delta merges with branch-filtered base). Evidence string carries `live smoke: derivative generate → overridden entity stays overridden across chapters`. Rebuild touched service images first. If full stack un-bootable: `live infra unavailable: <reason>` is the only allowed substitute.

## DPS parallelism plan
- DPS 1: **Two-project base+delta merge** — extend `assemble` to read source project (≤ branch) + derivative project (full), merge with delta-precedence; the GUARD project-scoping assertion. (return budget: 1500 tokens summary)
- DPS 2: **Override mutation seam** — apply `entity_override[]` to inherited entities post-assemble, re-read+re-apply every pack (self-syncing), entity-field + canon-rule scope. Shares the `assemble` path with DPS 1 — seam-stub the override-apply call site, integrate last.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Cross-project leak / GUARD gap:** a derivative pack that reads with null/wrong project_id, or widens to all projects — the exact leak C23's NOT-NULL guard exists for. Confirm the packer asserts derivative project-scoping.
- **Stale override cache:** caching the override mutation instead of re-reading+re-applying every pack → an edited override silently ignored (LOCKED: override-at-retrieve is self-syncing).
- **Branch-filter regression:** delta or base leaking content **after** `branch_point` from the source — base must stay `≤ branch_point`.
- **Precedence bug:** inherited base entity overriding a delta entity on collision (delta must win), or override not applied before the entity hits the prompt window.
- **Mock-only false-green:** unit-pass with no real cross-service generate — confirm the live-smoke token reflects a genuine derivative pack on a running stack (rebuild stale images first).
- **Normalization seam:** base vs delta entity identity compared without reconciling the two partitions' normalization (recurring cross-service bug class).

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only composition packer `assemble` + override-apply + tests + `scripts/raid/verify-cycle-25.sh` changed; base read `≤ branch_point` from source project, delta from derivative project, delta-precedence merge, overrides re-applied every pack, project-scoping asserted; NO schema change, NO new override types, NO critic/flywheel/living-world/FE; live-smoke token present. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C25** row (G2; before_order branch-filter + override seam already exist).
- OPEN_QUESTIONS_LOCKED.md — **§G2** (base source project ≤ branch + apply overrides + merge derivative delta; no knowledge schema change), **Architecture-review locks** (CONFIRMED: branch-filter + override seam exist; C25 wires the two-project merge; override re-applied every pack = self-syncing; packer asserts project-scoping for derivatives).
- `docs/specs/2026-06-13-derivative-works-living-world-plan.md` — packer override-merge.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **G2 two-project merge:** base = **source** project_id (`≤ branch_point`), delta = **derivative's own** project_id. Delta wins on collision. No shared-graph plumbing.
- 🔴 **Self-syncing override (LOCKED):** re-read + re-apply `entity_override[]` **every pack** — NEVER cache the mutation, or an edited override is silently lost.
- 🔴 **GUARD:** the packer **asserts project-scoping for derivatives** — refuse a null/missing project_id (defends the cross-project grounding leak).
- 🔴 **Acceptance MUST include:** a real **live-smoke** — generate in a derivative, overridden entity stays overridden across chapters. Rebuild stale images first; mock-only is a false-green.
- 🔴 **Do NOT touch:** knowledge/composition schema (C23 owns it); no critic (C26), flywheel (C27), living-world (C28), wizard FE (C24); no new override types.
- 🔴 **Fresh session reminder:** this is a new `/raid 25` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
