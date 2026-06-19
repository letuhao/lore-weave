# Build Plan — Genre·Kind·Attribute (standards → sovereign instance)

**Status:** DESIGN (awaiting REVIEW/redline) · **Size:** XL · **Owner:** glossary-service
**Authority spec:** [docs/specs/2026-06-19-genre-kind-attribute-tiering.md](../specs/2026-06-19-genre-kind-attribute-tiering.md)
**Validated by:** [docs/specs/spikes/2026-06-19-G0-copydown-spike.sql](../specs/spikes/2026-06-19-G0-copydown-spike.sql) (copy-down + book-local single-tier read PROVEN on postgres:16)
**UX drafts:** [design-drafts/glossary-tiering/](../../design-drafts/glossary-tiering/) (index, 01-manage, 02-attribute-matrix, 03-entity-form, 04-sync)

> This is the "how" doc. The spec is the "what/why". Read the spec's §0 vocabulary and §2–§4 first.
> Everything here implements that model; where this doc and the spec disagree, the spec wins (and this doc is wrong — fix it).

---

## 0. Ratified decisions (this session)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| **R1** | Adopt trigger & granularity | **Pick-list at book setup** | One-time scaffold step at book creation / first glossary open: user checks genres + kinds → copy-down runs. `+ adopt more` pulls additional standards later. No lazy per-reference path. |
| **R2** | Existing-data disposition | **Full reset** | Drop ALL glossary data (entities, values, kinds, attrs, genre_groups). Rebuild from zero: re-seed system standards, books re-scaffold via adopt. **No data-migration transform** — clean teardown + create. |
| **R3** | Broken-window strategy | **Destructive on-branch (A)** | Glossary is non-functional on `feat/glossary-assistant-coverage` from G1→G6; **main is not merged until the epic is green**. No additive/coexistence layer. One cutover at G6. |
| **R4** | Cross-service reset scope | **All test data — clear it** | Neo4j KG anchors are cleared at G1; composition/enrichment/worker-ai caches recompute from the live glossary post-reset. Nothing to preserve. |

R1+R2 together: the migration is a **destructive create** (not an `ALTER` transform), and the entity layer repoints to book-local FKs with no legacy rows to carry. This is the simplest possible path and is only safe because **only test/dump data exists** (user-confirmed).

---

## 1. Current → target delta (accurate, from code audit)

### RETIRE (dropped in the full reset)
| Today | Why it goes |
|---|---|
| `genre_groups` (per-book filter buckets) | replaced by tiered `*_genres` + `book_active_genres` |
| `system_kinds.genre_tags`, `system_kind_attributes.genre_tags`, `user_kinds.genre_tags` (TEXT[]) | the flat-genre drift; replaced by `*_kind_genres` link tables + per-(kind,genre) attributes |
| `system_kind_attributes`, `user_kind_attributes` (per-kind, genre-tagged) | reshaped into `*_attributes` keyed by **(kind, genre, code)** |
| `entity_attribute_values.attr_def_id → system_kind_attributes` | repoints to `book_attributes` (book-local) |
| `glossary_entities.kind_id → system_kinds` | repoints to `book_kinds` (book-local) |

### KEEP (correct as-is, data reset)
- `system_kinds`, `user_kinds` (SS-4 — shape is right; data truncated + re-seeded)
- `entity_kind_aliases` (code→kind resolution; retargeted to book/system code space)
- `attribute_translations`, `evidences` (per-value children; FK chain unchanged, repointed via parent)
- `merge_candidates` (kind_id ref → repoint to book_kinds)

### NEW (created in the rebuild)
`system_genres` · `user_genres` · `book_genres` · `system_kind_genres` · `user_kind_genres` · `book_kind_genres` · `system_attributes` · `user_attributes` · `book_attributes` · `book_kinds` · `book_active_genres` · `entity_genres`

> Naming follows the spec (`*_attributes`, not `*_kind_attributes`) — the kind+genre are FK columns, not name prefixes.

---

## 2. Concrete DDL (Postgres, matches existing conventions: UUID PKs, timestamptz)

> The spike used `bigserial` for brevity; production uses `uuid DEFAULT gen_random_uuid()` to match `system_kinds.kind_id`.

