# M7 — Translation Feedback → Learning (spec / plan-of-record)

**Date:** 2026-06-08 · **Branch:** `feat/translation-pipeline-v3` · **Mode:** v2.2 + `/review-impl` (no AMAW, PO 2026-06-08)
**Why:** translation is **not wired to learning-service** at all — no signal is collected for future tuning. Production-readiness gate (PO: "won't merge to main until translation is production-ready"). The user emphasised: human review **and adjustment** + an LLM-action log are the levers for future quality correction; without collection there is no way to tune.

## Current gap (investigated 2026-06-08)
- translation emits ONE event: `chapter.translated` → **statistics-service** (tokens/status only, no quality content).
- learning consumes `glossary` (actor=user), `knowledge`, `chat` — **NOT translation**.
- `target_kind` enum has no `translation`.
- `translation_quality_issues` + chapter `quality_score`/`unresolved_high_count`/`qa_rounds_used` exist but stay **local**.
- **No human-edit-translation feature** — `TranslationViewer` is read-only (copy/compare/set-active). The richest signal (LLM-draft ↔ human-edit diff) has no source yet.
- M6a name-confirm emits `actor=pipeline` → learning ignores it.

## Reused infrastructure (proven)
- **Q3a (chat feedback)** = emit template: `outbox_events(event_type, aggregate_type, aggregate_id, payload)` → worker-infra relay → `loreweave:events:<stream>` → learning.
- **Q2 (corrections-as-gold)** = before/after projection template.
- learning `dispatcher.register(event_type, handler)` + `persist_consumed_score(target_kind, target_id, user_id, book_id, metric, value, source, …)` + `ensure_score_configs` seed + `score_config` validation.

## Three channels → four slices (PO: slice + checkpoint each)

### M7a — Channel 2: LLM action log (data already exists) — FIRST
On chapter-translation completion, emit a quality-rollup event → learning persists an **auto** signal so the LLM's behaviour is queryable for tuning.
- translation: emit `translation.quality` (per chapter_translation) with `quality_score`, `unresolved_high_count`, `qa_rounds_used`, per-issue-type counts, `pipeline_version`, `target_language`.
- learning: consume on `loreweave:events:translation`; `target_kind=translation`, `target_id=chapter_translation_id`, metrics `translation_quality_score` (+ issue-rate); `source=auto`; idempotent on `origin_event_id`; per-owner; score_config seeded.

### M7b — Channel 1a: existing human judgment signals
Wire the human actions that ALREADY exist → learning (`source=human`): set-active (version chosen), M5b publish-accept (override gate), M6a name-confirm (currently actor=pipeline — give it a learning-visible path). Metrics e.g. `translation_human_accept`, `translation_version_chosen`.

### M7c — Channel 1b: human-edit feature + before/after gold (the richest signal)
**Build** a human-edit-translation capability (save an edited version) + FE editor, then capture `translation.corrected` carrying the LLM-draft ↔ human-edit diff → learning gold (`source=human`, before/after like Q2). This is the gold the user wants for tuning.

### M7d — Channel 3: online LLM-judge of translation fidelity (heaviest, last)
Mirror Q4b: a judge scores translation fidelity vs source → `quality_scores(metric=translation_judge_fidelity, source=auto, panel_safe=false)`. Config + feed gated, off by default.

## Cross-cutting
- New stream `loreweave:events:translation` (relay source mapping in worker-infra + compose).
- New `target_kind=translation`; new score_config rows (numeric metrics).
- Additive throughout; V2 byte-parity unaffected; per-owner isolation; idempotent dedup.
- Each slice: v2.2 + `/review-impl`; cross-service ⇒ live-smoke token at VERIFY.
