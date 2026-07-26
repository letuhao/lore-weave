# 22 · Scene — data model, CRUD surface (GUI + MCP), Browser & Inspector

> **Status:** 📐 specced 2026-07-10 · ✏️ **amended 2026-07-10** (see the Amendment block below) · branch `feat/context-budget-law` (studio track) · **L** (files≈20, logic≈11, side_effects=4 — reduced from XL by the read-only-index amendment)
> **Prerequisite:** [`23_book_architecture.md`](23_book_architecture.md) Phase 0.
> Design draft: [`design-drafts/screens/studio/screen-scene-browser.html`](../../../design-drafts/screens/studio/screen-scene-browser.html) — renders both panels, the Work-less state, and the SceneRail before/after. Every field carries a **provenance tick** (teal = identity / amber = intent) so a field on the wrong side of the seam is visible at a glance.
> **Cross-service:** `book-service` (Go) + `composition-service` (Python) + `frontend`. `knowledge-service` and `worker-infra` are untouched **by design** (see SC3).
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), [`docs/standards/scope-separation.md`](../../standards/scope-separation.md) (two-layer SSOT↔derived pattern).

---

## ⚠ Amendment 2026-07-10 — reconciliation with [`23_book_architecture.md`](23_book_architecture.md)

**Nothing in this file was built when the amendment landed** (`scene_tools.go`, `outline_node.scene_id`, and the `SceneBrowser` panel were all absent). Everything below is therefore a spec edit, not a migration.

`23` locks the governing model: **composition is the durable *spec* (desired state); book-service is the *implementation* (hand-edited prose, the SSOT of content); `book-service.scenes` is the *index* (a source map over `chapter.body`).** The relation between plan and prose is `terraform plan` — desired ↔ actual, reconciled — **not** source → binary. Prose is never rebuilt from the plan.

Five decisions in this file were written against the opposite assumption and are superseded:

| # | Was | Now | Why |
|---|---|---|---|
| **SC1** | *"`book-service.scenes` is the scene **SSOT** (identity)"* | **`scenes` is the scene INDEX** — parse leaves over `chapter.body`, derived by the parser, never hand-edited. The word *SSOT* was doing damage: the SSOT of scene *content* is the prose; the SSOT of scene *intent* is `outline_node`. It still gains `book_id`/`title`/`origin` and its public `/v1` CRUD. | `path`, `leaf_text`, `content_hash`, `parse_version` are parser output — a `.pdb`, not a source file. |
| **SC2** | `outline_node.scene_id` + `UNIQUE(project_id, scene_id)` | **Anchor inverted:** `scenes.source_scene_id UUID NULL`, **no uniqueness**. `outline_node.scene_id` and its scoped-unique index are **deleted from this spec.** | The **index carries the map**, not the thing indexed. `scope-separation`'s pattern is authored-SSOT ← derived-anchor: glossary(authored) ← knowledge(derived) ⇒ composition(spec) ← book(index). SC2 as written pointed it the other way while citing the precedent. |
| **SC5** | *"Greenfield scene creation writes book-service **first**"* | **Inverted, and simpler: authoring writes composition only.** The `scenes` index row appears when prose exists. **There is now no cross-service write on create at all.** | You author the spec, then the prose; the symbol table is emitted by the parser, not by the author. Removes a cross-service write rather than justifying one. |
| **SC6** | *"Import materializes intent … if a Work exists"* | **Unchanged in behavior, renamed in intent: this is the *decompiler*.** With `23`'s BA8 the spec tree is Per-book, so it no longer depends on a Work existing. State it in those terms so the next agent does not invert it back. | A binary acquires source by decompilation. `arc_import_analyze` / `motif_mine` are the same move at arc scale. |
| **OQ-2** | *"Should `composition_work` re-scope to Per-book? — out of scope, real"* | **Resolved by [`23`](23_book_architecture.md) BA8: the spec tree is Per-book.** `plan_run`, `authoring_runs`, and `plan_bootstrap_proposal` are **already** `book_id NOT NULL` — PlanForge decided this; the spec layer follows precedent, not argument. | OQ-2 was the **root cause**, and SC1 was a workaround for it. `UNIQUE(project_id, scene_id)` existed *only* to let two per-user Works hold two plans for one scene. Fix the scope and the index disappears. Collaborator divergence becomes a **branch of the spec**, which is the same mechanism as "many versions" — one concept, not two. |

**Cardinality, checked and corrected.** An earlier reading feared `composition_work.book_id NOT NULL` foreclosed "one source → many books". It does not, and no `work_build` table is needed: `chapter_translations(chapter_id, book_id, target_language)` attaches a translation to the **same chapter in the same book**, and `chapter_revisions(chapter_id, body, message, author_user_id)` attaches a version to the same chapter. **A book already holds its own languages and its own history.** `book_id NOT NULL` is honest. One Work : one book.

**Ordering.** `23` is a **prerequisite**. This file's `SceneBrowser` already offers *"Group-by: … Arc (hidden when no Work)"* — a leaf spec routing around a missing trunk. `23`'s `structure_node` supplies the trunk, and Phase 0 of `23` (the Per-book re-key) must land before this file's B1.

