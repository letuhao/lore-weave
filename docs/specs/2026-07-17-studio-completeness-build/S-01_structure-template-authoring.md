# S-01 · Structure-template authoring (custom story structures)

> **Tier A — DATA-layer build.** The audit found `StructureTemplatesRepo` has ONLY `list_for_user` + `get`;
> the sole `INSERT INTO structure_template` is the built-in seed (`migrate.py:1985`, `owner_user_id NULL`).
> The schema provisions a per-user tier (`owner_user_id` col + `idx_structure_template_owner`) and the SELECT
> filters on it, but **no code can populate it** — the advertised "user-custom story structure" tier is dead.
> **HTML draft:** ✅ net-new (`design-drafts/screens/studio/screen-structure-templates.html`).

## 1. Goal / user story

A user decomposes a book's chapters against a *story structure* (Save the Cat, Hero's Journey, …). Today
only the 6 seeded built-ins exist and they are read-only. **Goal:** let a user author, edit, archive, and
restore their OWN story structures (a named ordered list of beats), then decompose against them — exactly as
against a built-in. Built-ins stay admin/seed-only and read-only.

## 2. Current state (verified against code)

```
structure_template (migrate.py:179)
  id UUID PK · owner_user_id UUID (NULL = built-in) · name TEXT · kind TEXT DEFAULT 'generic'
  · beats JSONB DEFAULT '[]' · created_at
  idx_structure_template_owner ON (owner_user_id)
  ⚠ NO unique constraint · NO updated_at · NO version (OCC) · NO is_archived (soft-delete)
```
- Repo: `list_for_user(user_id)` (built-ins + own), `get(user_id, template_id)` (own or built-in, else None).
- Consumer: `POST /works/{pid}/outline/decompose` (`plan.py`) maps a template's `beats` onto EXISTING
  chapters (never mints chapters). This consumer is UNCHANGED by this spec — it already takes a template id.
- Model `StructureTemplate` (`models.py:130`): id, owner_user_id, name (`_Title`), kind, beats, created_at.

## 3. Tenancy — the load-bearing decision (User-Boundaries)

⚠️ **This is the exact shape of the `entity_kinds` canonical bug** (a shared table with no scope-keyed
unique). Do NOT add a bare `UNIQUE(name)`. Tiers:

| Tier | owner_user_id | Who writes | Visible to |
|---|---|---|---|
| **System** (built-in) | `NULL` | admin/seed only — **this spec adds NO user write path to owner-NULL rows** | everyone (read-only) |
| **Per-user** | the user | that user | that user |

Constraints (partial, so the two tiers never collide):
```sql
CREATE UNIQUE INDEX uq_structure_template_user_name
  ON structure_template(owner_user_id, name) WHERE owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_structure_template_builtin_name
  ON structure_template(name) WHERE owner_user_id IS NULL;
```
Every write route derives `owner_user_id` from the **authenticated user**, never from the request body, and
**refuses to touch an `owner_user_id IS NULL` row** (a user editing a built-in must CLONE it first — mirror
the glossary system→user clone pattern). `get`/`update`/`archive` all keep the existing
`(owner_user_id IS NULL OR owner_user_id = $me)` visibility but gate WRITES on `owner_user_id = $me`.

## 4. Schema migration (additive, idempotent)

