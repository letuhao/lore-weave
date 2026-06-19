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
- **"entity"** → *only* the Layer-2 glossary lore object. Never a kind/genre/attribute.
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

## 3. Resolver

For entity `E` of kind `K` in book `B`:

```
activeGenres = E.genre_override (if any) else B.default_genres        # D2
applicable   = (activeGenres ∩ kind_genres(K)) ∪ {universal}          # D4, sparse via D3
for g in applicable:
    attrs(K,g) = mergeByCode(                                          # System→User→Book, D1
        system_attributes  where (kind=K, genre=g),
        user_attributes    where (kind=K, genre=g),
        book_attributes    where (kind=K, genre=g, book=B))           # higher tier shadows by code
form = concat over g of namespace(attrs(K,g), g)                      # D5: code·genre on cross-genre clash
```

- **Complexity:** linear in the book's own ontology size — `O(|B.genres| × |attrs(K, ·)|)`, bounded per book; reads served from `entity_snapshot`.
- **Reads are boundary-local (D8):** a book resolves over its **own adopted copies** of the tiers (self-contained), not live-current upstream. `mergeByCode` runs over the book's frozen layers; upstream changes arrive only via on-demand sync (§3b). This is what makes resolution boundary-bounded and a book reproducible.
- **Cache key:** resolved definitions per `(book, kind, active-genres)`; invalidate on a sync-apply (not on upstream edits — those don't reach the book until adopted).

---

## 3b. Boundary independence & change propagation (D8)

**Principle (the package/dependency model):** boundaries (a book, a user) are independent. You **depend by copy**, not by live link. A publisher (System) **cannot mutate or delete a consumer's data**. Consumers **adopt upgrades on demand**, never automatically. Each boundary holds its **own frozen copy** of the definitions it has adopted; nothing flows in by itself.

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
- **Books are self-contained** (approved, strong isolation): a book copies everything it uses (system base included) → maximal reproducibility (the per-book KG schema), bounded duplication (dedup'd by `entity_snapshot` on reads).
- The resolver falls back to `entity_snapshot` for anything whose source was retired.

**Edge cases this principle resolves** (from the design stress-test):
- *M2 — book/entity drops a genre after values entered:* values are frozen + snapshot-backed; entity still renders; restorable. Not orphaned.
- *M5 — removing the `universal` genre:* deprecate, never destroys; `universal` is also mandatory/always-applied.
- *SS-4 `deleteKind`-cascades-entities worry:* gone — you deprecate, never hard-delete across a boundary.

---

## 4. Schema (sketch — DDL refined per build slice)

Separate table per `(tier, level)` (consistent with the SS-4 explicit-system-tables decision). Polymorphic `(kind, genre)` references use **nullable per-tier columns + a CHECK that exactly one tier-ref is non-null** (the SS-7 pattern — preserves FK integrity; no soft references).

```
-- GENRE level (mirror for user_/book_; book_genres adds book_id + E0 gating)
system_genres(genre_id, code UNIQUE, name, description, icon, color, is_hidden, sort_order, ...)
user_genres  (genre_id, owner_user_id, code, ..., UNIQUE(owner_user_id, code))
book_genres  (genre_id, book_id,       code, ..., UNIQUE(book_id, code))

-- KIND level — SS-4 shipped system_kinds + user_kinds; book_kinds is SS-5
-- (existing; unchanged except they join the kind_genres link below)

-- KIND ↔ GENRE support link (D4). The link itself is tiered (who declared it).
kind_genres(
  link_id,
  -- polymorphic kind ref (exactly one non-null + CHECK):
  system_kind_id?, user_kind_id?, book_kind_id?,
  -- polymorphic genre ref (exactly one non-null + CHECK):
  system_genre_id?, user_genre_id?, book_genre_id?,
  owner_user_id?, book_id?,          -- the tier that declared this support
  UNIQUE(<kind ref>, <genre ref>, <declaring scope>)
)

-- ATTRIBUTE level — keyed by (kind × genre × code), tiered. Reconciles SS-4's
-- system_kind_attributes / user_kind_attributes (which were keyed by kind only).
system_attributes / user_attributes / book_attributes (
  attr_id,
  system_kind_id?/user_kind_id?/book_kind_id?,     -- polymorphic kind ref + CHECK
  system_genre_id?/user_genre_id?/book_genre_id?,  -- polymorphic genre ref + CHECK
  code, name, description,        -- description is GENRE-SPECIFIC
  field_type, is_required, sort_order, options[],
  owner_user_id?/book_id?,        -- tier ownership (per table)
  deleted_at, ...,
  UNIQUE(<kind ref>, <genre ref>, code, <tier scope>)
)

-- GENRE attachment (D2)
book_genres_active(book_id, genre_ref...)   -- the book's DEFAULT active genre set
entity_genres(entity_id, genre_ref...)      -- per-entity override (presence ⇒ overrides book default)

-- 'universal' is a seeded system_genre that always applies (every kind supports it).
```

- **Entity kind/attr-value references** (`glossary_entities.kind_id`, `entity_attribute_values.attr_def_id`) become tier-aware (nullable per-tier + discriminator) — this is the **SS-7** polymorphic repoint; until then they keep referencing `system_kinds` as today.

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
| `kind_genres` | G2 | explicit kind↔genre support link (D4) |
| `book_active_genres` (book default set) + `entity_genres` (per-entity override) | G2 | genre attachment (D2) |
| `book_kinds` · `book_attributes` | SS-5 | book tier of kind + attribute |

**🔧 UPDATE existing**

| Table | Change | Slice |
|---|---|---|
| `system_kind_attributes` / `user_kind_attributes` | **add genre dimension** → keyed by `(kind, genre, code)` (become `system_attributes`/`user_attributes`); backfill onto a seeded `universal` genre | G3 |
| all definition tables | add `source_ref` (copy-on-adopt diff) + `deprecated_at` (deprecate-not-delete) | G1–G4 |
| `glossary_entities.kind_id`, `entity_attribute_values.attr_def_id` | tier-aware polymorphic refs (+ `entity_genres` link) | SS-7 |

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
6. **(later) SS-5 book_kinds · SS-7 polymorphic entity ref + restore bulk-merge/assistant tiering · KG `relation` level.**

Each slice: additive + idempotent migrations, real-PG tests incl. the tenancy + merge guards, `/amaw` for the data-shape migrations (G3).

---

## 8. Open items for the spec review

- Drafts `entity-form.html` / `manage.html` need a small update to show **per-entity genre override** (D2) and **explicit kind_genres membership** (D4) — currently they imply book-only genres + implicit membership.
- Confirm the **polymorphic ref** shape (nullable-per-tier + CHECK) vs a unified registry before G3.
