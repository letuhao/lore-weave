# Genre · Kind · Attribute Tiering — Design Spec

> **Date:** 2026-06-19 · **Phase:** DESIGN (re-architecture) · **Status:** Draft for approval
> **Drafts:** `design-drafts/glossary-tiering/{index,01-manage,02-attribute-matrix,03-entity-form,04-sync}.html`
> **Supersedes the drifted model** behind SS-4..SS-7 (docs 89, 93–96): those treated *kind* tiering in isolation; this restores the full **genre → kind → attribute** model across **system / user / book**, which was the primary design from March and drifted to a flat `genre_tags TEXT[]` on a single global table.

---

## 0. Vocabulary & two layers (read first — these terms are locked)

"Entity" and "attribute" each get used for two different things; that ambiguity is a drift source. The system has **two layers**:

**Layer 1 — the Ontology (definitions / schema).** Tiered System→User→Book, copy-on-adopt. Defines *what shape lore can take*.

| Term | What it is | Tables |
|---|---|---|
| **Genre** | a thematic context (xianxia, romance) | `system/user/book_genres` |
| **Kind** | a category of lore object (character, location) | `system/user/book_kinds` |
| **Attribute *definition*** | a *field* a `(kind × genre)` provides (`cultivation_realm`) | `system/user/book_attributes` |
| **kind↔genre link** | which genres a kind supports | `kind_genres` |
| *(reserved)* **Relation definition** | an edge type (`master_of`) — KG | *(future)* |

**Layer 2 — the Lore data (instances).** Per-book. The actual lore objects + their data.

| Term | What it is | Tables |
|---|---|---|
| **Glossary entity** | an actual lore object — *Diệp Phàm* (a character) | `glossary_entities` |
| **Attribute *value*** | a datum — *Diệp Phàm*.cultivation_realm = "Qi Refining" | `entity_attribute_values` |
| **entity↔genre** | which genres this entity carries | `entity_genres` |

**Locked terms:**
- **"entity"** → *only* the Layer-2 glossary lore object. Never a kind/genre/attribute. **Entities live only inside a book (the sovereign instance)** — System/User standards hold no entities.
- **kind / genre / attribute-definition** → **"definitions"** (Layer-1 tiered ontology). They are first-class objects (ER "entities") but we never call them "entities."
- **"attribute"** → never bare; always **"attribute definition"** (schema) or **"attribute value"** (data).
- **"glossary"** → the *container/feature*, not a single thing.

**One-sentence model:** a **glossary entity** *is of a* **kind** *and carries* **genres**; those `(kind × genre)` pairs supply **attribute definitions**; the entity stores an **attribute value** for each.

---

## 1. Why (root cause of the drift)

The original model was a **3-tier × 3-level** ontology where **attributes depend on both a kind and a genre** (a `character` carries different attributes — and different attribute *descriptions* — in a *xianxia* book vs a *romance* book). It was never written down, so over ~3 months it collapsed to:

- one global `entity_kinds` table (`UNIQUE(code)`, user-mutable) — a **tenancy defect** (one user's edit mutated every user's kinds), and
- a flat `genre_tags TEXT[]` array on kinds/attributes — losing genre as a first-class, tiered, attribute-scoping dimension.

SS-4 (2026-06-19) already corrected the *kind* row: split `system_kinds` / `user_kinds`, scope-keyed `UNIQUE(owner_user_id, code)`, and locked system writes (T1 lock). This spec restores the **full** model and reconciles SS-4 into it.

---

## 2. The model — 3 tiers × 3 levels (+ a reserved 4th level)

| Level ↓ \ Tier → | **System** (admin/seed, everyone reads) | **User** (`owner_user_id`) | **Book** (`book_id` + E0 grants) |
|---|---|---|---|
| **Genre** | `system_genres` | `user_genres` | `book_genres` |
| **Kind** | `system_kinds` *(SS-4 ✓)* | `user_kinds` *(SS-4 ✓)* | `book_kinds` *(SS-5)* |
| **Attribute** (keyed by **kind × genre × code**) | `system_attributes` | `user_attributes` | `book_attributes` |
| **Relation** *(reserved — KG edges, added when custom KG building ships)* | *(future)* | *(future)* | *(future)* |

