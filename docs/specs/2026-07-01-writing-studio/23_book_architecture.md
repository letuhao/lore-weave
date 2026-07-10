# 23 · Book Architecture — the durable spec layer (`structure_node`)

> **Status:** 📐 specced 2026-07-10 · branch `feat/context-budget-law` (studio track) · **XL** (new schema + migration + cross-cutting logic)
> **Scope:** `composition-service` (Python) + `frontend`. `book-service` is touched only by [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md), which this file amends.
> **Prerequisite for:** `22` (its `SceneBrowser` already offers a *"Group by: Arc"* over a container that today holds nothing).
> Follows [`docs/standards/scope-separation.md`](../../standards/scope-separation.md), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md).

---

## Why

**The presenting complaint (verbatim, 2026-07-10):** *"the current arc is just a simple container for chapter and nothing more… after we complete plan and make real book we only keep chapter and lost the architecture of the book. This is critical design — you build and compile source code then you lose the source code, only keep binary files."*

The complaint is correct and understates the problem. The arc is not merely thin — it is **write-only structure**: created, listed, and never read to make a decision. And the richness the author authors (parallel plotlines, pacing, cast roles) is *consumed and discarded* at materialize time.

### The governing model (locked, 2026-07-10)

After working the compiler analogy end-to-end, the team landed on a **corrected** version of it. It is the frame every decision below rests on, so it is stated once, precisely:

| Software | LoreWeave | Home |
|---|---|---|
| package registry (npm / Maven Central) | `arc_template`, `motif` — versioned, published, `visibility`, `imported_derived` license taint | composition |
| **lockfile** (`package-lock.json`) | `motif_application` — pins `motif_version`, "what was bound, not what's live" | composition |
| project manifest (`pom.xml`) | `composition_work.settings` | composition |
| **the spec / desired state** | **`structure_node` + scene intent + beats — THIS FILE. Authored. Durable.** | composition |
| the implementation | `chapters`, `chapter_blocks`, `chapter_drafts`, `chapter_revisions`, translations. **Hand-edited. SSOT of content.** | book-service |
| **debug symbols / source map** | `scenes` — parse leaves, `content_hash`, `parse_version` | book-service, derived |
| `terraform plan` (drift) | `arc_conformance` | composition |

**The one place the compiler analogy must NOT be taken literally.** Prose is *not* build output. Nobody edits `dist/bundle.js`; everybody edits chapter 12. In a compiler the source holds all the information and the binary is a total function of it. Here the plan holds ~1% and the prose holds the rest — generation is a **lossy expansion**, not a compilation. `rm -rf book/ && recompile` does not restore the manuscript; it destroys it and writes a different one.

So the correct relation between plan and prose is **desired-state ↔ actual-state**, not source → binary. Both are durable, neither derives the other, and you *reconcile* rather than rebuild. The existence of `arc_conformance` is the proof: **you never diff a binary against its source — you just rebuild it.**

Two consequences that drive this entire spec:

1. The spec layer (`structure_node`) must be a **first-class, durable, editable object** — not a byproduct of applying a template.
2. `arc_conformance` must diff **spec vs prose**, not **template vs prose**.

---

## Investigation findings

Read from source on 2026-07-10, not from prior docs.

### F1 — `outline_node kind='arc'` is write-only structure

Four consumers exist, all structural plumbing. None reads an arc to make a decision:

| Consumer | Ref | What it does |
|---|---|---|
| decompose-commit | [`outline.py:268`](../../../services/composition-service/app/db/repositories/outline.py#L268) | creates it |
| list roots | [`outline.py:411`](../../../services/composition-service/app/db/repositories/outline.py#L411) | `WHERE a.kind='arc'` |
| count grouping | [`outline.py:532`](../../../services/composition-service/app/db/repositories/outline.py#L532) | `{"arc":"arcs", …}` |
| graph label | [`plan_forge/decompose.py:13`](../../../services/composition-service/app/engine/plan_forge/decompose.py#L13) | renders a node label |

**The packer never reads an arc.** [`app/packer/pack.py`](../../../services/composition-service/app/packer/pack.py) is the single prompt-assembly chokepoint shared by ComposeView, ChapterAssembleView and Agent Mode's `EngineDraftingSeam`. It contains no arc read. The arc therefore cannot steer generation *even in principle*.

This is the **write-only behavior** class CLAUDE.md's Settings & Configuration Boundary names explicitly: *"a stored-but-unread blob is a bug, not a feature."*

The arc row's own columns confirm it. `outline_node` ([`migrate.py:156`](../../../services/composition-service/app/db/migrate.py#L156)) gives an arc only `title`, `goal`, `synopsis`, `status`, `rank`, `parent_id`. Every remaining column (`pov_entity_id`, `present_entity_ids`, `chapter_id`, `tension`, `beat_role`, `story_order`) serves chapter/scene/beat kinds; the table's own CHECKs (`outline_chapter_required`, `outline_beatrole_kind`) exclude arcs from two of them.

### F2 — the structure exists, on the wrong object, and is destroyed on use

`arc_template` ([`migrate.py:762`](../../../services/composition-service/app/db/migrate.py#L762)) is genuinely rich: `threads` (parallel tracks), `layout` (motif placements with spans, ordering, causal `triggers`), `pacing`, `arc_roster`, plus `embedding`, 2-tier tenancy, `version`, `imported_derived`.

But it is a **book-independent library blueprint**. `build_materialize_spec` flattens it into chapters and scenes, and the sole surviving trace of the plan is a JSONB annotation smeared across descendant *scene* rows:

```python
row_ann["arc_template_id"] = arc_template_id     # arc_materialize.py:160
```

No foreign key. No version pin. No `tracks`, `pacing`, or `roster` anywhere on the instance. **This is the compiler that deletes its input.**

### F3 — conformance diffs prose against the *template*, because there is no plan object

`arc_conformance.py` identifies its own scope by template id ([`:315`](../../../services/composition-service/app/engine/arc_conformance.py#L315)):

```python
"scope": "arc",
"arc_template_id": str(arc.id),
"arc_name": arc.name,
```

and `composition_conformance_run` **rejects the call without one** ([`server.py:3024`](../../../services/composition-service/app/mcp/server.py#L3024)):

```python
return {"success": False, "error": "arc_template_id is required when scope='arc'"}
```

It reconstructs "what was realized" by scanning `motif_application`. An arc authored directly — never from a template — is therefore **unconformable**, and an arc whose template was later edited is diffed against a moving target.

### F4 — a book-level UI already reaches into a planning project for arcs

[`useChapterBrowserGroups.ts`](../../../frontend/src/features/books/hooks/useChapterBrowserGroups.ts) opens:

> *"arc-grouping lookup for the browser's table view: 'which arc is chapter N in'… For EACH arc we then cursor-follow its direct chapter children… This is O(arcs) requests, not O(chapters)."*

The Chapter Browser and `ManuscriptNavigator`'s arc badges pay an N+1 cross-service fetch, plus a comment justifying it, to answer a question about a **book**. An imported book — which has no `composition_work`, hence no `outline_node` — can never have arcs at all.

### F5 — composition already runs two tenancy regimes, and the newer one is per-book

| Regime | Tables | Scope key |
|---|---|---|
| legacy (A3 / outline) | `outline_node`, `scene_link`, `scene_grounding_pins`, `generation_job`, `canon_rule`, `style_profile`, `narrative_thread` | `(user_id, project_id)` |
| **PlanForge (newer)** | `plan_run` ([`:935`](../../../services/composition-service/app/db/migrate.py#L935)), `authoring_runs` ([`:988`](../../../services/composition-service/app/db/migrate.py#L988)), `plan_bootstrap_proposal` ([`:1103`](../../../services/composition-service/app/db/migrate.py#L1103)) | **`book_id NOT NULL`** (`plan_run.work_id` is *nullable*) |

PlanForge already decided this. The spec layer follows it. This is `22`'s OQ-2, answered by precedent rather than by argument.

### F6 — the agent cannot author, apply, move, or safely type an arc

Of 48 composition MCP tools, three touch arcs: `composition_arc_suggest` (read), `composition_arc_import_analyze` (import), `composition_conformance_run` (diff). Four defects:

- **No `arc_template` create/patch tool.** CRUD is REST-only ([`routers/arc.py`](../../../services/composition-service/app/routers/arc.py)). The agent can *suggest* an arc and then cannot create it.
- **No materialize/apply tool.** REST-only ([`plan.py:1227`](../../../services/composition-service/app/routers/plan.py#L1227)). The agent cannot apply what it suggested. Authoring an arc from a premise is **agentic logic behind a raw HTTP route** — an MCP-first invariant violation, and a hard block on [S06 "idea → arc"](../2026-07-09-agent-discoverability-and-workflow/scenarios/S06-flagship-idea-to-arc.md), where Mai never picks a template from a library.
- **No reorder/reparent tool.** `_NodeUpdateArgs` exposes `title/goal/synopsis/status` only — no `rank`, no `parent_id`. `OutlineTree.tsx` gives a human full drag-reorder. **The human can restructure a book; the agent can only rename things.**
- **`kind` and `status` are free strings.** `_NodeCreateArgs` declares `kind: str`, `status: str = "empty"` — closed sets guarded only by a DB CHECK. A mid-tier model sending `kind:"Arc"` gets a constraint violation, not a clean rejection. This is the `panel_id` bug class (mcp-tool-io IN-2).

### F7 — nested arcs are silently possible and nothing handles them

`outline_node.parent_id` carries no constraint tying it to `kind`. An arc may today parent an arc. No consumer handles it, no test covers it.

### F8 — vocabulary collisions

`arc` names four things: `arc_template` (blueprint), `outline_node kind='arc'` (tree root), the character-arc entity timeline (`CharacterArcView.tsx`), and `motif.kind='emotion_arc'`.

`thread` names two **unrelated** things one letter apart: `arc_template.threads` (parallel plotlines) and `narrative_thread` ([`migrate.py:275`](../../../services/composition-service/app/db/migrate.py#L275)) — the promise/foreshadow **debt ledger**.

This has already leaked into planning: [`21_plan_hub.md`](21_plan_hub.md) files *"#10 `arc`"* as a **cross-ref lens** — correct for the *character* arc, with the consequence that the **story** arc, which is the graph's own root, has no seat in the Hub's information architecture at all.

---

## The design: the spec layer becomes a first-class object

```
  composition (the SPEC — desired state)          book-service (the IMPLEMENTATION)
  ┌────────────────────────────────────┐          ┌──────────────────────────────┐
  │ structure_node   saga → arc → arc  │          │ chapters                     │
  │   tracks · roster · roster_bindings│          │ chapter_blocks / drafts /    │
  │   (pacing DERIVED from tension)    │          │ revisions / translations     │
  │   ↑ arc_template_id (provenance)   │          │   ── hand-edited, SSOT ──    │
  ├────────────────────────────────────┤          ├──────────────────────────────┤
  │ outline_node  chapter → scene → beat│  ◀────── │ scenes  (parse index)        │
  │   .structure_node_id  (on chapter) │source_   │   .source_scene_id  (§22)    │
  │   scene intent (§22 SC4)           │scene_id  │   leaf_text, content_hash    │
  └────────────────────────────────────┘          └──────────────────────────────┘
           │                                                    ▲
      arc_conformance ── diff(spec, prose) ────────────────────┘
           │
      arc_template / motif  (the REGISTRY)   motif_application (the LOCKFILE)
```

**`arc_template` is not demoted.** It keeps every genuine library concern (`visibility`, `embedding`, `genre_tags`, `imported_derived`, `version`) and sheds the job it was never suited for: standing in for a plan that did not exist. Template ↔ spec is a pair of explicit, snapshot operations — `apply` and `extract` — never a live sync, exactly as `motif_application.motif_version` already pins what was bound.

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **BA1** | **`structure_node` is a first-class table in composition**, `kind IN ('saga','arc')`, nesting via `parent_id`. A *sub-arc* is an arc whose parent is an arc — no third kind. `CHECK (kind <> 'saga' OR parent_id IS NULL)`. | The spec layer must be durable and editable in its own right (F1/F2). Two kinds + nesting expresses saga→arc→sub-arc without a third enum value nobody would maintain. |
| **BA2** ✏️ *[BPS-4](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared)* | **`outline_node` loses `kind='arc'` AND `kind='beat'`** → `CHECK (kind IN ('chapter','scene'))`. A chapter-kind node carries `structure_node_id`. | Removes the three-ontology conflation (structural plan / book shadow / native unit). `'beat'` is **verified dead**: nothing writes it, and every read excludes it (`outline.py:521` — *"'beat' is excluded (structural, not navigable)"*). Beats live in `beat_role` and `motif.beats` / `structure_template.beats`. |
| **BA3** ✏️ *[BPS-3](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared)* | **`structure_node` owns `tracks`, `roster`, `roster_bindings`.** **`pacing` is NOT stored** — an arc's curve *is* its member scenes' `outline_node.tension` (derived). `arc_template` keeps `pacing` (a template has no scenes) and otherwise mirrors the shape. `apply(template)→spec` writes the template's curve **into** scene `tension`; `extract(spec)→template` reads it back out. Both are explicit snapshot ops. | The spec is desired state; the template is a published artifact. Two authored representations of one fact is the drift bug in miniature (DA-7). Shape-compatibility is what lets `ArcTimelineEditor` edit both (see GUI). |
| **BA4** | **`arc_conformance` retargets to `diff(structure_node, prose)`.** `composition_conformance_run(scope='arc')` takes `arc_id`, **not** `arc_template_id`. Template drift becomes a separate, optional `composition_arc_template_drift(arc_id)`. | F3. "Did the prose realize *my plan*" is the question; the template is where the plan came from, not what it is measured against. |
| **BA5** | **`layout` is NOT stored on the spec.** `motif_application` **is** the realized layout — real `motif_id`, pinned `motif_version`, `outline_node_id`, `role_bindings`. | The abstract(code)→concrete(id, versioned) transition already exists and is already correct. Storing `layout` twice creates a sync problem. |
| **BA6** | **Span is DERIVED, never stored:** `min/max(story_order)` over member chapters. `is_contiguous` is computed and **warn-only** — a romance plotline may legitimately span non-contiguous chapters. | A stored range goes stale the moment a chapter is inserted or reordered. |
| **BA7** ✏️ *[BPS-3](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared)* | **Cascade resolution.** `tracks`, `roster`, `roster_bindings` resolve root-ancestor → leaf, **shadowing by `key`**. `pacing` is **derived per arc** from its member scenes' `tension`, so it neither merges nor is stored — each arc's curve simply covers its own span, and they coexist. | Identical to the tenancy cascade (System → Per-user → Per-book, shadow by `code`) already in CLAUDE.md — no new mental model. A saga binds `protagonist` once; sub-arcs inherit unless they override. Coexisting derived curves let the packer say *"60% through arc 'Betrayal', 20% through saga 'Ascension'."* |
| **BA8** | **`structure_node` is scoped `book_id` (Per-book), not `(user_id, project_id)`.** Phase 0 additively adds `book_id` to `outline_node` and switches reads to it. | F5 — PlanForge already went per-book. Fixes F4 (Work-less books get arcs) and resolves `22`'s OQ-2 at the root. **A spec is shared by the team, like one `main.tf`.** Collaborator divergence is a *branch of the spec*, not a private copy of it. |
| **BA9** | **Nesting guarded by a trigger, not by CHECK gymnastics:** `story_arc_depth_guard` BEFORE INSERT/UPDATE computes `depth` from the parent, rejects cycles, rejects `depth > 2`. | F7. Same shape as the existing `motif_application_scope_guard` trigger ([`migrate.py:736`](../../../services/composition-service/app/db/migrate.py#L736)). Depth 0..2 = saga → arc → sub-arc; capped **explicitly**, never silently. |
| **BA10** | **Vocabulary fix, in this change.** `threads` → **`tracks`** on both spec and template; `narrative_thread` keeps "thread" for the debt ledger. Tool namespaces: `composition_arc_*` (spec) · `composition_arc_template_*` (library) · `composition_character_arc_*` (entity lens). `motif.kind='emotion_arc'` stays (namespaced inside `motif`). | F8. `arc_template.threads` and `narrative_thread` are unrelated concepts one letter apart. "One name for one concept" (Frontend-Tool-Contract). |
| **BA11** | **Full MCP surface.** Spec CRUD (`create/get/list/update/delete/restore`), `composition_arc_move` (reparent+reorder), `composition_arc_assign_chapters`; template CRUD (`composition_arc_template_create/patch/list/get/adopt`); `composition_arc_apply`, `composition_arc_extract_template`; plus the missing `composition_outline_node_move`. All closed-set args get `enum` + `CLOSED_SET_ARGS` registration; `depth`, `tension` get range validation **at the schema**. | F6. MCP-first invariant. Unblocks S06 — the agent authors an arc from conversation and Mai never sees the word "template". |
| **BA12** | **The packer MUST read the arc, proven by effect.** `pack.py` injects the resolved arc chain (saga→arc), merged `tracks`, pacing position, `roster_bindings`, and the open-promise rollup. **A test asserts the injected prompt changes when `tracks` changes.** Shipping `structure_node` without this is shipping the same write-only bug in a new table. | F1 is the whole reason this spec exists. Per `checklist-is-self-report-enforce-by-tests`, a checklist item is DONE only when a test asserts its EFFECT. |
| **BA13** | **Provenance is nullable.** `arc_template_id UUID REFERENCES arc_template(id) ON DELETE SET NULL`, `template_version INT`. An arc authored from conversation has none. | S06. Also makes `extract → publish → adopt` a real round trip. |
| **BA14** | **`parts` vs `saga` is explicitly PARKED.** `book-service.parts` is a *physical/parse* division (`path`, `parse_version`); `structure_node` is *narrative*. This spec adds no relation between them. | Deferred by the PO, 2026-07-10 ("we don't discuss this now"). Recorded as OQ-4 so it is parked, not forgotten. |
| **BA15** | **Promise rollup is a query, not storage.** "Which promises does this arc open / pay?" = `narrative_thread` whose `opened_at_node`/`payoff_node` lies in the arc's chapter subtree. | `narrative_thread` already models the ledger correctly. No new column. |

---

## Target data model

### `structure_node` (new — the spec)

```sql
CREATE TABLE IF NOT EXISTS structure_node (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id         UUID NOT NULL,                              -- BA8: Per-book (cross-DB id, no FK)
  parent_id       UUID REFERENCES structure_node(id) ON DELETE CASCADE,
  kind            TEXT NOT NULL CHECK (kind IN ('saga','arc')),
  depth           SMALLINT NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 2),
  rank            TEXT NOT NULL,                              -- LexoRank, same scheme as outline_node

  title           TEXT NOT NULL DEFAULT '',
  summary         TEXT NOT NULL DEFAULT '',
  goal            TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'outline'
                    CHECK (status IN ('empty','outline','drafting','done')),

  -- STRUCTURE (BA3) — the thing that was missing
  tracks          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label}]  (was arc_template.threads)
  roster          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key, actant, label, constraints[]}]
  roster_bindings JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {role_key: glossary_entity_id}
  -- NO `pacing` column (BPS-3): an arc's curve IS its member scenes' outline_node.tension.
  -- A stored second copy is the drift bug in miniature. arc_template keeps `pacing` because
  -- a template has no scenes; apply() writes that curve INTO scene tension values.

  -- PROVENANCE (BA13) — nullable; an arc need not come from a template
  arc_template_id  UUID REFERENCES arc_template(id) ON DELETE SET NULL,
  template_version INT,

  version         INT NOT NULL DEFAULT 1,
  is_archived     BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT structure_saga_is_root CHECK (kind <> 'saga' OR parent_id IS NULL)   -- BA1
);

CREATE INDEX IF NOT EXISTS idx_structure_node_book   ON structure_node(book_id) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_structure_node_parent ON structure_node(parent_id, rank COLLATE "C", id)
  WHERE NOT is_archived;
```

**BA9 — depth + cycle guard** (mirrors `motif_application_scope_guard`):

```sql
CREATE OR REPLACE FUNCTION structure_node_depth_guard() RETURNS trigger AS $$
DECLARE parent_depth SMALLINT; parent_book UUID; walker UUID;
BEGIN
  IF NEW.parent_id IS NULL THEN
    NEW.depth := 0;
  ELSE
    SELECT depth, book_id INTO parent_depth, parent_book FROM structure_node WHERE id = NEW.parent_id;
    IF parent_depth IS NULL THEN
      RAISE EXCEPTION 'structure_node parent % not found', NEW.parent_id USING ERRCODE = 'check_violation';
    END IF;
    IF parent_book <> NEW.book_id THEN            -- cross-book reparent (the H-5 scope-guard lesson)
      RAISE EXCEPTION 'structure_node parent % not in book %', NEW.parent_id, NEW.book_id
        USING ERRCODE = 'check_violation';
    END IF;
    NEW.depth := parent_depth + 1;
    IF NEW.depth > 2 THEN
      RAISE EXCEPTION 'structure_node depth % exceeds saga→arc→sub-arc', NEW.depth
        USING ERRCODE = 'check_violation';
    END IF;
    -- cycle guard: walk ancestors, refuse to find NEW.id
    walker := NEW.parent_id;
    WHILE walker IS NOT NULL LOOP
      IF walker = NEW.id THEN
        RAISE EXCEPTION 'structure_node cycle via %', NEW.id USING ERRCODE = 'check_violation';
      END IF;
      SELECT parent_id INTO walker FROM structure_node WHERE id = walker;
    END LOOP;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

> A subtree reparent changes descendants' depth. `composition_arc_move` recomputes the subtree in one statement (recursive CTE) inside the same transaction; the trigger validates each row.

### `outline_node` (amended)

```sql
-- BA8 · Phase 0: additive book scope. Backfilled from composition_work(project_id → book_id).
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS book_id UUID;
CREATE INDEX IF NOT EXISTS idx_outline_node_book ON outline_node(book_id) WHERE NOT is_archived;

-- BA2 · chapter-kind nodes attach to the spec
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS structure_node_id UUID
  REFERENCES structure_node(id) ON DELETE SET NULL;
ALTER TABLE outline_node ADD CONSTRAINT outline_structure_kind
  CHECK (structure_node_id IS NULL OR kind = 'chapter');

-- BA2 · after the Phase 1/4 backfill, BOTH 'arc' and 'beat' are gone (BPS-4)
--   CHECK (kind IN ('chapter','scene'))
```

### `arc_template` (amended)

```sql
ALTER TABLE arc_template RENAME COLUMN threads    TO tracks;   -- BA10
ALTER TABLE arc_template RENAME COLUMN arc_roster TO roster;   -- BPS-5
```

`layout`, `pacing`, `chapter_span` unchanged — the template keeps `pacing` (BPS-3: it has no scenes to derive one from). Both renames land in the same migration: a column rename touches neither `embedding` nor `layout`, so the "don't churn published library rows" objection was empty (BPS-5 supersedes OQ-3).

### `motif_application` (amended)

```sql
ALTER TABLE motif_application ADD COLUMN IF NOT EXISTS structure_node_id UUID
  REFERENCES structure_node(id) ON DELETE SET NULL;          -- replaces annotations->>'arc_template_id'
CREATE INDEX IF NOT EXISTS idx_motif_application_structure ON motif_application(structure_node_id);
```

---

## Migration

The annotation hack is its own data source — **the thing that is wrong today is what lets us recover the pin, and then it is deleted.**

| Phase | Step | Guard |
|---|---|---|
| **0** | `ALTER outline_node ADD book_id`; **batched** backfill from `composition_work` (10k+ chapter books — same batched shape as `15_chapter_browser.md` A1). Switch all reads to `book_id`. Keep `project_id` as a legacy column. | **Pre-flight assertion:** `SELECT book_id FROM composition_work GROUP BY book_id HAVING count(*) > 1` must return **zero rows**. If a book has two Works, the migration **fails loudly** and the merge is resolved by hand. Never silently merged. |
| **1** | Create `structure_node` + trigger. For each `outline_node WHERE kind='arc'`: insert a `structure_node` (copy `title`/`goal`→`goal`/`synopsis`→`summary`/`status`, `kind='arc'`, `depth=0`, `rank`), then `UPDATE` its child chapters `SET structure_node_id = <new>, parent_id = NULL`. | Row counts asserted equal. |
| **2** | Backfill provenance: `arc_template_id` + `template_version` from `motif_application.annotations->>'arc_template_id'`, taken over each arc's descendant scenes (all descendants of one arc carry the same value — asserted, not assumed). | A disagreeing arc → log + leave NULL. **Never guess.** |
| **3** | Backfill `motif_application.structure_node_id` from the same annotation. Drop the annotation key. | |
| **4** | `DELETE FROM outline_node WHERE kind='arc'`; swap the `kind` CHECK to `('chapter','scene')` (BPS-4). | Orphan check: no `outline_node` with `parent_id` pointing at a deleted arc. **Beat guard:** `SELECT count(*) WHERE kind='beat'` must be **0** — nothing writes beats, but `kind` is a free string today (F6), so an agent *could* have. Non-zero ⇒ **fail loudly**, never auto-delete. |
| **5** | `arc_template RENAME threads → tracks`, `arc_roster → roster` (BPS-5). | Update `layout[].thread` readers (they key on track `key`, unchanged). |

**Rollback:** phases 0–3 are additive and reversible. Phase 4 is the point of no return; it runs only after phase 1–3 assertions pass in the same transaction.

---

## Resolution semantics (BA7)

```
resolve_tracks(arc)          = merge(ancestors root→leaf, then self), shadow by `key`
resolve_roster(arc)          = merge(...), shadow by `key`
resolve_roster_bindings(arc) = merge(...), shadow by `role_key`
pacing(arc)                  = [scene.tension for scene ∈ span(arc)]      -- BPS-3, DERIVED (not stored)
span(arc)                    = min/max(story_order) over member chapters  -- BA6,   DERIVED
open_promises(arc)           = narrative_thread WHERE opened_at_node ∈ subtree(arc)  -- BA15
```

---

## API + MCP surface

### Spec CRUD — `composition_arc_*` (BA11)

| Tool | Kind | Notes |
|---|---|---|
| `composition_arc_list` | R | book-scoped tree; the Chapter Browser's group headers in **one** call (fixes F4's N+1) |
| `composition_arc_get` | R | |
| `composition_arc_create` | A | `kind: Literal['saga','arc']`, `parent_arc_id?`, `tracks?`, `roster?` — **no `pacing`** (BPS-3: set scene `tension` instead) |
| `composition_arc_update` | A | `expected_version` OCC; `status` enum |
| `composition_arc_delete` / `_restore` | A | soft-archive |
| `composition_arc_move` | A | **reparent + reorder**; recomputes subtree `depth` |
| `composition_arc_assign_chapters` | A | sets `outline_node.structure_node_id` for chapter nodes |

### Template ops — `composition_arc_template_*`

`_create` · `_patch` · `_list` · `_get` · `_adopt` (all currently REST-only), plus:

| Tool | Notes |
|---|---|
| `composition_arc_apply` | template → spec: rescale span, bind roster, emit `motif_application` rows. Was `POST /works/{id}/arc/materialize` ([`plan.py:1227`](../../../services/composition-service/app/routers/plan.py#L1227)). |
| `composition_arc_extract_template` | spec → template: "save my plan as a template". `motif_application` rows → `layout`. |
| `composition_arc_template_drift` | the *optional* question BA4 splits out. |

### Retargeted

- `composition_conformance_run(scope='arc', arc_id=…)` — **`arc_template_id` removed** (BA4).
- `composition_outline_node_move(node_id, parent_id, rank)` — the missing reorder (F6).
- `composition_outline_node_create/_update`: `kind: Literal['chapter','scene']` (BPS-4), `status: Literal[…]` (F6).

REST `/v1/composition/arcs/*` mirrors the read tools. **Writes stay MCP-first *for agents*** — MCP-first governs *agent* logic, not human GUIs: a human GUI cannot call MCP tools, and every existing panel writes REST (`OutlineTree`'s `reorderNode`/`patchNode` with `If-Match` OCC is the precedent). Phase B therefore also ships **REST write mirrors over the same repo methods** — one repo method, two front doors ([`24`](24_plan_hub_v2.md) PH20/OQ-3).

---

## GUI surface

**`structure_node` becomes Plan Hub *Core*** ([`21_plan_hub.md`](21_plan_hub.md)) — the graph's own nodes, nested arcs rendering as collapsible super-nodes. `21`'s row *"#10 `arc` (character arc) → cross-ref lens"* is **correct and stays**; this spec supplies the *story* arc that row was mistaken for (F8).

**`ArcTimelineEditor` is reused, not forked.** It is already prop-driven — `{ arc, threads, placements, chapterSpan, canEdit, onEdit, saving, saveError }` — and does **not** hardcode `ArcTemplate`. Because BA3 keeps spec and template shape-compatible, the same tracks × chapters grid edits both. This is the single biggest reason not to invent a separate instance schema. *(DOCK-2: no fork.)*

**New `arc-inspector` drawer**, sectioned: **Structure** (tracks; pacing rendered as a *derived* curve over member scenes' `tension`, editable **through** the scenes — BPS-3) · **Roster** (slots + `roster_bindings` to real cast) · **Chapters** (membership, derived span, `is_contiguous` warning) · **Conformance** (spec-vs-prose drift) · **Provenance** (template + pinned version, drift link, `extract as template`).

**`useChapterBrowserGroups`** collapses to one `composition_arc_list` call.

---

## Task breakdown

> ### ⚠ Superseded 2026-07-10 — migration ownership moved to [`25_package_migration_master.md`](25_package_migration_master.md)
> Phase 0 below AND this spec's "Migration" section (phases 0–5) are **owned and superseded by 25** (M0–M5): 25 absorbs them with the derivative-Work (C23 dị bản) corrections this spec predates. In particular **P0.0's multi-Work pre-flight is replaced by 25 M0.1** — the query below lacks the derivative exemption (`source_work_id IS NULL`) and would fail on any book with a dị bản. Three register refinements forced by that shipped feature: 25 **PM-3** (BPS-1: `project_id` survives as the Work *partition* key), **PM-4** (BPS-2: the manifest unique is *partial*), **PM-10** (BPS-6: replay stays `(project_id, idempotency_key)`). The tables below remain as design intent; execution order, DDL, and backfills come from 25.

### Phase 0 — book scope (prerequisite; widened by [BPS-1](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared); **execution superseded by 25 M0–M3**)

Per **BPS-1**, the re-key is **not** limited to `outline_node`. Every table inside `<book>/` takes
`book_id` as its scope key, and `user_id` demotes to `created_by`/actor. Piecemeal would mean
migrating twice.

| # | Task | File(s) |
|---|---|---|
| P0.0 | **Pre-flight (BPS-2):** assert `SELECT book_id FROM composition_work GROUP BY book_id HAVING count(*)>1` returns zero rows. **Verify** that knowledge-service does not assume a per-user project before making `composition_work.book_id` UNIQUE. | — |
| P0.1 | `book_id` + batched backfill on the **12** re-keyed tables: `outline_node`, `scene_link`, `narrative_thread`, `canon_rule`, `style_profile`, `voice_profile`, `scene_grounding_pins`, `divergence_spec`, `entity_override`, `reference_source`, `generation_job`, `decompose_commit` | `app/db/migrate.py` |
| P0.2 | `UNIQUE(book_id)` on `composition_work` (BPS-2); `user_id` → `created_by` | `app/db/migrate.py` |
| P0.3 | Switch all reads to `book_id`; `_work_or_deny` → `_book_or_deny` (BPS-8 — drops a query per tool call) | `app/db/repositories/*`, `app/mcp/server.py` |
| P0.4 | `pack.py`'s five gated repos (`narrative_threads`, `grounding_pins`, `style_profile`, `voice_profile`, `canon_rules` — `pack.py:184-187`) read by `book_id` | `app/packer/pack.py` |

### Phase A — schema + engine
| # | Task | File(s) |
|---|---|---|
| A1 | `structure_node` + depth/cycle trigger; `outline_node.structure_node_id`; `motif_application.structure_node_id` | `app/db/migrate.py` |
| A2 | Migration phases 1–5 with assertions | `app/db/migrate.py` |
| A3 | `StructureRepo` (tree CRUD, `move` w/ recursive depth recompute, cascade resolvers) | `app/db/repositories/structure.py` (new) |
| A4 | Retarget `arc_conformance` → `diff(structure_node, prose)`; `template_drift` split out | `app/engine/arc_conformance.py` |
| A5 | `arc_apply` (was materialize) + `arc_extract_template` | `app/engine/arc_apply.py`, `arc_materialize.py` |
| A6 | **`pack.py` injects resolved arc context** (BA12) | `app/packer/pack.py` |
| A7 | `threads`→`tracks` rename + `layout[].thread` readers | `migrate.py`, `arc_*.py`, `models.py` |

### Phase B — MCP
| # | Task | File(s) |
|---|---|---|
| B1 | 7 `composition_arc_*` spec tools | `app/mcp/server.py` |
| B2 | 5 `composition_arc_template_*` + `_apply` + `_extract_template` + `_drift` | `app/mcp/server.py` |
| B3 | `composition_outline_node_move`; `kind`/`status` → `Literal` + `CLOSED_SET_ARGS` | `app/mcp/server.py` |
| B4 | `conformance_run` takes `arc_id` | `app/mcp/server.py`, `routers/conformance.py` |

### Phase C — frontend
| # | Task | File(s) |
|---|---|---|
| C1 | `StructureNode` type + `arcApi` spec calls | `features/composition/motif/arcTypes.ts`, `arcApi.ts` |
| C2 | `ArcTimelineEditor` accepts a spec (no fork) | `.../components/ArcTimelineEditor.tsx` |
| C3 | `arc-inspector` panel + registry + palette | `features/studio/panels/ArcInspector*.tsx` |
| C4 | Plan Hub Core rendering of nested arcs | per `21_plan_hub.md` |
| C5 | `useChapterBrowserGroups` → one `composition_arc_list` call | `features/books/hooks/` |
| C6 | i18n | `i18n/locales/*/studio.json` |

### Phase D — contracts & verification
| # | Task |
|---|---|
| D1 | OpenAPI for `/v1/composition/arcs/*` |
| D2 | **BA12 effect test** — assert `pack.py`'s assembled prompt changes when `tracks` changes. Without this, `structure_node` ships as F1 in a new table. |
| D3 | Nesting tests: depth-3 rejected · cycle rejected · cross-book reparent rejected · subtree move recomputes depth |
| D4 | Cascade tests: sub-arc shadows saga `roster` by key. **Derivation tests (BPS-3/BA6):** editing a scene's `tension` changes `pacing(arc)`; inserting a chapter changes `span(arc)` — neither is stored |
| D5 | Migration test on a copy of the shared dev DB: arc count preserved, provenance recovered, zero orphans. Per `kg-integration-tests-truncate-shared-dev-db`, this runs against a **snapshot**, never the live dev DB. |
| D6 | **Cross-service live-smoke** (≥2 services): import a book with no Work → `composition_arc_list` returns its arcs (F4) → agent authors an arc via `composition_arc_create` → `composition_arc_apply` binds motifs → `conformance_run(arc_id)` reports drift. Drive the real path per `prefer-e2e-and-evaluation-over-live-smoke-poc`. |
| D7 | S06 replay on `gemma-4-26b-a4b-qat`: idea → arc, without the model emitting the word "template". |

> ### ⚠ Superseded 2026-07-10 — link-step ownership moved to [`27_planforge_v2_compiler.md`](27_planforge_v2_compiler.md)
> E1/E2/E4 below are owned and superseded by **27** (PF-8, V2-E), with two corrections this spec predates: **(a)** link idempotency is NOT bare `event_id` — event ids are 0%-stable across re-proposes (POC 03), so 27 **PF-10** re-keys to a partial unique on `(book_id, plan_run_id, plan_event_id)` (refines BPS-18); **(b)** linked nodes carry `chapter_id NULL` until prose exists, which requires the `outline_chapter_required` CHECK swap (27 §Target data model, DDL riding 25). E5/E3 (the BPS-20 fixture-constant fix + dead-payload deletion) were **built and verified 2026-07-10** — those stand as records of done work.

### Phase E — the PlanForge link step ([BPS-18](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared) · blueprint **M5**, *"Writing Studio debt #1"* · **execution superseded by 27 V2-E**)

`structure_node` is the **link target PlanForge has been missing.** `plan_forge/compile.py` emits an
`outline_skeleton` in the IR's exact shape (`{"kind":"arc"}`, `{"kind":"chapter","parent_arc":…}`),
and **nothing reads it** — verified across every service and the frontend. Two of its five payloads
do have linkers (`glossary_seeds` → `bootstrap_service.py:90`; `planning_package` →
`plan_forge_service.py:375,440,701`). The one carrying the book's architecture does not.

| # | Task | File(s) |
|---|---|---|
| ~~E5~~ ✅ 🐞 | **DONE 2026-07-10 ([BPS-20](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared)).** `genre_tags` → caller kwarg, default `[]`. `constraints` → `charter.style_constraints` + `forbids`. `arc_id` → required. `planner_state` → derived from `spec.layers.variables`. Guarded by `tests/unit/test_plan_forge_no_fixture_constants.py`. *(The `mock_pipeline_result` import turned out to be legitimate — `:784` `pipeline_preview`, worker-disabled path. Left alone.)* | `engine/plan_forge/compile.py`, `services/plan_forge_service.py` |
| ~~E3~~ ✅ | **DONE 2026-07-10** (folded into E5 — it removed the last fixture constant, `language: "vi"`). `planner_state_init` and `working_memory_charter` deleted; no reader anywhere (DA-13). `outline_skeleton` retained for E1. | `engine/plan_forge/compile.py` |
| E1 | `link_outline_skeleton(run_id, book_id)` — `outline_skeleton` → `structure_node` (arc) + `outline_node` (chapter). **Idempotent on `event_id`** (a re-link updates, never duplicates). | `services/plan_forge_service.py` |
| E2 | `plan_compile` records `structure_node_id` provenance on the `package` artifact | `engine/plan_forge/compile.py` |
| E4 | `plan_compile` returning `200` having linked **zero** nodes is a **bug**, not a no-op — return per-node counts (`silent-success-is-a-bug-not-environment`) | `services/plan_forge_service.py` |

> **This is the complaint that started this spec, seen from the compiler's end.** The book's
> architecture was never *lost* when the plan became prose. **It was never linked.**

---

**Ordering.** **E5 is independent — fix it first, it is live.** P0 gates everything else. A1–A2 gate A3–A7. B needs A3. C needs B. **E1–E4 need A1** (`structure_node` must exist before anything can link into it). Per `fanout-independent-slices-parallel-build-serial-integrate`, A4–A7 and B1–B4 build in parallel on disjoint files with **one** serial VERIFY.

---

## Open questions

**All five are CLEARED.** Dispositions live in the Decisions Register:
[`00A_BOOK_PACKAGE_STRUCTURE.md` §9](00A_BOOK_PACKAGE_STRUCTURE.md#9-decisions-register--every-open-question-cleared).

| # | Question | Cleared by |
|---|---|---|
| ~~OQ-1~~ | Is `pacing` intent and `tension` realized? | **[BPS-3]** — *neither.* Both are intent, so `structure_node.pacing` is **deleted and derived** from member scenes' `tension`. `arc_template.pacing` stays. Folded into BA3/BA7. |
| ~~OQ-2~~ | Spec branching for collaborator divergence? | **[BPS-15]** — **not built in v1.** One spec per book, shared; divergence forks the book. Conscious deferral (gate #5). Revisit trigger: the first real request for two plans on one book. |
| ~~OQ-3~~ | `roster` vs `arc_roster` name asymmetry? | **[BPS-5]** — **rename the template column too.** A rename touches neither `embedding` nor `layout`, so the objection was empty. Folded into the Phase-5 migration. |
| ~~OQ-4~~ | `parts` (physical) vs `saga` (narrative)? | **[BPS-9]** — **PARKED by the PO**, now with guard-rail **DA-12**: *nothing may infer narrative structure from `parts`*. Parked ≠ undefended. |
| ~~OQ-5~~ | Auto-mint a draft template on direct authoring? | **[BPS-10]** — **explicit action only.** Provenance stays nullable (BA13). Auto-minting pollutes the registry. |

Two questions this spec did **not** ask, raised and cleared by the register:

| # | Question | Cleared by |
|---|---|---|
| — | Which per-user tables follow the spec to Per-book? | **[BPS-1]** — **all 12 inside `<book>/`**; `user_id` demotes to actor. Widens Phase 0 below. |
| — | `outline_node.kind='beat'` — keep or drop? | **[BPS-4]** — **dropped, verified dead.** Folded into BA2 + migration Phase 4. |

And the question this spec raised but could not answer, **now answered**:

| # | Question | Answer |
|---|---|---|
| **BPS-14** ✅ | Does PlanForge's `outline_skeleton` (`plan_forge/compile.py:44-104`) ever reach `outline_node`? | **No — confirmed.** PlanForge is a **compiler with no link step** for its `spec/` payload. Two of its five payloads link (`glossary_seeds`, `planning_package`); `outline_skeleton`, `planner_state_init`, and `working_memory_charter` are read by **nothing**. The blueprint's **M5** names it: *"Wire Manuscript — plan events → outline nodes (Writing Studio debt #1)"*. It was never built because `outline_node kind='arc'` was not a coherent link target. **`structure_node` is.** → **Phase E**. |
| **BPS-20** 🐞 | — | A live bug found while answering BPS-14: `compile.py` hardcodes the POC fixture's `genre_tags`/`constraints`/`arc_id` into **every** book's planning package, and they reach `propose_cast`. **FIX NOW** → E5. |

---

## Risks

| Risk | Mitigation |
|---|---|
| **`structure_node` ships as write-only, exactly like `outline_node kind='arc'`** | **BA12 + D2.** A test asserts the packer's prompt changes when `tracks` changes. This is the single most important gate in the spec. |
| Phase-0 backfill locks `outline_node` on a 10k-chapter book | Batched backfill, proven shape from `15_chapter_browser.md` A1 |
| A book with two Works silently merges two plan trees | Phase-0 **pre-flight assertion fails loudly**; hand-resolved. Never merged silently. |
| Provenance backfill guesses wrong when an arc's scenes disagree on `arc_template_id` | Log + leave NULL. `template_drift` degrades to "unknown", not to a wrong answer. |
| Subtree reparent leaves stale `depth` | Recursive-CTE recompute inside the move transaction; the trigger validates every touched row |
| `arc_apply` regresses `motif_application` idempotency | It reuses the A3 commit primitives (atomic + idempotent + replace) unchanged; `decompose_commit`'s `idempotency_key` shape is preserved |
| A future agent re-adds `layout` to the spec "for symmetry" | BA5 states why `motif_application` **is** the layout, in this file, where that agent will look |
| Cross-book reparent | Guarded at the DB by `structure_node_depth_guard` (the H-5 lesson from `motif_application_scope_guard`) |
