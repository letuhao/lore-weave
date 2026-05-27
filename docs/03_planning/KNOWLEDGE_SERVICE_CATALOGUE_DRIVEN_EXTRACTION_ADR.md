# ADR — Catalogue-Driven Extraction (knowledge-service)

- **Status:** Proposed (`/review-impl` folded: 3 MED + 4 LOW)
- **Date:** 2026-05-22
- **Deciders:** PO (user) + Lead (agent)
- **Supersedes/relates:** `KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`, `87_MODULE05_GENRE_PROFILE_ARCHITECTURE_ADR.md` (genre→kind profiles), `KNOWLEDGE_SERVICE_EMBEDDING_MODEL_REF_ADR.md` (same "knowledge-service imposed a parallel model that diverged from the SSOT" failure shape).

---

## 1. Context — the divergence (verified against code)

LoreWeave's authored SSOT for entity taxonomy is the glossary `entity_kinds` **catalogue** — a data-driven, genre-aware, extensible table, NOT a fixed enum:

- `entity_kinds(kind_id, code, name, icon, color, is_default, is_hidden, sort_order, genre_tags)` — seeded with 12 default kinds (`character, location, item, event, terminology, …`), each with its own per-kind `attribute_definitions` schema; `genre_groups` + `genre_tags` make the visible kind set genre-dependent. (`services/glossary-service/internal/domain/kinds.go`, `internal/migrate/migrate.go`.)
- In this model **"event" is just a kind**, and an event's sub-type (`type`) is **free text** (`kinds.go:105-115`).
- `glossary_entities.kind_id` is a FK into the catalogue.

The knowledge-service extraction layer (added later) imposes its **own hardcoded closed enums** that neither match nor reference the catalogue:

| Axis | Glossary SSOT | Extraction (current) |
|---|---|---|
| Entity kind | open catalogue (12 default, genre-extensible) | `Literal["person","place","organization","artifact","concept","other"]` (6, fixed) — `loreweave_extraction/extractors/entity.py` |
| Event sub-type | free text (`event.type`) | `Literal["action","dialogue","battle","travel","discovery","death","birth","other"]` (8, fixed) — `extractors/event.py` |
| Fact type | (n/a — fact is knowledge-only) | extractor `type` |
| **FE knowledge filter** | (glossary FE fetches catalogue dynamically — `useEntityKinds`) | **hardcoded 3rd vocabulary** `[character, location, organization, concept, item, event_ref, preference]` — `frontend/src/features/knowledge/components/EntitiesTab.tsx:22` |

There are in fact **three** divergent vocabularies (glossary catalogue / extractor 6-enum / FE knowledge filter), none fully aligned — textbook taxonomy rot. Note `event_ref` and `preference` in the FE set match neither the catalogue nor the extractor enum (see R4).

**Pass-1 is already aligned** — `pattern_writer._DEFAULT_ENTITY_KIND = "character"` (a catalogue code). Only the Pass-2 (LLM) extractor diverged; Pass-1 is the model to follow.

A **partial, hardcoded bridge** already exists and confirms the mismatch is real but capped:
- `entity_resolver._EXTRACTOR_TO_GLOSSARY_KIND` maps **6→5** (`person→character, place→location, artifact→item, concept→terminology`; `organization/event` pass through). This is the *only* path from extractor vocab to catalogue vocab.
- `:Entity.kind` is a **Neo4j property** (not a label) → values can change without a graph-schema migration.
- `glossary_sync.sync_glossary_entity_to_neo4j` pulls curated glossary entities INTO Neo4j using the catalogue `kind_code`; `glossary_client.propose_entities` pushes extracted entities OUT to glossary; `select_for_context` already returns `kind_code` — so **retrieval + curation already speak catalogue vocab; only extraction does not.**

### Consequences (the symptoms)

1. **Data loss.** Event sub-type `kind` is validated against the 8-enum and **dropped on mismatch** (`event.py:_tolerant_parse_events` → `ValidationError`) — *and the kind isn't even persisted* (`pass2_writer.merge_event` is called without `kind`). 8/10 golden chapters extracted **0 events**; the 2 that survived happened to use in-enum kinds. Pure liability.
2. **Vocabulary ceiling.** Extraction can emit at most 6 entity kinds → ≤5 catalogue kinds. It is **structurally unable** to produce `terminology`, `trope`, or any genre/user kind (`sect`, `technique`, `cultivation realm`). Genre fiction — a core LoreWeave target — is permanently flattened to `concept`/`other`.
3. **Measurement artifact.** The LLM-judge eval (2026-05-21, see `eval/QUALITY_EVAL_BASELINES.md`) showed extraction *precision ≈ 1.0* (validated by a discrimination probe) — i.e. the model extracts real things; the recall/quality gap is partly the schema **rejecting valid extractions**, not the model failing.

This is the same failure shape as the embedding-model-ref ADR: knowledge-service shipped a parallel taxonomy that diverged from the SSOT and silently degraded the product.

