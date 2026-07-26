# 36 · Editor-craft ports — style, voice, references, divergence, work settings, story structure · AND the spec-16 retirement gate

> **Status:** 📐 SPEC (written 2026-07-13, PO-approval pending) — buildable. **No implementation this phase** (plan 30 PO-4).
> **Type:** FS · **Size:** **L** (files ≈ 26, logic ≈ 11, side_effects = 4 — 3 new panel ids + the `frontend-tools` contract + 5 new/changed REST routes + 2 new MCP tool families; **no migration**).
> **Wave:** 6 of [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md). **Closes:** G-STYLE-VOICE (M) · G-REFERENCES-SHELF (S) · G-DIVERGENCE (M) · G-WORK-SETTINGS (S, PARTIAL) · G-STORY-STRUCTURE (M).
> **Panels:** `style-voice` · `reference-shelf` · `divergence` (all category `editor`) — **plus** a Composition **section** in the existing `book-settings` panel and a Beats **facet** + Decompose **action** in the existing `plan-hub` (neither is a new panel — plan 30 §5.3 re-map).
> **Inherits, does not re-litigate:** plan 30 §0 (PO-1..PO-4) · §8.1 (spec-28 AN-8 edit discipline, Tier-W descriptor spine, OCC, grant gating, AN-9/AN-10) · §10 (the REFUTED list).
> **Depends on Wave 0:** X-1 (`AddModelCta` DOCK-7) · X-2 (`CATEGORY_ORDER`) · X-3 (`guideBodyKey` assertion) · X-4 (Lane-B handlers) · X-5 (`ui_show_panel` retirement).
> **Gates:** 🔴 **spec 16's `ChapterEditorPage` retirement (GG-4) unblocks when — and only when — this wave closes.** §10.
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), [`docs/standards/settings-and-config.md`](../../standards/settings-and-config.md) (SET-1..8).
> Design drafts (GG-6): [`design-drafts/screens/studio/screen-style-voice-references.html`](../../../design-drafts/screens/studio/screen-style-voice-references.html) (①–⑤: the cascade, the shelf) · [`screen-divergence.html`](../../../design-drafts/screens/studio/screen-divergence.html) (①–⑧: divergence **+ the `book-settings` Composition section + the `plan-hub` Beats facet** — the file name predates the pairing plan 30 §11 sets; do not split it).

---

## Why

Five capabilities that shape **what the model actually writes** are reachable only from a page the product has already declared dead.