### 2.1 Genre tier
```sql
CREATE TABLE system_genres (
  genre_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,
  name        text NOT NULL,
  icon        text, color text, sort_order int NOT NULL DEFAULT 0,
  content_hash text NOT NULL,            -- for Sync change-detection (G5)
  is_default  boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE user_genres (
  genre_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  code text NOT NULL, name text NOT NULL,
  icon text, color text, sort_order int NOT NULL DEFAULT 0,
  cloned_from_genre_id uuid REFERENCES system_genres(genre_id) ON DELETE SET NULL,
  content_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,                -- recycle bin (parity with user_kinds)
  UNIQUE (owner_user_id, code)
);
CREATE TABLE book_genres (
  genre_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id    uuid NOT NULL,
  code text NOT NULL, name text NOT NULL,
  icon text, color text, sort_order int NOT NULL DEFAULT 0,
  source_ref text,                       -- 'system:<genre_id>' | 'user:<genre_id>' | NULL(book-native)
  source_hash text,                      -- content_hash captured at adopt; vs source for "update available"
  deprecated_at timestamptz,             -- boundary independence: remove = deprecate, never destroy
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (book_id, code)
);
```

### 2.2 Kind↔genre links (per tier, plain FKs)
```sql
CREATE TABLE system_kind_genres (
  kind_id  uuid NOT NULL REFERENCES system_kinds(kind_id) ON DELETE CASCADE,
  genre_id uuid NOT NULL REFERENCES system_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (kind_id, genre_id)
);
CREATE TABLE user_kind_genres (
  kind_id  uuid NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  genre_id uuid NOT NULL REFERENCES user_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (kind_id, genre_id)
);
CREATE TABLE book_kind_genres (
  book_id  uuid NOT NULL,
  kind_id  uuid NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  genre_id uuid NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (kind_id, genre_id)
);
```

### 2.3 Attributes (per tier, keyed by kind × genre × code)
```sql
CREATE TABLE system_attributes (
  attr_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind_id  uuid NOT NULL REFERENCES system_kinds(kind_id) ON DELETE CASCADE,
  genre_id uuid NOT NULL REFERENCES system_genres(genre_id) ON DELETE CASCADE,
  code text NOT NULL, name text NOT NULL, description text,
  field_type text NOT NULL, is_required boolean NOT NULL DEFAULT false, sort_order int NOT NULL DEFAULT 0,
  options jsonb, auto_fill_prompt text, translation_hint text,   -- carried from system_kind_attributes
  content_hash text NOT NULL,
  UNIQUE (kind_id, genre_id, code)
);
-- user_attributes: same + owner_user_id, cloned_from_attr_id REFERENCES system_attributes ON DELETE SET NULL,
--                  deleted_at; UNIQUE (owner_user_id, kind_id, genre_id, code).
--                  kind_id/genre_id may reference EITHER system or user tier — see §2.6 "attach-by-code".
-- book_attributes: same + book_id, source_ref, source_hash, deprecated_at;
--                  kind_id→book_kinds, genre_id→book_genres; UNIQUE (book_id, kind_id, genre_id, code).
```

### 2.4 Book kinds + activation
```sql
CREATE TABLE book_kinds (
  book_kind_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id uuid NOT NULL,
  code text NOT NULL, name text NOT NULL, icon text, color text, sort_order int NOT NULL DEFAULT 0,
  source_ref text, source_hash text, deprecated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (book_id, code)
);
CREATE TABLE book_active_genres (
  book_id  uuid NOT NULL,
  genre_id uuid NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (book_id, genre_id)
);
```

### 2.5 Entity layer repoint (book-local plain FKs)
```sql
ALTER TABLE glossary_entities   -- (recreated in full reset)
  kind_id uuid NOT NULL REFERENCES book_kinds(book_kind_id);     -- was → system_kinds
CREATE TABLE entity_genres (    -- per-entity genre override (D2)
  entity_id uuid NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  genre_id  uuid NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (entity_id, genre_id)
);
-- entity_attribute_values.attr_def_id  uuid → book_attributes(attr_id)   -- was → system_kind_attributes
```

### 2.6 The "attach-by-code" rule (user attributes onto system kinds/genres)
A user attribute can ride on top of a **system** kind×genre pair (e.g. add `dao_heart` to system `character × xianxia`). Rather than a polymorphic FK, `user_attributes.kind_id/genre_id` reference the **user tier**, and a user who wants to extend a system pair first **clones** that kind/genre into their tier (D6 — identity-by-code; the clone keeps the same `code`, so resolution still merges by code at adopt). This keeps every FK diagonal (single-tier) and is what the spike proved. The Manage UI's "Override/extend in my tier ↓" performs the clone implicitly.

---

## 3. Resolver — the two moments (from spec §3, now in real types)