---

## 2. Decision

Adopt **catalogue-driven extraction**: the glossary `entity_kinds` catalogue is the single taxonomy authority; extraction reads it instead of imposing a closed enum, and **never drops** an item for an unrecognised kind.

Resolved design questions (PO-approved 2026-05-22):

1. **Hinge — keep `:Event` as a distinct node; open its sub-type.** `:Event` carries `event_order` (chronology), `chapter_id`, and its own embedding for Mode-3 L4 timeline retrieval (`neo4j_schema.cypher:103-118,209-216`) — semantics a generic typed entity does not have. We do **not** collapse events into the unified kind axis. Instead: drop the 8-value `kind` Literal → free-text sub-type, and **persist it** (`merge_event` gains a `kind`/`subtype` param). Entity `kind` becomes catalogue-driven.
2. **Scope — design both stages; implement Stage 1 now.** Stage 1 = align extraction to the catalogue the glossary exposes (12 seeded kinds today). Stage 2 (user/genre-editable kinds) documented, deferred.
3. **Coupling — knowledge reads the catalogue from glossary** via a new `/internal/books/{book_id}/entity-kinds` endpoint, fetched once per extraction job and cached (TTL, per `(book_id)` — genre-scoped in Stage 2). Approved knowledge→glossary dependency direction (already exists for `known-entities`).
4. **`other` fallback retained** as the safety net: an item whose kind matches nothing in the catalogue is kept (kind coerced to `other` for the graph property) — **never dropped**.

---

## 3. Target architecture

### 3.1 Kind sourcing