- **Resolution:** within a single genre, an attribute `code` resolves **System → User → Book**; the highest tier that defines it wins (shadow-by-`code`). A regular user **never edits a System row** — they *override/clone* it into their own tier (CLAUDE.md › User Boundaries & Tenancy).
- **The "9 combinations":** an attribute attaches to a `(kind, genre)` pair; kind and genre each carry a tier, so an attribute spans any of the **3×3 = 9** `(kind-tier × genre-tier)` pairs (e.g. a *user* attribute added onto a *system* kind × *system* genre). The attribute's **own tier** is the table it lives in.
- **Genre is a full tiered level, exactly symmetric with kind** — three tiers, resolution by `code`, copy-on-adopt, recycle bin, deprecate-not-delete: all identical to kind. The only genre-specific traits are inherent, not structural: an entity has **one kind** but **selects multiple genres**, and genre **scopes which attributes apply**. The old per-book `genre_groups` + flat `genre_tags[]` were the drift; they are retired (§6).

### Decision records (do not re-litigate)

- **D1 — Structured, not generic EAV (for definitions).** Dimensions (tier, genre) are *known and stable*; only *instances* (which genres/kinds/attrs) are open-ended. Structured tables give unlimited instances **with** FK integrity + real indexes + reviewability. Generic EAV would add open *dimensions* we don't need, at the cost of the exact integrity that the tenancy bug came from. **Values** stay EAV (`entity_attribute_values`) and **reads** stay on the existing `entity_snapshot` flat model — the same "structured definitions + EAV values + snapshot reads" shape Akeneo PIM uses. The snapshot is orthogonal to this choice (we have it either way), so it is not a reason to go abstract.
- **D2 — Genre attachment = book-default + per-entity override.** A book declares its default genre set (its "world settings"); an entity inherits it but may override (add/remove) its own genres.
- **D3 — `(kind × genre)` pairs are sparse.** Attribute rows exist only where meaningful; the resolver only ever touches pairs that have rows.
- **D4 — Explicit `kind_genres` link.** A kind declares which genres it supports, independent of whether attributes exist yet (enables zero-attribute genres for future KG extraction scoping + explicit "kinds in this genre" organization).
- **D5 — Multi-genre conflict = keep-both-namespaced.** When two applicable genres define the same attribute `code` with different meaning, **both are kept**, namespaced `code·genre` (e.g. `rank·xianxia` = cultivation tier, `rank·romance` = social standing). Stored as independent value rows; no silent override across genres. (Cross-*tier* same-code within one genre still shadows.) **Refinement (M1):** only namespace when the two definitions actually **differ** (field_type/description); identical re-use of a `code` collapses to one field.
- **D6 — Identity is by `code` across tiers; customization is per-cell.** A `character` is *the* character at every tier (a same-code higher-tier definition **shadows/extends** the lower one, it is not a separate coexisting thing). You customize at the granularity of a single **attribute cell** `(kind, genre, code)`, not by cloning a whole kind. "Clone" is an optional **bulk-seed convenience**, not a separate identity. *(This retro-reframes SS-4's `user_kinds`-as-frozen-clone: a same-code user kind is an override of the system kind; `user_attributes` may attach to a shared kind identity — the 9 combinations.)*
- **D7 — In a book, the "User" tier = the book owner's.** Resolution `System → User → Book` uses the **book owner's** user tier (single & consistent for all E0 grantees — matches E0-4b where the book owner is the partition identity). A user's personal user-tier customizations apply only in their *own* books / no-book personal context. Without this, two collaborators would see different schemas for the same entity.
- **D8 — Boundary independence (copy-on-adopt + on-demand sync).** See the dedicated section below. Boundaries are independent: upstream changes never push or destroy downstream; adoption is pull-based.

---

## 3. Resolver — two moments (scaffold at adopt, read book-local)

Under the standards→instance model (§3b), resolution happens in **two moments**, not as a live cross-tier read:

**(a) At adopt — scaffold from the standards into the book.** When a book first uses a kind/genre, the adopt operation resolves the **System** and **User** *standards* by `code` (System base, then the book owner's User additions/overrides — D6 by-code, D7 owner's-user) and **copies the result into the book's own tier**. From then on, the definition is the book's — owned and frozen.

**(b) At read — book-local, single-tier.** The form is read entirely from the book's own definitions; **no cross-tier merge**:

```
activeGenres = E.genre_override (if any) else B.active_genres          # D2
applicable   = (activeGenres ∩ book_kind_genres(K)) ∪ {universal}     # D4, sparse via D3
form         = book_attributes where (book_kind = K, book_genre ∈ applicable)
               displayed namespaced by genre on same-code clash        # D5 — free: distinct rows
```

- **Single-tier read** — a sovereign book reads its own ontology; reproducible, no cross-tier join. Served from `entity_snapshot`.
- **The merge runs once, at adopt (a)** — applying D6 (identity by `code`) + D7 (owner's User tier). Each copied row keeps a `source_ref` so Sync (§3b) can later diff it against its standard.
- **Complexity:** `O(|active genres| × |attrs(K, ·)|)` within the book — bounded, linear.

---

## 3b. Boundary independence & change propagation (D8)

**Principle (standards → sovereign instance).** System and User are **standards** (templates), not shared live data — they hold *definitions only, no entities*. A **book is a sovereign instance** scaffolded from those standards, exactly like a project generated from a starter: it copies what it needs in, then **owns and evolves it independently**. This is *instantiation, not duplication* — nobody calls a generated `pom.xml` a "duplicate" of the Spring Boot starter.

| Spring Boot | LoreWeave |
|---|---|
| `start.spring.io` / a starter | **System** standard |
| your team's archetype/scaffold | **User** standard (the book owner's — D7) |
| a generated, committed project | **Book** instance |
| bumping a starter dep later, when you choose | **Sync** (on-demand) |

Consequences: a standard (System/User) **cannot mutate or delete an instance's data**; the book **adopts upgrades on demand**, never automatically; **entities belong to the book** (Layer-2 lore lives only in the instance — System/User hold no entities).

**What happens on each upstream operation:**

| Operation | What does NOT happen | What happens instead |
|---|---|---|
| **Remove** a definition | not hard-deleted out from under dependents; no cascade; entities never break | **soft-deprecate / retire** the source (retained). Copies elsewhere untouched; entities keep rendering from snapshot. Dependents migrate off **on demand** only. |
| **Edit** a definition | does not push into any other tier or rewrite any value | source **publishes a new version**; adopters see *"source changed — review diff?"* and **pull on demand** (the sync surface). Until pulled, the frozen copy stands. |
| **Add** a definition | does not auto-inject into existing books/entities | becomes **available to adopt**; existing boundaries pull on demand; only newly-created books/entities get the current set. |

→ **remove = deprecate · edit = publish · add = offer.** All pull-based.

**Mechanics (schema impact):**
- Adopted copies carry a **`source_ref`** (which upstream def they came from) so the sync surface can diff & offer — without ever auto-applying.
- **No hard delete across boundaries** — a `deprecated_at` / retired state on definitions; hard-delete only of a boundary's *own* unused, un-adopted rows.
- **Adoption is lazy** (approved): a book copies a definition on **first use**, plus an explicit "manage this book's adopted set" surface.
- **Books are sovereign instances** (approved): a book scaffolds everything it uses (system base included) into its own tier → maximal reproducibility (the per-book KG schema). This is **not** "duplication to minimize" — it is the architecture working as intended (a self-contained project, like a generated repo). No upstream version-pinning; the book owns its copy.
- The resolver falls back to `entity_snapshot` for anything whose source was retired.

**Edge cases this principle resolves** (from the design stress-test):
- *M2 — book/entity drops a genre after values entered:* values are frozen + snapshot-backed; entity still renders; restorable. Not orphaned.
- *M5 — removing the `universal` genre:* deprecate, never destroys; `universal` is also mandatory/always-applied.
- *SS-4 `deleteKind`-cascades-entities worry:* gone — you deprecate, never hard-delete across a boundary.

---

## 4. Schema (sketch — DDL refined per build slice)

**Each tier is self-contained — no polymorphic refs.** Because a book is a sovereign instance (§3b) and adoption copies a dependency *down* into your tier before you attach to it, every reference is **diagonal** (system→system, user→user, book→book) and is a **plain FK within the tier**. The "9 combinations" stays true *conceptually* (you may customize any kind×genre) but is always *physically* tier-local. Cross-tier relationship exists only as a nullable **`source_ref`** for Sync, never as a live FK. (This is what kills the old nullable-per-tier + CHECK polymorphism — and the SS-7 polymorphic entity repoint with it.)

```
-- GENRE — mirror per tier; every adopted (user/book) row carries source_ref for Sync
system_genres(genre_id, code UNIQUE, name, description, icon, color, is_hidden, sort_order, deprecated_at, ...)
user_genres  (genre_id, owner_user_id, code, ..., source_ref?, deprecated_at, UNIQUE(owner_user_id, code))
book_genres  (genre_id, book_id,       code, ..., source_ref?, deprecated_at, UNIQUE(book_id, code))

-- KIND — mirror per tier (SS-4 shipped system_kinds + user_kinds; book_kinds is SS-5)
--   + source_ref?, deprecated_at

-- KIND ↔ GENRE support link (D4) — per tier, plain FKs within the tier
system_kind_genres(system_kind_id FK, system_genre_id FK, UNIQUE(system_kind_id, system_genre_id))
user_kind_genres  (user_kind_id   FK, user_genre_id   FK, UNIQUE(user_kind_id,   user_genre_id))
book_kind_genres  (book_kind_id   FK, book_genre_id   FK, UNIQUE(book_kind_id,   book_genre_id))

-- ATTRIBUTE — per tier, plain FKs to that tier's kind + genre
system_attributes(attr_id, system_kind_id FK, system_genre_id FK,
  code, name, description,                     -- description is GENRE-SPECIFIC
  field_type, is_required, sort_order, options[], deprecated_at,
  UNIQUE(system_kind_id, system_genre_id, code))
user_attributes  (attr_id, user_kind_id FK, user_genre_id FK, ..., source_ref?,
  UNIQUE(user_kind_id, user_genre_id, code))
book_attributes  (attr_id, book_kind_id FK, book_genre_id FK, ..., source_ref?,
  UNIQUE(book_kind_id, book_genre_id, code))
-- D5 keep-both is FREE: same `code` in two genres = two rows (different *_genre_id).

-- GENRE attachment (D2) — book-local
book_active_genres(book_id, book_genre_id FK)   -- the book's DEFAULT active set
entity_genres(entity_id, book_genre_id FK)      -- per-entity override (presence ⇒ replaces default)

-- 'universal' — a system genre, scaffolded into every book, mandatory/always-applied.
```

- **Entity references are book-local plain FKs** — `glossary_entities.kind_id → book_kinds`, `entity_attribute_values.attr_def_id → book_attributes`. The old **SS-7 polymorphic entity repoint is no longer needed**; sovereignty makes it a plain in-book FK. (SS-4's `glossary_entities.kind_id → system_kinds` becomes `→ book_kinds` once books own their kinds.)

---

## 5. Knowledge-Graph readiness (forward fit, no conflict)

The tiered glossary is the **authored per-book ontology** a custom KG builds against (glossary = authored SSOT; knowledge-service = derived Neo4j graph anchored via `glossary_entity_id` — the existing two-layer plan). The book tier **is** the per-book KG schema VCTĐ needs ("built specifically to resolve specific problems"). Genres also scope extraction patterns (xianxia → master–disciple/sect edges; romance → relationship edges).

**Reserved extension:** a KG is about typed **edges**, which today are weak (free-text attributes). When custom KG building ships, add a **`relation` level** (relation/edge types, tiered system/user/book like kinds — e.g. a book-custom `sworn_brother` for VCTĐ). This is **additive** — keep the tiering generic so "exactly 3 levels" is never hardcoded in schema/UI.

---

## 6. SS-4 reconciliation

What SS-4 shipped is a correct slice; this expands it:

| SS-4 artifact | Reconciliation |
|---|---|
| `system_kinds` / `user_kinds` | Keep as-is (the Kind row). |
| `system_kind_attributes` / `user_kind_attributes` (keyed by **kind only**) | **Gain the genre dimension** → become `system_attributes` / `user_attributes` keyed by `(kind, genre, code)`. Backfill existing rows onto the seeded `universal` genre. |
| T1 lock (system write routes removed) | Keep. New genre/attribute writes follow the same tier rules (user/book write to their own tier; system seed/admin-only). |
| `user_kind_handler.go` CRUD | Extend to carry `genre_ref`; the tenant-isolation guarantees and recycle-bin pattern carry over. |

---

## 6b. Current → target schema delta (migration checklist)

**🆕 NEW**

| Table | Slice | Note |
|---|---|---|
| `system_genres` · `user_genres` · `book_genres` | G1 | the genre tier (fully symmetric with kind); `genre_groups` data migrates into `book_genres` |
| `system_kind_genres` · `user_kind_genres` · `book_kind_genres` | G2 | explicit kind↔genre support link (D4) — per-tier plain FKs |
| `book_active_genres` (book default set) + `entity_genres` (per-entity override) | G2 | genre attachment (D2) |
| `book_kinds` · `book_attributes` | SS-5 | book tier of kind + attribute |

**🔧 UPDATE existing**

| Table | Change | Slice |
|---|---|---|
| `system_kind_attributes` / `user_kind_attributes` | **add genre dimension** → keyed by `(kind, genre, code)` (become `system_attributes`/`user_attributes`); backfill onto a seeded `universal` genre | G3 |
| all definition tables | add `source_ref` (copy-on-adopt diff) + `deprecated_at` (deprecate-not-delete) | G1–G4 |
| `glossary_entities.kind_id` → `book_kinds`, `entity_attribute_values.attr_def_id` → `book_attributes` | **book-local plain FK** (sovereignty — no polymorphic repoint) + `entity_genres` link | SS-5 |

**🗑 RETIRE / migrate away**

| Old | Becomes |
|---|---|
| `genre_groups` (per-book, free-form) | `book_genres` |
| `genre_tags TEXT[]` on kinds/attrs/books | `kind_genres` links + the genre tables (translate array values → genre refs, then drop) |

---

## 7. Build sequencing (proposed)

1. **G1 — Genre tier:** `system_genres`/`user_genres`/`book_genres` + seed system genres (universal, + the current `genre_groups` data migrated) + CRUD (tiered, system read-only).
2. **G2 — kind_genres link (D4)** + book default genre set + per-entity override (D2).
3. **G3 — Attribute reconciliation:** add genre dimension to the attribute tables (rename/rework `*_kind_attributes` → `*_attributes` keyed by `(kind, genre, code)`); backfill onto `universal`.
4. **G4 — Resolver + merge (keep-both-namespaced)** + cache + snapshot integration.
5. **G5 — Frontend:** the `design-drafts/` UX (manage workspace, attribute matrix, entity form) — full rework per the approved drafts.
6. **(later) SS-5 book tier** (book_kinds/genres/attributes) **+ repoint entity refs to book-local FKs · restore bulk-merge/assistant tiering at the tiered model · KG `relation` level.** (The old "SS-7 polymorphic repoint" is dropped — sovereignty makes entity refs plain in-book FKs.)

Each slice: additive + idempotent migrations, real-PG tests incl. the tenancy + merge guards, `/amaw` for the data-shape migrations (G3).

---

## 8. Open items for the spec review

- Drafts `entity-form.html` / `manage.html` need a small update to show **per-entity genre override** (D2) and **explicit kind_genres membership** (D4) — currently they imply book-only genres + implicit membership.
- Confirm the **polymorphic ref** shape (nullable-per-tier + CHECK) vs a unified registry before G3.
