# Plan — M4d-2: 2-pass cold-start translation (full-spec source→target seeding)

- **Date:** 2026-06-07
- **Branch:** `feat/translation-pipeline-v3`
- **Size:** XL, cross-service (translation-service + glossary-service), 3 LLM passes. **Sliced** → 2a/2b/2c.
- **Spec:** §11.3.C + §12 of `docs/specs/2026-06-06-translation-pipeline-v3-multi-agent.md`.
- **Mode:** v2.2 + mandatory `/review-impl` (PO 2026-06-07).

## Goal

For **cold-start** books (empty glossary), improve proper-noun consistency by translating twice:
pass 1 translate → **extract source→target name pairs** → seed them into the glossary as
**drafts with target translations** → re-fetch the (now-seeded) glossary → pass 2 re-translate with
the seeded names enforced. Opt-in via a `cold_start_mode` setting; **V2 parity preserved**.

## Why the full spec needs new components (CLARIFY finding 2026-06-07)

The literal spec ("seed glossary → re-translate with glossary") cannot reuse existing parts:
- Translation's extraction prompt is **source-language-only** (`extraction_prompt.py:25` — "Do NOT
  translate") → yields source names, **no target**.
- `post_extracted_entities` + glossary `extract-entities` (`extractedEntity` struct) carry **no
  translation field** → seeding stores source names with empty targets → pass 2 has nothing to
  enforce → no consistency gain.

So the goal requires a **new bilingual (source→target) extractor** + **glossary writeback that
carries the target translation**. The PO chose to build these (over the lightweight in-run hint).

## Slices

### M4d-2a — Bilingual source→target name extractor (translation-service) — THIS PASS
- NEW `app/workers/v3/bilingual_extractor.py`:
  - `NamePair(source, target, kind)` dataclass.
  - `BILINGUAL_EXTRACT_PROMPT` — given the source chapter + its pass-1 translation, emit JSON
    `[{source, target, kind}]` for **recurring proper nouns** (characters/places/items). Bounded count.
  - `extract_name_pairs(source_text, translated_text, source_lang, target_lang, *, llm_client, msg)
    → list[NamePair]` — build prompt, one LLM call, tolerant JSON parse, **best-effort** (any
    failure → `[]`, never raises). Mirrors `llm_verifier.llm_verify` invocation conventions.
- Tests: prompt build, parse (valid / malformed / empty / non-list), degrade-on-error, recurrence
  filtering. Hermetic (FakeLLMClient).
- **Self-contained** (no orchestrator wiring yet — like M4a "client only").

### M4d-2b — Target-translation writeback (cross-service) — DEFERRED row D-TRANSL-M4D2B
- glossary `extract-entities`: extend `extractedEntity` with an optional per-entity target
  translation (`{language_code, value}`) → on upsert, write an `attribute_translations` row for the
  `name` attr at `confidence='machine'` (so the M1d trust ladder treats it as a soft hint, not canon).
  Backward-compatible (omitted → today's behavior).
- translation: a writeback path that sends `NamePair` rows as entities **with** the target translation
  + `default_tags=['ai-suggested']` (reuse mui#1's draft-inbox surface).

### M4d-2c — Orchestrator 2-pass + config plumbing — DEFERRED row D-TRANSL-M4D2C
- `cold_start_mode = single_pass (default) | two_pass`, plumbed settings→job→coordinator→worker
  (mirror `qa_depth`; `effective_settings` + `CreateJobPayload` validator + `jobs.py` INSERT +
  `coordinator.py` forward).
- Orchestrator: when glossary is empty (cold start) AND `two_pass` AND the extractor found recurring
  pairs → pass 1 translate → `extract_name_pairs` → writeback (2b) → re-fetch glossary →
  **pass 2 re-translate** with the seeded glossary. Guard the 2× cost (skip when no recurring names).
  V2 path untouched.

## Risks / open points
- 3 LLM passes (translate ×2 + extract) — cost. Gate pass-2 on "found recurring names" + opt-in only.
- Overlaps mui#1 (KG→glossary end-of-book writeback) — 2b uses the SAME draft surface + `ai-suggested`
  tag + `ai-rejected` tombstone, so they converge rather than conflict; targets land at
  `confidence='machine'` (trust ladder demotes → no false canon).
- Cold-start detection = empty `translation-glossary` fetch (already computed in the orchestrator).