**Moment A — adopt/scaffold (the only cross-tier resolution):** `INSERT … SELECT` resolving System→User by `code` (User shadows System), copying into the book tier. Proven in the spike (`resolved` CTE: system rows `WHERE NOT EXISTS` a user override `UNION ALL` all user rows → map codes to book ids). Runs on pick-list submit and on `+ adopt more`.

**Moment B — read (book-local, single-tier):** every form/matrix read hits only `book_*` tables. Active genres = `entity_genres` override else `book_active_genres`; applicable = `∩ book_kind_genres ∪ {universal}`; namespaced `code·genre` **only** on a real same-code clash across genres (M1). EXPLAIN-verified: zero `system_*`/`user_*` in the read plan.

---

## 4. API contract (contract-first — author NEW OpenAPI before any FE)

No glossary REST OpenAPI exists today; this milestone **creates** `contracts/api/glossary-service/kinds_genres_attributes.yaml`. Surface:

### Standards — System (read-only) + User (CRUD, recycle-bin parity with user-kinds)
```
GET    /v1/glossary/genres                         # merged system+user (read)
GET    /v1/glossary/user-genres                    # list
POST   /v1/glossary/user-genres                    # create
PATCH  /v1/glossary/user-genres/{id}               # update
DELETE /v1/glossary/user-genres/{id}               # → recycle bin
       /v1/glossary/user-genres-trash/...          # list/restore/purge (mirror user-kinds-trash)
GET    /v1/glossary/system-attributes?kind=&genre= # read system attrs for a (kind,genre)
GET/POST/PATCH/DELETE /v1/glossary/user-attributes # user attrs (attach-by-code, §2.6)
       (+ user-kind-genres link CRUD under user-kinds/{id}/genres)
```
### Book (sovereign instance)
```
POST   /v1/glossary/books/{book_id}/adopt          # R1 pick-list: { genres:[code], kinds:[code] } → copy-down
GET    /v1/glossary/books/{book_id}/ontology       # book-local genres+kinds+attributes (the Manage workspace)
GET/POST/PATCH/DELETE  …/books/{book_id}/genres|kinds|attributes        # book-tier CRUD
PUT    …/books/{book_id}/active-genres              # set book default genres
GET    …/books/{book_id}/kinds/{kind}/matrix        # 02-attribute-matrix read (kind × active genres)
```
### Sync (G5)
```
GET    /v1/glossary/books/{book_id}/sync/available  # diff: source_hash vs upstream content_hash → "N updates"
POST   /v1/glossary/books/{book_id}/sync/apply       # per-row { ref, choice: keep_mine|take_theirs }
```
### Entity (repointed)
```
POST   …/books/{book_id}/entities         # kind = book_kind; genres default from book_active_genres
PATCH  …/entities/{id}/genres             # per-entity override (D2)
… existing entity/attribute-value routes, attr_def now → book_attributes
```

---

## 5. Sync change-detection mechanism