```sql
ALTER TABLE structure_template ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE structure_template ADD COLUMN IF NOT EXISTS version    INT         NOT NULL DEFAULT 1;
ALTER TABLE structure_template ADD COLUMN IF NOT EXISTS is_archived BOOLEAN     NOT NULL DEFAULT false;
-- the two partial unique indexes from §3
```
`beats` shape stays as the seed + decompose consumer use it — **`[{key, label, purpose, order}]`** (verified
against the "Save the Cat" seed, `migrate.py:1775`) — no beat-schema change here.
`version` follows the `canon_rule` OCC pattern (the audit's "complete" control). `is_archived` gives the
soft-delete + restore that motif/arc-template lack (S-08) so this domain ships symmetric from day one.

## 5. Repository methods (new — `StructureTemplatesRepo`)

- `create(user_id, name, kind, beats) -> StructureTemplate` — INSERT with `owner_user_id = user_id`;
  maps the partial-unique violation to a domain `DuplicateName` error (→ 409).
- `update(user_id, template_id, expected_version, *, name?, kind?, beats?) -> StructureTemplate | None` —
  `UPDATE … SET …, version = version + 1, updated_at = now() WHERE id = $ AND owner_user_id = $me AND
  version = $expected`. Returns None if not found/not-owned; raises `VersionConflict` (→ 412) if the row
  exists but version mismatches (distinguish the two with a follow-up existence check, per the
  `add-column-if-not-exists` OCC idiom).
- `archive(user_id, template_id) -> bool` — soft `SET is_archived = true WHERE owner_user_id = $me`.
- `restore(user_id, template_id) -> bool` — `SET is_archived = false WHERE owner_user_id = $me`.
- `list_for_user` gains an `include_archived: bool = False` param (default hides archived, matching
  `list_all` in canon_rules). Built-ins are never archived.

**Amend `list_for_user`/`get`:** add `AND NOT is_archived` to the default list; `get` still returns an
archived own-row (so restore can target it), built-ins unaffected.

## 6. REST routes (mirror `canon.py`, grant model = the user owns their own templates)

```
GET    /v1/composition/structure-templates                 (list; ?include_archived)
POST   /v1/composition/structure-templates                 (create; 201; 409 on dup name)
GET    /v1/composition/structure-templates/{id}            (get)
PATCH  /v1/composition/structure-templates/{id}            (update; If-Match → 412 on OCC)
DELETE /v1/composition/structure-templates/{id}            (soft archive; 204)
POST   /v1/composition/structure-templates/{id}/restore    (restore)
```
Writes on a built-in (`owner_user_id IS NULL`) → **403** with a message pointing at clone. No project/book
scope — a story structure is per-user, reusable across books (like the built-ins).

## 7. MCP tools (MCP-first invariant — agent parity)

`composition_structure_template_{create,update,archive,restore}` on composition-service, each wrapping the
repo method above. `beats` is a structured arg (list of `{key, label, purpose, order}`). **`kind` is a FREE-TEXT label, NOT a
closed enum** — SEALED after CLARIFY-verify: `structure_template.kind` is read **nowhere** semantically (every
`.kind` consumer is outline-node / diagnostics / arc, not template), so forcing a user's custom structure to
claim it is "save_the_cat" would be wrong. `kind` defaults to `'generic'`; the built-ins carry descriptive
labels (`save_the_cat`, `hero_journey`, `story_circle`, `kishotenketsu`, …) purely for display. Do NOT
register it in `CLOSED_SET_ARGS`.

## 8. Frontend (net-new panel → HTML draft first)

New panel `structure-templates` (category `storyBible`), GG-8 shape: catalog row + `panel_id` enum +
`contracts/frontend-tools.contract.json` + i18n `guideBodyKey` + `CATEGORY_ORDER` + a Lane-B effect handler
(`structureTemplateEffects`) so an agent write refreshes it. Surfaces: a list (built-ins badged read-only,
own editable), a beat-list editor (add/reorder/remove/label beats), create/rename/archive/restore, and a
**"Clone this built-in"** action that copies a seed's beats into a new own-template. Deep-link OUT: "Use in
decompose" → **the studio `decompose` panel (S-13 / G-STORY-STRUCTURE), pre-selecting this template**. The HTML
draft decides the beat-row layout + the clone affordance; the component follows it.

> **CORRECTION (2026-07-18):** the original line said "→ the plan-hub decompose action". **That target did not
> exist** — decompose is the legacy `PlannerView` inside `CompositionPanel` (reached only via the chapter-editor
> route), not a studio panel; plan-hub has no decompose. So this panel ships **without** the "Use in decompose"
> button; the studio-native decompose surface + its deep-link are specced in **[`S-13_studio-decompose-surface.md`]
> (S-13_studio-decompose-surface.md)** (an M FE port — the decompose UX already exists in `usePlanner`/`PlannerView`).
> The loop is not broken meanwhile: a custom structure already resolves through the legacy planner (locked by
> `test_the_decompose_consumer_resolves_a_custom_template`).

## 9. Tests (evidence gate)

- **tenancy (the bug this spec exists to not reintroduce):** user B cannot GET/PATCH/DELETE user A's
  template (404/403); a user cannot PATCH/DELETE a built-in (403); two users may each have a template named
  "My Structure" (partial-unique scoped) but one user cannot have two.
- **OCC:** a stale `version` PATCH → 412; a fresh one → 200 + version bump.
- **soft-delete symmetry:** archive hides from the default list, `get` still returns it, restore un-hides.
- **consumer unbroken:** the decompose flow still resolves a custom template by id and maps its beats.
- **MCP parity:** each tool round-trips; `kind` rejects an off-enum value at the contract layer.
- **migration idempotency:** re-run adds nothing (all `IF NOT EXISTS`); the two partial uniques don't fire
  on the 6 seeds.

## 10. Out of scope / by-design

- No sharing/collaboration tier for structure templates (per-user only, like built-ins). If book-shared is
  wanted later it mirrors the arc-template `book_shared` tier — a separate spec.
- No change to `beats` semantics or the decompose engine.
- Built-in authoring stays admin/seed-only (System tier is read-only to users by the User-Boundaries law).
