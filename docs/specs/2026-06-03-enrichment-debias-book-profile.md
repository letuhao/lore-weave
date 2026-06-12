# De-bias enrichment — per-book worldview profile + multi-kind, multi-language generation · 2026-06-03

> **Severity: HIGH production bug.** The enrichment generation + verification + gap
> model are pinned to ONE book's universe (《封神演义》/商周, Chinese, `location`-only).
> **Any non-Fengshen book already gets wrong output, and any non-location entity
> CRASHES** (`dimensions_for(CHARACTER)` → `KeyError`). The platform is multi-book /
> multi-genre, so this is a defect, not a demo limitation. **Foundational fix — do
> BEFORE the Compose build** (Compose's "any subject" premise depends on it).
>
> **Status: DESIGN v2 (detailed, scope-expanded after a full code audit) + adversarial
> design-review pass (decisions A–E folded, 2026-06-03).** Branch
> `lore-enrichment/foundation`. Supersedes the v1 draft (which covered 3 of the 5
> bias layers and missed the multi-kind crash). PO scope locked 2026-06-03 — see §0
> + the review resolutions in §6.

---

## 0. PO-locked scope (2026-06-03)

| Decision | Choice |
|---|---|
| **Depth of fix** | **Full 5 layers + dynamic dimensions** — profile + parameterized prompts + profile-driven anachronism + multi-language + genericized gap model (runs on ANY entity-kind). |
| **Dimension source** | **Hybrid: static per-kind tables + profile override** — built-in tables (location/character/item/faction/event/generic) are the deterministic default; a book profile may add / remove / reweight / relabel dimensions per kind (the "dynamic" half, AI-suggestable). |
| **Input generalization** | **OUT of scope — Compose owns it.** This fix only de-biases OUTPUT (generation + verify + dimensions run correctly for any book/kind/language). "Enrich from an arbitrary glossary entry / fact / free text" stays the Compose feature (modes D→C→F→B). |
| **Profile bootstrap** | **AI-suggest + author-editable.** One LLM call proposes the profile from the book's metadata + sample chapters; author edits in a Settings panel. Fengshen demo seeded with today's constants (no regression). Unset book → neutral default (language=auto, era OFF). |
| **Granularity** | **Per-book.** Optional per-job override deferred to Compose (`/compose` may carry a one-off profile patch). |

---

## 1. The bug — five layers of hardcoded bias (audited evidence)

| # | Layer | Hardcoded to | Evidence | Effect on a non-Fengshen book |
|---|---|---|---|---|
| 1 | **Gap model — kinds** | only `LOCATION` modeled | `gaps/model.py:152` `DIMENSIONS_BY_KIND={LOCATION:…}`; `dimensions_for()` **raises `KeyError`** for any other kind | **Enrichment CRASHES / silently skips** every character, item, faction, event — i.e. most of a novel |
| 2 | **Gap model — dimensions** | 历史/地理/文化 (+ EN features/inhabitants); salience ref = 玉虛宮 | `gaps/model.py:111-147`, `_SALIENCE_REF=55.0` | location-shaped, Chinese-labelled dims forced onto every entity |
| 3 | **Prompts** | 《封神演义》 + 商周 era + 中文 + 地点 | `generation/generate.py:85-89`, `strategies/fabrication.py:202-211`, `strategies/recook.py:232-242` | every entity described as Shang-Zhou xianxia, in Chinese |
| 4 | **Verify (anachronism)** | 商周 global denylist | `verify/canon_verify.py:202-278` `ANACHRONISM_MARKERS` (~70 markers, applied to ALL books) | a sci-fi / modern book gets auto-flagged for "modern tech" |
| 5 | **No worldview source** | book client reads zero metadata | `clients/book.py` reads only chapter hierarchy | the bias is *unfixable* today — nothing supplies a per-book setting |

**Plus 3 location-hardcodes in the detect/enqueue path** (`api/gaps.py`):
`coverages_from_rows` skips any kind without a static table (L99-102); `AutoEnrichTarget.entity_kind="location"` (L56); `create_job(…, entity_kind="location")` (L256, L270).

**Plus a 6th bias layer found by the architecture benchmark (KB8) — the WRITE-BACK / promote path (H0-critical, the canon-write path):**
| Hardcode | Location | Effect |
|---|---|---|
| `_location_kind_code()` → `return "location"` | `services/writeback.py:95` | promoting a non-location enrichment writes the wrong glossary kind_code (latent: anchor resolves by name today, but wrong for new entities / kind-specific logic) |
| `"source_language": "zh"` | `clients/writeback.py:148` | the entity-anchor extract-entities call is always told zh |
| fallback dimension `"补充"` | `services/writeback.py:164` | a dimension-less fact gets a Chinese marker on any book |

**Glossary side is dynamic-safe (verified, KB8):** `entity_enrichments.dimension` is free `TEXT` (no CHECK); kinds are an `entity_kinds` FK already seeded by extraction (we enrich the kind glossary returns → round-trips). So **no glossary Go change** — only the lore-enrichment write-back path needs de-biasing (pass the proposal's real kind + `profile.language` + a neutral fallback dimension id).

### What is NOT broken (audit green-lights)
- **Persistence is already kind/dimension-agnostic.** `enrichment_proposal.entity_kind` is free `TEXT` with **no CHECK**; there is no `dimension` column (dims live in `provenance_json`). Dynamic kinds/dimensions do **not** break the DB or the H0 trigger. The only vocab CHECK is `technique IN (...)` (untouched).
- **Glossary coverage already returns every kind** (`EntityCoverageRow.kind`) — lore-enrichment is the only place filtering to location. **No glossary-service (Go) change needed for multi-kind.**
- **Threading seams exist.** `StrategyContext` is a frozen pydantic model (trivial additive field); `assembly.build_live_runner` already has `book_id`; `GroundedProposal.dimensions` is keyed by the dimension **label** (the carrier flows everywhere already).

---

## 2. The fix — a per-book profile + a kind/language-aware dimension resolver

Two new core abstractions, both read by every technique + the verifier:

1. **`BookProfile`** — the per-book worldview (worldview / language / era policy / voice / anachronism markers / dimension overrides).
2. **`resolve_dimensions(kind, profile)`** — replaces the frozen `dimensions_for(kind)`: static table → localized by `profile.language` → merged with `profile.dimension_overrides[kind]`. Never raises for an unknown kind (falls back to a generic set).

### 2.0 Data sources — the foundation reads BOTH book + knowledge, by role (PO-locked + design-review 2026-06-03)

Neither source alone is sufficient; each answers a different question:

| Need | Source | Role |
|---|---|---|
| **Infer the worldview** (worldview/language/era/voice) | **book-service** (metadata + sample chapters) **+ knowledge KG summary if available** | "understand the book" — genre/voice live in the prose, not the derived structure |
| **Know what is already canon** (gap detection, contradiction, write-back target) | **glossary + knowledge** (the extracted SSOT) | "what exists already" — structured, rankable, comparable |
| **Ground the generation** (what the model cites) | **knowledge RAG (`build_context`) + glossary canon + KG facts** (primary); `source_corpus` only for deliberate external refs / selected chapters | "faithful evidence" — **reuse the already-extracted digest, do NOT re-ingest** |

**Grounding architecture (CORRECTED by design-review KB5, 2026-06-03).** An extracted book is **already** chunked into passages + facts inside knowledge-service (`GraphStats.passage_count`, KG facts) and described in glossary (`short_description`). So grounding **reuses that digest** — it does NOT re-embed the book into a private `source_corpus`. Priority of grounding sources:

1. **Glossary authored canon (entity-tight) — `list_entities` `short_description`** of THE entity → a clean, entity-scoped `GroundingRef`. Primary tight grounding.
2. **KG neighbourhood facts (entity-tight)** — fabrication already reads these; extend the same lookup to the P1 grounding. Entity-scoped, citeable.
3. **Knowledge RAG breadth — `KnowledgeClient.build_context(message = entity + missing-dimension labels)`** (verified 2026-06-03): returns **one assembled context STRING** (a chat-shaped memory block: `<passages>`/`<entities>`), Mode 3 "full" includes L3 passages. **Caveats:** it is a *blob*, not per-chunk scored refs (wrap as ONE `GroundingRef`, `corpus_id='knowledge:context'`; per-chunk citation granularity is NOT available from this seam); scope is **(user, project)** not book (a multi-book project grounds across books — demo `project_id := book_id` is fine); needs `project.extraction_enabled` (matches the KB2 prerequisite); 404 on cross-user/missing → degrade. Use it for **breadth**, after the entity-tight sources. **No re-ingest, no chapter cap.**
4. **`source_corpus` (DELIBERATE only)** — (a) **external reference material** (the original work for a fanfic, history for re-cook — see §2.10 shared reference library, KB4); (b) **author-SELECTED chapters** (an explicit selection list, never auto-bulk / never "top-N chapters"). The corpus-register path already exists for this.

> **PLAN/BUILD note (build_context):** parse just the `<passages>` portion of the blob for the grounding excerpt (avoid feeding the chat-memory framing to the generator); if per-chunk citation granularity is later required, add a dedicated knowledge-service passage-search internal endpoint (out of Slice-0 scope).

**Why not re-ingest chapters (KB5):** nobody loads a 5000-chapter web novel into a second embedding store just to enrich; a "first-100-chapters" cap is arbitrary and starves entities described late. The knowledge graph already digested ALL chapters — query it. Raw-chapter ingest is only for material knowledge does NOT have (external refs) or a deliberate author selection.

**PO decisions:** grounding primary = reuse knowledge/glossary; raw-chapter ingest = author **selection list** + external refs only; profile AI-suggest = **book metadata + N chapters + a KG summary when the graph is non-empty**.

### 2.0.1 Prerequisite chain — enrichment is DOWNSTREAM of extraction (design-review KB2)
Enrichment fills gaps in entities the platform already KNOWS about. Gap detection reads `list_enrichment_coverage(book_id)` from glossary; a freshly-uploaded book with no extracted entities yields **zero gaps → nothing to enrich** (correct, not a bug). The real chain is:

```
upload book → knowledge EXTRACTION (entities/facts/passages → glossary + KG) → enrich (detect gaps → ground via build_context → generate)
```

This is a hard dependency the foundation must state (and the FE should message: "extract this book first"). The ONLY way to enrich an entity that does not yet exist is **Compose mode `target=new`** (author seeds a new entity) — which is why that mode exists. De-bias does NOT add an own-entity-creation path (Compose owns it).

### 2.1 `enrichment_book_profile` (new table, keyed by book_id)

| field | type | meaning |
|---|---|---|
| `book_id` | UUID PK | the book |
| `worldview` | TEXT NOT NULL DEFAULT `''` | free-text setting ("Shang-Zhou mythic xianxia (封神演义)" \| "near-future cyberpunk Saigon" \| "Victorian gothic horror") |
| `language` | TEXT NOT NULL DEFAULT `'auto'` | output language (`zh`/`en`/`vi`/… or `auto` = book's language) |
| `era_policy` | TEXT NULL | free-text era/anachronism constraint ("no post-商周 tech, no foreign religions"); **NULL = no era constraint → anachronism check OFF** |
| `voice` | TEXT NULL | optional tone/voice hint |
| `anachronism_markers` | JSONB NULL | optional explicit denylist `[{term, reason}]`; NULL + era_policy set → advisory-only (no auto-reject); the Fengshen seed populates this with today's `ANACHRONISM_MARKERS` |
| `dimension_overrides` | JSONB NOT NULL DEFAULT `'{}'` | per-kind add/remove/reweight/relabel (§2.4) — the "dynamic dimensions" half |
| `profile_source` | TEXT NOT NULL DEFAULT `'manual'` | `seed` \| `ai_suggested` \| `manual` (provenance of the values) |
| `created_at` / `updated_at` | timestamptz | |

Idempotent DDL in `app/db/migrate.py` (house style: `CREATE TABLE IF NOT EXISTS` + matching `DOWN_DDL` drop). No CHECK on language/kind (free text, future-proof).

### 2.2 `BookProfile` model + reader (neutral default)
- New `app/db/book_profile.py`: `async get_book_profile(pool, book_id) -> BookProfile`. Returns the **neutral default** when unset: `worldview=''`, `language='auto'`, `era_policy=None` (anachronism OFF), `voice=None`, `anachronism_markers=()`, `dimension_overrides={}`.
- `BookProfile` is a small frozen pydantic model. A module-level `NEUTRAL_PROFILE` constant is the fallback used everywhere `book_id` is absent (so a job that never supplied a book behaves identically to today's "no profile" path, just with anachronism OFF instead of 商周).

### 2.3 Threading — `StrategyContext.profile` (additive, frozen field)
- `StrategyContext` gains `profile: BookProfile = NEUTRAL_PROFILE` (additive; existing constructions default to neutral → no caller breaks).
- `assembly.build_live_runner` resolves the profile once from `book_id` (`get_book_profile`) and:
  - puts it on the `StrategyContext` the runner threads to strategies (so prompts + dimension resolution read it), and
  - passes its anachronism config to the `CanonVerifier` (§2.6).
- The detect endpoint (`api/gaps.py`) resolves the profile from `body.book_id` and threads it into `coverages_from_rows` + the engine (so the dimension SET it computes gaps against matches the book).
- The worker (`resume_consumer`) already carries `book_id` on the request → resolve there; **no new wire field**.

### 2.4 Dimension model refactor (the multi-kind + dynamic half) — `gaps/model.py`
1. **Stop GATING on the enums — kind and dimension are dynamic (design-review KB3).** Kind and attribute are author/profile-extensible, so using a closed `EntityKind`/`Dimension` enum as a *validation gate* is wrong (it silently skips any kind/dimension it didn't enumerate — the very bug class we're fixing). **Loosen the FIELD TYPES to free `str`** (`Gap.entity_kind`/dimension tuples, `EntityCoverage`, `DimensionSpec.dimension`, the proposal) so arbitrary kinds/dimensions are representable. **Verified test-ripple minimiser (2026-06-03):** KEEP `EntityKind`/`Dimension` as `str`-valued enums of the BUILT-IN values, used as **constants to key the static tables** — NOT as field types. Because a `str`-enum member equals its string (`EntityKind.LOCATION == "location"`), the ~72 existing `EntityKind.LOCATION`/`Dimension.HISTORY` test references keep compiling (they're valid `str` values); only assertions that rely on enum-INSTANCE identity or on `dimensions_for` raising `KeyError` break (~10-20, concentrated in `test_gap_model`/`test_gap_engine`). `rank_score`/engine iterate the resolved table, never the enum. An unknown kind → GENERIC table (never `ValueError`/skip); `coverages_from_rows` stops doing `EntityKind(r.kind)` (the current skip-on-unknown bug, KB3).
2. **Static per-kind tables** for `LOCATION` (unchanged), `CHARACTER`, `ITEM`, `FACTION`, `EVENT`, plus a **`GENERIC`** fallback (description / details / significance) used for any kind without a specific table — so enrichment **never silently skips** an entity (replacing the current `KeyError`/skip).
   - The tables store **language-neutral ids + payload shapes + weights + a `required` flag**; the human label is resolved by language (next point), NOT hardcoded.
3. **Label localization.** A `label_for(dim_id, language)` table resolves the display label. **`label_for("history","zh") == "历史"`** etc., so for the Fengshen book (language=zh) the labels are byte-identical to today → no data/regression drift. Unknown (id, language) → the id itself (English-ish fallback).
4. **`resolve_dimensions(kind, profile) -> tuple[DimensionSpec,…]`** replaces `dimensions_for(kind)`:
   - start from the static table for `kind` (or `GENERIC`),
   - localize each label via `profile.language`,
   - apply `profile.dimension_overrides[kind]`: `add` (author-supplied spec incl. label + weight + required + payload_shape), `remove` (ids), `relabel` (id→label), `reweight` (id→weight).
   - returns a frozen tuple; deterministic given (kind, profile). Each `DimensionSpec` carries BOTH a stable `id` and a localized `label`.
   - **Dimension identity = the stable `id`, NOT the label (PO decision A, 2026-06-03).** This fixes the round-trip bug: glossary stores supplements keyed by a dimension marker — enrichment **writes the stable id** as that marker (enrichment controls the string it persists → no glossary Go change), so `list_enrichment_coverage` returns ids and detect compares present/missing **by id**. A language change or a profile relabel then never makes an already-present dimension look missing (the label is display-only). The id is also recorded in the proposal's `provenance_json` for lifetime traceability. **Legacy / demo rows** keyed by a label (历史) are handled by a `label→id` fallback via `resolve_dimensions(kind, profile)` at detect (try id-match first, then resolve the label). Pinned by a round-trip test.
5. Salience: keep the log-damp but relabel `_SALIENCE_REF` as a generic "reference mention count" (book-neutral; the number only shapes damping, not correctness).

### 2.5 Parameterize the prompt builders — `generate.py` / `fabrication.py` / `recook.py`
Each builder takes `(profile, kind_label)` (dimension labels already come localized in `proposal.dimensions`):
- **Instruction language = the target output language (PO decision D, 2026-06-03).** The whole prompt (not just the requested output) is rendered in `profile.language` — an English book gets an English instruction, a Chinese book Chinese. (Avoids a strong Classical-Chinese model being told in Chinese to write English.) A small per-language instruction-template set; `auto`/unknown → English. The Fengshen profile (`zh`) reproduces today's Chinese prompt byte-for-byte.
- `"你是一位忠于《封神演义》原著的…"` → a worldview-faithful instruction built from `profile.worldview`, in `profile.language`, matching `profile.voice`. Keep JSON-only + grounding rules unchanged.
- `"为地点「{name}」"` → `"for the {kind_label} «{name}»"` (kind_label localized: location→地点/place, character→人物/character …).
- fabrication/recook era clause → rendered from `profile.era_policy`; **omitted entirely when `era_policy` is NULL**.
- recook re-contextualisation target → `profile.worldview` + `profile.era_policy`.
- Language line ("内容必须为中文") → `profile.language` (omit / "the book's language" when `auto`).
- **No-regression rule:** with the Fengshen profile every rendered string equals today's byte-for-byte (pin with a golden test).

### 2.6 Profile-driven anachronism (verify) — `canon_verify.py`
- The global `ANACHRONISM_MARKERS` constant is demoted to **`FENGSHEN_ANACHRONISM_MARKERS`** (seed data for the Fengshen profile row), no longer a global default.
- `CanonVerifier.__init__` gains `anachronism_markers: Sequence[(term, reason)] = ()` (and the era-policy context). `_check_anachronism` iterates the **profile's** markers:
  - markers present (Fengshen) → identical behavior to today,
  - `era_policy` NULL and no markers → **anachronism check OFF** (zero flags — never auto-reject a sci-fi/modern book for "modern tech"),
  - `era_policy` set but no explicit markers → advisory-only (no C3 auto-reject) — honest "we can't enforce an era we have no denylist for".
- Contradiction / injection / regurgitation checks are **era-agnostic** → unchanged.

### 2.7 Profile authoring — endpoints + AI-suggest
- `GET  /v1/lore-enrichment/books/{book_id}/profile` → the profile (neutral default if unset).
- `PUT  /v1/lore-enrichment/books/{book_id}/profile` → upsert (sets `profile_source='manual'` on author edit).
- `POST /v1/lore-enrichment/books/{book_id}/profile/suggest` → **AI-suggest** (PO: book + KG): read the book's metadata (title/language/synopsis) + a few sample chapters via book-service, **AND a KG summary (top entities/relations) from knowledge-service when the graph is non-empty**, ONE LLM call → propose `worldview`/`language`/`era_policy`/`voice` **AND per-kind `dimension_overrides` (PO decision E, 2026-06-03)** — the LLM suggests a genre-appropriate dimension set (e.g. a cyberpunk character: implant_loadout / faction_ties / street_cred) returned in the override shape, `profile_source='ai_suggested'`. The KG summary is **best-effort** — an empty/down graph degrades to book-only (never blocks suggest). **Does NOT persist** — returns a draft the author reviews + edits (incl. the suggested dimensions in the override editor) then PUTs. The override JSON is schema-validated server-side before persist (reject malformed LLM output).
- OpenAPI contract updated; gateway passes through (`/v1/lore-enrichment` is proxied).
- **Dependency — VERIFIED 2026-06-03, no new Go endpoint needed.** book-service already exposes the internal reads: `GET /internal/books/{id}/chapters` (list — for the selection UI + sampling), `GET /internal/books/{id}/chapters/{cid}/draft-text` (chapter text), `GET /internal/books/{id}/projection` (owner + counts; title/language derivable from chapters' `original_language`). `clients/book.py` adds a `list_chapters` + `get_chapter_text` method over these. No book-level synopsis field exists → AI-suggest infers from sample chapters (the documented fallback). KG summary reuses `KnowledgeReadPort`/`build_context` (degrade-safe).

### 2.9 Grounding wiring (CORRECTED — reuse knowledge, no re-ingest; see §2.0)
The v1 "auto-ingest the book's chapters" idea is **dropped** (design-review KB5). Instead:
- **New grounding source: a `KnowledgeContextGrounding`** that calls `KnowledgeClient.build_context(message = canonical_name + missing-dimension labels, project_id)` and projects the returned context into `GroundingRef`s (synthetic `corpus_id='knowledge:context'`, the assembled passage text as the excerpt, score = the relevance the endpoint reports or a fixed 1.0). Degrades safely (empty context → no grounding from this source; Q6).
- **Plus glossary canon** (`list_entities` → the entity's `short_description`) and **KG neighbour facts** as additional grounding refs.
- The P1 retrieval path becomes a **composed grounding** = knowledge-context ∪ glossary-canon ∪ (optional) source_corpus, deduped, top-K by score. Generation's "refuse if no grounding" rule (H0) is satisfied for any extracted book; an entity with truly nothing known still refuses (correct — don't fabricate in P1).
- **`source_corpus` retrieval stays** but is fed ONLY by deliberate ingest: §2.10 shared reference library + an author **chapter-selection** ingest (`POST …/ground` taking an explicit `chapter_ids: [...]` selection — a list the FE renders from the book's chapter list, NOT a count/auto-bulk). Idempotent on `content_sha256`.
- **H0 unchanged:** grounding is evidence, not canon. No chapter cap, no "top-N chapters" — the digest is already in knowledge.

### 2.10 Shared reference library (design-review KB4)
`source_corpus` is per-project today, so a fanfic can't reuse the original work as reference, and history corpora can't be shared across books. Add a **shared, public-domain reference library**: corpora with `project_id IS NULL` (global), readable by any project (PD/licensed material only — no cross-user private data, so Q3 scoping is preserved). A project **opts in** by reference (no copy/re-embed). The Fengshen original + 山海经 + Shang-Zhou history become library entries any 封神 fanfic project can ground/re-cook on.
- Schema: `source_corpus.project_id` becomes nullable (NULL = shared library); retrieval scopes to `project_id = $proj OR project_id IS NULL`. Library writes are admin/curated (not user-ingest) to keep the PD guarantee.
- v1 may ship the library read-path + seed the demo PD corpora as shared; a full curation UI is deferrable.

### 2.8 Seed the Fengshen demo (no regression)
- Seed the demo book's `enrichment_book_profile` row = today's constants: `worldview='商周·封神演义'`, `language='zh'`, `era_policy='商周封神纪元：不得出现后世朝代、近现代器物、外来宗教'`, `voice='原著文言-白话'`, `anachronism_markers=FENGSHEN_ANACHRONISM_MARKERS`, `dimension_overrides={}` (the static LOCATION table already matches), `profile_source='seed'`.
- Delivered as an idempotent seed script (`scripts/seed_fengshen_profile.py`, book_id via env/arg) — **not** a hardcoded UUID in `migrate.py`.

---

## 3. Affected files

**BE (lore-enrichment-service):**
- new `app/db/book_profile.py` (model + reader + `NEUTRAL_PROFILE`)
- `app/db/migrate.py` (+`enrichment_book_profile` DDL + DOWN_DDL)
- `app/gaps/model.py` (loosen Dimension → str id; CHARACTER/ITEM/FACTION/EVENT/GENERIC tables; `label_for`; `resolve_dimensions(kind, profile)`; salience relabel)
- `app/gaps/engine.py` (`resolve_dimensions(kind, profile)` instead of `dimensions_for(kind)`; thread profile)
- `app/retrieval/strategy.py` (`_gap_query`/`_dimension_slots` via `resolve_dimensions`; read `context.profile`)
- `app/generation/generate.py`, `app/strategies/fabrication.py`, `app/strategies/recook.py` (prompt builders → `(profile, kind_label)`)
- `app/verify/canon_verify.py` (anachronism → profile markers; demote constant to `FENGSHEN_ANACHRONISM_MARKERS`)
- `app/strategies/base.py` (`StrategyContext.profile`)
- `app/jobs/assembly.py` (resolve profile from `book_id`; thread to context + verifier)
- `app/api/gaps.py` (resolve profile; multi-kind `coverages_from_rows`; drop `entity_kind="location"` hardcodes in `AutoEnrichTarget` + `create_job`)
- `app/worker/resume_consumer.py` (resolve profile from request `book_id`)
- new `app/api/book_profile.py` (GET/PUT/suggest) + openapi + `app/clients/book.py` metadata/sample-text method
- new grounding sources (§2.9): `KnowledgeContextGrounding` (via `KnowledgeClient.build_context`) + glossary-canon grounding + KG-neighbour grounding, composed into the P1 retrieval path; `app/api/grounding.py` `POST …/books/{id}/ground` now takes an explicit `chapter_ids` **selection** (not a count) for deliberate raw-chapter ingest
- shared reference library (§2.10): `source_corpus.project_id` nullable; retrieval scopes `project_id = $proj OR project_id IS NULL`; seed demo PD corpora as shared
- AI-suggest KG summary: light top-entities read via `KnowledgeReadPort` / `build_context` (degrade-safe)
- `app/gaps/model.py` + `app/gaps/engine.py` + `app/api/gaps.py`: `entity_kind`/dimension become free `str` (drop the `EntityKind`/`Dimension` enum gate, KB3); GENERIC fallback, no skip
- **write-back path de-bias (KB8):** `app/services/writeback.py` (`_location_kind_code` → the proposal's real kind; neutral fallback dimension id, not `"补充"`) + `app/clients/writeback.py` (`source_language` from `profile.language`, not hardcoded `"zh"`). Glossary Go unchanged (dimension free-text; kinds pre-seeded by extraction)
- `scripts/seed_fengshen_profile.py`

**FE (frontend/src/features/enrichment/):** new **Settings** panel (worldview/language/era/voice + dimension-override editor + "Suggest from book") + `api.ts`/`types.ts`/`hooks/useBookProfile.ts`/i18n ×4 + vitest.

**book-service (Go):** possibly a `GET /internal/books/{id}` metadata endpoint (verify in PLAN; else fallback).

---

## 4. Slices (each its own VERIFY + POST-REVIEW + COMMIT)

- **Slice 0a — Profile foundation (BE, the worldview/language/era de-bias).** Table + reader + `NEUTRAL_PROFILE` + `StrategyContext.profile` + parameterize the 3 prompt builders + profile-driven anachronism + assembly resolve&thread + Fengshen seed. **Still location-only.** **Acceptance:** Fengshen profile → prompts/markers byte-identical (existing 562+ tests stay green); neutral profile → NO 封神/商周/中文 in prompts AND anachronism OFF (new golden tests pin both).
- **Slice 0b — Multi-kind + dynamic dimensions (BE), incl. the WRITE-BACK path (KB8).** Drop the `EntityKind`/`Dimension` enum gate (free `str`); CHARACTER/ITEM/FACTION/EVENT/GENERIC tables; `label_for`; `resolve_dimensions(kind, profile)` w/ overrides; update engine/retrieval/gaps.py; remove the 3 detect-path location hardcodes **AND the 3 write-back hardcodes** (`_location_kind_code`, `source_language="zh"`, `"补充"` fallback). **Acceptance:** a CHARACTER gap detects + enriches **and PROMOTES to glossary end-to-end** (unit + a live single-gap smoke incl. a promote → correct kind on the canonical entity + supplement keyed by stable id); an unmodeled kind uses GENERIC (never skipped); LOCATION output + promote unchanged (Fengshen byte-identical).
- **Slice 0c — Grounding wiring: reuse knowledge, no re-ingest (BE, §2.9 — load-bearing).** Add `KnowledgeContextGrounding` (via `build_context`) + glossary-canon + KG-neighbour grounding, composed into the P1 path; (optional) `POST …/ground` chapter-**selection** ingest + shared reference library read-path (§2.10). Detect/enrich on an **unextracted** book returns a clear "extract first" signal (KB2), not a cryptic refuse. **Acceptance:** an extracted non-Fengshen book → grounding from `build_context`/canon → generation no longer refuses (live single-gap smoke); an unextracted book → clear prerequisite signal; selected-chapter ingest works; library corpus reachable cross-project.
- **Slice 0d — Profile API + AI-suggest (BE).** GET/PUT/suggest endpoints + openapi + book-service metadata read (+ Go endpoint if missing) + best-effort KG summary; suggest returns text fields **+ per-kind `dimension_overrides`** (server-validated). **Acceptance:** suggest returns a sane draft incl. genre dimensions for a non-Fengshen book (book-only when KG empty); PUT round-trips + rejects malformed overrides; H0/scope guards.
- **Slice 0e — FE Settings panel.** Worldview/language/era/voice + dimension-override editor + "Suggest from book" + (optional) a chapter-**selection** picker for deliberate extra grounding + "extract first" empty-state messaging (KB2) + i18n ×4 + vitest.
- **Then** the Compose slices (D→C→F→B) build on the now book-aware prompts + the shared grounding ingest.

Slices **0a + 0b + 0c are the bug fix proper** (output correct for any book/kind/language AND a real new book actually produces grounded output); 0d + 0e are the authoring UX. 0a is shippable alone (fixes worldview/era/language for the already-grounded demo); 0b unblocks "any entity"; 0c unblocks "any *new* book".

---

## 5. Why this is the right fix (not a workaround)
- Removes the bias at the SOURCE — one profile + one dimension resolver, read by every technique + the verifier — instead of per-mode patches.
- Fixes **existing** enrichment for non-Fengshen books AND non-location entities, not just Compose.
- **Regression-safe by construction:** the Fengshen profile reproduces today's behavior byte-for-byte; neutral default only relaxes (anachronism OFF, language auto).
- **Persistence needs no schema loosening** (entity_kind/dimension already free text) — lower-risk than it looks.
- Unblocks Compose's freeform/any-subject premise + the multi-language, multi-genre product goal.
- **Not legal/era advice** — `era_policy` is an authoring aid, not a correctness guarantee.

## 6. Design-review resolutions + remaining open items

**Resolved in the 2026-06-03 adversarial design review (decisions A/C/D/E):**
- **(A)** dimension identity = stable `id` (provenance + glossary marker), match by id, label display-only → round-trip robust (§2.4).
- **(C)** grounding = explicit pre-step ground job (cap + chapter-limit) + enrich gated on grounded state (§2.9).
- **(D)** prompt instruction rendered in the target language (§2.5).
- **(E)** AI-suggest proposes per-kind `dimension_overrides` too, server-validated (§2.7).

**(B) DEFERRED — eval-gate / eval-suite de-bias.** The C15 eval suite (`enrichment-v1`) + scorers are Fengshen-tuned, so the gate that unlocks **P2/P3** never meaningfully passes for a non-Fengshen book. **Per PO (2026-06-03): out of Slice 0 scope — defer to the full eval refactor.** Consequence: **Slice 0 makes P1 (template/retrieval) correct for ANY book** (P1 is ungated); **P2/P3 stay Fengshen-gated.** A **temporary LLM-as-judge** gate may later unlock P2/P3 for other books as a stopgap before the full suite de-bias. New deferral row → `LE-debias-eval-suite`.

**Architecture benchmark (7 scenarios, 2026-06-03) — resolutions:**
- **KB2** enrich is downstream of extraction → documented as a hard prerequisite chain (§2.0.1); FE shows "extract first".
- **KB3** kind + dimension are dynamic → dropped BOTH enums; free `str` + GENERIC fallback, no skip (§2.4).
- **KB4** no shared reference corpus → shared PD reference library, `project_id` nullable, opt-in by reference (§2.10).
- **KB5** re-ingesting chapters is wrong → grounding **reuses `build_context` + glossary canon + KG facts**; raw-chapter ingest only via explicit **chapter selection** + external library; no chapter cap (§2.0/§2.9).
- **KB6** edit/delete profile → **non-issue**: profile is read-only at runtime, no stored coupling; promoted supplements live in glossary SSOT independently. Dropped.
- **KB7** anthology / ambiguous worldview → **author declares** (per-book profile + per-job override in Compose); the LLM never guesses. Known limitation, no v1 fix.
- **KB8** promote write-back is a 6th bias layer → de-bias the write-back path (kind from proposal, `source_language` from profile, neutral fallback dimension); glossary Go verified dynamic-safe (no change). Folded into Slice 0b (§1, §3, §4). **H0-critical — this is the canon-write path.**
- **KB9** C12 contradiction multi-language → EN already works (`extract_canon_terms` Latin + EN negation); **vi/diacritic Latin under-fires to ~off** (`[A-Za-z]{3,}` misses diacritics, vi negation absent) — SAFE direction (under-fire never creates false canon; human gate backstops), documented residual. No fix needed for Slice 0; a vi segmenter/negation set is a future enhancement.

**PLAN-phase verifications — DONE 2026-06-03 (code-traced):**
- **`build_context`** ✅ usable — returns passage-level content (Mode 3 full, L3) but as ONE chat-shaped context STRING, (user, project)-scoped, needs `extraction_enabled`. → grounding uses it for BREADTH after entity-tight glossary/KG sources; wrap as one ref, parse `<passages>` (§2.9). Per-chunk citation granularity needs a future passage-search endpoint (out of scope).
- **book-service** ✅ no new Go endpoint — `/internal/books/{id}/chapters` + `/chapters/{cid}/draft-text` + `/projection` cover AI-suggest + selection-ingest (§2.7).
- **test-ripple** ✅ contained to ~6-7 files: enum (~10-20 real breaks if enums kept as constants + field types loosened, §2.4), anachronism-OFF (~4 files inject Fengshen markers), write-back kind (~1-2 files). The nominal 179 is overcount (location fixtures keep working).

**Remaining to confirm in PLAN:**
- **book-service metadata endpoint** for AI-suggest + the grounding chapter-text read (exists? else a small Go addition or a chapters-only fallback) — §2.7/§2.9.
- **`Dimension` enum → str loosening** ripple: count test touches in `tests/test_gap_model.py`, `test_gap_engine.py`, `test_retrieval_strategy.py` (enum asserted directly) + which pipeline tests assume anachronism-ON (now NEUTRAL→OFF) → plan the test migration with the code (finding F).
- **`kind_label_for(kind, language)`** table + **`freeform` kind** (Compose) → maps to GENERIC / a single free dimension (finding G) — specify alongside the dimension tables.
- **Profile read consistency** detect-vs-run: profile read fresh at run; `targets` carry a `present_dimensions` snapshot from detect → an author editing the profile between detect and enrich has a small drift window (finding F) — document; acceptable.
- **Per-job profile override** field on `/compose` — deferred to Compose; confirm the patch shape there.