- New glossary endpoint `GET /internal/books/{book_id}/entity-kinds` → `[{code, name, description?}]`. Stage 1 returns the **global** non-hidden catalogue (the `entity_kinds` table is seeded globally, not per-book — LOW#2); `book_id` is in the path for forward-compat so Stage 2 can genre-filter by the book's profile without a contract change. Internal-token auth, mirrors `known-entities`.
- New `GlossaryClient.list_kinds(book_id)` (graceful-degrade: returns `None` on failure).
- New `app/extraction/kind_catalogue.py`: fetch + `TTLCache` (per `book_id`, ~5 min) + a **degradation-only fallback constant** mirroring `domain.DefaultKinds` codes, used ONLY when glossary is unreachable (extraction must not block on glossary). LOW#3: this constant is a staleness vector if the catalogue grows — it is acceptable because it is a degradation path, not the primary source; document it as such and keep it minimal.

### 3.2 Prompt change (entity + event)

- Entity prompt: replace the hardcoded `person|place|...` vocabulary with the injected catalogue codes + names ("choose the best-fitting kind from this list; if none fit, use `other`; never omit an entity"). Multilingual examples unchanged.
- Event prompt: `kind` becomes "a short free-text sub-type (e.g. battle, betrayal, coronation)"; keep the rest.

### 3.3 Schema / parser leniency (never drop) + kind normalization

- `extractors/entity.py`: `LLMEntityCandidate.kind` becomes `str` (was effectively enum-bound via downstream); tolerant-parse keeps any non-empty kind, defaults `other`.
- `extractors/event.py`: remove the `EventKind` `Literal`; `_LLMEvent.kind: str = "other"`; `_tolerant_parse_events` no longer drops on kind. (Bug fix folds in here.)
- `pass2_writer.merge_event(... kind=evt.kind ...)` → persist sub-type on `:Event` (new optional property; additive).
- **Kind normalization (MED#2, /review-impl).** An LLM will not echo catalogue codes exactly (`"Character"`, `"char"`, `"faction"` for `organization`). A raw kind string flows into the anchor-lookup key `(folded_name, kind)` (`entity_resolver`) and into the `:Entity.kind` property — a near-miss causes a duplicate entity + an off-vocabulary property value. Add `normalize_kind_to_catalogue(raw, catalogue) -> code`: exact casefold match against catalogue codes → that code; else `other`. Applied in `pass2_writer` BEFORE `resolve_or_merge_entity` and persist. (Replaces the deleted `_EXTRACTOR_TO_GLOSSARY_KIND` translation with a catalogue-aware one.)

### 3.3.1 Event drop — confirm BOTH mechanisms (MED#3)

The kind-enum drop is **not proven to be the dominant** cause of event R≈0. A second filter — `_postprocess` drops events with **no resolvable participants** (`event.py:282-285`) — is untouched by the kind fix. **Stage-1 BUILD MUST first capture qwen3.6's raw `result.events`** for a failing chapter (requires the extraction model loaded) to confirm whether events are lost to (a) out-of-enum kind, (b) missing participants, or (c) the model emitting none. Re-evaluate the no-participants filter (is requiring a named participant too strict for narrative events?) once the raw output is in hand. Do not claim event recall is fixed until measured.

### 3.4 Remove the divergent bridge

- Delete `_EXTRACTOR_TO_GLOSSARY_KIND` + `normalize_kind_for_anchor_lookup` translation (entity_resolver.py:52-84) — extraction now emits catalogue codes directly, so anchor lookup matches without translation. **Audit every caller** before removal (memory `feedback_audit_all_callsites_when_adding_optional_kwarg`).

### 3.5 FE knowledge entity filter (MED#1)

`EntitiesTab.tsx` hardcodes a 3rd kind vocabulary in `KIND_OPTIONS`. Reconcile it to the catalogue: fetch kinds dynamically (the glossary FE already does this via `useEntityKinds`) instead of a literal array, so the filter always matches what extraction writes. In scope for Stage 1 (otherwise the filter silently mismatches the new catalogue-coded entities). Resolve `event_ref` / `preference` first (R4).

### 3.6 Stage 2 (documented, deferred)

User/genre-editable catalogue: glossary-side CRUD on `entity_kinds` (currently "read-only MVP") + genre selection per book wired to `genre_groups`; the `entity-kinds` endpoint filters by the book's genre profile (per `87_MODULE05_GENRE_PROFILE_ARCHITECTURE_ADR.md`). Extraction code is unchanged — it already reads whatever the endpoint returns.

---

## 4. Backward compatibility & migration

- **Existing `:Entity.kind` values** are already a mix of catalogue codes (anchored/glossary-synced entities) and the 6-enum (new extraction). After this change new extraction writes catalogue codes; **old 6-enum values remain** until re-extraction. A one-off backfill (`person→character`, etc., the same map being deleted) can normalise historical nodes — optional, low-priority (the public entity API filters on whatever value is stored).
- `:Event.kind` is a **new additive property**; existing events simply lack it (null).
- No Neo4j schema migration (kind is a property, not a label/constraint).

---

## 5. LLM reliability risk (must measure, not assume)

A larger / dynamic kind vocabulary can REDUCE per-kind classification accuracy — the 6-enum partly existed for LLM reliability. This is now **measurable** with the validated LLM-judge harness:

- Before/after the prompt change, run extraction on the 9 golden chapters → judge precision/recall per category.
- Watch for: kind-misclassification (entity judged `partial` for wrong kind), `other`-overuse (LLM giving up), and whether event recall actually recovers.
- If accuracy drops on the full 12-kind set, fall back to a curated subset per genre (Stage 2 lever) rather than reverting to a closed enum.

---

## 6. Risks / open questions

- **R1 — genre not yet selected per book.** Stage 1 returns all non-hidden kinds; a detective novel sees xianxia kinds. Acceptable for Stage 1 (still better than the 6-enum); Stage 2 genre-filters.
- **R2 — `propose_entities` write-through is unwired in the live pass-2 path** (`pass2_writer` does not call it). Out of scope here, but flag: catalogue-aligned extraction makes wiring it through cleaner later. Track as a separate item.
- **R3 — fact `type`** is left as-is this cycle (facts are knowledge-only, not in the glossary catalogue). Revisit if facts ever anchor to glossary.
- **Q1 — should `:Event.kind` reconcile to a glossary "event sub-type" vocabulary** if Stage 2 introduces one? Defer.
- **R4 — `event_ref` / `preference` in the FE `KIND_OPTIONS`** match neither catalogue nor extractor vocab. Before reconciling the FE filter, determine what writes them: is `event_ref` an entity that points at an `:Event` (a distinct axis), and is `preference` a user-memory kind (chat-turn extraction, not novel content)? They may be legitimate knowledge-only kinds that should NOT be forced into the glossary catalogue. **Investigate during Stage-1 CLARIFY** before deleting/replacing the FE list.

---

## 7. Acceptance criteria (Stage 1)

1. Extraction prompt emits kinds from the injected catalogue; no hardcoded entity/event kind enum remains in the extractors.
2. **Raw qwen3.6 `result.events` captured first** to confirm the event-loss cause(s); no event dropped for an unrecognised kind; the no-participants filter reviewed against the raw output; `:Event.kind` persisted.
3. `normalize_kind_to_catalogue` maps off-vocabulary LLM kinds to a catalogue code (or `other`), applied before anchor lookup + persist; unit-covered incl. near-miss cases.
4. `entity-kinds` endpoint + client + cache + glossary-unreachable fallback, all unit-covered.
5. `_EXTRACTOR_TO_GLOSSARY_KIND` removed; all call sites audited; anchor resolution still matches (regression test).
6. FE `EntitiesTab` kind filter fetches the catalogue dynamically (no hardcoded `KIND_OPTIONS`); `event_ref`/`preference` (R4) resolved.
7. LLM-judge before/after on the 9 golden chapters recorded in `QUALITY_EVAL_BASELINES.md`; event recall measured (judge-coverage caveat noted — the judge itself sat at ~68% precision coverage).
8. Existing unit suites green; no Neo4j schema migration required.