`pack()` folds **density/pace** and **per-character voice tags** into every draft prompt
([`packer/pack.py:269-285`](../../../services/composition-service/app/packer/pack.py#L269)). It folds in the
author's **reference corpus** by cosine top-K. The **critic model** decides whether your prose is
reviewed at all. The **story structure** decides how a chapter is decomposed into scenes. And **dị bản**
(divergence — the AU/what-if derivative) is a whole shipped subsystem: a DB schema, a 4-step wizard, a
promotion path, a grounding-layer view.

Every one of them lives on `ChapterEditorPage` → `CompositionPanel` ([25 sub-tabs](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L87)),
routed at [`App.tsx:134`](../../../frontend/src/App.tsx#L134), under an 18-line banner that says **DO NOT EDIT**.
A Studio user cannot reach any of them. Three of them **nobody** can reach — not even the agent:

| Capability | Human surface | Agent surface |
|---|---|---|
| density / pace / voice tags | legacy page only | **none** — there is no `composition_style_*` / `composition_voice_*` MCP tool ([tool census below](#f-ec1)) |
| reference shelf | legacy page only | **none** (⚠ `composition_find_references` is a *different thing* — plan 30 §10) |
| divergence (dị bản) | legacy page only | **none** |
| the critic model | **nobody** — zero FE writers of `critic_model_ref` | **none** (no work-update tool) |
| story structure (6 built-ins) | legacy page only, and **read-only at every layer** | **none** (no decompose tool) |

This is not five small ports. It is the moment the Studio stops being *strictly less capable* than the
page it replaced — which is exactly the condition spec 16 named and never mechanically enforced.

**This is a PORT spec.** Its shape is *what changes*, not *what to build*. The files that move:

| Moves into the Studio | LOC-ish | Becomes |
|---|---|---|
| [`composition/components/StyleVoicePanel.tsx`](../../../frontend/src/features/composition/components/StyleVoicePanel.tsx) + [`hooks/useStyleVoice.ts`](../../../frontend/src/features/composition/hooks/useStyleVoice.ts) | 172 + 71 | `studio/panels/StyleVoicePanel.tsx` (`style-voice`) |
| [`composition/components/ReferencesPanel.tsx`](../../../frontend/src/features/composition/components/ReferencesPanel.tsx) + [`hooks/useReferences.ts`](../../../frontend/src/features/composition/hooks/useReferences.ts) | 176 + ~80 | `studio/panels/ReferenceShelfPanel.tsx` (`reference-shelf`) |
| `DivergenceWizard.tsx` + `DivergenceWizardSteps.tsx` + `DivergenceWizardButton.tsx` + [`useDivergenceWizard.ts`](../../../frontend/src/features/composition/hooks/useDivergenceWizard.ts) + `DerivativeBanner.tsx` + `DerivativeGroundingLayers.tsx` + `PromoteWhatIfButton.tsx` + `useWhatIfPromotion.ts` + `useDerivativeContext.ts` | ~600 | `studio/panels/DivergencePanel.tsx` (`divergence`) + a banner in the Editor chrome |
| [`composition/components/CompositionSettingsView.tsx`](../../../frontend/src/features/composition/components/CompositionSettingsView.tsx) | 99 | a **section** inside `pages/book-tabs/SettingsTab.tsx` (which `book-settings` already wraps) |

**The misreading to pre-empt.** `CompositionPanel` takes a `soloPanel` prop
([`:89`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L89), used today by the
pop-out host) that mounts exactly one sub-tab. It is tempting to make each new dock panel
`<CompositionPanel soloPanel="style" />` and call it DOCK-2 reuse. **Do not.** `CompositionPanel`'s body
calls ~20 hooks before it reaches the slot table (work resolution, cast, derivative context, polish
proposals, publish gate…) and depends on `WorkspaceLayoutContext`. Reuse the **leaves** — the four
components above are already clean props-only views over self-contained hooks. Reuse the leaf, not the shell.

---

## Investigation findings

Everything below was read from source on 2026-07-13, at HEAD `9262ed53e`. Where the audit in plan 30 was
wrong, this section says so and the correction is load-bearing.

### F-EC1 — style/voice: the CRUD is complete; the *resolution* is invisible; the agent is locked out

[`routers/style_voice.py`](../../../services/composition-service/app/routers/style_voice.py) ships 6 routes:
`GET|PUT|DELETE /works/{pid}/style-profile(s)` and `GET|PUT|DELETE /works/{pid}/voice-profiles`. `PUT` is an
upsert (`ON CONFLICT (project_id, scope_type, scope_id) DO UPDATE`), so LIST + UPSERT + DELETE **is** complete
CRUD. **Zero backend work for the panel.** Confirmed.

Two defects the audit did not name:

1. **The panel has no way to CLEAR an override.** `useDeleteStyleProfile` exists
   ([`useStyleVoice.ts:30`](../../../frontend/src/features/composition/hooks/useStyleVoice.ts#L30)) and
   **`StyleVoicePanel` never calls it.** The DELETE route is a live, tested, unreachable capability.
2. **The most-specific-wins cascade is real and completely hidden.**
   [`StyleProfileRepo.resolve()`](../../../services/composition-service/app/db/repositories/style_voice.py#L86)
   picks `scene > chapter > work`, and `None` → the packer stays neutral. The panel renders
   `density={row?.density ?? 50}` ([`StyleVoicePanel.tsx:131`](../../../frontend/src/features/composition/components/StyleVoicePanel.tsx#L131)):
   a scene with **no** row and a scene explicitly set to 50/50 look **identical**, and a scene inheriting
   80/20 from its chapter renders as 50/50 — *a value the packer will never use.* **The GUI lies about the
   effective value.** That is SET-1 (`effective value + source tier`, no silent hidden default) breached in
   the one place a user can see it.

**Tool census (`grep '^ *name="composition_' mcp/server.py` — 62 tools):** there is **no**
`composition_style_*`, no `composition_voice_*`. The **INVERSE gap is real** — the agent cannot set the two
knobs that most directly shape its own output.

### F-EC2 — references: no UPDATE, and the embedding model is a one-way door

[`routers/references.py`](../../../services/composition-service/app/routers/references.py) ships 4 routes:
LIST, ADD (embed+store), DELETE (hard), and per-scene top-K search. **No `PATCH`.** Fixing a typo in a title
means delete + re-add, which **re-embeds** (a paid provider call to fix a typo).

Worse, and unstated in the audit: the Work's embedding model is **write-through on the first add**
([`:134-137`](../../../services/composition-service/app/routers/references.py#L134)) and is thereafter
**authoritative and immutable** — *"a differing value here is ignored"* ([`:54-57`](../../../services/composition-service/app/routers/references.py#L54)).
LIST returns only `embed_model_set: bool` ([`:92`](../../../services/composition-service/app/routers/references.py#L92)) —
never the ref. So the user cannot see which model owns their vector space and cannot change it. This is
correct engineering (one Work = one vector space) reported dishonestly (an invisible, permanent choice
made by a first click).

[`GroundingPanel.tsx:15`](../../../frontend/src/features/composition/components/GroundingPanel.tsx#L15) says out
loud that reference items *"have their own ReferencesPanel, so they're not grouped here"* — the port was
**consciously skipped**. The Studio ships the pin surface and not the corpus the pins draw from.

### F-EC3 — divergence: the audit is right about UPDATE, and wrong about DELETE and LIST

The audit says *"CREATE-ONCE + READ-ONE… no UPDATE, no DELETE, no LIST"*. Two-thirds correct:

- **UPDATE — confirmed missing.** `divergence_spec` + `entity_override[]` are written **once**, inside the
  `POST /works/{pid}/derive` transaction ([`works.py:378-405`](../../../services/composition-service/app/routers/works.py#L378)),
  and there is no route, no repo method, and no MCP tool that touches them again. The proposed *"manage
  entity_override rows"* leg is **unbuildable on today's backend.** ✅ audit correct.
- **DELETE — REFUTED. It exists.** `status` is in `_UPDATABLE_COLUMNS`
  ([`repositories/works.py:42`](../../../services/composition-service/app/db/repositories/works.py#L42)) and in
  `WorkPatch` ([`works.py:61`](../../../services/composition-service/app/routers/works.py#L61)), and
  `resolve_by_book` filters `status = 'active'`
  ([`repositories/works.py:268`](../../../services/composition-service/app/db/repositories/works.py#L268)). So
  `PATCH /works/{pid} {status:'archived'}` **is** the sibling-consistent soft-delete, today, with If-Match OCC.
- **LIST — REFUTED. It is derivable, today, with zero backend work.** `GET /books/{bid}/work` returns
  `{status, work, candidates[]}`; when a book has >1 marked Work the response is
  `status:"candidates"` + **every** Work row ([`work_resolution.py:93-97`](../../../services/composition-service/app/work_resolution.py#L93)),
  each carrying `source_work_id` and `branch_point`. **The canonical Work is the one with
  `source_work_id === null`; the derivatives are the rest.** BE-13 shrinks accordingly (§Backend prerequisites).

**F-EC3a — the wizard collects a name and throws it away.** `useDivergenceWizard.submit()` refuses to fire
unless `name.trim().length > 0` ([`:169`](../../../frontend/src/features/composition/hooks/useDivergenceWizard.ts#L169)) —
and `buildBody()` ([`:106-121`](../../../frontend/src/features/composition/hooks/useDivergenceWizard.ts#L106))
returns `{branch_point, divergence, entity_overrides}`. **No `name`.** `DeriveBody`
([`types.ts:41`](../../../frontend/src/features/composition/types.ts#L41)) has no such field, `POST /derive`
would ignore it, and **`composition_work` has no name column** ([`migrate.py:34-44`](../../../services/composition-service/app/db/migrate.py#L34)).
The user is *forced* to type a label that goes nowhere. This is the repo's own
`silent-success-is-a-bug` class, shipped — and it is why there is no way to tell two dị bản apart.
**A derivative must be nameable before it can be listed.** (BE-13a.)

**F-EC3b — the Studio identifies "my Work" by array position — at TWELVE sites, not three.**
The audit (and this spec's first draft) named three. `grep -rn "candidates\[0\]" frontend/src services/` at HEAD
`9262ed53e`, excluding tests and the unrelated `candidates` (model lists, glossary merge, scene anchors):

| # | Site | Lane | Blast radius when a derivative sorts first |
|---|---|---|---|
| 1 | [`studio/manuscript/unit/ManuscriptUnitProvider.tsx:138`](../../../frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx#L138) | studio | the open document |
| 2 | [`studio/manuscript/useManuscriptJump.ts:48`](../../../frontend/src/features/studio/manuscript/useManuscriptJump.ts#L48) | studio | jump-to-chapter |
| 3 | [`studio/manuscript/useManuscriptTree.ts:55`](../../../frontend/src/features/studio/manuscript/useManuscriptTree.ts#L55) | studio | the navigator tree |
| 4 | 🔴 [`studio/panels/EditorPanel.tsx:189`](../../../frontend/src/features/studio/panels/EditorPanel.tsx#L189) | studio | **the Editor itself** |
| 5 | 🔴 [`studio/panels/useQualityWork.ts:49`](../../../frontend/src/features/studio/panels/useQualityWork.ts#L49) | studio | **every quality panel** |
| 6 | 🔴 [`studio/panels/useSceneInspector.ts:31`](../../../frontend/src/features/studio/panels/useSceneInspector.ts#L31) | studio | scene-inspector |
| 7 | 🔴 [`books/hooks/useChapterBrowserGroups.ts:89`](../../../frontend/src/features/books/hooks/useChapterBrowserGroups.ts#L89) | studio | `chapter-browser` |
| 8–11 | [`CompositionPanel.tsx:156`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L156) · [`OutlineTree.tsx:118`](../../../frontend/src/features/composition/components/OutlineTree.tsx#L118) · [`usePublishGate.ts:51`](../../../frontend/src/features/composition/hooks/usePublishGate.ts#L51) · [`ChapterEditorPage.tsx:218`](../../../frontend/src/pages/ChapterEditorPage.tsx#L218) | **legacy** | the legacy page is **NOT deleted this wave** (GG-4/OQ-2) — a user who derives in the Studio and then opens it gets the wrong Work |
| 12 | [`internal_model_settings.py:82-86`](../../../services/composition-service/app/routers/internal_model_settings.py#L82) | BE | the Book tier of the model cascade; it even *documents* the assumption (*"rows[0] is the canonical manifest… minted before any C23 derivative"*) |

It works today only because `resolve_by_book` is `ORDER BY created_at, project_id` and a derive requires a
pre-existing source. **The predicate is `source_work_id IS NULL`, not "index 0."** Dormant only because the Studio
cannot create a derivative. **This wave arms it — at all twelve sites, not three.** (EC-3c.)

⚠ **The predicate must be nullish, not `=== null`.** `Work.source_work_id` is **optional** in the FE type
([`types.ts:19`](../../../frontend/src/features/composition/types.ts#L19): `source_work_id?: string | null`) and
absent from most fixtures. `w.source_work_id === null` returns **no canonical work** for any row where the field is
`undefined` — a silent "no Work" for every pre-C23 book. Write `!w.source_work_id`.

### F-EC4 — work settings: a full-blob REPLACE, and a Book tier of the model cascade that no GUI can write

[`repositories/works.py:311-313`](../../../services/composition-service/app/db/repositories/works.py#L311):
`params.append(json.dumps(value)); set_clauses.append(f"settings = ${len(params)}::jsonb")` — a **full-blob
REPLACE**. Confirmed. Today no data is lost only because every FE caller hand-merges
(`useSetWorkSettings` spreads `{...currentSettings, ...patch}`,
[`useWork.ts:135`](../../../frontend/src/features/composition/hooks/useWork.ts#L135)). But `patchWork`
([`api.ts:443`](../../../frontend/src/features/composition/api.ts#L443)) sends **no `If-Match`** — while the
route **supports it** and 412s with `WORK_VERSION_CONFLICT`
([`works.py:588,597,603-607`](../../../services/composition-service/app/routers/works.py#L588)). Two panels
saving two different keys → the second read-modify-write silently reverts the first. A genuine lost-update
window, on a live route, one header away from closed.

The three "silent hidden default" keys, verified by grep across `frontend/src`:

| Key | FE writers | Consumer | What the silence costs |
|---|---|---|---|
| `critic_model_ref` / `_source` | **ZERO** | [`engine.py:1643-1656`](../../../services/composition-service/app/routers/engine.py#L1643) | *"critique skipped: no distinct critic model configured"* — a warning string in a JSON body. **Every Studio user's LLM critic is off, permanently, with no way to turn it on.** |
| `capture_correction_prose` | **ZERO** | [`engine.py:1766`](../../../services/composition-service/app/routers/engine.py#L1766) | gates whether a correction stores the verbatim prose. **Wave 1's correction flywheel (BE-9) captures structure only until this is switchable.** |
| `reference_embed_model_ref` / `_source` | server-only (F-EC2) | `references.py` | the vector-space owner, invisible |

**F-EC4a — the bigger find.** The model cascade already has a **Book tier**, and it is fed by
`work.settings.model_roles` ([`internal_model_settings.py:46-65`](../../../services/composition-service/app/routers/internal_model_settings.py#L46)),
with `critic` already in the canonical closed set
([`settings_resolution.py:39`](../../../services/chat-service/app/services/settings_resolution.py#L39):
`CRITIC = "critic"`). `grep -rn "model_roles" frontend/src` → **nothing**. **The Book tier of the model
cascade has no writer in any GUI.** The legacy `default_model_ref` / `critic_model_ref` scalars are read
*only* as a dual-read compatibility shim (`:58` *"legacy scalars fill only roles the new map didn't set"*).

⇒ The Composition section is not "a settings form." It is **the Book-tier writer of the model cascade**, and
it must write `settings.model_roles.{composer,critic,planner}` — **not** a fourth bespoke `critic_model_ref`
picker. Adding one would be SET-8 (`one home, one name`) violated in the same commit that cites SET-8.

**F-EC4b — 🔴 …and `model_roles` HAS NO READER IN composition-service. Writing it alone is a NO-OP.**
This is the correction that saves the wave from shipping its own headline bug. `_model_roles_from_settings`
([`internal_model_settings.py:46`](../../../services/composition-service/app/routers/internal_model_settings.py#L46))
is a **`/internal` route serving chat-service's cascade** — it is *not* how composition-service's own engine
picks the critic. The engine reads the **legacy scalars, directly off the blob, at SEVEN sites**:

```
$ grep -rn "critic_model_ref" services/composition-service/app --include=*.py | grep -v test
routers/engine.py:465   c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
routers/engine.py:529   …  :1029  …  :1099  …  :1261  …  :1345
routers/engine.py:1644  critic_ref = settings_dict.get("critic_model_ref")     ← the "critique skipped" gate
routers/internal_model_settings.py:62   (the /internal cascade route — a DIFFERENT consumer)
```
`grep -rn "model_roles" services/composition-service/app` → **`internal_model_settings.py` and nothing else.**

⇒ A Composition section that writes **only** `settings.model_roles.critic` leaves all seven engine sites reading
`critic_model_ref` → `None` → *"critique skipped: no distinct critic model configured"* — **forever**, while the
GUI proudly renders *"critic: gpt-4o · book"*. That is **`silent-success-is-a-bug` / stored-but-unread**, shipped
by the very spec that cites the rule. M4a's own DoD (*"critic model set ⇒ the critique is no longer skipped"*)
**would red.** The fix is **not** "write both keys" (that is two homes — SET-8 again). The fix is **BE-21**: one
`resolve_model_role(settings, role)` helper in composition-service that reads `model_roles.<role>` **first** and
falls back to the legacy scalar (the dual-read `_model_roles_from_settings` already performs — lift it out of the
router), and all seven engine sites call it. **`model_roles` becomes the one home; the legacy scalar becomes the
shim.** Without BE-21, EC-4 is a write-only editor.

### F-EC5 — story structure: read-only at every layer, and an `active_template_id` nobody reads

`StructureTemplatesRepo` has exactly two methods — `list_for_user` and `get`
([`structure_templates.py:32,43`](../../../services/composition-service/app/db/repositories/structure_templates.py#L32)) —
whose own docstring says *"Read-only in V0."* The only route is `GET /v1/composition/templates`
([`canon.py:192`](../../../services/composition-service/app/routers/canon.py#L192)). There is no POST, no PATCH,
no DELETE, no MCP tool. The table advertises a user-custom tier (`owner_user_id` nullable,
[`migrate.py:179`](../../../services/composition-service/app/db/migrate.py#L179)) and **no code anywhere can
insert one.** Every user sees the 6 seeded built-ins, forever. ✅ audit correct.

**And `composition_work.active_template_id` is a WRITE-ONLY COLUMN.** It is declared
([`migrate.py:39`](../../../services/composition-service/app/db/migrate.py#L39)), updatable
([`repositories/works.py:42`](../../../services/composition-service/app/db/repositories/works.py#L42)),
accepted by `PATCH /works` ([`works.py:60`](../../../services/composition-service/app/routers/works.py#L60)),
typed in the FE ([`types.ts:7`](../../../frontend/src/features/composition/types.ts#L7)) — and **read by
nothing**: zero hits in `routers/`, `engine/`, `packer/`, and zero non-test hits in `frontend/src`. Decompose
takes `structure_template_id` in the request body **every single time**
([`plan.py:71`](../../../services/composition-service/app/routers/plan.py#L71)). The book's story structure has
a home in the schema and no resident. That column is exactly the SET-8 one-home this wave needs — **fill it.**

**F-EC5a — PlanDrawer has no Beats facet.** Spec 24 **PH16** names the chapter/scene facet set as
*Overview · **Beats** · Canon here · References · Critic*. What shipped
([`PlanDrawer.tsx:232-293`](../../../frontend/src/features/plan-hub/components/PlanDrawer.tsx#L232)) is
Overview · Cast & Setting · Craft · Canon here · Open threads · References (empty) · Critic (empty). **Beats
is absent**, and `beat_role` is a read-only `<Field>` inside Overview (`:236`). `PlanDrawerEdit` edits
title/status/tension/goal/synopsis/chapter_id — **not `beat_role`**. Yet `beat_role` **is** REST-writable
today ([`NodePatch`, `outline.py:88`](../../../services/composition-service/app/routers/outline.py#L88), If-Match
guarded). The Beats facet is **zero backend work.**

**F-EC6 — decompose spends money with no cost gate.** `POST /works/{pid}/outline/decompose` takes a raw
`model_ref` and runs an LLM (inline, or 202+`job_id` when `COMPOSITION_WORKER_ENABLED`,
[`plan.py:545-556`](../../../services/composition-service/app/routers/plan.py#L545)). It is **not** in
`_ALL_DESCRIPTORS` ([`actions.py:96-101`](../../../services/composition-service/app/routers/actions.py#L96)) —
there is no `composition.decompose` descriptor, no `/actions/preview` estimate, and **no
`_precheck_or_402` usage-billing hold**, unlike its four Tier-W siblings (`motif_mine`, `arc_import`,
`conformance_run`, `generate`). The legacy planner has been spending un-precheck'd tokens since it shipped.
Porting the button *as-is* into the Studio would ship a known cost-gate hole onto a new surface. §BE-20.

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **EC-1** | **`style-voice` renders the CASCADE, not a slider pair.** Every scope row shows **effective value + source tier** (`scene` / `chapter` / `work` / `neutral`), reusing the shipped [`TierChip`](../../../frontend/src/features/chat-ai-settings/components/TierChip.tsx) **and its sibling `ClearOverride`** (same file, `:60` — it already renders *"clear · inherit &lt;the value you'd get&gt;"*; a clear button that doesn't name the fallback is *"a dare, not an affordance"*, its words). ⚠ **TierChip needs 4 new rows, and this is the one FE prerequisite of M1:** its `CLS`/`LABEL`/`TITLE` maps (`:13-38`) know only `session`/`book`/`account`/`system`/`unavailable`/`no_model_configured`. It **does not throw** on an unknown tier — it falls back to the raw string with muted styling and no tooltip — which is *worse* than a crash: the panel ships looking done while every chip reads `scene` in grey. **Add `scene`/`chapter`/`work`/`neutral` to all three maps** (`neutral` → label *"unset"*, title *"No row at any scope — the packer adds no density/pace directive"*). Extending the ONE chip is the whole point; forking a second one is the defect. An inherited scope renders the inherited numbers **greyed with its source chip**, and `ClearOverride` appears **only** when a row exists at that exact scope. | F-EC1. SET-1. A slider that shows 50 when the packer will use 80 is a lying control; it is also the exact `dirty-signal-computed-but-not-surfaced` class. |
| **EC-2** | **The panel id is `reference-shelf`, NOT `references`.** This **amends plan 30 §5.2's proposed id.** | Plan 30 §10 already records that `composition_find_references` (entity backlinks, spec 28 AN-3) and the reference shelf are two different things sharing a word, and that Wave 7 ships a `find-references` lens. Two enum members called `references` and `find-references` next to each other, disambiguated only by an LLM's guess, is the **exact** silent-no-op class the `panel_id` enum was added to kill. One name for one concept. |
| **EC-2a** | **v1 of `reference-shelf` is add / delete / retrieve — and it SAYS SO.** No edit. The embedding model is rendered **read-only** with its ref, its source tier, and one honest sentence: *"every reference of this book is embedded with this model; changing it would re-embed all N."* | F-EC2. BE-17 (PATCH + widened LIST) is a v2 slice, not a v1 blocker (plan 30 BE-17). Silence about a permanent one-way choice is worse than a disabled control that explains itself. |
| **EC-3** | **`divergence` is a MANAGE panel, not a wizard launcher.** It lists this book's Works (canonical + derivatives) from the **existing** `GET /books/{bid}/work` `candidates[]`, keyed on `source_work_id`; opens the ported 4-step wizard to create one; switches the Studio's active Work; archives one (`PATCH {status:'archived'}`); and renders the derivative's spec (taxonomy · branch point · POV anchor · canon rules · entity overrides) from `GET /works/{pid}/derivative-context`. | F-EC3. Three of the four verbs already exist. The panel is worth building *because* the LIST exists and nothing surfaces it. |
| **EC-3a** | **Editing a divergence spec is OUT OF v1 SCOPE, and the panel says why.** The spec + overrides render **read-only** with an inline note: *"the divergence spec is written once, at derive (works.py:378) — editing it needs BE-13."* No disabled mystery button. | The proposed *"manage entity_override rows"* is unbuildable today (F-EC3). Plan 30's own house rule: name the backend cost up front, never hand-wave it. BE-13 is scoped below and may land in the same wave if the PO wants it — but the panel does not depend on it. |
| **EC-3b** | **A derivative gets a NAME (BE-13a) before the panel ships.** The wizard's step-4 name is wired to a real, persisted field. | F-EC3a: today it is collected and discarded. A LIST of unnamed UUID rows is not a surface. This is the smallest possible BE slice (`settings.derivative_name`, no DDL — see BE-13a) and it is a **hard prerequisite of the panel**, not a nice-to-have. |
| **EC-3c** | **"Which Work am I in" becomes an explicit predicate — at ALL TWELVE sites (F-EC3b's table), not three.** A shared `selectCanonicalWork(candidates)` / `selectDerivatives(candidates)` helper (`features/composition/workSelect.ts`, predicate `!w.source_work_id`) replaces `candidates[0]` at the **7 studio sites + the 4 legacy sites**, and `internal_model_settings.py:85` gains the same predicate server-side. Ships **with** the divergence panel, in the same slice. The legacy 4 are **in scope**: the page is not deleted this wave (OQ-2), so leaving them on `candidates[0]` ships the bug on the surface we refuse to delete. | F-EC3b. Position-as-identity is a latent bug that only this wave can trigger. Fixing it *after* shipping the panel means shipping the bug. |
| **EC-3d** | **🔴 `selectCanonicalWork` is NOT what a panel should call — `useActiveWork(bookId)` is.** EC-3c and EC-3's *Switch to* **contradict each other** if left as written: `selectCanonicalWork()` returns the *canonical* Work, so a user who switches to a dị bản would have the Editor, the navigator, the quality panels and the scene-inspector **each independently re-resolve back to canon**. Therefore: `useActiveWork(bookId)` = `activeWorkProjectId ?? selectCanonicalWork(candidates).project_id`, and **every one of the 7 studio sites calls THAT**, never `selectCanonicalWork` directly. `selectCanonicalWork` stays the *fallback*, not the resolver. **Where `activeWorkProjectId` lives:** a **per-user, per-book server setting** — two users of a shared book will want different active Works (CLAUDE.md User Boundaries + Data Persistence: *"UI state that must persist → DB, NOT localStorage"*). v1 stores it under the **caller's** preferences (`/v1/me/preferences`, key `lw_active_work.<book_id>`), **not** in `work.settings` (that blob is per-book and shared — one user switching would move every collaborator's Editor). It is **hydrated into the studio bus on mount**, and the bus is what the panels read. | The bus alone is not a persistence tier: a reload would silently drop the user back into canon while the `DerivativeBanner` was the only thing that ever said which Work they were in. And `work.settings` is the wrong home — a per-user choice in a per-book blob is the `entity_kinds` tenancy bug, re-shipped. |
| **EC-4** | **The Composition section is the Book-tier writer of the model cascade — and BE-21 makes the engine READ it.** It writes `settings.model_roles.{composer,critic,planner}` through the existing role vocabulary and renders each with its effective value + source tier (the account tier is inherited, and shown as inherited). It does **not** add a `critic_model_ref` control. **BE-21 is a HARD PREREQUISITE, not a nicety:** composition-service's engine reads the *legacy scalar* at 7 sites and `model_roles` **nowhere** (F-EC4b), so without it this section is a write-only editor and M4a's behaviour test reds. After BE-21: `model_roles` is the one home; the legacy scalar is the read-fallback shim. | F-EC4a + F-EC4b. SET-8: one home, one name. Writing *both* keys to dodge BE-21 is two homes — the same violation, wearing a hat. |
| **EC-4b** | **`PATCH /works/{pid}` gets a server-side shallow merge (`settings = COALESCE(settings,'{}'::jsonb) \|\| $n::jsonb`). `If-Match` is added **per call site**, NOT blanket-on-`patchWork`.** | BE-18. The merge closes the *blind* lost update (two panels, two keys) and is behaviour-preserving: every FE caller already sends the full hand-merged blob, and the merge is **shallow**, so `useWorldMap`'s whole-`world_map`-key replace still deletes sub-keys correctly. ⚠ **The blanket-If-Match half of the original decision was WRONG and is struck.** `patchWork` ([`api.ts:443`](../../../frontend/src/features/composition/api.ts#L443)) is a **shared writer with 5 call sites** — `useSetWorkSettings`, `useChapterAssembly`, `useProgress`, **`useWorldMap` (a node-drag writer: one PATCH per drag)**, and the divergence archive. Putting `If-Match` on the function itself makes the **world-map drag self-412 against its own previous write** the moment the cached `work.version` is one behind — the exact `instant-commit-control-over-occ-entity-needs-write-serialization` bug. So: `patchWork(pid, patch, token, { ifMatch? })`. **Required** for the Composition section's save and the divergence archive (a human-paced, conflict-meaningful write). **Not** for `useWorldMap` — the BE-18 merge already closes its lost-update window, and a 412 mid-drag is a worse bug than the one it fixes. Any call site that *does* adopt `If-Match` must **chain** its writes and **re-seed `version` from the response**. Key removal, if ever needed, is a `settings_unset: [key]` field, not a blob replace. |
| **EC-5** | **`active_template_id` becomes the ONE home of the book's story structure.** The Composition section picks it; the decompose action **defaults** to it and writes it back on commit; the Beats facet **reads** it. `structure_template_id` stays on the decompose request (per-run override), but it is no longer the only place the answer lives. | F-EC5. A declared, patchable, FE-typed column with zero readers is the *stored-but-unread ⇒ write-only-behavior* bug CLAUDE.md bans — and it is already in the schema, waiting. |
| **EC-5a** | **User-authored structure templates (BE-12) are OUT of v1.** The picker renders the 6 System-tier built-ins, and — where a real user would expect "save my own" — an honest empty affordance, not a disabled button with no explanation. | The write path needs 3 routes **plus** clone-to-user tenancy (the 6 built-ins are `owner_user_id IS NULL` = System tier; a regular user must never mutate them — CLAUDE.md User Boundaries). That is its own slice with its own tenancy review. **PO decides at CLARIFY** (plan 30 BE-12 says exactly this). Recommendation: **defer** — nobody has asked for it, and shipping the 6 built-ins reachable is 90% of the value. |
| **EC-5b** | **The Decompose action goes through the generic Tier-W spine (BE-20). It does not ship before that spine exists.** | F-EC6 + plan 30's cost-gate rule. Shipping a new button that spends LLM tokens with no estimate and no billing precheck, in the wave whose whole thesis is "the human deserves the same rails the agent has", would be self-refuting. Milestone M4 splits so the free half (Beats facet, structure one-home) is not held hostage. |
| **EC-6** | **Reuse the leaves, not `CompositionPanel`.** No new dock panel mounts `CompositionPanel` in any mode. | §Why. `soloPanel` looks like free DOCK-2 reuse and drags in ~20 hooks and a layout context. |

---

## The design

All three panels are `category: 'editor'`, DOCK-2 thin, and resolve their Work the same way every sibling
composition panel does: `useStudioHost().bookId` → `useWorkResolution(bookId)` → **`selectCanonicalWork()`**
(EC-3c) → `project_id`. Scope comes off the studio bus (`activeChapterId` / `activeSceneId`, already published
by `StudioFrame` and `SceneRail`).

**The Work-less state is a first-class state for all three** (an imported book with no co-writer Work
resolves `status: 'none' | 'unmarked_single' | 'unavailable'`). Each renders the same CTA the legacy panel
does — *"Set up the co-writer for this book"* → `useCreateWork` — never a spinner, never a crash, never an
empty list that reads as "you have none."

### 1 · `style-voice` (category `editor`)

```
┌ STYLE & VOICE ────────────────────────────────── ⟳ ⤢ ✕ ┐
│ PROSE STYLE                                             │
│ Scope:  [ Work ] [ Chapter 41 ] [ Scene 3 ]             │  ← disabled when no chapter/scene is active
│                                                         │
│  Density  ▁▃▅▇  62   ● chapter        [Clear override]  │  ← TierChip: which scope actually supplied it
│  Pace     ▁▃▅▇  40   ● chapter        [Clear override]  │
│  ⓘ This scene inherits from Chapter 41. Editing here     │
│    creates a scene-level override.                      │
│                                                         │
│ CHARACTER VOICE                                         │
│  Lam Vũ        [terse] [ironic] [+]              ✕      │
│  Diệp Thanh    [formal] [archaic] [+]            ✕      │
│  [ search the cast… ]                                   │
└─────────────────────────────────────────────────────────┘
```

| State | Render |
|---|---|
| loading | `Skeleton` (the sibling convention) |
| no Work | *"Set up the co-writer"* CTA |
| **inherited** | numbers greyed + the **source** TierChip (`work` / `chapter`) + the inherit sentence; **no** Clear button |
| **overridden at this scope** | numbers solid + `● scene` chip + **Clear override** (→ `DELETE /style-profile?scope_type&scope_id`) |
| **unset everywhere** | `● neutral (unset)` + *"the packer adds no density/pace directive"* — **not** 50/50 |
| error | inline row-level error; the slider reverts to the server value |
| voice: no cast | *"No characters in the glossary yet"* → deep-link `host.openPanel('glossary')` |

**Writes.** `PUT /works/{pid}/style-profile` (upsert), `DELETE …/style-profile?scope_type=&scope_id=`,
`PUT /works/{pid}/voice-profiles`, `DELETE …/voice-profiles/{entity_id}`. Commit on pointer-up / Enter
(never per-keystroke). No OCC on these tables (no `version` column) — the upsert is last-writer-wins **by
design**, and the memory `instant-commit-control-over-occ-entity-needs-write-serialization` does **not**
apply (there is no version to self-412 against). Rapid slider commits are debounced and **chained** so two
in-flight PUTs cannot land out of order.

### 2 · `reference-shelf` (category `editor`)

Straight port of `ReferencesPanel` (add form · per-scene retrieval with pin/exclude · library), plus:

- an **embedding-model header row**: `bge-m3 · user_model · set on first add` (read-only, EC-2a) or, when
  unset, the model picker the current panel already renders.
- ⚠ **the model picker's empty state must NOT be `AddModelCta`** unless Wave 0's X-1 has landed. Today
  `ReferencesPanel` renders a plain warning div (`references-no-embed-model`, [`:76`](../../../frontend/src/features/composition/components/ReferencesPanel.tsx#L76)) — **keep it that way** or route it through
  `host.openPanel('settings', { params: { tab: 'providers' } })`. A raw `<Link>` here tears down the dock.

| State | Render |
|---|---|
| no embed model set | the picker + *"this choice is permanent for this book"* |
| embed provider down | `references-unavailable` — *"Retrieval unavailable (embedding provider down)"* (the BE already returns a neutral empty with `unavailable: true`, [`references.py:208-211`](../../../services/composition-service/app/routers/references.py#L208)) |
| no active scene | library only; the retrieval block is **absent** (not empty) with *"select a scene to see what it retrieves"* |
| empty library | *"No references yet — add influences above."* |
| add in flight | button → *"Adding…"*, disabled (this is a **paid embed call** — one at a time) |
| delete | immediate; **no undo** — the row's embedding is gone. The confirm dialog says so (`ConfirmDialog`, DOCK-9). |

### 3 · `divergence` (category `editor`)

```
┌ DIVERGENCE (DỊ BẢN) ──────────────────────────── ⟳ ⤢ ✕ ┐
│ ● Nghịch thiên — canonical            [ active ]        │
│                                                         │
│ DERIVATIVES (2)                                         │
│ ○ "Nếu Lam Vũ chết ở hồi 3"      AU · from ch. 62       │
│      3 entity overrides · 2 added canon rules           │
│      [ Switch to ] [ Archive ]                          │
│ ○ "POV: Diệp Thanh"        POV shift · from ch. 1       │
│      anchor: Diệp Thanh · 0 overrides                   │
│      [ Switch to ] [ Archive ]                          │
│                                                         │
│ [ + New divergence ]  → the 4-step wizard               │
└─────────────────────────────────────────────────────────┘
```

Reads: `GET /books/{bid}/work` → `selectDerivatives(candidates)`; per selected derivative,
`GET /works/{pid}/derivative-context` (taxonomy · branch_point · pov_anchor · canon_rules · overrides).
Writes: `POST /works/{pid}/derive` (the ported wizard) · `PATCH /works/{pid} {status:'archived'}` (If-Match).

| State | Render |
|---|---|
| no derivatives | the canonical row + *"A dị bản branches your book at a chapter and diverges — the source stays read-only."* + the New button |
| spec section | **read-only**, with the EC-3a note naming `works.py:378` and BE-13 |
| archive | `ConfirmDialog`: *"Archive this dị bản? Its chapters and knowledge partition are kept; it disappears from this list."* (it is a soft delete — say so, don't imply destruction) |
| 412 on archive | *"changed elsewhere — reloaded"* (the SceneRail recovery wording, verbatim; PH20) |
| switch-to | publishes the active Work to the studio bus; the Editor's `DerivativeBanner` lights up (*"you are adapting from read-only canon"*). **This is the one cross-panel effect in the wave** — spec it in the bus, not in a singleton. |
| derive in flight | the wizard's own `isSubmitting`; a derive mints a **fresh knowledge project** ([`works.py:363-376`](../../../services/composition-service/app/routers/works.py#L363)) and can 503 (`PROJECT_CREATE_UNAVAILABLE`) — surface that verbatim, it is not a generic failure |

### 4 · The Composition section in `book-settings` (NOT a new panel)

`book-settings` is a DOCK-2 wrapper over [`pages/book-tabs/SettingsTab.tsx`](../../../frontend/src/pages/book-tabs/SettingsTab.tsx).
The section goes **into `SettingsTab`** (so the classic book page gets it too — GG-1 is about human surfaces,
not Studio surfaces) as a self-contained `<CompositionSettingsSection bookId>` with **its own save path**
(`PATCH /works`), *not* folded into the book form's dirty-save bar (two resources, two saves).

| Row | Control | Tier shown |
|---|---|---|
| Story structure | select ← `GET /templates` → `PATCH /works {active_template_id}` | book |
| Prose composer model | ModelPicker → `settings.model_roles.composer` | book, inheriting **account** |
| Critic model | ModelPicker → `settings.model_roles.critic` | book, inheriting **account** — **with the honest warning**: *"the critic is skipped unless it is a different model from the drafter"* ([`engine.py:1649`](../../../services/composition-service/app/routers/engine.py#L1649)) |
| Planner model | ModelPicker → `settings.model_roles.planner` | book, inheriting **account** |
| Assembly mode | select (`per_scene` \| `chapter`) — closed set, 422 at the boundary ([`works.py:64-72`](../../../services/composition-service/app/routers/works.py#L64)) | book |
| Track narrative threads | toggle → `narrative_thread_enabled` | book |
| **Capture correction prose** | toggle → `capture_correction_prose` | book — **defaults OFF, and says what it does**: *"store the verbatim before/after prose of each correction so the model can learn your taste. Off = structural signal only."* |
| Reference embedding model | **read-only** + *"set on first add; changing re-embeds all N references"* | book |

Every row carries its **source tier** chip. No row shows a value the engine will not use. Legacy
`default_model_ref` is **read** (for back-compat) and **written** only as the dual-read shim's `chat` role.

### 5 · `plan-hub`: the Beats facet + the Decompose action (NOT a new panel)

- **Beats facet** (PH16, F-EC5a): a new `<Section title="Beats">` in `PlanDrawer`'s chapter/scene facet set.
  Reads the Work's `active_template_id` → `GET /templates` → that template's `beats[]`; renders the beat
  sheet with **this node's `beat_role` selected**; the selector is a **closed set fed by the template**
  (never a free-text input) → `PATCH /outline/nodes/{id} {beat_role}` with `If-Match: <version>` → 412 →
  *"changed elsewhere — reloaded."* **Zero backend.**
  - no `active_template_id` → *"No story structure chosen for this book"* + deep-link to the
    `book-settings` Composition section (`host.openPanel('book-settings')`).
- **Decompose action** on a chapter node's drawer: *"Decompose with a structure…"* → a `FormDialog`
  (structure ▾ defaulting to `active_template_id` · premise · model) → **`/actions/preview` → confirm**
  (BE-20) → 202 + `job_id` → **`ui_watch_job` → `job-detail`** (PO-3) → on success a **preview tree** the
  user accepts → `POST /works/{pid}/outline/decompose/commit`.
  - **Work-less book** → the action renders **disabled with a reason** (PH7 visible-fallback): decompose is
    Work-scoped (`/works/{pid}/…`) and the Hub is book-keyed (PH9). Never a dead button.
  - **already-planned chapter** → the BE refuses unless `replace=true` ([`plan.py:707`](../../../services/composition-service/app/routers/plan.py#L707)); the dialog surfaces that as an explicit *"replace the existing scenes"* checkbox, never as an opaque 400.
  - **empty plan** → the BE 400s `EMPTY_DECOMPOSE_PLAN` ([`plan.py:682-687`](../../../services/composition-service/app/routers/plan.py#L682)) with a real reason. Render it. Do not say "something went wrong."

---

## Backend prerequisites

**Contract.** A later agent builds from this table. `EXISTS` = verified at HEAD `9262ed53e`. Every
composition route is auto-proxied by the gateway (`pathFilter: p.startsWith('/v1/composition')`,
[`gateway-setup.ts:354`](../../../services/api-gateway-bff/src/gateway-setup.ts#L354)) — **zero gateway work.**

| # | Route / tool | METHOD + path | Request | Response | Errors | Size | Status |
|---|---|---|---|---|---|---|---|
| — | style profiles | `GET\|PUT /works/{pid}/style-profile(s)` · `DELETE /works/{pid}/style-profile?scope_type&scope_id` | `{scope_type, scope_id, density 0-100, pace 0-100}` | the row / `{removed: bool}` | 404 no-work/no-grant · 403 under-tier · 422 range | — | ✅ **EXISTS** |
| — | voice profiles | `GET\|PUT /works/{pid}/voice-profiles` · `DELETE …/{entity_id}` | `{entity_id, entity_name, tags[≤20]}` | the row / `{removed}` | as above | — | ✅ **EXISTS** |
| — | references | `GET\|POST /works/{pid}/references` · `DELETE /references/{rid}` · `GET /works/{pid}/scenes/{nid}/references?q&limit` | see [`references.py:49-59`](../../../services/composition-service/app/routers/references.py#L49) | `{references[], embed_model_set}` / `{hits[], embed_model_set, unavailable?}` | 422 `REFERENCE_EMBED_MODEL_UNSET` · 502 `REFERENCE_EMBED_FAILED` | — | ✅ **EXISTS** |
| — | derive · derivative-context · work patch · templates | `POST /works/{pid}/derive` · `GET /works/{pid}/derivative-context` · `PATCH /works/{pid}` (If-Match) · `GET /templates` | — | — | 412 `WORK_VERSION_CONFLICT` · 503 `PROJECT_CREATE_UNAVAILABLE` | — | ✅ **EXISTS** |
| — | beat_role write | `PATCH /outline/nodes/{id}` `{beat_role}` + `If-Match` | — | node | 412 `NODE_VERSION_CONFLICT` | — | ✅ **EXISTS** |
| **BE-10** | `composition_style_upsert` · `_style_delete` · `_style_list` · `composition_voice_upsert` · `_voice_delete` · `_voice_list` (MCP, Tier-A) | MCP | mirror the REST bodies; `project_id` derived from the **row/book**, never a body arg (H13) | the row + `_meta.undo_hint` (delete ⇒ the prior values; upsert ⇒ the prior row or `None` if it was unset) | uniform `not_accessible` | **S** | 🔨 **MUST-BUILD** — the INVERSE gap. ⚠ **3-schema-source FastMCP caveat** (memory `knowledge-mcp-three-schema-sources-fastmcp-strips`). |
| **BE-13a** | **name a derivative** | extend `DeriveBody` with `name: str (1..200)`; persist to `settings.derivative_name`; return it on `/derivative-context` + in `candidates[]` | `{name, branch_point, divergence, entity_overrides}` | Work | 422 empty name | **XS** | 🔨 **MUST-BUILD** — **hard prerequisite of the panel** (F-EC3a). **No DDL**: `settings` is a JSONB blob the Work already carries. |
| **BE-18** | **fix the settings REPLACE** | `repositories/works.py:311` → `settings = COALESCE(settings,'{}'::jsonb) \|\| $n::jsonb`; add `settings_unset: list[str]` to `WorkPatch` for key removal; FE `patchWork` gains an **optional** `ifMatch` (per-call-site, **never blanket** — EC-4b: `useWorldMap` drags through this same function) | — | — | 412 as today | **XS** | 🔨 **MUST-BUILD** — EC-4b. A real lost-update window on a live route. |
| **BE-21** | 🔴 **make the engine READ `model_roles`** | one `resolve_model_role(settings, role) -> (ref, source)` helper in composition-service: `settings.model_roles.<role>` **first**, legacy scalar as fallback (lift the dual-read out of [`internal_model_settings.py:46-65`](../../../services/composition-service/app/routers/internal_model_settings.py#L46) — do not write a second copy); **all 7 `critic_model_ref` read sites** in `routers/engine.py` (`465, 529, 1029, 1099, 1261, 1345, 1644`) call it | — | — | unchanged | **S** | 🔨 **MUST-BUILD** — **HARD PREREQUISITE of the Composition section (F-EC4b).** Without it, EC-4 writes a key **nothing reads** and M4a's DoD behaviour test reds. Gates **M4a**. |
| **BE-20** | **cost-gate decompose** | (a) MCP `composition_decompose` (**Tier-W** — executes nothing, mints a confirm token, mirrors `composition_conformance_run`); (b) descriptor `composition.decompose` in `_ALL_DESCRIPTORS`; (c) `_execute_decompose` = `_claim_or_replay` → `_precheck_or_402` → enqueue the **existing** `plan_pipeline`/decompose worker op | `{project_id, structure_template_id, premise, model_ref, model_source, pipeline?, replace?}` | `{outcome:"action_accepted", descriptor, job_id, poll:"composition_get_mine_job"}` | 402 quota · 400 `action_error` · 410 `token_expired` | **M** | 🔨 **MUST-BUILD** — F-EC6 + EC-5b. **Also closes an INVERSE gap** (the agent cannot decompose today either). Gates **M4b only**. |
| **BE-13** | divergence spec/override CRUD | `PATCH /works/{pid}/divergence-spec` · `POST\|PATCH\|DELETE /works/{pid}/overrides` | — | — | — | **M** | ⏸ **DEFERRED to v2** (EC-3a). ⚠ `D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH` stays **dormant** as long as no builder copies `outline_node` rows into the derivative partition (plan 30 §10). |
| **BE-17** | reference update + model surfacing | `PATCH /references/{rid}` (metadata only, **no re-embed**) · widen LIST to return `reference_embed_model_ref/_source` | — | — | — | **S** | ⏸ **DEFERRED to v2** (EC-2a). |
| **BE-12** | `structure_template` authoring | `POST /templates` · `PATCH\|DELETE /templates/{id}` + `POST /templates/{id}/clone` | — | — | — | **M** | ⏸ **PO DECIDES at CLARIFY** (EC-5a; recommendation: defer). **Tenancy is the whole job**: the 6 built-ins are System tier (`owner_user_id IS NULL`) — a user **clones**, never mutates. |

**What this wave does NOT need:** no migration, no new table, no gateway change, no new
`FE_BRIDGE_TOOL_ALLOWLIST` entry (every panel read/write is REST; only BE-20's propose uses `mcpExecute`,
whose allowlist entry lands with BE-20).

---

## Registration checklist (GG-8) — three new panel ids

The drift-lock is an **equality**, not a number: **py enum == contract enum == openable**, and this wave moves it
by **exactly +3**. ⚠ **Do NOT hard-code an absolute count.** At HEAD `9262ed53e` the baseline is **57 == 57 == 57**
(verified: `contracts/frontend-tools.contract.json` `panel_id.enum` has 57 members) — but Wave 6 sits **downstream
of Waves 1–3** in plan 30 §9's sequencing, and each of those adds panels (`quality-canon-rules`, `progress`,
`quality-corrections`, `quality-heal`, `motif-library`, `quality-conformance`, …). By the time this wave starts the
baseline will be **higher**, and a DoD that asserts "58/58/58" would send a builder hunting a phantom regression.
**Assert `N_before + 3 == N_after` and the three-way equality — never a literal.**
All three panels are openable by a **bare id** (they resolve their own scope from `bookId` + the bus), so none
is `hiddenFromPalette` and **all three enter the enum** — the X-12 params trap does not apply here.

| # | File | Add |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/StyleVoicePanel.tsx` · `ReferenceShelfPanel.tsx` · `DivergencePanel.tsx` | root `data-testid="studio-style-voice-panel"` / `studio-reference-shelf-panel` / `studio-divergence-panel` |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | 3 `STUDIO_PANELS` rows — `{ id, component, titleKey, descKey, category: 'editor', guideBodyKey }`. `category` and `guideBodyKey` are **both** mandatory (X-2/X-3 add the assertions). |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.style-voice.{title,desc,guideBody}` · `panels.reference-shelf.*` · `panels.divergence.*` |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**, never by hand |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append `"style-voice"`, `"reference-shelf"`, `"divergence"` to the `panel_id` **enum** (`:402`); (b) append a per-panel clause to the tool **description** (`:403-481`) — that gloss is the model's only hint. Say *"`reference-shelf` = the author's research corpus (NOT entity backlinks — that is `find_references`)"*, explicitly, so the two never collide in a tool-search. |
| 6 | `contracts/frontend-tools.contract.json` | **regenerate, never hand-edit:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py` — commit the regenerated JSON **in the same commit** as steps 2 + 5. |
| 7 *(cond.)* | `frontend/src/features/studio/host/studioLinks.ts` | none needed — no external URL resolves to these panels |
| 8 **(mandatory)** | `frontend/src/features/studio/agent/handlers/compositionEffects.ts` — ⚠ **NOT new: [`31`](31_quality_completion.md) §Registration step 8 CREATES this file in Wave 1** (canon-rule + `composition_record_correction` handlers). **EXTEND it; do not re-create it.** | Add `registerEffectHandler(/^composition_(style\|voice)_/, …)` → invalidate `['composition','style-profiles',pid]` / `['voice-profiles',pid]` **and** `['composition','grounding',pid]` (the resolved style surfaces in the grounding preview — `useStyleVoice.ts:24-25` already does this on the human path; the agent path must not be the one that goes stale). ⚠ **Use a `RegExp`, not the bare string `'composition_(style\|voice)_'`** — `registerEffectHandler`'s string branch is `tool === p \|\| tool.startsWith(p)` ([`effectRegistry.ts:41`](../../../frontend/src/features/studio/agent/effectRegistry.ts#L41)), **not** a pattern match: a string containing `(a\|b)` would match **nothing** and the handler would be a silent no-op — the exact `silent-success-is-a-bug` class, invisible to a unit test that registers and calls its own fake. |
| 9 *(cond.)* | `tours.ts` / `tourCatalog.ts` | not a role-tour step in v1 |
| 10 **(new — EC-3d)** | `frontend/src/features/studio/host/types.ts` (+ its reducer) | 🔴 **The bus has NO active-Work concept today** — it carries `activeChapterId` / `activeSceneId` (`:36-37,73-74`) and nothing else. *Switch to* needs `activeWorkProjectId` + a `work:switch` event, hydrated on mount from `/v1/me/preferences`. This file is **not** on the "Do NOT touch" list below — but it is load-bearing for **7 consumer sites** (EC-3c), so change it once, in M3, and make every consumer read `useActiveWork()`. |

**Verify (all four green — the first two are the drift-locks):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx` (all derive
from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## Agent surface

| Domain | Tools today | After this wave |
|---|---|---|
| style / voice | **none** | `composition_style_{list,upsert,delete}` · `composition_voice_{list,upsert,delete}` (BE-10, Tier-A, `_meta.undo_hint`) |
| references | **none** | **still none** — v1 is human-only. *An honest INVERSE gap, recorded, not hidden:* the agent can `pack()` with references and cannot curate them. Cheap follow-up (the routes exist); out of this wave's scope. |
| divergence | **none** | **still none.** Deriving mints a knowledge project and forks the book's whole grounding partition — an AN-8 Tier-W-shaped action that deserves its own confirm design, not a bolt-on. Recorded as an open INVERSE gap. |
| work settings | `composition_get_work` (read) — **no update tool** | **still none.** A `composition_update_work` would let an agent silently change the user's *models*, and spec 28's AN-8 edit-discipline table gives settings **no** agent channel. **Consciously won't-fix** (defer gate #5) — recorded so it stops re-surfacing. |
| story structure | **none** | `composition_decompose` (BE-20, **Tier-W** — executes nothing; the effect lives in `actions.py` keyed on `composition.decompose`) |

**⚠ AN-8's table gains two object classes — write them INTO spec 28, do not fork it.** BE-10 introduces
`style_profile` and `voice_profile` as agent-writable object classes. §8.1 says AN-8's edit-discipline table is
the ONE place a class's channel/tier/undo path is recorded. These follow the existing convention exactly
(**Tier-A**, `_meta.undo_hint`, no new confirmation convention), so this is an *addition*, not an amendment — but
an unrecorded addition is how the table erodes. Add the two rows to
[`28_agent_native_studio.md`](28_agent_native_studio.md)'s AN-8 table in the same commit as BE-10, exactly as PO-1
requires for AN-12.

**Lane-B effect handlers (X-4).** `composition_(style|voice)_*` and `composition_decompose` need handlers, or
an agent write leaves the human's panel stale — the class X-4 exists to kill. Registered in the same
`compositionEffects.ts` Wave 0 creates. `composition_decompose`'s handler invalidates the outline + plan-hub
keys on the **job's completion**, not on the tool call (a Tier-W tool returns a token, not an effect).

**The discovery scent (AN-C2 / X-10).** Six new tools the model is never told about are six tools that will
never be called (spec 28 AN-11 calls "shipped but never called" a FAIL). One clause in
`stream_service.py`'s `book_context_note`. ⚠ **`stream_service.py` is Track C's, mid-edit** (plan 30 §9) —
**sequence this after Track C lands**, and do not touch the file before then.

---

## Compliance

**Tenancy.** No new table, therefore no new scope key. Every row this wave writes is **Per-book**:
`style_profile` / `voice_profile` / `reference_source` / `divergence_spec` / `entity_override` all carry
`project_id` **and** `book_id`, and every route gates the caller's **E0 book grant** (VIEW to read, EDIT to
write) via `_gate_work` / `_require_work` — resolving the Work by project and the grant by *its* book
([`style_voice.py:34-48`](../../../services/composition-service/app/routers/style_voice.py#L34)). By-id routes
(`DELETE /references/{rid}`) derive scope **from the row** ([`references.py:160-165`](../../../services/composition-service/app/routers/references.py#L160)) —
the `gate-must-derive-scope-from-the-loaded-row` law, already honoured. **`structure_template` is the one
System-tier resource here**: the 6 built-ins are `owner_user_id IS NULL` and are **read-only to every user**.
BE-12, if it is ever built, must be **clone-to-user**, never mutate-the-shared-row (the `entity_kinds` bug).

**Settings (SET-1..8).** Every control in the Composition section and in `style-voice` surfaces its
**effective value + source tier**; nothing renders a default the engine will not use (EC-1). All state is
**server-side** (`composition_work.settings`, PATCHed) — **no localStorage**. Closed sets are enum-validated
at the write boundary (`assembly_mode` 422s server-side today; `beat_role` becomes a template-fed select;
`taxonomy` is a `Literal`). **One home:** models → `settings.model_roles` (EC-4); story structure →
`active_template_id` (EC-5). Every toggle in the section is **CONSUMED, proven by effect** — the DoD requires
a test per key that asserts the *behaviour changes*, not that the blob was written.

**OCC.** `PATCH /works` and `PATCH /outline/nodes/{id}` both take `If-Match: <version>` and 412 with
`WORK_VERSION_CONFLICT` / `NODE_VERSION_CONFLICT` carrying the current row. Every panel that 412s
**reloads and says so** — *"changed elsewhere — reloaded"* (the SceneRail wording, PH20) — and never
silently overwrites. `style_profile` / `voice_profile` have **no version column**: their PUT is an
upsert, last-writer-wins **by design**; rapid commits are chained (not raced), and the
`instant-commit-control-over-occ-entity` memory does not apply (no version ⇒ no self-412).

⚠ **But it DOES apply to `composition_work`, and EC-4b is where this wave nearly re-shipped it.** `patchWork`
is one shared function over a **versioned** row with **5 call sites**, one of which (`useWorldMap` → node drag)
is a textbook instant-commit control. `If-Match` is therefore **opt-in per call site** (EC-4b), and any site that
opts in must **chain its writes and re-seed `version` from the response**. A blanket `If-Match` on `patchWork`
would make the world map 412 against itself on the second drag — the memory, verbatim, on a route this wave
touches for an unrelated reason.

**Cost gates.** Two paid actions in this wave. **Reference add** embeds one passage — a single cheap
provider call on an explicit user action, already fail-closed with a 502 and no silent retry; it stays a
direct call (it is not Tier-W and never was). **Decompose** spends real LLM tokens and therefore goes through
the **generic** `GET /v1/composition/actions/preview` → `POST /v1/composition/actions/confirm` spine
(BE-20) — **never** a bespoke per-action estimate route (plan 30 §3.3: three such invented routes 404 in
production today). No new confirmation convention is introduced anywhere in this wave (AN-8).

---

## Milestones

Each is independently shippable, ends at a POST-REVIEW, and is revertable.

| # | Slice | BE prereq | DoD |
|---|---|---|---|
| **M1** | **`style-voice`** — port + the cascade (EC-1) + `TierChip`'s 4 new tier rows + the `ClearOverride` affordance + BE-10 (the 6 MCP tools) | BE-10 (S) | Panel green; the drift-locks green at **`N+1` three-way equality** (never a literal — §Registration); a test asserts an **inherited** scope renders the *inherited* numbers + the source chip (not 50/50); a test asserts the `scene`/`chapter`/`work`/`neutral` chips render their **labels**, not the raw tier string (the TierChip-fallback trap); a test asserts `ClearOverride` calls DELETE and the row falls back to the parent scope; **an agent `composition_style_upsert` re-renders the open panel** (Lane-B). |
| **M2** | **`reference-shelf`** — port + the read-only embed-model header (EC-2a) | none | Panel green at **`N+2`**; add → the passage embeds and appears in the library; per-scene retrieval renders hits with pin/exclude; provider-down renders `references-unavailable`, **not** a 500; the delete confirm names the re-embed cost. |
| **M3** | **`divergence`** — BE-13a (name) + EC-3c (the `source_work_id` predicate, **all 12 sites**) + EC-3d (`useActiveWork` + the bus + the persisted per-user active Work) + the panel + the wizard port + the banner | BE-13a (XS) | Panel green at **`N+3`**; **a derivative is created, named, listed, switched-to and archived, all from the dock**; the spec renders read-only with the EC-3a note; **a hygiene test asserts `candidates[0]` appears NOWHERE in `frontend/src` or `services/` outside tests** (a count-based DoD is how 9 of the 12 sites were missed the first time — grep for the *pattern*, not a number); `selectCanonicalWork` has a test proving a *derivative sorted first* (impossible today, trivial in a fixture) still resolves the canonical one, **and** a `source_work_id: undefined` fixture still resolves (the `=== null` trap); **`Switch to` survives a reload** — the Editor, navigator, scene-inspector and quality panels are ALL still on the derivative (this is the test that proves EC-3d, and the one a bus-only implementation fails). |
| **M4a** | **Story structure, the free half** — the Composition section (incl. **BE-21** + BE-18) + `active_template_id` as the one home + the **Beats facet** in `PlanDrawer` | **BE-21 (S)** · BE-18 (XS) | Every key in the section shows effective value + source tier; **a behaviour test per key** — *"critic model set ⇒ the critique is no longer skipped"* is the one that **only passes if BE-21 landed** (without it the engine still reads `critic_model_ref` and returns *"critique skipped"* — F-EC4b); `capture_correction_prose` on ⇒ `raw_before/raw_after` are stored ([`engine.py:1766`](../../../services/composition-service/app/routers/engine.py#L1766)); two concurrent PATCHes to two different keys **both survive** (the BE-18 merge) and a stale same-key PATCH from the section **412s**; **a world-map drag still does NOT 412** (the EC-4b regression guard); the Beats facet writes `beat_role` and 412s cleanly. |
| **M4b** | **The Decompose action** | **BE-20 (M)** | `/actions/preview` returns a real estimate; confirm enqueues; a decompose with an exhausted budget **402s before the LLM runs** (the precheck); the preview tree commits; `EMPTY_DECOMPOSE_PLAN` and the already-planned 400 render as real reasons. |
| **M5** | **The GG-4 gate** — §10 | none | The parity contract test is green **and lists what is still unported**. |

---

## Definition of Done

1. **All four drift-locks green** (the two commands in §Registration), with all three counts moving **+3 in lockstep** (`N_before + 3 == N_after` across py enum == contract enum == openable). ⚠ **Assert the delta, never a literal** — this spec's own §Registration says so, and an earlier cut of this line said `60 == 60 == 60`, which is **wrong**: Waves 1–5 land **9** panels before this wave, so the baseline is **66** and the end state is **69**. A literal here is exactly the phantom regression §Registration warns about.
2. **Unit + integration suites green**, per service: `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup` · `cd frontend && npx vitest run`.
3. **A behaviour test per settings key** (SET-4, "consumed, proven by effect"). *Writing the blob is not evidence.*
4. **Cross-service live-smoke** (composition + chat-service + frontend ⇒ ≥2 services): an agent turn calling
   `composition_style_upsert` **changes the next draft prompt** — assert the density directive appears in the
   packed prompt (the `test_pack_arc_wired.py` BA12 effect-test pattern). A green mock is not proof.
5. 🔴 **LIVE BROWSER SMOKE — mandatory, non-negotiable** (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`;
   a green unit suite has hidden *"the FE could not actually execute it"* four times in this repo). New Playwright
   spec `frontend/e2e/studio-editor-craft.spec.ts`, against the **baked nginx build on :5174** (a host `vite dev`
   **shadows** it — memory `frontend-5174-is-baked-prod-nginx-not-vite`), driving the dock via
   `evaluate` + `data-testid` (refs go stale — memory `playwright-live-dockview-automation-recipe`), signed in as
   `claude-test@loreweave.dev`:
   - `ui_open_studio_panel {panel_id:"style-voice"}` from the agent chat **mounts the dock tab** — move the
     density slider, reload, assert it persisted and that the **source chip** says `work`.
   - `ui_open_studio_panel {panel_id:"reference-shelf"}` → add a reference with a **local** embed model
     (`bge-m3`, $0) → it appears in the library → select a scene → it is retrieved.
   - `ui_open_studio_panel {panel_id:"divergence"}` → run the wizard → the named derivative appears in the list
     → switch to it → the `DerivativeBanner` renders in the Editor → archive it → it leaves the list.
   - `book-settings` → Composition → set the critic model → a critique run **no longer** returns
     *"critique skipped."*
   - `plan-hub` → a chapter's drawer → **Beats** → change `beat_role` → reload → it persisted.
6. **No new global `*_ENABLED` env flag** gating any of this (CLAUDE.md Settings boundary). There are none.
7. **SESSION_HANDOFF updated + committed in the same commit as the code**; the Deferred rows below filed.

---

## The GG-4 gate — spec 16's `ChapterEditorPage` retirement

**This is the section the wave exists to earn.**

**The gate.** When M1–M4 close, every legacy-only editor-craft capability has a Studio home, and **only then**
may spec 16's retirement proceed. Retiring earlier **deletes shipped features** — 70,183 bytes,
[25 sub-tabs](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L87), still mounted at
[`App.tsx:134`](../../../frontend/src/App.tsx#L134). Spec 16 M1 claims the Studio is *"the sole chapter-editing
surface."* **That is not true of the code**, and its only enforcement is an 18-line prose banner: no lint rule,
no hygiene test, no route assertion.

**Three things the audit did not say, and a builder must know:**

1. 🔴 **The retirement is not "pending" — it was CANCELLED.** Spec 16's own status line reads *"Phase 4b (M9 —
   **kept** `ChapterEditorPage.tsx`, marked deprecated, **not deleted**)"*, and the file's banner says *"a
   decision to keep it around, **not** a decision pending removal (spec 16 Phase 4b, 2026-07-05: kept
   indefinitely)."* So this wave does **not** unblock a queued deletion; it **reopens a closed decision**. The
   PO must choose again: *delete*, or *keep as a deprecated URL-only fallback forever*. Do not "resume" a
   retirement nobody re-authorized.
2. 🔴 **M6 (mobile) is still unresolved, and it is a real blocker on deletion.**
   [`MobileEditorShell.tsx`](../../../frontend/src/components/editor/MobileEditorShell.tsx) and
   `MobilePanelSwitcher.tsx` exist **only** on the legacy path. The Studio's entire mobile concession is
   *"collapse the sidebar by default"* ([`useStudioChrome.ts:13-16`](../../../frontend/src/features/studio/hooks/useStudioChrome.ts#L13)).
   Deleting the page deletes **the only mobile chapter-editing surface in the product.** Spec 16 M6 explicitly
   left this open ("NOT decided here") and M9 gates deletion on it. **This wave does not close it.**
3. **`editorBridge` is still alive, for a reason that expired.** Spec 16's P1 left the global
   `registerEditorTarget` singleton in place **because the page was being retired** — a premise Phase 4b
   cancelled and nobody revisited. It has **10 referencing files** today. Deletion is the moment it can finally
   die; keeping the page keeps the singleton.

**The mechanical guard — this is the deliverable.** A comment is the weakest available guard
(`built-mounted-unreachable-duplicated-nav-list`). Two tests, and they land **with** the retirement — but the
first should land **now, in M5**, red-listing what is still unported, so the gate is machine-checked instead of
argued:

```ts
// frontend/src/features/studio/panels/__tests__/legacyParityContract.test.ts
// THE GG-4 GATE, MECHANIZED. Every legacy CompositionPanel sub-tab maps to a Studio panel id
// (or carries an explicit, reviewed reason not to). Retiring ChapterEditorPage while any row
// still reads UNPORTED deletes a shipped feature. This test is the gate — not a comment.
const LEGACY_SUBTAB_HOME: Record<SubTab, string | { retired: string }> = {
  style:       'style-voice',        // ← this wave, M1
  references:  'reference-shelf',    // ← this wave, M2
  settings:    'book-settings',      // ← this wave, M4a
  beats:       'plan-hub',           // ← this wave, M4a (drawer facet)
  canon:       'quality-canon-rules',// ← Wave 1
  polish:      'quality-heal',       // ← Wave 1
  progress:    'progress',           // ← Wave 1
  flywheel:    'quality-corrections',// ← Wave 1
  motifs:      'motif-library',      // ← Wave 3
  conformance: 'quality-conformance',// ← Wave 3
  arc:         'arc-templates',      // ← Wave 4
  // …every one of the 25…
  threads:     { retired: 'duplicate of quality-promises — delete, do not port (00C Q-3c)' },
};
it('every legacy sub-tab has a Studio home or a reviewed retirement reason', () => {
  for (const [tab, home] of Object.entries(LEGACY_SUBTAB_HOME)) {
    if (typeof home === 'string') expect(OPENABLE_STUDIO_PANEL_IDS).toContain(home);
    else expect(home.retired.length).toBeGreaterThan(20);   // a reason, not a shrug
  }
});
```

```ts
// frontend/src/__tests__/legacyEditorRouteRetired.test.tsx   (lands WITH the deletion, not before)
it('the legacy edit route is gone and redirects — bookmarks must not 404', () => {
  expect(routeTable()).not.toContain('/books/:bookId/chapters/:chapterId/edit');
  expect(redirectFor('/books/b1/chapters/c1/edit')).toBe('/books/b1/studio');
});
it('nothing imports ChapterEditorPage', () => { /* hygiene grep over frontend/src */ });
```

⚠ The hygiene grep must match an **import**, not the literal string — a grep for `ChapterEditorPage` hits this
spec, spec 16, and the banner itself (`hygiene-grep-literal-token-in-comment-false-positive`).

**Recommendation to the PO (not a decision):** ship M5's parity contract in this wave; **do not delete the
page in this wave.** Take the delete decision separately, once M6 (mobile) has an answer, with the parity test
green and `editorBridge` scheduled to die in the same PR.

---

## Open questions / Deferred

| # | Question | Recommendation | Owner |
|---|---|---|---|
| **OQ-1** | **Is `structure_template` authoring (BE-12) in v1?** | **Defer.** The 6 built-ins reachable is 90% of the value; the write path is 3 routes **plus** a clone-to-user tenancy design. Plan 30 BE-12 says "decide in CLARIFY" — this is that decision. | **PO, at CLARIFY** |
| **OQ-2** | **Delete `ChapterEditorPage`, or keep it as a deprecated fallback?** Phase 4b already chose *keep*; this wave only removes the *feature-loss* objection, not the *mobile* one. | Keep for now; take the decision when M6 has an answer. **Do not fold it into this wave.** | **PO** |
| **OQ-3** | **BE-20 (M) is a real chunk of work for one button.** Alternative: point the Decompose action at the existing route (as the legacy planner does) and label it "no cost estimate." | **Build BE-20.** Porting a known cost-gate hole onto a new surface, in the wave whose thesis is *"the human deserves the agent's rails"*, is self-refuting. M4 is split so this blocks only M4b. | **PO** |
| **OQ-4** | **UNVERIFIED — how many references does a typical Work hold?** EC-2a's *"changing the model re-embeds all N"* copy needs a real N to be honest, and BE-17's cost depends on it. | Measure on the dev DB before writing the copy. | builder |
| **OQ-5** | **UNVERIFIED — does the Book tier of the model cascade actually reach `chat-service`'s resolver end-to-end?** The route ([`internal_model_settings.py`](../../../services/composition-service/app/routers/internal_model_settings.py)) and the consumer ([`ai_settings.py:194`](../../../services/chat-service/app/routers/ai_settings.py#L194)) both exist; **nothing has ever written a `model_roles` map**, so the path is unexercised in production. M4a is the first writer. | **Live-smoke it explicitly** — write `model_roles.critic` from the panel, then read `GET /v1/chat/ai-settings/effective` and assert `source_tier === 'book'`. This is a `new-cross-service-contract-needs-consumer-live-smoke` case. | builder |
| **OQ-6** | Should `reference-shelf` also surface the **pinned** references the `GroundingPanel` shows, or does the split stand? | The split stands (shelf = the corpus; grounding = what this scene actually uses). Both panels deep-link to each other. | — |
| **OQ-7** | **Where does the per-user active Work live (EC-3d)?** v1 says `/v1/me/preferences` key `lw_active_work.<book_id>`. The alternative — a `composition_work`-side "last opened by user X" table — is a new table for a preference. | **Preferences.** It is per-user UI state that must survive a reload: exactly what `/v1/me/preferences` is for, and exactly what `work.settings` (per-book, shared) must **not** hold. A new table would need its own tenancy review for zero extra capability. | **PO, at CLARIFY** |
| **OQ-8** | **Does BE-21's role-resolver change `composer`/`planner` behaviour too, or only `critic`?** The 7 sites are all `critic`; `default_model_ref` (→ role `chat`) has its own readers. | Ship BE-21 as a **generic** `resolve_model_role(settings, role)` but **only re-point the 7 `critic` sites** in this wave. Re-pointing the `default_model_ref` readers is a separate, wider blast radius (the eval scripts write it) and earns its own slice. Record it. | builder |

**Deferred rows to file in `SESSION_HANDOFF.md`:**

| ID | Row | Gate |
|---|---|---|
| `D-REF-UPDATE-AND-MODEL-SURFACE` | BE-17: `PATCH /references/{rid}` + widen LIST to expose `reference_embed_model_ref` | #2 (large-ish / v2 slice) |
| `D-DIVERGENCE-SPEC-EDIT` | BE-13: `PATCH /divergence-spec` + override CRUD — **unbuildable on today's backend**, needs new write semantics | #2 (structural) |
| `D-STRUCTURE-TEMPLATE-AUTHORING` | BE-12 + clone-to-user tenancy | #4 (PO decision — OQ-1) |
| `D-REFERENCES-MCP-TOOLS` | the agent still cannot curate the corpus it grounds on (INVERSE gap) | #3 (naturally-next-phase) |
| `D-DIVERGENCE-MCP-TOOLS` | deriving forks a knowledge partition — needs its own AN-8 confirm design | #2 (structural) |
| `D-STUDIO-MOBILE-SHELL` | **the Studio has no mobile editing surface** — spec 16 M6, still open, now a hard blocker on retirement | #4 (product decision) |
| `D-EDITORBRIDGE-SINGLETON` | 10 files; alive only because the page it was going to die with was kept | #3 (dies with the page) |
| `D-WORK-MODEL-ROLES-DEFAULT-REF` | BE-21 re-points the **7 `critic`** read sites at `model_roles`; the `default_model_ref` (→ role `chat`) readers — incl. 8 `scripts/eval_*.py` — still read the legacy scalar. One home is only half-built until they follow. | #2 (wider blast radius — its own slice; OQ-8) |
