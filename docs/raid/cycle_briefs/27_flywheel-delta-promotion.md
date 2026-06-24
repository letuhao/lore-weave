# Cycle 27: Flywheel on delta + what-if→derivative promotion

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** **CROSS-SERVICE. dị bản M4.** Two linked pieces: (1) **Flywheel on the delta** — when a derivative chapter is **approved**, its extraction writes into the **delta graph** (the derivative's own `project_id` partition, G2), so the next scene's grounding is enriched by what the dị bản itself established. (2) **What-if → derivative promotion** — promote an ephemeral "what-if" exploration into a **persistent derivative** Work (materialize it via the C23 derive path so it gets its own project_id + spec). Verify: approve a dị bản chapter → the delta enriches next-scene grounding.
- **Acceptance gate:** `scripts/raid/verify-cycle-27.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G2 (extraction targets the derivative's own delta partition), derivative write-order (forward from branch_point; out-of-order = thinner delta, not a break), GUARD (delta extraction is project-scoped — never null)
- **DPS count:** 2
- **Estimated wall time:** 4–5h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C25, C26
- Files expected to exist (grep-able paths): the C25 packer two-project merge (delta read path); the C26 derivative critic; `composition_work.source_work_id`/`project_id` (C23); the knowledge extraction trigger the approved-chapter flow invokes (writes into a project's partition).

## Scope (IN)
- **Delta flywheel:** on **approval** of a derivative chapter, trigger knowledge extraction **into the derivative's own `project_id`** (the delta partition) — so subsequent packs (C25) merge the newly-established delta facts into next-scene grounding. Forward-from-branch write-order (LOCKED).
- **What-if → derivative promotion:** a UI/API action that takes an ephemeral what-if exploration and **promotes it to a persistent derivative** by materializing it through the C23 `POST /works/{id}/derive` path (own project_id + divergence spec + overrides carried over).
- **Project-scope guard at extraction:** the approved-chapter extraction asserts a **non-null derivative project_id** before dispatching (defends the cross-project leak; never extract into "all projects").
- `scripts/raid/verify-cycle-27.sh` (acceptance gate) + a **Playwright screenshot** of the promotion action where a UI surface exists.

## Scope (OUT — explicitly)
- **NO schema/migration** (C23), **NO packer merge logic** (C25 — flywheel WRITES delta; C25 reads it), **NO critic** (C26).
- **NO living-world view** (C28), **NO wizard/studio FE** (C24).
- **NO new extraction engine** — reuse the existing knowledge extraction trigger, just target the delta project_id.
- NO relationship/event override work; NO base/canon graph writes (delta only — the source partition stays untouched, COW).
- NO cross-tenant derivative publishing (deferred).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: delta-extraction trigger + what-if-promotion unit tests (`services/composition-service/.../test_delta_flywheel*.py`, promotion test) — extraction targets the derivative project_id, promotion materializes via derive, project-scope guard fires on null.
- Lints pass: composition + knowledge linters touched; provider-gate green.
- Integration smoke: **live smoke (REQUIRED — cross-service)** — on a stacked-up composition + knowledge, **approve a dị bản chapter → the delta graph is enriched → the next-scene pack grounding reflects it**. Evidence string carries `live smoke: approve dị bản chapter → delta enriches next-scene grounding`. Rebuild touched service images first. Plus a **Playwright screenshot** of the what-if→derivative promotion. If full stack un-bootable: `live infra unavailable: <reason>` is the only allowed substitute.

## DPS parallelism plan
- DPS 1: **Delta flywheel** — approved-derivative-chapter hook → knowledge extraction into the derivative's own project_id (delta), forward-write-order, non-null project-scope guard, next-pack-sees-it test. (return budget: 1500 tokens summary)
- DPS 2: **What-if → derivative promotion** — promote action (FE + API) materializing a what-if into a persistent derivative via the C23 derive path (own project_id + spec + overrides); Playwright shot. Independent of DPS 1 until convergence on the derivative Work.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Wrong partition write:** extraction writing into the **source/base** project_id (or null → all projects) instead of the derivative's delta partition → corrupts canon / cross-project leak. Confirm the non-null derivative project-scope guard.
- **Flywheel not closing:** delta written but the next pack (C25) doesn't read it — confirm the live-smoke shows next-scene grounding actually enriched (reconcile-by-truth: re-use the packer's own delta-read predicate).
- **Promotion drops spec/overrides:** what-if→derivative materialization that loses the divergence spec or overrides, or reuses an existing project_id instead of a fresh one (G2).
- **Mock-only false-green:** unit-pass with no real approve→extract→re-pack on a running stack (rebuild stale images first).
- **Out-of-order panic:** treating out-of-order authoring as a correctness break — LOCKED: it just yields a thinner delta, grounding degrades gracefully.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only the delta-extraction trigger + what-if-promotion + tests + `scripts/raid/verify-cycle-27.sh` changed; extraction targets the derivative's OWN project_id (never source/null) with a project-scope guard; promotion materializes via the C23 derive path (fresh project_id + spec + overrides); live-smoke + Playwright evidence present; NO schema/packer/critic change, NO living-world/wizard FE, NO base-graph writes. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C27** row (dị bản M4; approved derivative chapters extract into the delta graph; promote a what-if to a persistent derivative).
- OPEN_QUESTIONS_LOCKED.md — **§G2** (derivative's own delta partition), **dị bản locks** (cross-tenant publishing deferred), **Architecture-review locks** (derivative write-order = forward from branch_point, out-of-order = thinner delta; GUARD: project-scoped, never null).
- `docs/specs/2026-06-13-derivative-works-living-world-plan.md` — dị bản M4.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Delta-only write (G2):** approved-chapter extraction writes into the **derivative's own project_id** — NEVER the source/base partition, NEVER null. The source graph stays untouched (COW).
- 🔴 **Project-scope guard:** assert a non-null derivative project_id before dispatching extraction (defends the cross-project grounding leak).
- 🔴 **Promotion keeps spec+overrides:** what-if→derivative materializes via the **C23 derive path** with a fresh project_id; do not drop the divergence spec/overrides or reuse a project_id.
- 🔴 **Acceptance MUST include:** a real **live-smoke** (approve dị bản chapter → delta enriches next-scene grounding) **and** a Playwright shot of the promotion. Rebuild stale images first; mock-only is a false-green.
- 🔴 **Do NOT touch:** schema (C23), packer (C25), critic (C26), living-world (C28), wizard FE (C24); no base-graph writes.
- 🔴 **Fresh session reminder:** this is a new `/raid 27` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
