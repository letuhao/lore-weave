# Plan — Enrichment Production-Ready Quality (epic LE-PROD)

**Date:** 2026-06-04 · **Branch:** lore-enrichment/foundation · **Size:** XL (spec+plan, sliced)
**Origin:** user-scenario E2E (Playwright MCP) surfaced two findings; PO chose the most
ambitious scope (ingest real corpus + build eval suite).

## Findings → verdicts (root-caused, not assumed)

1. **`KeyError: <EntityKind.CHARACTER: 'character'>` on 3 failed jobs (6/3).**
   **Root cause = ALREADY FIXED.** The original `dimensions_for` (commit `8bd4834d`) did
   `DIMENSIONS_BY_KIND[kind]` and its docstring literally said *"Raises KeyError for an
   entity-kind that has no modeled dimension set"* — the service was LOCATION-only.
   De-bias C1 (`e783d039`) added the multi-kind tables AND switched to
   `.get(kind, GENERIC_DIMENSIONS)`. The 3 rows are stale pre-fix artifacts (all dated
   6/3, `entity_kind='location'`); a `retrieval|character|completed` row exists from the
   SAME day after the fix. Live problem is only: (a) raw Python tracebacks shown to users,
   (b) stale rows polluting the Jobs panel.

2. **P1 retrieval returns empty ("检索片段未提及") or regurgitation-auto-rejected.**
   **Root cause = grounding starvation (data), not a code bug.** The demo project has only
   5 one-chunk corpora (4 ephemeral compose pastes + 1 tiny stub). The book's 5 chapters
   live in book-service/MinIO but were never ingested as `source_corpus`; knowledge digest
   for the book is empty (no passages); glossary descriptions are thin. So retrieval embeds
   a query and finds ~1 weak chunk → LLM honestly says "未提及" or parrots it → auto-reject.

## Scope (PO-approved)

- Retrieval: thin-grounding UX **+ ingest the real 封神演义 corpus**.
- Eval-suite (LE-debias-eval-suite): **in scope this round** (was deferred).

## Slices (each: full 12-phase workflow + /review-impl + own commit)

### Slice A — Honest failure surfacing + KeyError regression lock  `[FS, S–M]`
- **BE test:** `dimensions_for`/`resolve_dimensions`/`_gap_from_target` over every built-in
  `EntityKind` + an unknown kind → GENERIC fallback, NEVER raises. Permanently locks the C1 fix.
- **FE:** JobsPanel maps `error_message` for display — friendly headline (known-cause map +
  generic "internal error" fallback), raw detail demoted to title/expander. Never render a
  raw `KeyError: <…>` as primary text. i18n parity (en/vi/ja/zh-TW).
- **Data:** GC the 3 stale pre-fix `KeyError` rows (confirmed fixed; documented in SESSION).

### Slice B — Thin-grounding detection + actionable result  `[FS, M]`
- **BE:** typed `InsufficientGroundingError` raised in `GapPipeline.run_gap` BEFORE the
  generation LLM call when composed grounding is empty OR below a quality bar (top score <
  threshold and/or total grounding chars < N). Config-driven thresholds (`config.py`,
  conservative defaults). Runner treats it like `GenerationError` (skip, no wasted spend)
  but records a distinct user-facing reason + `grounding_strength` (count, top score).
- **FE:** when a gap is skipped for thin grounding, show actionable copy ("chưa đủ nguồn —
  paste context / đính kèm file / dùng Fabrication") + a grounding-strength indicator. i18n.

### Slice C — Ingest the book's chapters as a retrieval corpus  `[BE+data, L]`
- **BE:** generic ingest path (script + optional internal endpoint) that pulls a book's
  chapters from book-service (text in MinIO via `storage_key`), chunks + embeds via the
  existing `ingest_corpus` seam, tagged CURATED (non-ephemeral, license=public_domain),
  idempotent (content-hash names). `book_id` param — not hardcoded to the demo.
- **Verify (live-smoke):** after ingest, a P1 retrieval job on a demo location/character
  grounds on real chapters → coherent, non-empty, non-regurgitated output.
- Note: 5 chapters = partial corpus; additive (more chapters later improve coverage).

### Slice D — Output-quality eval suite (LE-debias-eval-suite)  `[BE, L]`
- **BE:** harness (under `eval/`) running a fixture gap-set through the pipeline, scoring:
  grounding-faithfulness (reuse regurgitation/contradiction signals + a faithfulness check),
  coherence, dimension-coverage. Emits a JSON+markdown report + a pass/fail gate threshold.
- Wire a passing run into the existing eval-gate seam (the gate-aware factory already reads
  an eval gate — this suite produces the passing run that unlocks P2/P3 legitimately).

## Order & dependencies
A (independent, fast, kills the scary UX) → C (corpus = prereq for good retrieval + a
meaningful eval) → B (thin-grounding UX, complements C) → D (eval validates the whole).

## Invariants held throughout
- H0 (origin='enrichment', confidence<1.0, quarantined, promote-only). No hardcoded secrets
  (env). No hardcoded model names (model_ref via provider-registry). Glossary = SSOT for
  taxonomy. Stage only changed files. Faithful VERIFY evidence (cross-service live-smoke).