Each standards row carries `content_hash` (hash of the semantic fields: name, description, field_type, is_required, options…). At adopt, the book copy stores `source_ref` + `source_hash` (= the standard's `content_hash` at copy time).
- **Update available** ⇔ `book.source_ref` resolves to a live standard whose `content_hash ≠ book.source_hash`.
- **Source retired** ⇔ `source_ref` resolves to a `deprecated_at IS NOT NULL` (or absent) standard → shown as a "retired source" card (04-sync), book copy stays frozen.
- **Apply**: `take_theirs` overwrites the book row's semantic fields + updates `source_hash`; `keep_mine` just bumps `source_hash` to silence the prompt (accept divergence). All pull-based, per-row, never auto-pushed (D8).

---

## 6. Seeding plan (system standards rebuilt from DefaultKinds)

Source of truth stays `domain/kinds.go::DefaultKinds` (12 kinds, each with `Attrs` + `GenreTags`). New `Seed()`:
1. **system_genres** ← the union of all `GenreTags` across DefaultKinds (universal, fantasy, romance, drama, historical, …) + `xianxia`/`mystery` if we extend. Compute `content_hash`.
2. **system_kinds** ← the 12 kinds (drop `genre_tags` column usage).
3. **system_kind_genres** ← one link per `(kind, genre)` from each kind's `GenreTags`.
4. **system_attributes** ← each `SeedKind.Attrs` distributed to **(kind, genre)** pairs. **Open question O1:** today an attr is per-kind tagged with the kind's genres — does each attr replicate to *every* genre the kind has, or do we author genre-specific attr sets? Recommend: seed each attr under the kind's genres, then hand-curate genre-specific divergence (e.g. `rank` differing xianxia/romance) as a follow-up seed pass.
5. Idempotency: `ON CONFLICT (code) DO NOTHING` per tier (parity with current Seed()).

---

## 7. Extraction / assistant retarget (the integration surface)

All currently bind to system tier; in the sovereign model they must bind **book-local**:
| Site | Today | Target |
|---|---|---|
| `loadKindMap` (extraction_handler.go:730) | `system_kinds` + aliases → code→id | `book_kinds` for the book → code→book_kind_id |
| `loadAttrDefMap` (:770) | `system_kind_attributes` → "kind:code"→id | `book_attributes` → "kind:genre:code"→attr_id |
| `createExtractedEntity` (:879) | writes `kind_id`→system, values→system attr_def | writes `kind_id`→book_kind, values→book_attr |
| `internalExtractionProfile` (:46) | `genre_groups` + `system_kinds` + genre_tags filter | `book_active_genres` + `book_kinds`/`book_attributes` |
| **translation-glossary** read (`/internal/books/{id}/translation-glossary`) | `entity_attribute_values` + `attribute_translations` + `system_kind_attributes.code` | `book_attributes` (E2 — was missing; breaks translation JSONL context if not retargeted) |
| `confirmSchema` / `createKindFromParams` / `createAttrDefFromParams` | mint into `system_kinds`/`system_kind_attributes` | **O2:** assistant proposes into the **book** ontology, not system (tenancy — a user's extraction must not mutate system standards). Repoint propose/confirm to book tier. |

> Implication: a book MUST be adopted (have book_kinds) before extraction can run against it. The pick-list (R1) becomes a precondition — extraction profile returns "book not scaffolded" until adopt has run.

---

## 8. Milestone sequencing (each = a shippable risk boundary, VERIFY-gated)

| M | Title | Ships | Risk boundary / VERIFY |
|---|-------|-------|------------------------|
| **G1** | Schema rebuild + seed (full reset) | Truncate wiki_* + clear KG anchors (E1/E3) → drop retired (§1) → create all new tables (§2) → re-seed system standards incl. `unknown` (§6, E6). One migration. | DB migration (L+). Live-smoke: migrate up on throwaway DB, assert seeded counts + the spike's invariants in Go. |
| **G2** | Standards CRUD + **contract frozen** | OpenAPI (§4) authored; system read + user CRUD genres/attributes/kind-genres; recycle-bin parity. | Contract-first gate. Unit + handler tests; tenancy deny-tests (user can't write system). |
| **G3** | Book adopt (pick-list) + book-tier CRUD | `POST …/adopt` copy-down (Moment A); `/ontology` read (Moment B); `+ adopt more`. | The copy-down — re-prove the spike's assertions through the real handler on a live book. |
| **G4** | Entity repoint + extraction retarget | entities→book_kinds, values→book_attributes, entity_genres; retarget §7 sites; confirmSchema→book. | ≥2-service live-smoke (translation/extraction → glossary). The "book must be adopted first" precondition. |
| **G5** | Sync (on-demand diff/apply) | `sync/available` + `sync/apply` (§5); 04-sync surface. | diff correctness: edit a standard → "update available" → apply both choices. |
| **G6** | Frontend | React from the 5 drafts (MVC: hooks/context/components per CLAUDE.md). | Browser smoke (Playwright) on test account; multi-genre form + matrix + sync. |

Deferred (tracked, not this epic): restore bulk-merge (`createKindAlias`) retargeted to book model; per-book custom KG `relation` level (spec §5).

---

## 9. Decisions RATIFIED (2026-06-19)

- **O1 — attribute seeding granularity** → **Replicate + curate.** Seed each attr under all the kind's genres, then hand-curate genre-specific divergence (e.g. `rank` differing xianxia/romance) as a follow-up seed pass.
- **O2 — assistant write tier** → **Book-local.** Extraction / `confirmSchema` propose into the **book** ontology, not system. System-tier minting by the assistant is retired (tenancy). Any legitimate system mint stays admin-only.
- **O3 — system genre vocabulary** → **Seed the drafts' vocabulary too** (universal/fantasy/romance/drama/historical **+ xianxia/mystery**) so demos and drafts match.
- **O4 — `universal` semantics** → **Mandatory + always-active.** Every kind links to `universal`; it anchors genre-independent base attrs (name/description). Cannot be dropped from a book's active genres or an entity's genre set.

---

## 10. Workflow

Per CLAUDE.md task-sizing this effort is **XL** (schema + migration + multi-service contract + FE). Each Gn milestone runs the full 12-phase cycle with its own VERIFY evidence + 2-stage REVIEW; POST-REVIEW batched per-milestone. G1 and G4 are DB/cross-service → `/review-impl` recommended at their POST-REVIEW. No `/amaw` unless the user invokes it.

---

## 11. Pre-build evaluation — full-reset blast radius (code-audited)

A full reset is NOT confined to glossary's own tables. Audit (2026-06-19) found these ripples. **All are test/dump data** (user-confirmed), so the resolution is a *coordinated* reset, but G1 must own the coordination, not assume "drop glossary_entities" is local.

| # | Finding | Severity | Resolution (folded into plan) |
|---|---------|----------|-------------------------------|
| **E1** | **Wiki tables are FK-bound to entities with `ON DELETE RESTRICT`** — `wiki_articles.entity_id`, `superseded_by_entity_id` (migrate.go:597,626). A drop of `glossary_entities` is *blocked* until wiki rows are cleared. | HIGH (blocks migration) | G1 truncates wiki_* (articles/revisions/suggestions/source_usage/staleness) **before** dropping entities. Wiki feature unchanged; it re-populates as entities are recreated. |
| **E2** | **Translation is a SECOND retarget site, not in §7.** `/internal/books/{id}/translation-glossary` (glossary_client.py) reads `entity_attribute_values` + `attribute_translations` + `system_kind_attributes.code`. Repoint breaks its JSONL context. | HIGH (silent breakage) | Add translation-glossary read handler to the §7 retarget list → book_attributes. Now part of G4; G4 live-smoke must include a real translation context fetch. |
| **E3** | **Knowledge-service Neo4j anchors** store `glossary_entity_id` on `:Entity` nodes (entities.py:103). A reset orphans every anchor; `get_entity_by_glossary_id` returns nothing. | MED (test data, planned svc) | G1 includes a "clear KG anchors" step (`unlink_from_glossary` over all, or truncate the Neo4j test graph). Confirm Neo4j holds only test data. |
| **E4** | **Soft orphans** — composition-service, lore-enrichment (`cleanup_loc_orphans.py` SQL on glossary_entities), worker-ai token-budget count all hold in-memory/SQL refs to entity ids. | LOW (test data, recompute) | No code change; they recompute from the live glossary after reset. Note in SESSION_HANDOFF so a stale-count blip isn't mis-debugged. |
| **E5** | **Gateway needs NO changes** — `api-gateway-bff` proxies all `/v1/glossary/*` by pathFilter (gateway-setup.ts:102). New routes (adopt/ontology/sync/user-genres) flow through automatically. | — (good news) | Resolves the §4 BFF concern: contract is glossary-service-only; no BFF wiring. |
| **E6** | **`unknown` kind must be auto-adopted.** Extraction parks unrecognized kinds under `unknown` (extraction_handler.go:500+). In the book model, every book needs `unknown` or parking fails. | MED (correctness) | Adopt always seeds `unknown` into the book regardless of pick-list (not user-selectable). |
| **E7** | **Adopt idempotency/concurrency.** Double-submit pick-list or concurrent `+ adopt more` could double copy-down. | LOW-MED | Copy-down uses `ON CONFLICT (book_id, code) DO NOTHING` + a per-book advisory lock (mirror migrate.go execGuarded). |
| **E8** | **Rollback plan** (DB-migration guardrail). | process | Destructive on a feature branch only. Rollback = `git revert` the migration commit + re-run `migrate up` (re-seeds clean). Main is never touched until the epic is green. |

### The one architectural decision left — the **broken window** (needs your call)

The audit confirms the existing **frontend is ~39 files** (29 glossary + 10 glossary-translate) all bound to the current EAV/kind schema, plus wiki + translation context. The moment **G1** lands the new schema, *everything downstream is broken until G6 restores the FE*. Two strategies:

- **(A) Destructive on-branch, restore at G6** — full reset as designed; the app on `feat/glossary-assistant-coverage` is non-functional for glossary from G1→G6; **main stays safe** (we don't merge until the epic is green). Matches the ratified full-reset choice; simplest; one cutover.
- **(B) Additive coexistence** — build the new tables alongside the old, keep the old FE/queries working, dual-read during transition, cut over + drop old at G6. App never breaks, but ~2× the surface (dual schema, migration shims) and contradicts the clean full-reset.

**Recommendation: (A)** — it's a hobby project on an isolated branch with only test data; the coexistence tax buys nothing here. The broken window is contained to the branch and closed at G6.

**→ RATIFIED (R3): (A) destructive on-branch. (R4): all cross-service data is test — G1 clears Neo4j anchors; the rest recompute.**
