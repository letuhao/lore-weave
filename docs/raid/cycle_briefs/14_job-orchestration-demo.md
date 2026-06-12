# Cycle 14: Job orchestration (DEMO milestone)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Wire the full P1 enrichment pipeline into ONE end-to-end job runner in `lore-enrichment-service`: `estimate → start → detect location gaps → template+retrieval enrich → schema-gov generation (origin='enriched', quarantined) → canon-verify → quarantined Chinese proposals → review API → author promote → write-back to glossary SSOT`. Emit lifecycle events on Redis Streams. Enforce a per-job **cost-cap** that includes a reserved **eval-cost** budget line (M5). This is the **DEMO milestone**: P1 runs end-to-end on the 4 locked Fengshen LOCATIONS. No NEW pipeline logic — orchestrate existing C6–C13 components only.
- **Acceptance gate:** `scripts/raid/verify-cycle-14.sh` exits 0
- **Top 3 LOCKED decisions consumed:** H0, Q-R2, Q2
- **DPS count:** 3
- **Estimated wall time:** 4–6 h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C13
- Files expected to exist (grep-able paths): `services/lore-enrichment-service/app/` (C0 skeleton, `config.py` fail-fast, `/health`), strategy core + job state machine + cost guardrail (C8), template strategy (C9), retrieval strategy + `/internal/embed` reuse (C10), schema-gov generation + `origin='enriched'` tagging (C11), canon-verify + injection-defense (C12), proposal store mirroring pending_facts (C2/Q1), review API (list/approve/reject/edit/`promote`) + write-back via glossary `extract-entities`/wiki (C13)

## Scope (IN)
- End-to-end **job runner** (`app/jobs/runner.py` or equivalent) chaining the existing P1 stages: gap-detect (C7) → template (C9) → retrieval (C10) → schema-gov gen + H0 tag (C11) → canon-verify (C12) → proposal persist (quarantined, Chinese) → expose for review (C13).
- **Redis Streams events**: emit `lore_enrichment.job.{started,stage_completed,proposal_created,paused,completed,failed}` on a stream key; consumer-group-safe; idempotent producer (dedupe key per job+stage).
- **Cost-cap orchestration**: per-job estimate before start; running tally; **reserved eval-cost line** (M5) counted into the cap; **pause** (not crash) on cap breach; resume after author raises cap. Reuse the C8 cost guardrail — do not re-implement.
- **Demo wiring**: a runnable entry (script/endpoint) that runs the full P1 job over the 4 locked LOCATIONS (玉虛宮, 碧遊宮/金鰲島, 蓬萊, 陳塘關) on a seeded Fengshen KG/corpus.
- `scripts/raid/verify-cycle-14.sh` — the cycle's CI gate (created by this runner).
- Live cross-service smoke: full P1 job → enriched quarantined proposals → review → author promote → write-back observed in glossary.

## Scope (OUT — explicitly)
- **No NEW enrichment logic** — gap model, strategies, generation, verify, review are owned by C6–C13. C14 only orchestrates them.
- **No P2/P3 strategies** (fabrication c / re-cook d) — those are C16/C17, gated behind C15.
- **No eval framework** — C15 owns the eval suite/gate. C14 only RESERVES the eval-cost budget line; it does NOT run or score eval.
- **No direct Neo4j canonical writes** — write-back goes through glossary SSOT only (Q2); `glossary_sync` (C4/K14) propagates to Neo4j.
- **No edits to** `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`; **no edits to** `tests/quality/` climate/geo eval files.
- **No hardcoded model names** — Qwen 3.6 + bge-m3 resolved via provider-registry, never literals.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `services/lore-enrichment-service/tests/test_job_runner.py` (stage chaining, pause-on-cap, idempotent event emit), `tests/test_job_events.py` (Redis Streams contract). Run via the service's pytest.
- Lints pass: ruff/mypy for the service; secret-scan clean (no hardcoded secrets/model names).
- **Live-smoke token REQUIRED** (cross-service, ≥2 services — CLAUDE.md VERIFY rule): evidence string MUST carry `live smoke: full P1 job on Fengshen → quarantined enriched proposals → review → author promote → write-back to glossary observed`. If full stack not bootable, use `live infra unavailable: <reason>` or `LIVE-SMOKE deferred to D-C14-LIVE-SMOKE` (track row in SESSION_PATCH). Mock-only green is NOT sufficient.
- `scripts/raid/verify-cycle-14.sh` exits 0 (runs the suite + asserts the demo job reaches `completed` and every proposal carries `source_type='enriched'` + `pending_validation=true` + `confidence<1.0`).

