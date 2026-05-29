# Cycle 2: Data model + H0

## 🎯 TL;DR (30 seconds — TOP critical info)
Author the persistence layer for `lore-enrichment-service` in its **own** DB `loreweave_lore_enrichment`: Alembic-style migrations for 5 tables — `enrichment_job`, `enrichment_proposal`, `source_corpus`, `enrichment_template`, `cultural_grounding_ref`. The proposal table carries the **H0 invariant** (enriched lore != canon): `origin`, `technique`, `provenance_json`, `confidence` (<1.0), `source_refs_json`, `cultural_grounding_ref`, and the `review_status` lifecycle `proposed → author_reviewing → approved → promoted | rejected`, plus `promoted_entity_id/by/at`. This is **L+ DB work**: ship a clean reversible down-migration and an H0 lifecycle round-trip test. No business logic, no API handlers, no glossary/KG writes — schema + migration + test only.

**Acceptance gate:** `scripts/raid/verify-cycle-2.sh` exits 0 (created by this cycle's runner; forward ref is fine).

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- C0 gives the FastAPI skeleton, `config.py` (fail-fast secrets), DB pool/`deps.py`, and the `loreweave_lore_enrichment` DB wiring + docker-compose. C2 builds the migrations and ORM models on top of that pool. No dependency on C1/C3 (parallel siblings under C0).

## Scope (IN)
- **Migration tooling**: Alembic (or Alembic-style) env wired to the C0 DB pool; one revision creating all 5 tables; reversible `downgrade()` that drops them cleanly (reverse dependency order).
- **`enrichment_job`**: id, project_id, user_id (per-user/per-project scoping, Q3), status/state-machine column, technique, cost fields, timestamps.
- **`enrichment_proposal`** (H0 carrier): id, job_id FK, entity-kind/target, generated content (Chinese, source-faithful), **`origin`** (e.g. `enrichment`), **`technique`**, **`provenance_json`**, **`confidence`** (NUMERIC, CHECK < 1.0), **`source_refs_json`**, **`cultural_grounding_ref`** FK, **`review_status`** enum/CHECK (`proposed|author_reviewing|approved|promoted|rejected`), **`promoted_entity_id`**, **`promoted_by`**, **`promoted_at`**.
- **`source_corpus`**: id, project_id, name, kind (e.g. 山海经/Fengshen), license/provenance metadata.
- **`enrichment_template`**: id, entity-kind, dimension set, scaffold body, version.
- **`cultural_grounding_ref`**: id, source_corpus_id FK, chunk/citation locator, text excerpt — the anchor a proposal cites.
- **H0 lifecycle round-trip test**: insert proposal (`proposed`, confidence<1.0, origin set) → advance through `author_reviewing → approved → promoted`, asserting `promoted_entity_id/by/at` populate only on `promoted`; assert a `rejected` terminal branch; assert no path sets confidence to 1.0 or strips `origin`.
- **Migration up/down test**: apply `upgrade()` then `downgrade()` on a throwaway DB; assert clean teardown + re-apply (idempotent round-trip).

## Scope (OUT — explicitly)
- NO API handlers / endpoints (that is C3 contract + stubs).
- NO strategy/generation/gap logic (C7–C12), NO orchestration (C14).
- NO writes to glossary SSOT or Neo4j (that is C13 via `extract-entities` + wiki; **NEVER** write Neo4j canonical content here, Q2).
- NO knowledge-service / embedding calls (C10 owns `/internal/embed` reuse).
- NO model names hardcoded anywhere (resolved via provider-registry; none belong in schema).
- DO NOT touch `world-service`, `game-server`, `tilemap`, `infra/existing-prod/`, or other agents' files (schema is isolated, Q5).
- DO NOT edit climate/geo eval files or `tests/quality/` judge files.

## Acceptance criteria (CI gates — exit code 0 = pass)
- `scripts/raid/verify-cycle-2.sh` exits 0, asserting:
  1. `upgrade()` applies cleanly on a fresh `loreweave_lore_enrichment` (all 5 tables + FKs + CHECK constraints present).
  2. `downgrade()` reverses to empty with no orphaned objects; up→down→up round-trip is idempotent.
  3. H0 lifecycle round-trip test passes: `review_status` transitions valid; `promoted_*` only on promote; `confidence < 1.0` enforced by CHECK; `origin` non-null/immutable in the round-trip.
  4. Service unit suite green (`pytest` in the service dir).
- **Cross-service: NO.** Single-service, single-DB schema change → no live-smoke token required.

## DPS parallelism plan
- DPS A — **migration + ORM models**: write Alembic revision (`upgrade`/`downgrade`) + SQLAlchemy models for all 5 tables. Owns enum/CHECK definitions.
- DPS B — **tests**: H0 lifecycle round-trip + up/down idempotency test + `verify-cycle-2.sh`. Depends on A's table/column names (agree the column contract first, then run in parallel).
- Single migration file + single models module → keep DPS count low (2) to avoid merge churn on the revision file. Serialize only the final revision-id stamp.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak**: can any column default or transition let an enriched proposal look like canon? Confidence must be CHECK `< 1.0`; `origin` non-null with no canon default; no `source_type='glossary'` shortcut. Promotion must RETAIN the permanent origin marker (`promoted_from_proposal_id`/`promoted_by`/`promoted_at`/original technique) — never erase provenance.
- **Down-migration correctness**: does `downgrade()` drop in reverse FK order without leaving enums/sequences/orphans? Is up→down→up idempotent, or does a re-apply collide?
- **Lifecycle integrity**: are illegal `review_status` jumps (e.g. `proposed → promoted`) blocked by CHECK/enum + test? Are `promoted_*` columns nullable until promote and required at promote?
- **Scoping**: are `project_id`/`user_id` present so Q3 per-user/per-project isolation is enforceable downstream?
- **False-green**: does the round-trip test actually exercise a real DB (not mock-only)? A mocked session that never hits constraints is a fake pass.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only files under the lore-enrichment service migrations/models/tests + `scripts/raid/verify-cycle-2.sh` changed; NO edits to glossary/knowledge-service/world-service/game-server/infra-prod/eval files; NO API handlers or strategy logic added; NO hardcoded model names; H0 columns present with `confidence < 1.0` CHECK and reversible down-migration. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- `docs/plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md` — C2 row + H0 invariant note.
- `docs/plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md` — H0 (lifecycle + permanent origin marker), Q1 (mirror knowledge-service pending_facts), Q2 (write-through SSOT, never Neo4j), Q3 (scoping), Q5 (schema isolation).
- `docs/03_planning/lore-enrichment/PLAN.md` — service/data-model intent.
- `docs/03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md` — ground-truth constraints.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 is the core invariant**: enriched lore != canon. Enforce at schema level — `origin` non-null, `confidence` CHECK `< 1.0`, lifecycle `proposed→author_reviewing→approved→promoted|rejected`; promotion KEEPS the permanent origin marker (`promoted_from_proposal_id/by/at`, original technique). Never default a proposal to canon.
- 🔴 **Acceptance gate**: `scripts/raid/verify-cycle-2.sh` must exit 0 — migration up/down clean (reversible, idempotent) AND H0 lifecycle round-trip test passes against a real DB (no mock-only false-green).
- 🔴 **Do-not-touch**: this DB schema is isolated (Q5). NO writes to glossary SSOT/Neo4j (Q2), NO API handlers (C3), NO strategy logic, NO hardcoded model names, NO edits to world-service/game-server/infra-prod or climate/geo/judge eval files.