**Unchanged and still correct:** F1–F6, SC3, SC4, SC7–SC13, SC11 (the browser reads book-service — a binary without source must still be browsable, which holds under both models), and the whole verification design D1–D4. **F2's exposure matrix remains the core find of this spec.**

---

## Why

The scene is the smallest unit an author actually thinks in, and today it is the least
addressable object in the system. The presenting complaint — *"the current scene is too
simple, no browser, and I don't know its structure — it seems like only text to store a
description"* — turns out to be **half right for the wrong reason.** The model is not thin.
The **exposure** is: a 12-column authoring entity is reachable through 2 editable GUI fields
and 4 writable MCP fields, and a second, entirely separate scene entity holds the real
manuscript text and has no user-facing route at all.

Three defects, all verified against code (§Investigation):

1. **Two unrelated things are both called "scene."** They share a `chapter_id`, are never
   joined, and neither knows the other exists.
2. **Fields that drive generation are unreachable.** `present_entity_ids` gates whether the
   packer injects a character's voice tags; `tension` gates `adaptive_k`'s reasoning policy at
   `>= 70`. Neither can be set by a human or an agent. This is the *write-only behavior* class
   CLAUDE.md's Settings & Configuration Boundary names explicitly.
3. **No browser, at any layer.** Not "no GUI" — there is no HTTP route. Both scene endpoints
   in `book-service` are registered under `/internal` behind `requireInternalToken`.

---

## Investigation findings

Everything below was read from source, not from a prior doc.

### F1 — "scene" names two disjoint entities