## DPS parallelism plan
- **DPS 1 — Job runner + state machine wiring** (`app/jobs/runner.py`, `app/jobs/stages.py`): chain C7→C13 stages, estimate/start/pause/resume/cancel reusing C8 guardrail; on cap breach → pause + event, never crash. (return budget: 1500 tokens summary)
- **DPS 2 — Redis Streams events + cost-cap eval line** (`app/jobs/events.py`, cost tally): idempotent producer (dedupe per job+stage), consumer-group-safe stream contract; add reserved eval-cost budget line into the per-job cap. (return budget: 1500 tokens)
- **DPS 3 — Demo wiring + verify script + tests** (`scripts/raid/verify-cycle-14.sh`, demo entry over 4 locked LOCATIONS, `tests/test_job_runner.py`, `tests/test_job_events.py`): seed-fixture-driven; assert H0 markers on every proposal. (return budget: 1500 tokens)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak (highest risk):** does ANY path let an enriched proposal land as canon without explicit author promote? Confirm every written proposal carries `source_type='enriched'`(or `enriched:<technique>`) + `pending_validation=true` + `confidence<1.0`, quarantined, visibly distinct from `source_type='glossary'`. Promotion must retain permanent origin marker (`origin='enrichment'`, `promoted_from_proposal_id`, `promoted_by`, `promoted_at`, `original_technique`).
- **Cross-service mock-only false-green:** the unit suite passing while the real glossary write-back / Redis emit is broken. Demand the live-smoke token; verify the write-back actually hits glossary `extract-entities`/wiki and `glossary_sync` (C4) carries it to Neo4j — not a stubbed client.
- **Event idempotency / partial-failure:** re-running or crash-resuming a job must not double-emit `proposal_created` or double-write proposals. Check dedupe key + at-least-once consumer assumptions.
- **Cost-cap correctness:** breach must PAUSE (resumable) not crash/silently-drop; eval-cost line must be counted into the cap, not ignored.
- **Hardcoded model names / secrets:** grep for `qwen`, `bge-m3`, raw URLs/keys — all must resolve via provider-registry / env.
- **Scope creep:** any NEW gap/strategy/gen/verify/eval logic implemented here instead of orchestrating C6–C13 is a violation.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All Scope (IN) items present: job runner, Redis Streams events, cost-cap with eval line, demo wiring over 4 LOCATIONS, verify-cycle-14.sh.
- No Scope (OUT) items touched: no new pipeline logic, no P2/P3, no eval framework, no direct Neo4j writes, no world-service/game-server/infra/existing-prod or climate/geo eval edits.
- All acceptance criteria met incl. live-smoke token present (or explicit deferral/infra-unavailable token).
- Cross-cycle invariant intact: H0 quarantine holds end-to-end; write-back via glossary SSOT only.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C14 row + demo milestone + parallelism + cross-service list): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- LOCKED decisions (full): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — H0, Q-R1, Q-R2, Q1, Q2, Q3, Q6
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md), [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): H0, Q-R1, Q-R2, Q1, Q2, Q3, Q6

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (enriched != canon):** every proposal written end-to-end MUST be `source_type='enriched'` + `pending_validation=true` + `confidence<1.0`, quarantined; ONLY author promote canonizes, and promoted entity keeps a permanent origin marker. No silent canon path.
- 🔴 **Q2 (write through SSOT):** write-back goes through glossary (`extract-entities` + wiki); `glossary_sync` (C4) propagates to Neo4j. NEVER write Neo4j canonical content directly.
- 🔴 **Q-R2 + cost discipline:** P1 only (template+retrieval). Cost-cap MUST include the reserved eval-cost line (M5) and PAUSE (resumable) on breach — never crash. No P2/P3, no eval scoring (that's C15).
- 🔴 **Acceptance MUST include:** cross-service `live smoke:` token (full P1 job → quarantined proposals → review → promote → write-back). Mock-only green fails the gate; if stack unbootable use the explicit deferral/infra-unavailable token.
- 🔴 **Do NOT touch:** no NEW pipeline logic (orchestrate C6–C13 only); no world-service/game-server/tilemap/infra/existing-prod; no `tests/quality/` climate/geo eval files; no hardcoded model names (Qwen/bge-m3 via provider-registry).
- 🔴 **Fresh session reminder:** this is a new `/raid 14` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
