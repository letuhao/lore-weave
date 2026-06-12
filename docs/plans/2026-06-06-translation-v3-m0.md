# M0 Plan — Translation V3 Readiness Gate + Scaffold

> **Feature:** [Translation Pipeline V3](../specs/2026-06-06-translation-pipeline-v3-multi-agent.md) · **Branch:** `feat/translation-pipeline-v3`
> **Milestone M0** (of M0–M6, see design §12.4). **Size:** L. **Flag:** ships with `pipeline_version` default `'v2'` → zero behavior change in prod.
> **Goal:** lay the foundation so later milestones (and any benchmarking) are *possible and safe* — instrumentation, persistence, the flag, and the tech-debt fixes — with **behavioral parity** to V2 when the flag is off.

## Why M0 first
The benchmark-readiness review ([arch review](../specs/2026-06-06-translation-v3-architecture-review-benchmark.md) §4) showed there is **no metrics module** and the block pipeline writes **no per-batch rows** — so today there is nothing to measure and no place to attach quality data. M0 fixes that substrate before any agent logic lands. It also clears the load-bearing tech debt (memo dead-code, non-transactional job insert) so M1+ build on a correct base.

## Scope (tasks, TDD order)

| ID | Task | Files | Test-first |
|----|------|-------|-----------|
| **T0.1** | **V8 schema (additive, idempotent)** — `pipeline_version` + `verifier_model_source/ref` + `max_qa_rounds` + `qa_depth` on prefs/book/job; `translation_quality_issues` table; `chapter_translations` rollup cols (`quality_score`, `unresolved_high_count`, `qa_rounds_used`) | `app/migrate.py` | assert DDL applies + columns exist (migrate smoke test) |
| **T0.2** | **Fix TD1 memo wiring** — thread `prev_memo` into `translate_chapter` / `translate_chapter_blocks`; fix `_save_chapter_memo` to build `story_summary` from the **translated block text** (not the always-`None` `translated_body_text`) | `app/workers/chapter_worker.py`, `session_translator.py` | test: block-pipeline chapter writes a non-empty memo; memo passed into pipeline |
| **T0.3** | **Block pipeline chunk rows (TD3 / W11)** — write `chapter_translation_chunks` per batch incl. `validation_errors/warnings`, `glossary_corrections`, `retry_count`; enables resume + per-batch trace | `session_translator.py` (block path) | test: N batches → N chunk rows with metrics populated |
| **T0.4** | **Instrumentation (W10)** — a small `app/metrics.py` emitting structured stage events (per-chapter & per-batch: latency, in/out tokens, calls, retries, outcome). Prometheus counters if a metrics dep is available; else structured-log fallback | `app/metrics.py` (new), wired in `chapter_worker.py` / `session_translator.py` | test: a translated chapter emits the expected stage events |
| **T0.5** | **Txn around job+chapters insert (W7)** | `app/routers/jobs.py` | test: simulated mid-loop failure leaves **no** partial job (rollback) |
| **T0.6** | **`pipeline_version` plumbing** — snapshot in `jobs.py` + `effective_settings.py`; carry in coordinator message; branch in `chapter_worker._process_chapter` | `jobs.py`, `effective_settings.py`, `coordinator.py`, `chapter_worker.py`, `models.py` | test: job with `pipeline_version='v3'` routes to v3 entrypoint |
| **T0.7** | **V3 package skeleton (parity)** — `app/workers/v3/__init__.py` + `orchestrator.translate_chapter_v3(...)` that, for now, **delegates to V2** `translate_chapter_blocks` (proves the flag path end-to-end with zero behavior change) | `app/workers/v3/` (new) | test: v3 entrypoint output == v2 output for a fixture chapter |

## Out of scope for M0 (later milestones)
Verifier/Corrector logic (M1/M2), romanization (M1), `select-for-context` upgrade (M1), knowledge layer (M4), concurrency knob + cost caps (M0.5 — separate small plan), DLQ reprocessing, sync-path convergence (M5).

## Acceptance / VERIFY
- Full `services/translation-service/tests/` suite green.
- With `pipeline_version='v2'` (default): **byte-identical** behavior to pre-M0 for a fixture chapter (parity test T0.7 + existing suite).
- With `pipeline_version='v3'`: routes through the skeleton, same output (parity).
- Cross-service note (CLAUDE.md ≥2-service rule): M0 is translation-only except the schema; evidence string will carry `live infra unavailable: <reason>` or a real smoke if a stack-up is bootable.
- Migration is additive/idempotent (`IF NOT EXISTS`) → rollback = flip flag + (optionally) drop new cols; no data migration.

## Risks
- Memo-wiring change touches the hot path → guard behind tests + keep V2 output identical (parity test is the gate).
- Instrumentation overhead must be negligible (structured events, no per-token work).
- `/amaw` recommended at **M2** (the multi-agent loop) rather than M0 — M0 is additive/mechanical, low adversarial-review value.
