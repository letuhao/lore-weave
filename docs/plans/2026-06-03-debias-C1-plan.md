# C1 — BE de-bias core · build plan · 2026-06-03

> Cycle 1 of [the de-bias decomposition](2026-06-03-debias-cycle-decomposition.md). Slices 0a+0b.
> Design: [spec](../specs/2026-06-03-enrichment-debias-book-profile.md). **Size: XL** (≥10 files, side effects: new table/migration, API, cross-service write-back). Full 12-phase v2.2; CLARIFY+DESIGN inherited from the (approved) spec.
> Branch `lore-enrichment/foundation`. Service: `services/lore-enrichment-service`.

## Goal
Generation + verification + the gap/dimension model + the promote write-back produce CORRECT output for ANY book / entity-kind / language — with the Fengshen demo byte-identical (no regression). Still uses existing grounding (C2 reworks grounding).

## Invariants (must hold at VERIFY)
- **No-regression:** Fengshen profile → prompts/markers/dimension-labels byte-identical → existing 562+ tests stay green.
- **H0 untouched:** confidence<1.0, origin immutable, promote-only — no guard loosened; write-back de-bias only changes kind/language/fallback-dimension, never an H0 column.
- **No glossary Go / book-service Go change.**

## TDD task order (write the test first, then the code)

| T | What | Files | Test-first |
|---|---|---|---|
| **T1** | `enrichment_book_profile` table (DDL + DOWN_DDL, idempotent, no FK) | `app/db/migrate.py` | `tests/db/test_migration_roundtrip.py` — table created + up→down→up clean |
| **T2** | `BookProfile` frozen model + `get_book_profile(pool, book_id)` + `NEUTRAL_PROFILE` (unset → neutral: lang=auto, era=None, markers=(), overrides={}) | new `app/db/book_profile.py` | new `tests/db/test_book_profile.py` — unset→neutral; set→fields round-trip |
| **T3** | Fengshen constants (`FENGSHEN_*`: worldview/era/voice) + `FENGSHEN_ANACHRONISM_MARKERS` (lifted from canon_verify) + seed script | new `scripts/seed_fengshen_profile.py`, `app/verify/canon_verify.py` (rename constant) | seed idempotent (db test or script self-check) |
| **T4** | `StrategyContext.profile: BookProfile = NEUTRAL_PROFILE` (additive); resolve in `assembly.build_live_runner` (from `book_id`) → context + verifier; worker `resume_consumer` resolves from request `book_id` | `app/strategies/base.py`, `app/jobs/assembly.py`, `app/worker/resume_consumer.py` | `tests/test_job_runner.py` / new — context carries profile; assembly resolves (mock reader) |
| **T5** | Stop gating on enums: loosen `entity_kind`/dimension field types to `str` (keep `EntityKind`/`Dimension` as constants); add CHARACTER/ITEM/FACTION/EVENT/GENERIC static tables + `label_for(id, language)` localization (zh labels == today's) | `app/gaps/model.py` | `tests/test_gap_model.py` — each kind resolves a table; unknown→GENERIC (no KeyError); `label_for("history","zh")=="历史"` |
| **T6** | `resolve_dimensions(kind, profile)` = static → localize(language) → merge `dimension_overrides` (add/remove/relabel/reweight); stable-id identity; update `engine.py` + `retrieval.strategy` (`_gap_query`/`_dimension_slots`) to call it | `app/gaps/model.py`, `app/gaps/engine.py`, `app/retrieval/strategy.py` | `tests/test_gap_engine.py`, `tests/test_retrieval_strategy.py` — neutral-en dims localized; override add/remove applied; Fengshen-zh unchanged |
| **T7** | Parameterize prompt builders with `(profile, kind_label)` + **instruction in target language** | `app/generation/generate.py`, `app/strategies/fabrication.py`, `app/strategies/recook.py` | `tests/test_generation.py` + new golden — Fengshen profile → **byte-identical** prompt; neutral-en → English instruction, no 封神/商周/中文/地点 |
| **T8** | Profile-driven anachronism: `CanonVerifier(anachronism_markers=…)`; neutral (no era/markers) → check OFF; thread markers from profile in assembly | `app/verify/canon_verify.py`, `app/jobs/assembly.py` | `tests/test_canon_verify.py` — Fengshen markers identical; empty markers → zero anachronism flags |
| **T9** | Detect-path de-bias: `coverages_from_rows` resolves per-kind via `resolve_dimensions` (no skip; GENERIC fallback); drop `AutoEnrichTarget.entity_kind="location"` default + `create_job(entity_kind="location")` (carry the real kind) | `app/api/gaps.py` | `tests/test_gaps_api.py` — a CHARACTER coverage row produces a gap (not skipped) |
| **T10** | **Write-back de-bias (KB8, H0-critical):** `_location_kind_code`→ the proposal's real `entity_kind`; `source_language` from `profile.language` (not `"zh"`); neutral fallback dimension id (not `"补充"`) | `app/services/writeback.py`, `app/clients/writeback.py` | `tests/test_clients.py` / writeback tests — kind_code = real kind; fallback dim neutral; **CHARACTER promote resolves correct glossary kind** |
| **T11** | Test-ripple migration (~6-7 files): enum-instance asserts, anachronism-ON tests inject `FENGSHEN_ANACHRONISM_MARKERS`, write-back kind asserts | `tests/test_gap_model.py`, `test_gap_engine.py`, `test_canon_verify.py`, `test_auto_reject.py`, `test_eval_scorers.py`, `test_clients.py` | (the migration itself) |
| **T12** | VERIFY: full unit suite green + **live smoke** — Fengshen no-regression run + a CHARACTER (and an English-profile) enrich→promote end-to-end on the demo | — | `live smoke: <one-liner>` evidence token |

## Acceptance (VERIFY gate)
1. `pytest` green incl. all migrated tests (Fengshen byte-identical golden passes).
2. Live smoke: a CHARACTER gap on the demo book enriches with correct dimensions + promotes → glossary supplement on the correct-kind canonical entity, keyed by stable id. (English-profile book: prompt in English, anachronism off.)
3. No H0 guard touched (DB trigger + CHECKs unchanged; confidence<1.0 holds).

## Risks
- **Stale-image / build-stack** (recurring op note): rebuild via `scripts/build-stack.sh` + `up -d --force-recreate` before the live smoke; freshness guard.
- **LM Studio JIT eviction** on multi-gap — use a single-gap CHARACTER for the live smoke.
- **Cross-service** (lore-enrichment + glossary on promote) → VERIFY needs a `live smoke` token (CLAUDE.md cross-service rule).

## Phases
CLARIFY ✅(spec) → DESIGN ✅(spec) → REVIEW(design, this cycle) → PLAN ✅(this file) → BUILD(T1–T11) → VERIFY(T12) → REVIEW(code, 2-stage) → QC → **POST-REVIEW + /review-impl** (write-back) → SESSION → COMMIT → RETRO.