| | `book-service.scenes` | `composition.outline_node WHERE kind='scene'` |
|---|---|---|
| Nature | parse leaf of a chapter's prose | the **authored** scene (plan/intent) |
| Scope key | `chapter_id → book_id` — **Per-book** | `(user_id, project_id)` — **Per-user** |
| DDL | [`migrate.go:270`](../../../services/book-service/internal/migrate/migrate.go#L270) | [`migrate.py:156`](../../../services/composition-service/app/db/migrate.py#L156) |
| Columns | `id, chapter_id, sort_order, path, leaf_text, content_hash, parse_version, lifecycle_state, trashed_at` · `UNIQUE(chapter_id, sort_order)` | 16, incl. `pov_entity_id, present_entity_ids[], goal, beat_role, tension, story_order, synopsis, version` |
| Written by | `parse.go:282`, `import_processor.go:291`, `import_processor_pdf.go:173` (all **Go**) | `OutlineRepo`, the planner, PlanForge commit |
| Read by | `knowledge-service` P2 extraction ([`book_client.py:520`](../../../services/knowledge-service/app/clients/book_client.py#L520)); `hierarchy.go:137` | 12 composition engine modules |
| HTTP surface | `/internal/…/scenes` ([`server.go:206`](../../../services/book-service/internal/api/server.go#L206)) + `/internal/…/hierarchy` ([`:215`](../../../services/book-service/internal/api/server.go#L215)) — **both behind `requireInternalToken`** | REST `/v1/composition/…` + 8 MCP tools |
| CRUD | **none** | full |

**Consequence.** Import a book → the parser fills `book-service.scenes` with real leaf text →
the Studio's [`SceneRail`](../../../frontend/src/features/studio/manuscript/SceneRail.tsx)
reads `outline_node` → renders *"No scenes for this chapter (outline it in the composer)."*
The parse result exists and is invisible. That empty rail is the origin of "the scene is too
simple."

### F2 — exposure matrix (the real defect)

`_UPDATABLE_COLUMNS` ([`outline.py:34`](../../../services/composition-service/app/db/repositories/outline.py#L34))
permits **all 12** authoring fields. Every layer above it drops most of them.

| Field | DB | Repo | MCP write | MCP read | FE `OutlineNode` type | SceneRail |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `synopsis` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ edit |
| `status` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ edit |
| `title` | ✓ | ✓ | ✓ | ✓ | ✓ | ⚠️ **create-only** — the row renders it as a *jump button*, never an input |
| `goal` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| `beat_role` | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ |
| `story_order` | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ |
| `pov_entity_id` | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| `present_entity_ids` | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| `tension` | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| `parent_id` `rank` `chapter_id` | ✓ | ✓ | via reorder | ✓ | ✓ | ✓ reorder |

Two named pathologies fall out:

- **`goal` is agent-writable and human-invisible.** `_NodeCreateArgs` and `_NodeUpdateArgs`
  both accept it; the FE `OutlineNode` type has no such key. An agent sets a scene's goal and
  no human can read or correct it.
- **`pov_entity_id` / `present_entity_ids` / `tension` are read-only to *everyone*.**
  `composition_get_outline_node` returns a full `node.model_dump(mode="json")`, so an agent
  can *read* them; no tool and no GUI can *write* them. Their only writer is the whole-outline
  PlanForge commit path. Yet `adaptive_k` gates "high dramatic tension" on `tension >= 70`,
  and the packer injects a character's `voice_profile` tags **only when that entity is present
  in the scene**. Generation behavior is driven by state nobody can inspect or set.

### F3 — what `outline_node` is structurally load-bearing for

Five in-database dependents inside composition's own DB, three with `ON DELETE CASCADE`:

| Dependent | Coupling | Ref |
|---|---|---|
| `generation_job.outline_node_id` | 2 × `JOIN`, 2 × `EXISTS` guard | [`generation_jobs.py:394`](../../../services/composition-service/app/db/repositories/generation_jobs.py#L394), [`:426`](../../../services/composition-service/app/db/repositories/generation_jobs.py#L426) |
| `motif_application.outline_node_id` | motif bindings JOIN the scene | [`motif_select.py:287`](../../../services/composition-service/app/engine/motif_select.py#L287) |
| `scene_link.from_node_id` / `.to_node_id` | **FK, cascade** | [`migrate.py:192`](../../../services/composition-service/app/db/migrate.py#L192) |
| `scene_grounding_pins.outline_node_id` | **FK, cascade** | [`migrate.py:384`](../../../services/composition-service/app/db/migrate.py#L384) |
| `motif_select.py:384` | `UPDATE outline_node SET is_archived` during motif re-binding | — |

`style_profile.scope_id` is already a soft ref (no FK) — no cost there.

### F4 — the "hot path" concern was unfounded

`useSceneWhatIf` makes **no API calls** — what-if is entirely client-side. `adaptive_k` and
`arc_conformance` read `tension`/`beat_role` off in-memory `OutlineNode` objects, not SQL.
There is no per-keystroke cross-service write to worry about. The cost of relocating the scene
is concentrated *entirely* in F3's five structural dependencies.

### F5 — satellite surfaces already exist and are healthy

`scene_link` has MCP tools (`composition_scene_link_create/delete`) and a GUI
(`SceneGraphCanvas`). `scene_grounding_pins` has `GroundingPanel` + a `PUT
…/scenes/{node_id}/grounding-pins` route. These are **not** part of the defect and are reused
as-is.

### F6 — the Tiptap anchor stores an `outline_node.id`

[`SceneAnchor.ts`](../../../frontend/src/components/editor/SceneAnchor.ts) persists
`data-scene-id` as a `sceneId` **attribute on an existing heading node**, and `SceneRail`
passes it an `OutlineNode.id`. Any change of scene identity would otherwise imply a data
migration over user prose. See SC7.

---

## The design: A′ — split identity from intent

> ✏️ **Amendment.** A′'s central move — *cut along the seam that already exists in the data* — is
> right and survives intact. What the amendment changes is **which side owns the identity, and
> therefore which side carries the anchor.** A′ named `scenes` the SSOT because that fixed a
> *tenancy* problem (per-user Works), then pointed the anchor composition → book while citing
> `scope-separation`, whose pattern points derived → authored. Fixing the tenancy problem at its
> root ([`23`](23_book_architecture.md) BA8) removes the reason to move identity at all. Read the
> section below with `scenes` = **index**, `outline_node` = **spec**, and the arrow reversed.

The user's call was **"scenes move to book-service"** (Option A) with a **model-first** scope
and **browser + inspector**. Literal Option A — moving the authoring fields too — converts all
five F3 dependencies into cross-service soft refs and forces the planner to rebuild cascade
semantics as an event + orphan sweeper. A′ delivers Option A's tenancy correctness at zero FK
cost by cutting along the seam that already exists in the data.

**A scene has two natures:**

- **Manuscript identity** — which book, which chapter, what order, what text span, parse
  provenance. Facts about the *manuscript*. **Per-book**, shared with every E0 grantee. This
  is what a browser browses and what `knowledge-service` extracts.
- **Authoring intent** — pov, present entities, tension, goal, synopsis, beat role, and all
  four new field groups. Claims about the *plan*. This is what the planner and packer reason
  over.

So: `book-service.scenes` becomes the **SSOT for identity** and gains a public, grant-gated
`/v1` CRUD. `outline_node` keeps its row **and every dependent**, gaining exactly one column —
`scene_id`, a soft ref to the book-service scene.

This is not a new pattern. It is the one this repo already standardizes on: `glossary-service`
is the authored SSOT, `knowledge-service` the derived layer anchored by `glossary_entity_id`
([scope-separation](../../standards/scope-separation.md)). Scenes become the same shape —
**book-service owns the scene; composition owns the plan for it.**

```
  composition.outline_node (kind='scene')        book-service.scenes
  ┌──────────────────────────────────┐           ┌──────────────────────────┐
  │ SPEC · Per-book (23 BA8)         │──────────▶│ INDEX · Per-book         │
  │ authored intent, durable         │  (pointed │ parse leaves over        │
  ├──────────────────────────────────┤   AT by)  │ chapter.body — derived   │
  │ id ◀── generation_job            │           ├──────────────────────────┤
  │    ◀── motif_application         │◀──────────│ source_scene_id  (soft,  │
  │    ◀── scene_link       (FK)     │           │   nullable, NON-unique)  │
  │    ◀── scene_grounding_pins (FK) │           │ id, book_id, chapter_id  │
  │    ◀── structure_node   (23)     │           │ leaf_text, content_hash  │
  └──────────────────────────────────┘           │ parse_version, origin    │
        ▲                                        └──────────────────────────┘
   planner, packer, PlanForge                          ▲
   (all in-DB joins intact)                  parse.go, import_processor{,_pdf}.go
                                             knowledge-service P2 extraction
```

**Why the anchor lives on `scenes` and carries no uniqueness.** The **index carries the map** —
a symbol table points at source, never the reverse. That is also what `scope-separation` actually
prescribes (authored SSOT ← derived anchor): `glossary`(authored) ← `knowledge`(derived) ⇒
`composition`(spec) ← `book`(index). Non-unique, because one spec scene may map to many parse
leaves across revisions and languages.

The `kg-glossary-fk-is-globally-unique` lesson (fixed in `6ab383f34`) still applies and is
**better served** by this direction: that bug was *two anchor-writers disagreeing on identity*.
Here there is exactly one writing **role** for `source_scene_id` — the index owner: book-service's parser plus worker-infra's book-DB import tail (the [`26`](26_structure_prose_indexing.md) IX-12 decompile write-back; DA-8 ✏️), never composition — and exactly one owner of
scene identity — the spec.

### Tier consequence, stated rather than buried

Per [`23`](23_book_architecture.md) BA8 the spec tree is **Per-book**, matching `plan_run` /
`authoring_runs` / `plan_bootstrap_proposal`, which are already `book_id NOT NULL`. So
collaborators **share one spec and one manuscript** — as a team shares one `main.tf`, not one
copy each. The original "shared manuscript, private plan" story is retired: it existed only to
work around per-user Works.

Divergence between collaborators is therefore a **branch of the spec**, not a private copy of it
— the same mechanism as "many versions", so it is *one* concept to build rather than two.
Branching itself is out of scope here (`23` OQ-2).

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **SC1** ✏️ *amended* | **`book-service.scenes` is the scene INDEX** — parse leaves over `chapter.body`, at the **Per-book** tier: owner + E0 grantees. It gains `book_id` (denormalized from `chapter_id`), `title`, `origin`, and a public `/v1` CRUD. It is **not** the SSOT: content lives in the prose, intent lives in `outline_node`. | An index is Per-book because the manuscript is. `path`/`leaf_text`/`content_hash`/`parse_version` are parser output — a `.pdb`, not a source file. Denormalizing `book_id` makes a book-wide browser a single indexed scan. |
| **SC2** ✏️ *superseded* | **Anchor inverted.** `outline_node` keeps `kind='scene'` and every dependent, and gains **nothing**. `book-service.scenes` gains **`source_scene_id UUID NULL`, non-unique**. `outline_node.scene_id` + `UNIQUE(project_id, scene_id)` are **deleted from this spec**. | The **index carries the map** — a symbol table points at source, not the reverse. This is what `scope-separation` actually says (authored SSOT ← derived anchor): composition(spec) ← book(index). Non-unique because one spec scene may map to many parse leaves, across revisions and languages. With `23` BA8 making the spec Per-book, `project_id` drops out of the key entirely. |
| **SC3** | **`knowledge-service` and `worker-infra` are not modified.** `/internal/…/scenes` keeps its exact response shape; the three Go `INSERT INTO scenes` writers keep writing their own service's DB. | The two obstacles that made literal-A expensive both dissolve. Also honors "each microservice owns its own Postgres database." |
| **SC4** | **All four new field groups land on `outline_node`, not on `scenes`** — every one of them is *authored intent*, not manuscript fact. New: `location_entity_id`, `story_time`, `conflict`, `outcome`, `value_shift`, `stakes`, `target_words`, `exit_state`. | Keeps the seam clean: an imported book's *facts* are extracted by knowledge-service; a scene's *conflict* is a claim the author makes. Also means book-service's migration stays additive-and-small. |
| **SC5** ✏️ *inverted* | **Greenfield scene creation writes composition ONLY.** The composer inserts an `outline_node` (spec scene). The `scenes` index row is emitted **when canon exists** — by the parser, **on publish** (never on draft/save: the index indexes the pinned published revision, and publish is the free debounce — [`26`](26_structure_prose_indexing.md) IX-1) — and back-links via `source_scene_id`. **There is no cross-service write on create.** | You author the spec, then the prose; a symbol table is emitted by the toolchain, never by the author. This removes the cross-service write that the original SC5 had to justify. A spec scene with no index row renders as *"not yet written"* — the correct affordance, not a bug. |
| **SC6** ✏️ *renamed* | **Import materializes the spec — this is the *decompiler*.** After parse, the import tail calls a composition internal route that upserts one `outline_node` per parsed scene, keyed on the book. Per `23` BA8 the spec tree is Per-book, so this **no longer depends on a Work existing**. | Fixes the empty-rail bug at its root. A binary acquires source by decompilation — `arc_import_analyze`/`motif_mine` are the same move at arc scale. Naming it explicitly is what stops the next agent inverting it back. The browser still does not depend on it (SC11); extraction is unaffected (SC3). |
| **SC7** | **`data-scene-id` in chapter prose keeps storing `outline_node.id`.** No prose migration. `SceneBrowser`/`SceneRail` resolve `scene_id → outline_node.id` before calling `jumpToSceneAnchor`. | The anchor's job is "jump to *this authored scene*" — an intent concern. Rewriting `data-scene-id` across every chapter body is a migration over user content for no behavioral gain, and anchors are already backfilled by the ⚓ action on title match ([F6](#f6--the-tiptap-anchor-stores-an-outline_nodeid)). |
| **SC8** | **MCP widens to the full intent set.** `composition_outline_node_create` / `_update` accept every `_UPDATABLE_COLUMNS` field plus the SC4 additions. Closed-set args (`status`, `beat_role`, `value_shift` sign, `item_type`) get `enum`; `tension` / `value_shift` / `target_words` get range validation at the schema, not the handler. | Closes both F2 pathologies in one pass. Per [mcp-tool-io](../../standards/mcp-tool-io.md) IN-2 (closed set ⇒ `enum`) — the `panel_id`-free-string bug class. |
| **SC9** | **New book-service MCP tools** `book_scene_list / get / create / update / delete / reorder`, VIEW-gated read + EDIT-gated write, mirroring the `steering` routes' tier split already in `server.go:253`. `book_scene_list` supports the browser's filters server-side. | MCP-first invariant: the browser's capability must be agent-reachable, not GUI-only. |
| **SC10** | **Two panels, not one.** `scene-browser` (book-wide table: filter/sort/group, bulk-act) and `scene-inspector` (single-scene full-field editor, folding in `scene_link` + `scene_grounding_pins`). `SceneRail` **stays** as the chapter-local strip beside the editor. | Same DOCK-8 reasoning as [`15b_chapter_browser.md`](15b_chapter_browser.md): tree/strip-for-writing vs table-for-triage-at-scale are different jobs. The inspector is a *detail pane over a selection*, not a third capability. |
| **SC11** | **The browser reads book-service and LEFT JOINs intent client-side** via one `composition_list_outline` call keyed by `chapter_id`. A Work-less book renders identity columns and greys the intent columns. | Preserves "a Work-less book still browses." No new BE join across services. |
| **SC12** | **`exit_state` is typed JSONB with a versioned envelope** (`{v:1, ...}`), validated by a Pydantic model on write — not a free-form blob. It mirrors the existing cross-chapter `ChapterExitState` delta, pushed down to scene granularity. | An unvalidated JSONB column becomes a schema nobody owns. Versioned envelope makes the next migration possible. |
| **SC13** | **Reconciles with D17**, not against it. D17 (*"scene prose stays in `chapter.body`; raw `scenes[]` is outline metadata only"*) still holds: `scenes.leaf_text` is a **parse projection** of `chapter.body`, derived and rebuilt by the parser, **never independently edited**. Scene CRUD writes identity + intent; prose edits go through `chapter_drafts` exactly as today. | D17 exists to prevent a second prose store. A read-only derived projection is not a second store — but it must be stated, or the next agent will "fix" the browser by making `leaf_text` editable. |

---

## Target data model

### book-service — `scenes` (the INDEX, Per-book)

```sql
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS book_id UUID
  REFERENCES books(id) ON DELETE CASCADE;              -- SC1, backfilled from chapters
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
                                                       -- parsed heading; the AUTHORED title
                                                       -- is outline_node.title (the spec)
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS source_scene_id UUID;   -- SC2 (amended): the source map.
                                                       -- soft ref → composition.outline_node.id
                                                       -- NULLABLE (undecompiled import) · NON-UNIQUE

CREATE INDEX IF NOT EXISTS idx_scenes_book_active
  ON scenes(book_id, chapter_id, sort_order) WHERE lifecycle_state = 'active';
CREATE INDEX IF NOT EXISTS idx_scenes_source
  ON scenes(source_scene_id) WHERE source_scene_id IS NOT NULL;
```

`leaf_text` stays; it is a derived projection (SC13). **`origin` is dropped** — with SC5 inverted,
every `scenes` row is parser output, so the column would be a constant. Its only consumer was
OQ-3 (*"does `origin='authored'` with empty `leaf_text` confuse P2 extraction?"*), which
**dissolves**: an index row exists only where prose exists, so extraction never sees an empty leaf.

> ⚠️ **`book_id` backfill must be batched.** This repo explicitly targets 10k+ chapter books;
> a bare `UPDATE scenes SET book_id = …` takes a full-table lock. Same batched shape as the
> `word_count` backfill in [`15b_chapter_browser.md`](15b_chapter_browser.md) A1.

### composition-service — `outline_node` (the SPEC — nothing anchors *out* of it)

```sql
-- SC2 (amended): NO `scene_id` column, NO scoped-unique index. The anchor lives on
-- book-service.scenes.source_scene_id. Book scope arrives via 23's Phase 0
-- (`outline_node.book_id`, backfilled from composition_work) — a prerequisite of this spec.

-- SC4 — authored intent, all four field groups
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS location_entity_id UUID;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS story_time   TEXT;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS conflict     TEXT NOT NULL DEFAULT '';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS outcome      TEXT NOT NULL DEFAULT '';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS value_shift  SMALLINT
  CHECK (value_shift IS NULL OR value_shift BETWEEN -100 AND 100);
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS stakes       TEXT NOT NULL DEFAULT '';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS target_words INT
  CHECK (target_words IS NULL OR target_words > 0);
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS exit_state   JSONB;     -- SC12, {v:1,…}
```

`_UPDATABLE_COLUMNS` and `_NULLABLE_UPDATE_COLUMNS` extend accordingly:
nullable-clearable = `location_entity_id, story_time, value_shift, target_words, exit_state`.

`value_shift` complements `tension` rather than duplicating it: `tension` is the scene's
*charge* (0..100, what `adaptive_k` gates on); `value_shift` is its *net change* (-100..100,
what arc conformance can integrate over a sequence). A scene can be maximally tense and end
where it began.

---

## API surface

### book-service — new public routes (under the existing `/v1/books/{book_id}` group)

> ✏️ **Amended — `scenes` becomes READ-ONLY at `/v1`, and Phase A shrinks.** Once `scenes` is the
> *index* (SC1) and authoring writes composition only (SC5), **every write route on `scenes` loses
> its author.** Creating a scene = authoring a spec node. Renaming one = editing the prose heading.
> Reordering = editing prose. Deleting = editing prose. All four are already served by the chapter
> editor or by `outline_node`'s existing REST + MCP surface. A write endpoint on a derived index is
> the "second prose store" that D17/SC13 exists to forbid.
>
> **Net: 8 routes → 3, and `book_scene_create/update/delete/reorder` drop out of SC9.** This is a
> scope *reduction*, and the strongest signal that the inverted model is the right one.

| Method | Path | Gate | Notes |
|---|---|---|---|
| `GET` | `/scenes` | VIEW | **book-wide**, the browser's list. Filters: `chapter_id`, `status`*, `pov_entity_id`*, `q`. Keyset-paged (10k+ books). |
| `GET` | `/chapters/{cid}/scenes` | VIEW | chapter-scoped list (the rail) |
| `GET` | `/scenes/{sid}` | VIEW | includes `source_scene_id` — the browser's join key |

\* `status` and `pov_entity_id` are **spec** fields and live in composition. Per SC11 the
browser joins client-side, so these two filters are **client-side in v1**. Marked, not hidden.
Promoting them to server-side would require a cross-service join — explicitly out of scope.

**Writes go to the spec, which already has them:** `composition_outline_node_create` /
`_update` / `_delete` / `_restore`, plus the new `composition_outline_node_move`
([`23`](23_book_architecture.md) B3) for reorder/reparent.

Existing `/internal/…/scenes` and `/internal/…/hierarchy` responses are **unchanged** (SC3).
The parser gains one write: it sets `source_scene_id` when a drafted spec scene is parsed
(matched on the `data-scene-id` anchor — SC7).

### composition-service

- `POST /internal/books/{book_id}/materialize-scenes` — SC6, **the decompiler**; idempotent upsert
  keyed on `(book_id, chapter_id, sort_order)`. Book-scoped (`23` BA8), so it no longer requires a Work.
  Returns a **per-scene outcome count** — a `200` with zero upserts on a book that has parsed scenes
  is a bug, per `silent-success-is-a-bug-not-environment`.
- `composition_outline_node_create` / `_update` widen to the full field set (SC8).
- `composition_list_outline` returns `outline_node.id` for every scene node — that **is** the
  browser's join key (`scenes.source_scene_id → outline_node.id`). No new column needed.

---

## GUI surface

### `scene-browser` — new dock panel (DOCK-1/6, palette + agent-openable)

Book-wide table. Columns: `#` · Title · Chapter · Status · POV · Tension · Beat · Words
(target/actual) · Updated. Filter chips for status / POV / beat_role, a tension range,
and a text query. Group-by: Chapter (default), **Arc** (now a real `structure_node` — see
[`23`](23_book_architecture.md)), POV, Beat. Bulk-select → set status, set POV, retarget words,
trash. *(Bulk writes target the **spec**, via `composition_outline_node_update`.)*

Keyset paging + row virtualization above a few hundred rows (same hard requirement as the
Chapter Browser).

**The list is a UNION over the source map, not a single table** — the direct consequence of the
inverted anchor, and the honest rendering of both failure modes:

| Row shape | Means | Renders |
|---|---|---|
| index + spec (joined on `source_scene_id`) | written and planned | normal |
| **spec only** (no index row) | planned, **not yet written** | greyed prose columns, *"not yet written"* |
| **index only** (`source_scene_id IS NULL`) | written, **not decompiled** (or anchor lost) | greyed intent columns, ⚓ *re-anchor* action (OQ-5) |

A book whose spec has never been decompiled (SC6) renders entirely as the third shape — which is
exactly right, and is what "browse a binary without its source" looks like.

### `scene-inspector` — detail pane

Every field on one surface, sectioned: **Identity** (title, chapter, order, origin, anchor
state) · **Intent** (pov, present entities, goal, synopsis, beat_role, tension, value_shift) ·
**Craft** (conflict, outcome, stakes, setting, story_time, target_words) · **State**
(`exit_state`, read-mostly) · **Links** (`scene_link`, reusing `SceneGraphCanvas`'s data) ·
**Grounding** (`scene_grounding_pins`, reusing `GroundingPanel`).

OCC via `expected_version` on every write, surfacing the existing 412 → *"changed elsewhere —
reloaded"* path `SceneRail` already implements.

### `SceneRail` — reconciled, not replaced

Stays the chapter-local strip. Two changes: it renders the **same union** as the browser, scoped
to one chapter (so an imported book's rail is no longer empty — the third row shape above), and
its title becomes editable inline (today the title is a jump *button* and can only ever be set at
create — F2). **The inline edit writes `outline_node.title` — the spec** — never `scenes.title`,
which is a parsed heading (SC1).

---

## Task breakdown

### Phase A — book-service (Go)

| # | Task | File(s) |
|---|---|---|
| A1 | `book_id` + `title` + **`source_scene_id`** columns (no `origin`); **batched** `book_id` backfill; `idx_scenes_book_active`, `idx_scenes_source` — *sequenced as [`25`](25_package_migration_master.md) Deploy 1's parallel lane ([`00B`](00B_EXECUTION_ROADMAP.md) Stage 1)* | `internal/migrate/migrate.go` |
| A2 | **3** public `/v1` scene routes, VIEW-gated (read-only — see the API amendment) | `internal/api/scenes.go`, `server.go` |
| A3 | Keyset paging + filters on the book-wide list | `internal/api/scenes.go` |
| A4 | `book_scene_list` / `book_scene_get` MCP tools (SC9, **read-only**), **including a `source_scene_id` filter arg on `_list`** — [`28`](28_agent_native_studio.md) AN-5b requires it (go-to-prose resolves spec scene → index row); 28-AN-C1's test reds without it | `internal/api/scene_tools.go` (new), `mcp_server.go` |
| A5 | Parse writers set `book_id`; **set `source_scene_id` by matching the `data-scene-id` anchor** (SC7). **⚠ A5 MUST ALSO re-run the `book_id` backfill under a bumped marker (`scenes_book_id_backfill_v2`)** — A1's backfill is one-time and marker-gated, so every scene created in the A1→A5 window carries `book_id NULL` *permanently*, and `idx_scenes_book_active` is book-keyed. The A2/A3 book-wide reads that ship in this same wave would silently omit those rows. This was raised as a Stage-1 finding, correctly refuted **as an A1 defect** (no `book_id` reader exists yet), and re-homed here: A1's correctness is *conditional on A5 doing this*. Ship A5 with a test asserting `count(*) FROM scenes WHERE book_id IS NULL = 0`. | `parse.go`, `worker-infra/…/import_processor{,_pdf}.go`, `internal/migrate/migrate.go` |

### Phase B — composition-service (Python)

| # | Task | File(s) |
|---|---|---|
| **B0** | **Prerequisite: the per-book re-key — owned by [`25`](25_package_migration_master.md) M0–M3** (23 Phase 0 is ⚠-superseded by it; 25's M0.1 pre-flight carries the derivative exemption 23's P0.0 lacked) | `app/db/migrate.py` via 25 |
| B1 | 8 SC4 columns; `exit_state` envelope model. **No `scene_id`, no scoped-unique index** (SC2 amended) | `app/db/migrate.py`, `app/db/models.py` |
| B2 | Extend `_UPDATABLE_COLUMNS` / `_NULLABLE_UPDATE_COLUMNS` | `app/db/repositories/outline.py` |
| B3 | Widen `_NodeCreateArgs` / `_NodeUpdateArgs` (SC8) — enums + ranges at the schema | `app/mcp/server.py` |
| B4 | `POST /internal/books/{book_id}/materialize-scenes` (SC6 decompiler, idempotent, per-scene counts) **+ an EDIT-gated `/v1` mirror** — the Hub's "Extract the plan" CTA is a human GUI and can call neither an internal-token route nor an MCP tool ([`24`](24_plan_hub_v2.md) OQ-9); the LLM arc-analysis step reuses the propose→confirm token pattern, never a bare priced endpoint | `app/routers/outline.py` |
| ~~B5~~ | ~~book-service scene first, then `outline_node`~~ — **deleted.** SC5 inverted: authoring writes composition only. No cross-service write on create. | — |

### Phase C — frontend (TS)

| # | Task | File(s) |
|---|---|---|
| C1 | `Scene` identity type + `booksApi` scene calls; widen `OutlineNode` with the 9 missing fields | `features/books/api.ts`, `features/composition/types.ts` |
| C2 | `scene-browser` panel + registry entry + palette entry | `features/studio/panels/SceneBrowser*.tsx` |
| C3 | `scene-inspector` panel; reuse `GroundingPanel` / `SceneGraphCanvas` data hooks (DOCK-2, no fork) | `features/studio/panels/SceneInspector*.tsx` |
| C4 | `SceneRail` reads identity from book-service; inline title edit | `features/studio/manuscript/SceneRail.tsx` |
| C5 | i18n keys for both panels | `i18n/locales/*/studio.json` |

### Phase D — contracts & verification

| # | Task |
|---|---|
| D1 | OpenAPI for the 8 new book-service routes (`contracts/api/`) |
| D2 | `contracts/frontend-tools.contract.json` regen if any `ui_*` arg changes |
| D3 | **Cross-service live-smoke** (mandatory — this touches ≥2 services): import a book → assert its scenes appear in the browser (no Work required) → assert the decompiler (SC6) upserted one spec node per parsed scene → author a scene in the composer, draft prose, assert the parser back-links `source_scene_id` → agent sets `tension=80` via MCP → assert `adaptive_k` picks the high-tension policy. Per `prefer-e2e-and-evaluation-over-live-smoke-poc`, drive it through the real path, not a hand-fed smoke. |
| D4 | **Tenancy test (inverted by BA8):** collaborator B on a shared book sees **both** the manuscript's scenes **and** the shared spec — one book, one spec, as a team shares one `main.tf`. Assert no per-user fork of `outline_node` exists for that book. This is the assertion that proves BA8's Per-book scope is real and not aspirational. |
| D5 | **Anchor-direction test:** assert `outline_node` has **no** `scene_id` column and that deleting a `scenes` row leaves the spec node intact (the index is disposable; the spec is not). The reverse — deleting a spec node — **renders** the back-link as null **at read time** via the union join; no physical write occurs (composition never writes book-service's DB, and the re-parser consults no node liveness — [`26`](26_structure_prose_indexing.md) OQ-4). |

**Ordering.** A and B are independent up to B5 (which needs A2). C needs A2 + B3. Per
`fanout-independent-slices-parallel-build-serial-integrate`, A1–A4 and B1–B4 can build in
parallel on disjoint files with **one** serial VERIFY.

---

## Open questions

| # | Question | Disposition |
|---|---|---|
> **All rows below are CLEARED.** Dispositions live in the Decisions Register:
> [`00A_BOOK_PACKAGE_STRUCTURE.md` §9](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared).

| # | Question | Cleared by |
|---|---|---|
| ~~**OQ-1**~~ | Should `book_scene_list`'s `status`/`pov` filters be server-side? | ✅ **[BPS-11]** — client-side in v1, documented in the panel footer (SC11). Revisit on **profiling evidence** from a 10k-scene book (defer gate #4), not speculation. |
| ~~**OQ-2**~~ | ~~Should `composition_work` re-scope to Per-book?~~ | ✅ **RESOLVED** by [`23`](23_book_architecture.md) BA8 — the spec tree is Per-book, following `plan_run`/`authoring_runs`/`plan_bootstrap_proposal`, which are already `book_id NOT NULL`. It was the **root cause**, not an enhancement: SC1/SC2 existed to work around it. Branching (`23` OQ-2) remains open. |
| ~~**OQ-3**~~ | ~~Does `origin='authored'` with empty `leaf_text` confuse P2 extraction?~~ | ✅ **DISSOLVED.** `origin` is dropped; an index row exists only where prose exists, so extraction never sees an empty leaf. |
| ~~**OQ-4**~~ | Should `exit_state` be author-written, generator-written, or both? | ✅ **[BPS-12]** — **both, with provenance.** The `{v:1,…}` envelope carries `source: 'generator' \| 'author'`. Without it, a regeneration silently discards an author's correction. Read-mostly in the inspector. |
| ~~**OQ-5**~~ | A spec scene the parser cannot match leaves `source_scene_id` NULL. Silently, or surfaced? | ✅ **[BPS-13]** — **surfaced, never silent.** The inspector distinguishes *"not yet written"* (no index row) from *"anchor lost"* (index row, NULL back-link) and offers the existing ⚓ re-anchor action (F6). A silent NULL is the `silent-success` bug class. |

## Risks

| Risk | Mitigation |
|---|---|
| `book_id` backfill locks a 10k-chapter book's `scenes` table | Batched backfill (A1), same shape as the proven `word_count` one |
| `materialize-scenes` double-inserts on import retry | Idempotent upsert keyed on `(book_id, chapter_id, sort_order)` — the natural key of a parse leaf. (The old guard, `UNIQUE(project_id, scene_id)`, no longer exists — SC2 amended.) |
| A future agent re-adds `outline_node.scene_id` "so composition can join to identity" | It doesn't need to: composition **is** the identity of the spec. The index points at it. Stated in SC2's amendment, where that agent will look. |
| A write endpoint reappears on `scenes` | It would be a second prose store (D17/SC13). The API amendment states why all four write verbs have no author. |
| Widening MCP args tempts free-string closed sets | SC8 mandates `enum` + `CLOSED_SET_ARGS` registration; a missing enum reds the contract test |
| A future agent "fixes" the browser by making `leaf_text` editable | SC13 states the D17 reconciliation explicitly, in this file, where that agent will look |
| Silent success: `materialize-scenes` returns 200 having upserted 0 rows | Return a per-scene outcome count; a 200-with-zero on a book that has parsed scenes is a **bug**, per `silent-success-is-a-bug-not-environment` |
