# Implementation Plan — Wave 6 · Editor-craft ports + the GG-4 retirement gate

> 🔴 **RECONCILED AGAINST THE ADJUDICATION REGISTER 2026-07-13.** This plan was written **blind** (it
> believed the register did not exist). It does:
> **[`docs/plans/studio-adjudication/wave-6-decisions.md`](studio-adjudication/wave-6-decisions.md)** —
> **64 items, 56 DECIDED against source.** **THE REGISTER OUTRANKS THIS PLAN.** See §0.1 (C12–C16) for
> every place it **overruled** what was written here. **Never re-litigate a decision from memory —
> re-read the register.**
>
> **Type:** FS · **Size:** **XL** (files ≈ 60 · logic ≈ 20 · side_effects = 8 — **5 new panel ids** · the
> `frontend-tools` contract · 🔴 **the OpenAPI contract (W6-C0)** · 4 changed REST bodies · **4 new REST
> routes** · **4 new MCP tool families (17 tools)** · 2 new descriptors · a tenancy fix on `PATCH /works`).
> *(Was **L**/3-panels before the reconciliation; five refuted defer rows came back IN, and two homeless
> legacy sub-tabs got panels.)*
> **NO MIGRATION.** No new table, no DDL, no gateway change **except one `FE_BRIDGE_TOOL_ALLOWLIST` entry**.
> **Source spec:** [`docs/specs/2026-07-01-writing-studio/36_editor_craft_ports.md`](../specs/2026-07-01-writing-studio/36_editor_craft_ports.md)
> **Master plan:** [`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) — §0 SEALED PO decisions · §8 GG-8 registration · §8.0 panel-id ledger · §8.0b Lane-B homes · §9 collisions · §10 REFUTED.
> **Drafts (the acceptance criterion for the UI):** [`design-drafts/screens/studio/screen-style-voice-references.html`](../../design-drafts/screens/studio/screen-style-voice-references.html) (①–⑤) · [`screen-divergence.html`](../../design-drafts/screens/studio/screen-divergence.html) (①–⑧ — divergence **+** the `book-settings` Composition section **+** the `plan-hub` Beats facet; the filename predates the pairing — **do not split it**).
> **Verified against code at HEAD `9262ed53e`** on 2026-07-13. Every backend claim below was re-read from source, not from a doc. Where the spec was wrong, this plan says so and **the correction is binding** (§0.1).

---

## 0 · The policy this plan is written under (BINDING — quoted from the PO)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** Anything left vague becomes a stall or a guess at
   3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE, WHICH TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the wave
   closes. It is a literal step in the Wave DoD (§8).
3. **DEFERRAL POLICY — "blocked ≠ stopped."** On hitting a blocker: write a tracked defer row and
   **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss; a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (plan 30 §0 PO-1..PO-4),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing.**
   Everything else — a missing route, an awkward refactor, an ugly seam — is a **defer row + continue.**
4. Every defer row carries: ID · wave/slice of origin · what · the gate reason (CLAUDE.md's 5 gates) ·
   target wave/trigger. **A defer row is never a silent drop.**
5. **CLAUDE.md's anti-laziness rule is in force:** *"missing infrastructure is NOT blocked — it is unbuilt
   work to implement."* A route that does not exist is a route you **WRITE**.

### 0.1 · Corrections to the spec — verified in code, BINDING over the spec's prose

> 🔴 **RECONCILED 2026-07-13 — THE ADJUDICATION REGISTER EXISTS.**
> This plan was originally written **blind**: it said *"the adjudication register named in the wave brief
> does not exist on disk"* and therefore bound **spec 36's own recommendations**. That was wrong. The
> register was recovered from the journal and is on disk at
> **[`docs/plans/studio-adjudication/wave-6-decisions.md`](studio-adjudication/wave-6-decisions.md)**
> (64 items · 56 DECIDED · 6 not-a-question · 2 deferred). **Every decision in that file was settled by
> reading source.**
>
> **THE REGISTER OUTRANKS THIS PLAN AND OUTRANKS SPEC 36.** Where they disagreed, this plan has been
> rewritten to the register. **Do not re-litigate a decision from memory — re-read the register.**
> The decision IDs (`Q-36-…`) are cited inline throughout; every one is a link back to its evidence.
>
> **What the reconciliation changed (the headline):** **five items this plan DEFERRED are now IN the
> wave** — BE-13 (divergence-spec editing), BE-17 (reference LIST-widen + PATCH), BE-10b (reference MCP
> tools), the divergence MCP tools, and the discovery scent (X-10). Each defer row was **refuted by code**
> (see §9). **Two new panels** are added (`scene-compose`, `chapter-assemble`) so that GG-4's retirement
> gate does not delete a shipped feature. Registration moves **+3 → +5**.

The **sixteen code-verified corrections** below are BINDING over the spec's prose. C1–C11 were found by this
plan; **C12–C16 come from the register** and correct **this plan**.

| # | Spec said | The code says | Consequence for this plan |
|---|---|---|---|
| **C1** | M3 DoD: *"a hygiene test asserts `candidates[0]` appears NOWHERE in `frontend/src` or `services/` outside tests"* | There are **5 UNRELATED** `candidates[0]` sites: `src/components/editor/SceneAnchor.ts:112` (prosemirror positions) · `src/features/glossary/lib/resolveDisplayValue.ts:35` · `src/features/plan-forge/components/PlannerPanel.tsx:77` (model list) · `services/composition-service/app/engine/prose_doc.py:77` · `services/knowledge-service/app/extraction/pass2_writer.py`. A repo-wide grep-for-zero **reds on day one.** | The hygiene test is **DIRECTORY-SCOPED** to `src/features/studio/**`, `src/features/composition/**`, `src/features/books/**`, `src/pages/**` — which contains exactly the 11 FE work-resolution sites and **zero** false positives. The BE site is `rows[0]`, not `candidates[0]`, and gets its **own pytest assertion.** See slice **W6-FE0**. |
| **C2** | BE-20: *"add `composition.decompose` to `_ALL_DESCRIPTORS`"* | `confirm_action`'s Work-scoped tail **ends in an unconditional fallthrough**: `return await _execute_conformance_run(...)` (`actions.py:342`). Adding the descriptor to the allowlist **without** an explicit branch routes a decompose confirm **into the conformance effect** — a silent wrong-effect on a **paid** action. | **W6-BE5 must convert the fallthrough into an explicit `if descriptor == _CONFORMANCE_RUN_DESCRIPTOR:` branch + a terminal `raise HTTPException(400, {"code":"action_error"})`.** A test asserts an unknown Work-scoped descriptor 400s instead of silently running conformance. |
| **C3** | EC-4b: *"`patchWork` is a shared writer with **5 call sites**"* | It has **4** today: `api.ts:443` (the def) ← `useChapterAssembly.ts:33` · `useProgress.ts:77` · `useWork.ts:135` (`useSetWorkSettings`, which is what `useWorldMap` writes through). | The divergence archive is the **5th, new**. The EC-4b analysis is otherwise exactly right — keep `ifMatch` opt-in. |
| **C4** | (unstated) | `WorksRepo.update` (`repositories/works.py:320-325`) appends `version = version + 1` **only when `expected_version is not None`.** A **blind** PATCH does **not** bump `version`. | Two consequences: (a) a world-map drag can never invalidate the Composition section's cached version ⇒ EC-4b's 412 fear is even smaller than feared — **but keep `ifMatch` opt-in anyway**, the reasoning stands; (b) it is a **real OCC hole** (a blind write is invisible to a later If-Match write). **Do NOT "fix" it this wave** — bumping on blind writes would make every If-Match caller 412 after any world-map drag. Defer row `D-WORK-BLIND-PATCH-NO-VERSION-BUMP`. |
| **C5** | BE-13a: *"persist to `settings.derivative_name`"* | `WorksRepo.create_derivative` (`repositories/works.py:130-158`) **already takes a `settings: dict \| None` kwarg** and writes it in the INSERT. And `_serialize_resolution` (`works.py:76`) already emits `w.model_dump()` for every candidate — which **includes `settings`**. | BE-13a is ~6 lines, and **`candidates[].settings.derivative_name` needs ZERO extra LIST work.** Only `/derivative-context` needs the new field. |
| **C6** | *"the Beats facet is zero backend work"* | Stronger: `NodeEdit` (`plan-hub/api.ts:118`) **already declares `beat_role`**, and `patchNode` **already sends `If-Match`** with a 412 recovery in `usePlanNodeWrites.onFailed`. | The Beats facet needs **zero api.ts and zero hook work** — it calls the existing `writes.edit(node.id, node.version, { beat_role })`. |
| **C7** | *"ModelPicker → `settings.model_roles.composer`… render each with its effective value + source tier"* | `ModelRole` (`chat-ai-settings/types.ts:41`) **already is** `'chat' \| 'composer' \| 'planner' \| 'embedding' \| 'rerank' \| 'critic'`, and `ModelResolution` already carries `source_tier` + `tier_stack`. | The Composition section reads the inherited/account tier straight off `useChatAiSettingsOptional()?.effective.models[role]`. No new resolution code. |
| **C8** | (the enum baseline) | `contracts/frontend-tools.contract.json` `panel_id.enum` has **57** members at HEAD (verified). Waves 1–5 add **9** (`quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`, `arc-inspector`, `motif-library`, `quality-conformance`, `arc-templates`, `plan-passes`). | 🔴 **Wave 6 starts at 66 and ends at 71 — it adds FIVE, not three** (`style-voice`, `reference-shelf`, `divergence`, **`scene-compose`**, **`chapter-assemble`** — the last two were added when §5.4 homed the orphaned sub-tabs). **NEVER assert a literal.** §6 gives the pre-flight command that COMPUTES `N_before`; the DoD asserts **`N_before + 5 == N_after`** **and** the three-way equality. |
| **C9** | *"TierChip does not throw on an unknown tier"* | Confirmed: `CLS[tier] ?? 'bg-muted…'`, `LABEL[tier] ?? tier`, `TITLE[tier] ?? tier` (`TierChip.tsx:41-49`). An unknown tier ships **looking done** while every chip reads the raw string `scene` in grey. | The M1 test must assert the **LABEL text**, not "it rendered". See `TierChip.test.tsx` in **W6-M1**. |
| **C10** | (the Lane-B pattern) | `registerEffectHandler`'s string branch is `tool === p \|\| tool.startsWith(p)` (`effectRegistry.ts:41`) — **prefix match, not pattern match.** | Every alternation handler **MUST be a `RegExp`.** `registerEffectHandler('composition_(style\|voice)_', …)` would match **nothing** and ship a silent no-op that a self-faking unit test cannot catch. |
| **C11** ⚠ **SUPERSEDED by C12** | BE-21: *"lift the dual-read out of `internal_model_settings.py`"* | `_model_roles_from_settings` returns `{role: {model_ref, model_source}}`. The 6 engine sites destructure **`c_src, c_ref = …`** — **source first, ref second.** | This plan originally mandated a **`(model_ref, model_source)`** tuple — **ref first** — i.e. the *opposite* of the call sites, requiring all 7 to be re-ordered. **The register kills the whole bug class instead. See C12.** |

**C12–C16 — from the adjudication register. These correct THIS PLAN.**

| # | This plan said | The **register** says (settled against source) | Consequence |
|---|---|---|---|
| **C12** | C11: `resolve_model_role` returns a **positional tuple**, and this plan chose `(ref, source)` while the 7 call sites read `(source, ref)`. | 🔴 **`Q-36-BE21-MODEL-ROLES-HAS-NO-READER` + `Q-36-OQ8-BE21-SCOPE-CRITIC-ONLY`: return a `RoleModel` NamedTuple `(model_source, model_ref)` — matching the existing `c_src, c_ref` sites — and precedent-mirror `services/knowledge-service/app/extraction/model_roles.py:32-103`.** Two of this plan's own sources disagreed on the order; a positional contract is the bug. | **NEVER destructure positionally. Access BY NAME** (`_c.model_source` / `_c.model_ref`), exactly as the register's item 3 writes the 7 sites. A NamedTuple accessed by name is order-proof. **W6-BE2 rewritten.** |
| **C13** | §9: **`D-DIVERGENCE-SPEC-EDIT`** — *"UNBUILDABLE on today's backend, needs new write semantics"* (gate #2, structural). | 🔴 **`Q-36-DEFERRED-BE13-DIVERGENCE-SPEC-EDIT`: FALSE.** `packer/pack.py:153-157`'s own docstring: *"the `entity_override[]` is read **FRESH** here on every pack (self-syncing — no cache; **an edited override takes effect on the next pack**)"*. Tables, columns, the `uq_entity_override_work_target` UNIQUE index (`migrate.py:175-176`), the repo write pattern and the EDIT gate **all exist**. *"New write semantics"* means, literally, **an UPDATE statement.** | **BUILD BE-13 in M3. Re-size M → S. Defer row DELETED.** Without it, a user who mistypes a POV anchor must **abandon the derivative and re-derive — losing every drafted chapter** (derive mints a *fresh* knowledge project, `works.py:371`). New slice **W6-BE6**. |
| **C14** | §9: **`D-REF-UPDATE-AND-MODEL-SURFACE`** (BE-17) deferred to v2; `EmbedModelHeader` must **not** name the model *("the `_ref` is NOT exposed by the LIST route")*. | 🔴 **`Q-36-DEFERRED-BE17-REF-UPDATE` + `Q-36-F-EC2-EMBED-MODEL-ONE-WAY-DOOR`: `list_references` ALREADY calls `reference_embed_model(work.settings)` (`references.py:92`) and **throws the `(source, ref)` tuple away** into an `is not None`.** This is not missing infrastructure — it is a **discarded value** (CLAUDE.md anti-laziness rule). The LIST-widen is **~4 lines**; the metadata `PATCH` is ~40. | **BUILD BOTH in M2. Defer row DELETED.** Today, fixing a **typo in a title** means delete + re-add — **a paid provider embed call to fix a typo.** New slice **W6-BE7**. |
| **C15** | §9: **`D-REFERENCES-MCP-TOOLS`** (gate #3) and **`D-DIVERGENCE-MCP-TOOLS`** (gate #2, *"deserves its own confirm design"*). | 🔴 **`Q-36-DEFERRED-REFERENCES-MCP` + `Q-36-DEFERRED-DIVERGENCE-MCP`: both premises refuted.** References: every route exists and **this wave already builds six MCP tools of exactly this shape** in the same file. Divergence: the AN-8 propose→confirm spine is **generic and already carries 11 descriptors** (`actions.py:96`), and an MCP tool path **already mints a knowledge project cross-service** (`mcp/server.py:561-600,583`). Shipping the reference + divergence **GUIs** while leaving their inverse half open, **in the one wave whose job is closing tool↔GUI gaps** (GG-2), is the defect the plan exists to kill. | **BUILD BOTH. Defer rows DELETED.** New slices **W6-BE4b** (4 reference tools) and **W6-BE8** (3 divergence tools). |
| **C16** | §7 + §9: **`D-WAVE6-DISCOVERY-SCENT`** — *"`stream_service.py` is Track C's and is **UNCOMMITTED AND MID-EDIT**. DO NOT TOUCH IT."* Called *"the ONE genuinely-external blocker in the wave."* | 🔴 **`Q-36-DISCOVERY-SCENT-BLOCKED-ON-TRACK-C`: the premise is FALSE at HEAD.** Track C's edits to that file are **committed** (`a23c3f15e`, `fd4702818`, `bac8802c2`, `a95f65378` — all ancestors of HEAD) and `git diff HEAD -- services/chat-service/app/services/stream_service.py` is **empty**. | **The hold is RELEASED. Build X-10 in-wave.** Defer row DELETED. A **dirty file is a wait of minutes** on a one-clause additive change — **never** a defer row. New slice **W6-BE9**. |

---

## 1 · What this wave closes, and its gates

**Panels (5 new — `category: 'editor'` unless noted):**
`style-voice` · `reference-shelf` · `divergence` · 🔴 **`scene-compose`** · 🔴 **`chapter-assemble`**

> 🔴 **`scene-compose` + `chapter-assemble` are NEW to this plan (the reconciliation).** They are **not
> new features** — they are the **homes** for two shipped legacy sub-tabs (`compose` = `ComposeView`,
> `assemble` = `ChapterAssembleView`) that had **no home in any wave**. Without them, M5's GG-4 gate is a
> **green map over a feature being deleted**. See **W6-M6** / **W6-M7** and §4.9.

**Non-panel surfaces (4):** a **Composition section** inside `pages/book-tabs/SettingsTab.tsx` (which
`book-settings` already wraps) · a **Beats facet** + **Decompose action** in `plan-hub`'s `PlanDrawer` ·
🔴 a **canon-at-branch-point view** inside the divergence wizard (M3) · 🔴 a **`CanonAtChapterPanel`
section** inside the existing `scene-inspector` panel (**no new panel id** — see W6-M3 §canonview).

**Gaps closed:** G-STYLE-VOICE (M) · G-REFERENCES-SHELF (S) · G-DIVERGENCE (M) · G-WORK-SETTINGS (S) ·
G-STORY-STRUCTURE (M) · **GG-2 for references + divergence** (the inverse/agent half — C15).

### Hard gates — what must be green BEFORE the first slice starts

🔴 **`Q-36-WAVE0-X1-X5-DEPENDENCY` (VERIFIED AT HEAD): Wave 0 has NOT landed. All five of X-1..X-5 are
still open.** This is a **sequencing fact, not an unknown** — the builder needs no further thought.
**Slice `W6-M0` is the mechanical Wave-0 gate; it runs FIRST.** A FAIL is **unbuilt work you BUILD from
plan 30 §Wave 0** (already fully scoped there) — **NOT a defer row**, and **not a stop-and-ask**
(CLAUDE.md: *"missing infrastructure is unbuilt work"*).

| Gate | Why | Pre-flight check | If RED |
|---|---|---|---|
| **X-1** — `AddModelCta` has a `useOptionalStudioHost()` branch | every new panel's empty state renders a button that **route-navigates and destroys the dock workspace** (DOCK-7) | §2 cmd C | 🔴 **BUILD IT in W6-M0** (one file — `Q-36-M2-ADDMODELCTA-DEPENDS-ON-X1`). Today: **0 hits.** |
| **X-2** — `'quality'` ∈ `CATEGORY_ORDER` | a category not in `CATEGORY_ORDER` gets `indexOf === -1` and silently sorts to the **TOP** of the palette | §2 cmd A | **BUILD IT in W6-M0.** (`editor` is present, so Wave 6's own panels are safe — but the membership assertion is X-2's and this wave's registration test runs it.) |
| **X-3** — `guideBodyKey` assertion in `panelCatalogContract.test.ts` | 5 new panels × silently missing User-Guide copy | §2 cmd B | 🔴 **BUILD IT** (one line). Today: **0 hits.** ⚠ *"just a test"* is the item a builder is most likely to wave through — **treat a FAIL identically to the other four.** |
| **X-4** — Lane-B effect handlers registered for the composition domain | M1's Lane-B DoD has **no machinery to assert against** without it | §2 cmd D | **BUILD IT in W6-M0/M1** — and delete the now-false comment at `useStudioEffectReconciler.ts:6-10`. |
| **X-5** — `ui_show_panel` **RETIRED** from `frontend_tools.py` | PO-3 seals X-5 as a **retirement**, not an enum-add. It is still **always-on with a free-string `panel` arg**, and `studioUiNav.test.ts:109` explicitly asserts it is **NOT** intercepted — i.e. the silent-no-op is a **locked-in behavior**. | §2 cmd K | **BUILD IT in W6-M0** (plan 30 §0 PO-3). |
| **`compositionEffects.ts` exists** (Wave 1 creates it — plan 30 §8.0b) | Wave 6 **EXTENDS** it. Two files for one domain **double-fire** (`matchEffectHandlers` returns EVERY match and `runEffectHandlers` awaits ALL). | §2 cmd D | **CREATE it WHOLE** — Wave 1's two handlers (`/^composition_canon_rule_/`, `/^composition_record_correction$/`) **AND** Wave 6's — in ONE `registerCompositionEffectHandlers()`; register it once in `useStudioEffectReconciler.ts`; close Wave 1's step-8 row as done (`Q-36-COMPOSITIONEFFECTS-EXTEND-NOT-CREATE` (b)). Leave a `// ONE file per domain — do not create a second.` banner. |
| **Wave 1–5 landed** (for the enum baseline) | the count is CUMULATIVE | §2 cmd E | Not a blocker — **assert the DELTA, never a literal** (C8), and **re-measure `N_before` PER MILESTONE**, not per wave (`Q-36-PANEL-COUNT-NEVER-A-LITERAL`). |

### The FIRST commit of this wave (`Q-36-SPEC-APPROVAL-GATE`)

Spec 36 line 3 still reads *"📐 SPEC (written 2026-07-13, PO-approval pending) — buildable. **No
implementation this phase** (plan 30 PO-4)."* **PO-4's specs-first hold is SATISFIED** (specs 31–38 + all
24 HTML drafts are on disk) and the QC adjudication **IS** the gate the PO named. **First commit:** replace
that line with
`"✅ APPROVED 2026-07-13 (QC gate) — BUILDABLE. Wave 6 of plan 30. PO-4's specs-first hold is SATISFIED (31–38 + all drafts on disk) and LIFTED. Approved in FULL — no scope cuts; M4b/BE-20 is IN."`
**Approved in FULL — no scope cuts.**

### What this wave unblocks

🔴 **GG-4.** When M1–M4 **and M6/M7** close, every legacy-only editor-craft capability has a Studio home,
and **only then** may spec 16's `ChapterEditorPage` retirement be *reconsidered*. **M5 ships the MECHANICAL
GUARD** (a parity contract test over **all 25** sub-tabs) — **not the deletion.** §9 OQ-2.

---

## 2 · Pre-flight — run these, paste the output, THEN start

```bash
# ── A · X-2: is 'quality' in CATEGORY_ORDER? (advisory for this wave)
grep -n "CATEGORY_ORDER" -A 4 frontend/src/features/studio/palette/useStudioCommands.ts

# ── B · X-3: does the catalog contract guard guideBodyKey?
grep -n "guideBodyKey" frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts
#    EMPTY ⇒ build the assertion in W6-M1 (see slice).

# ── C · X-1: does AddModelCta have the studio-host branch?
grep -n "useOptionalStudioHost" frontend/src/components/shared/AddModelCta.tsx
#    EMPTY ⇒ reference-shelf keeps the plain warning div (EC-2a). NOT a blocker.

# ── D · the Lane-B home for the composition domain (plan 30 §8.0b)
ls frontend/src/features/studio/agent/handlers/compositionEffects.ts
#    MISSING ⇒ W6-M1 CREATES it + registers it in useStudioEffectReconciler.ts. Never a 2nd file.

# ── E · THE ENUM BASELINE — compute N_before. DO NOT hard-code it.
python -c "import json;print(len(json.load(open('contracts/frontend-tools.contract.json'))['ui_open_studio_panel']['args']['panel_id']['enum']))"
node -e "const{OPENABLE_STUDIO_PANELS}=require('./frontend/src/features/studio/panels/catalog.ts');" 2>/dev/null || \
  grep -c "id: '" frontend/src/features/studio/panels/catalog.ts
#    Record N_before. 🔴 The DoD asserts N_before + 5 == N_after, three-way (FIVE panels — §0 C8).

# ── F · the 12 position-as-identity sites (EC-3c). Expect 11 FE + 1 BE.
grep -rn "candidates\[0\]" frontend/src/features/studio frontend/src/features/composition \
        frontend/src/features/books frontend/src/pages | grep -v "__tests__\|\.test\."
grep -n "rows\[0\]" services/composition-service/app/routers/internal_model_settings.py

# ── G · the 7 critic read sites (BE-21). Expect engine.py 465,529,1029,1099,1261,1345,1643-1644.
grep -rn "critic_model_ref" services/composition-service/app --include=*.py | grep -v test

# ── H · the settings full-blob REPLACE (BE-18)
grep -n "settings = \$" services/composition-service/app/db/repositories/works.py

# ── I · OQ-4 — CLOSED. DO NOT RE-MEASURE. `Q-36-OQ4-REFERENCE-COUNT-N` measured it:
#     reference_source = 0 rows / 0 works / 0 books across 12 composition_work rows, and ZERO works
#     have reference_embed_model_ref set. N = 0. THEREFORE **NO CONSTANT IS HONEST** — baking any
#     number into EC-2a's copy fabricates the very figure the clause exists to make truthful.
#     ⇒ N is **LIVE**: `references.length` from the LIST payload, i18n-pluralized. See W6-M2.
#     (Kept only as provenance; running it again is not a gate.)

# ── J · X-5 (PO-3): is ui_show_panel retired?
grep -n "ui_show_panel" services/chat-service/app/services/frontend_tools.py
#    PASS = 0 hits. Today: :52 (always-on list), :339 (tool def), :655 (registry) ⇒ BUILD X-5 in W6-M0.

# ── K · the discovery-scent file — is it REALLY dirty? (C16: the "blocked on Track C" claim was FALSE)
git status --short services/chat-service/app/services/stream_service.py
git diff HEAD -- services/chat-service/app/services/stream_service.py | head -1
#    EMPTY ⇒ edit it (W6-BE9). Non-empty ⇒ pull/rebase and re-check. A dirty file is a wait of
#    MINUTES on a one-clause additive change — it is NEVER a defer row.

# ── L · the CONTRACT (JOB 2 — contract-first). Which composition routes are already specced?
grep -n "^  /" contracts/api/composition/v1/openapi.yaml
#    17 paths at HEAD. style/voice, references, derive, derivative-context, divergence-spec,
#    overrides, decompose are ALL ABSENT ⇒ W6-C0 adds them BEFORE any FE slice consumes them.

# ── M · baseline green (record the counts — the DoD compares against them)
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3
cd services/chat-service      && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3
cd frontend                   && npx vitest run 2>&1 | tail -5
```

**Do NOT start a slice until §2 M is green.** A pre-existing red suite makes every DoD below a lie.

---

## 3 · Backend prerequisite slices (FIRST — a panel slice may not precede its route slice)

### **W6-M0** — the Wave-0 gate (X-1..X-5) 🔴 **RUNS BEFORE EVERYTHING**
**Kind:** FS · **dependsOn:** — · Source: `Q-36-WAVE0-X1-X5-DEPENDENCY` · `Q-36-M2-ADDMODELCTA-DEPENDS-ON-X1`

> **Verified at HEAD: Wave 0 is 0/5.** Do **not** trust a handoff line or a doc note claiming otherwise —
> **re-run the greps** (§2 cmds A–D, J). *This repo has twice had a "blocked on the missing route" item
> that already existed; here the inverse is true — the plan describes Wave 0 as near-done and it is 0/5.*
> Each item is **fully scoped in plan 30 §Wave 0**. Build it; do **not** write a defer row.

| Item | The change | The PASS check |
|---|---|---|
| **X-1** | `frontend/src/components/shared/AddModelCta.tsx` — add `useOptionalStudioHost()`. `host !== null` ⇒ render a `<button onClick={() => host.openPanel('settings', { params: { tab: 'providers' } })}>` with the **same** label/`<Plus/>`/className per variant. `host === null` ⇒ the existing `<Link to={to}>` **verbatim** (classic pages still need the `?return=` round-trip). ⚠ **`{ params: { tab } }` — `StudioHostProvider.tsx:77-94` forwards ONLY `opts.params`; `{ tab }` at the opts top level is a SILENT NO-OP.** **Fix at the shared component, NOT the ~8 call sites.** | `AddModelCta.test.tsx`: inside a `StudioHostProvider` ⇒ click calls `openPanel('settings', { params: { tab: 'providers' } })` **AND `container.querySelector('a[href]')` is `null`** (the anti-teardown assertion). Outside ⇒ still an `<a href="/settings/providers?return=…">`. |
| **X-1 fix-now** (same seam, 1 line) | `frontend/src/features/studio/host/studioLinks.ts:111` has **exactly that bug**: `openPanel('settings', settings[1] ? { tab: settings[1] } : undefined)` → must be `{ params: { tab: settings[1] } }`, else a `/settings/providers` studio link opens the panel on `account`. | a `studioLinks` unit test asserting the `params` wrapper. |
| **X-2** | add `'quality'` to `CATEGORY_ORDER` (`useStudioCommands.ts:20-22` — 9 entries; `catalog.ts:81-91` defines **10**). | `panelCatalogContract.test.ts` gains `CATEGORY_ORDER.includes(p.category)` for every openable panel. |
| **X-3** | `panelCatalogContract.test.ts` gains `it('every openable panel has a guideBodyKey')`. **Plus** (`Q-36-I18N-17-LOCALES`, mandated): a case that **reads `i18n/locales/en/studio.json` and asserts every catalog `titleKey`/`descKey`/`guideBodyKey` RESOLVES to a non-empty string** — nothing asserts this today, so a typo'd key ships as the raw string `panels.style-voice.title` in the palette. | both `it()`s green. |
| **X-4** | register the composition-domain Lane-B handlers (see the `compositionEffects.ts` gate above) **and delete the false comment at `useStudioEffectReconciler.ts:6-10`**, which claims the registered handlers cover the space. | `matchEffectHandlers('composition_canon_rule_create').length >= 1`. |
| **X-5** | **RETIRE `ui_show_panel`** (plan 30 §0 **PO-3** — a retirement, **not** an enum-add): remove it from `frontend_tools.py:52` (always-on), `:339` (tool def), `:655` (registry); migrate its callers to `ui_open_studio_panel`; **invert `studioUiNav.test.ts:106-109`** (it currently asserts the silent-no-op is *correct*). | §2 cmd J returns **0 hits**; the frontend-tools contract regenerates green. |

**DoD evidence:** `"W6-M0: X-1..X-5 all green — AddModelCta.test.tsx asserts openPanel({params:{tab:'providers'}}) AND zero <a href> in the dock; studioLinks params-wrapper test green; grep 'ui_show_panel' frontend_tools.py = 0 hits; matchEffectHandlers('composition_canon_rule_create').length === 1"`

---

### **W6-C0** — 🔴 **CONTRACT FIRST** — freeze the OpenAPI before any FE flow
**Kind:** BE (contract) · **dependsOn:** — · **RUNS BEFORE EVERY FE SLICE**

> **CLAUDE.md, non-negotiable: "Contract-first: API contract frozen before frontend flow."**
> This plan originally added ~7 routes and touched **zero** contract files. That is a `/review-impl`
> finding, not an oversight to absorb.

**THE FILE — verified, do not guess:**
🔴 **`contracts/api/composition/v1/openapi.yaml`** — a live, maintained spec (**498 lines, 17 paths** at
HEAD, already carrying `/works/{project_id}`, `/canon-rules/{rule_id}`, `/templates`,
`/outline/nodes/{node_id}`). **This is Wave 6's file.**
⚠ **`contracts/api/composition-service/plan-forge.v1.yaml` is a DIFFERENT file — that is Wave 5's.
Do not write into it.**
⚠ There is **no `contracts/api/book-service/`** (Wave 8's plan names one; it does not exist). Not this
wave's problem, but do not create it.

**Add these to `contracts/api/composition/v1/openapi.yaml` — path · method · request schema · response
schema · error codes. Every one is consumed by an FE slice in this wave.**

| # | METHOD + path | Status | Slice that consumes it |
|---|---|---|---|
| 1 | `GET /works/{project_id}/style-profiles` → `{items: StyleProfile[]}` · 404 · 403 | exists in code, **absent from the spec** | W6-M1 |
| 2 | `PUT /works/{project_id}/style-profile` ← `{scope_type: enum[work,chapter,scene], scope_id, density: 0..100, pace: 0..100}` → `StyleProfile` · 404 · 403 · 422 | ″ | W6-M1 |
| 3 | `DELETE /works/{project_id}/style-profile?scope_type&scope_id` → `{removed: bool}` · 404 · 403 | ″ | W6-M1 |
| 4 | `GET\|PUT /works/{project_id}/voice-profiles` · `DELETE /works/{project_id}/voice-profiles/{entity_id}` ← `{entity_id, entity_name: 1..200, tags: ≤20 × 1..40}` | ″ | W6-M1 |
| 5 | `GET /works/{project_id}/references` → 🔴 **`{references[], embed_model_set, reference_embed_model_ref, reference_embed_model_source}`** — **the last two are NEW (BE-17a)** | **CHANGED** | W6-BE7 · W6-M2 |
| 6 | `POST /works/{project_id}/references` ← `{content: ≤20000, title?, author?, source_url?, model_ref?, model_source?}` · 422 `REFERENCE_EMBED_MODEL_UNSET` · 502 `REFERENCE_EMBED_FAILED` | exists in code, absent from spec | W6-M2 |
| 7 | 🔴 **`PATCH /references/{reference_id}`** ← `{title?, author?, source_url?}` (`extra: forbid`) → `ReferenceSource` · **422 on `content`** · 404 | **NEW (BE-17b)** | W6-BE7 · W6-M2 |
| 8 | `DELETE /references/{reference_id}` → `{id, deleted: true}` · 404 | exists, absent | W6-M2 |
| 9 | `GET /works/{project_id}/scenes/{node_id}/references?q&limit` → `{hits[], embed_model_set, unavailable?}` | ″ | W6-M2 |
| 10 | `PATCH /works/{project_id}` + `If-Match` ← 🔴 **`{settings?, settings_unset?: string[] (≤32), status?, active_template_id?}`** — **`settings_unset` is NEW (BE-18)**; document that `settings` is now a **SHALLOW MERGE**, not a replace · 412 `WORK_VERSION_CONFLICT` (+`current`) · **404 on a foreign/System `active_template_id`** | **CHANGED** | W6-BE1 · W6-M4a |
| 11 | `POST /works/{project_id}/derive` ← 🔴 **`{name: str (1..200, REQUIRED), branch_point?, divergence{taxonomy, pov_anchor?, canon_rule[]}, entity_overrides[]}`** · **422 on a missing/whitespace name** · 409 `SOURCE_WORK_NOT_BACKED` · 502 `BOOK_SERVICE_UNAVAILABLE`/`PROJECT_CREATE_FAILED` · **503 `PROJECT_CREATE_UNAVAILABLE`** | **CHANGED (BE-13a)** | W6-BE3 · W6-M3 |
| 12 | `GET /works/{project_id}/derivative-context` → 🔴 **+ `derivative_name: str\|null`** | **CHANGED (BE-13a)** | W6-BE3 · W6-M3 |
| 13 | 🔴 **`PATCH /works/{project_id}/divergence-spec`** ← `{taxonomy?, pov_anchor?: uuid\|null, canon_rule?: string[]}` (an **explicit `null` CLEARS**; an **omitted key preserves**) → `DivergenceSpec` · 409 `NOT_A_DERIVATIVE` · 409 `WORK_NOT_BACKED` · 404 | **NEW (BE-13)** | W6-BE6 · W6-M3 |
| 14 | 🔴 **`PUT /works/{project_id}/overrides/{target_entity_id}`** ← `{overridden_fields: object}` → `EntityOverride` · 409 · 404 · **`DELETE` → 404 when 0 rows matched (never a silent 204)** | **NEW (BE-13)** | W6-BE6 · W6-M3 |
| 15 | `POST /works/{project_id}/outline/decompose` ← 🔴 **`structure_template_id` becomes `UUID \| None`** (falls back to `work.active_template_id`) · **NEW 400 `NO_STRUCTURE_TEMPLATE`** · 400 `NO_CHAPTERS`/`TOO_MANY_CHAPTERS` | **CHANGED (EC-5)** | W6-M4b |
| 16 | `POST /works/{project_id}/outline/decompose/commit` ← 🔴 **`CommitRequest` gains `structure_template_id?`** (the write-back) · **409 `CHAPTER_ALREADY_PLANNED`** (⚠ **409, not 400** — `plan.py:734-739`; spec 36 says 400 and is **wrong**) · 400 `EMPTY_DECOMPOSE_PLAN` | **CHANGED (EC-5)** | W6-M4b |
| 17 | `GET /actions/preview?token=` · `POST /actions/confirm?token=` → `{outcome, descriptor, job_id, poll}` · **402 quota** · 409 `already_consumed` · 410 expired · 400 `action_error` | exists in code, absent from spec | W6-BE5 · W6-M4b |

**Rules for the edit**
- **Additive only.** Do not renumber or re-key an existing path. Mirror the file's existing style
  (`components/schemas`, `bearerAuth`, the `/v1/composition` server prefix — **paths are relative to it**).
- **Every closed set is an `enum`** — `scope_type`, `taxonomy`, `assembly_mode`. A free string here is the
  Frontend-Tool-Contract bug class one layer down.
- **Every error code above appears in the spec's `responses`.** An error the FE renders and the contract
  does not name is a contract that lies.

**Test / DoD** — a contract is only real if a machine checks it:
```bash
npx @redocly/cli lint contracts/api/composition/v1/openapi.yaml   # 0 errors
python -c "import yaml,sys; d=yaml.safe_load(open('contracts/api/composition/v1/openapi.yaml')); \
p=d['paths']; req=['/works/{project_id}/style-profiles','/works/{project_id}/style-profile', \
'/works/{project_id}/voice-profiles','/works/{project_id}/references','/references/{reference_id}', \
'/works/{project_id}/derive','/works/{project_id}/derivative-context', \
'/works/{project_id}/divergence-spec','/works/{project_id}/overrides/{target_entity_id}']; \
missing=[r for r in req if r not in p]; sys.exit('MISSING: '+str(missing) if missing else 0)"
```
Wire that assertion into `services/composition-service/tests/unit/test_openapi_contract.py`
(`pytestmark = pytest.mark.xdist_group("pg")` is **not** needed — it reads a file) so a route added to the
router without a contract row **reds**.

**DoD evidence:** `"W6-C0: redocly lint = 0 errors · contracts/api/composition/v1/openapi.yaml now carries 9 new paths + 4 changed schemas (settings_unset, derive.name, derivative_name, structure_template_id write-back) · test_openapi_contract.py: 1 passed (every Wave-6 route is specced)"`

---

### Route contract table — what EXISTS vs what we BUILD

| # | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|
| — | `GET /v1/composition/works/{pid}/style-profiles` | — | `{items:[{created_by,project_id,scope_type,scope_id,density,pace,updated_at}]}` | 404 no-work/no-grant · 403 under-tier | ✅ **EXISTS** (`style_voice.py:60`) |
| — | `PUT /v1/composition/works/{pid}/style-profile` | `{scope_type:'work'\|'chapter'\|'scene', scope_id:UUID, density:0-100, pace:0-100}` | the row | 404 · 403 · 422 range | ✅ **EXISTS** (`:73`, upsert on `(project_id,scope_type,scope_id)`) |
| — | `DELETE /v1/composition/works/{pid}/style-profile?scope_type=&scope_id=` | query | `{removed:bool}` | 404 · 403 | ✅ **EXISTS** (`:89`) |
| — | `GET\|PUT /v1/composition/works/{pid}/voice-profiles` · `DELETE …/voice-profiles/{entity_id}` | `{entity_id, entity_name(1..200), tags[≤20, each 1..40]}` | the row / `{removed}` | as above | ✅ **EXISTS** (`:113,126,142`) |
| — | `GET\|POST /v1/composition/works/{pid}/references` · `DELETE /v1/composition/references/{rid}` · `GET /v1/composition/works/{pid}/scenes/{nid}/references?q&limit` | see `references.py:49` | `{references[], embed_model_set}` / `{hits[], embed_model_set, unavailable?}` | 422 `REFERENCE_EMBED_MODEL_UNSET` · 502 `REFERENCE_EMBED_FAILED` | ✅ **EXISTS** |
| — | `GET /v1/composition/books/{bid}/work` | — | `{status, work, candidates[], book_project_id}` — **`candidates[]` already carries `settings` + `source_work_id` + `branch_point`** | — | ✅ **EXISTS** (`works.py:131`) |
| — | `GET /v1/composition/works/{pid}/derivative-context` | — | `{is_derivative, source_work_id, source_project_id, branch_point, taxonomy, pov_anchor, canon_rules[], overrides[]}` | 404 · 403 | ✅ **EXISTS** (`works.py:443`) |
| — | `PATCH /v1/composition/works/{pid}` + `If-Match: <version>` | `{active_template_id?, status?, settings?}` | Work | 412 `WORK_VERSION_CONFLICT` (+ `current`) · 404 · 403 · 400 bad If-Match · 422 bad `assembly_mode` | ✅ **EXISTS** (`works.py:581`) |
| — | `POST /v1/composition/works/{pid}/derive` | `{branch_point?, divergence{taxonomy,pov_anchor,canon_rule[]}, entity_overrides[]}` | Work (201) | 409 `SOURCE_WORK_NOT_BACKED` · 502 `BOOK_SERVICE_UNAVAILABLE`/`PROJECT_CREATE_FAILED` · **503 `PROJECT_CREATE_UNAVAILABLE`** | ✅ **EXISTS** (`works.py:310`) |
| — | `GET /v1/composition/templates` | — | `{templates:[{id, owner_user_id, name, kind, beats[]}]}` | — | ✅ **EXISTS** (`canon.py:192`) |
| — | `PATCH /v1/composition/outline/nodes/{id}` + `If-Match` | `{beat_role?…}` | the whole node | 412 `NODE_VERSION_CONFLICT` | ✅ **EXISTS** (`outline.py:88`) |
| — | `POST /v1/composition/works/{pid}/outline/decompose` · `…/decompose/commit` | `DecomposeRequest` / `CommitRequest` | inline plan **or** 202+`job_id` | 400 `NO_CHAPTERS`/`TOO_MANY_CHAPTERS`/`EMPTY_DECOMPOSE_PLAN`/already-planned · 404 template | ✅ **EXISTS** (`plan.py:488,647`) — ⚠ **no cost gate** (F-EC6) |
| **BE-18** | `PATCH /v1/composition/works/{pid}` — **shallow-merge `settings`** + new `settings_unset: list[str]` + 🔴 **the `active_template_id` tenancy check** | — | — | **404** on a foreign/System template id | 🔨 **BUILD** — W6-BE1 |
| **BE-21** | `resolve_model_role(settings, role) -> RoleModel(model_source, model_ref) \| None` + all 7 engine `critic` sites read it **BY NAME** (C12) | — | — | — | 🔨 **BUILD** — W6-BE2 · **HARD PREREQ of M4a** |
| **BE-13a** | `POST /derive` gains **`name: str (1..200), REQUIRED`** → `settings.derivative_name`; `/derivative-context` returns `derivative_name` | — | — | **422** missing/whitespace name | 🔨 **BUILD** — W6-BE3 · **HARD PREREQ of M3** |
| **BE-10** | 6 MCP tools: `composition_style_{list,upsert,delete}` · `composition_voice_{list,upsert,delete}` — 🔴 **lists are Tier-R, writes Tier-A** | MCP | the row + `_meta.undo_hint` | uniform `not_accessible` | 🔨 **BUILD** — W6-BE4 |
| 🔴 **BE-10b** | 4 MCP tools: `composition_reference_{list,add,delete,search}` — **C15, un-deferred** | MCP | the row + `_meta.undo_hint` | structured refusal `reference_embed_model_unset` | 🔨 **BUILD** — W6-BE4b |
| **BE-20** | MCP `composition_decompose` (Tier-W) + `composition_decompose_commit` (Tier-A) + descriptor `composition.decompose` + `_execute_decompose` | MCP | `{confirm_token, descriptor, estimate}` → `{outcome:"action_accepted", job_id, poll: "composition_get_generation_job"}` | 402 quota · 400 `action_error` · 409 `already_consumed` | 🔨 **BUILD** — W6-BE5 · **gates M4b ONLY** |
| 🔴 **BE-13** | `PATCH /works/{pid}/divergence-spec` · `PUT\|DELETE /works/{pid}/overrides/{eid}` — **C13, un-deferred, size S** | see W6-C0 #13-14 | the row | 409 `NOT_A_DERIVATIVE` · 409 `WORK_NOT_BACKED` · 404 | 🔨 **BUILD** — W6-BE6 · **HARD PREREQ of M3's spec section** |
| 🔴 **BE-17** | `GET /references` **widened** (+`reference_embed_model_ref/_source`) · **`PATCH /references/{rid}`** (metadata only, **NO re-embed**) — **C14, un-deferred** | see W6-C0 #5,7 | the row | 422 on `content` | 🔨 **BUILD** — W6-BE7 · **HARD PREREQ of M2's header** |
| 🔴 **M6-D** | 3 MCP tools: `composition_list_derivatives` (R) · `composition_derivative_context` (R) · `composition_derive_work` (**W, propose→confirm, NO cost gate — derive makes ZERO LLM calls**) — **C15, un-deferred** | MCP | `{confirm_token, …}` → `{outcome:"action_done", project_id, work}` | 403 on a revoked grant · 503 `PROJECT_CREATE_UNAVAILABLE` | 🔨 **BUILD** — W6-BE8 |
| 🔴 **X-10** | the **discovery scent** — ONE clause in `stream_service.py`'s `book_context_note` — **C16, hold RELEASED** | — | — | — | 🔨 **BUILD** — W6-BE9 |
| 🔴 **EC-5** | `DecomposeRequest.structure_template_id` → `UUID \| None` (falls back to `work.active_template_id`); `CommitRequest` gains `structure_template_id?` (the **write-back on commit**) | — | — | **400 `NO_STRUCTURE_TEMPLATE`** | 🔨 **BUILD** — W6-BE5 · W6-M4b |

**Gateway:** every `/v1/composition/*` route is auto-proxied (`gateway-setup.ts:354`,
`pathFilter: p => p.startsWith('/v1/composition')`, **no rewrite**). **ZERO gateway work** — with **ONE**
exception: `FE_BRIDGE_TOOL_ALLOWLIST` gains `composition_decompose` (W6-BE5), which makes **M4b
cross-service ⇒ live-smoke MANDATORY** (`Q-36-BE20-MCPEXECUTE-ALLOWLIST`).

---

### **W6-BE1** — BE-18: close the settings lost-update window
**Kind:** BE · **dependsOn:** —

**Files**
| File | Change |
|---|---|
| `services/composition-service/app/db/repositories/works.py` | `update()` — the `settings` branch |
| `services/composition-service/app/routers/works.py` | `WorkPatch` + `patch_work` |
| `services/composition-service/tests/unit/test_works_repo_settings_merge.py` | **NEW** |
| `frontend/src/features/composition/api.ts` | `patchWork` signature |

**The change (BE)**

1. `repositories/works.py`, in `update()`, replace the settings SET clause (currently line ~311):
   ```python
   # BEFORE:  params.append(json.dumps(value)); set_clauses.append(f"settings = ${len(params)}::jsonb")
   # AFTER — BE-18. A full-blob REPLACE is a lost-update window: two panels saving two
   # different keys means the second read-modify-write silently reverts the first. The
   # server-side SHALLOW merge closes it and is behaviour-preserving (every FE caller
   # already sends the hand-merged blob). Shallow ⇒ useWorldMap's whole-`world_map`-key
   # replace still deletes sub-keys correctly, which a DEEP merge would break.
   if field == "settings":
       params.append(json.dumps(value))
       set_clauses.append(
           f"settings = COALESCE(settings, '{{}}'::jsonb) || ${len(params)}::jsonb"
       )
   ```
2. Add key REMOVAL (a merge can no longer delete a key):
   - add `settings_unset: list[str] | None = None` to `WorkPatch` (`routers/works.py:59`), with a
     `field_validator` capping it at 32 entries of ≤64 chars each (a runaway client must not build a
     giant SQL expression).
   - `patch_work` must **pop it before calling `works.update()`** — `_UPDATABLE_COLUMNS` is a frozenset
     of real columns and passing `settings_unset` raises `ValueError: field not updatable`. Thread it as
     a **new kwarg**:
     ```python
     patch_dict = patch.model_dump(exclude_unset=True)
     unset = patch_dict.pop("settings_unset", None)
     updated = await works.update(project_id, patch_dict, created_by=user_id,
                                  expected_version=expected_version, settings_unset=unset)
     ```
   - `WorksRepo.update(..., settings_unset: list[str] | None = None)` — when present, append
     `settings = settings - $n::text[]` to `set_clauses` **AFTER** the merge clause (order matters:
     merge-then-unset, so `{"settings": {...}, "settings_unset": [...]}` in one call is well-defined),
     and **treat a non-empty `settings_unset` as a non-empty patch** so the `if not updates: return
     await self.get(...)` early-return does not swallow an unset-only call.
3. **Do NOT touch the version-bump logic.** C4: a blind write does not bump `version`. Leave it —
   changing it 412s every If-Match caller after any world-map drag. Defer row filed (§9).

4. 🔴 **THE TENANCY HOLE — FIX IT HERE** (`Q-36-EC5-ACTIVE-TEMPLATE-ID-WRITE-ONLY` item 3; the register
   found this, the spec never asked for it). `patch_work` (`routers/works.py:581`) currently stamps **ANY**
   uuid into `active_template_id` **with zero validation** — so **user A can stamp user B's private
   template id into their own Work**. Add `templates: StructureTemplatesRepo =
   Depends(get_structure_templates_repo)` and, right after `patch_dict = patch.model_dump(exclude_unset=True)`
   (`works.py:598`):
   ```python
   # TENANCY (CLAUDE.md User Boundaries): active_template_id is a FK to a row that is either
   # System-tier (owner_user_id IS NULL) or the caller's own. StructureTemplatesRepo.get() is the
   # existing System-or-own gate — reuse it; do NOT re-derive the predicate.
   tid = patch_dict.get("active_template_id")
   if tid is not None and await templates.get(user_id, tid) is None:
       raise HTTPException(status_code=404, detail="structure template not found")
   ```
   An explicit `null` still **clears** it (it is in `_NULLABLE_UPDATE_COLUMNS`, `works.py:46`) — do not
   gate the null path.
   **Test (mandatory, in this slice):** `test_patch_with_another_users_private_template_404s` — user A
   PATCHes `active_template_id` = user B's private template ⇒ **404**, and the column is **unchanged**.

**The change (FE — the `ifMatch` half, PER CALL SITE, never blanket — EC-4b)**

`frontend/src/features/composition/api.ts:443`:
```ts
// EC-4b: If-Match is OPT-IN per call site. `patchWork` is a SHARED writer over a VERSIONED
// row with 5 call sites, one of which (useWorldMap → node drag) is an instant-commit control.
// A blanket If-Match here makes the world-map drag self-412 against its own previous write —
// the `instant-commit-control-over-occ-entity-needs-write-serialization` memory, verbatim.
// Required for: the Composition section's save + the divergence archive (human-paced,
// conflict-meaningful). NOT for useWorldMap — BE-18's merge already closes its lost-update
// window, and a 412 mid-drag is a worse bug than the one it fixes.
// Any call site that DOES adopt ifMatch must CHAIN its writes and RE-SEED `version` from the
// response. Key removal is `settings_unset: [key]`, NEVER a blob replace.
patchWork(
  projectId: string,
  patch: { settings?: Record<string, unknown>; settings_unset?: string[]; status?: string; active_template_id?: string | null },
  token: string,
  opts?: { ifMatch?: number },
): Promise<Work> {
  return apiJson(`${BASE}/works/${projectId}`, {
    method: 'PATCH', token, body: JSON.stringify(patch),
    ...(opts?.ifMatch !== undefined ? { headers: { 'If-Match': String(opts.ifMatch) } } : {}),
  });
}
```
**Change no existing caller.** `useChapterAssembly`, `useProgress`, `useSetWorkSettings` keep their
hand-merge and stay blind. (The hand-merge is now redundant but harmless — removing it is a separate
cleanup and would widen this slice's blast radius for zero behaviour gain.)

**Tests** — `services/composition-service/tests/unit/test_works_repo_settings_merge.py` (**NEW**; hits the
real dev DB ⇒ `pytestmark = pytest.mark.xdist_group("pg")`):
- `test_two_patches_to_different_keys_both_survive` — seed `{}`; PATCH `{settings:{a:1}}`; PATCH
  `{settings:{b:2}}`; assert the row is `{a:1, b:2}`. **This test REDS before the change** (it would be
  `{b:2}`) — write it first.
- `test_settings_unset_removes_a_key` — seed `{a:1,b:2}`; PATCH `{settings_unset:["a"]}` ⇒ `{b:2}`.
- `test_settings_and_unset_in_one_call_merges_then_unsets` — seed `{a:1}`; PATCH
  `{settings:{b:2}, settings_unset:["a"]}` ⇒ `{b:2}`.
- `test_whole_subkey_replace_still_deletes_subkeys` — seed `{world_map:{positions:{p1:1}, backdrop:"x"}}`;
  PATCH `{settings:{world_map:{positions:{p1:2}}}}` ⇒ `world_map` is `{positions:{p1:2}}` (**no**
  `backdrop`). *The shallow-merge guard: a DEEP merge would fail this and silently resurrect `backdrop`.*
- `test_stale_if_match_412s_and_returns_current` — PATCH with `If-Match: <old>` ⇒ 412 +
  `detail.code == "WORK_VERSION_CONFLICT"` + `detail.current.version`.
- `test_settings_unset_over_32_keys_422s`.

**DoD evidence:** `"test_works_repo_settings_merge.py: 6 passed — incl. test_two_patches_to_different_keys_both_survive (RED before the merge, GREEN after) and test_whole_subkey_replace_still_deletes_subkeys"`

---

### **W6-BE2** — BE-21: make composition-service's engine READ `model_roles` 🔴
**Kind:** BE · **dependsOn:** — · **HARD PREREQUISITE of M4a**

> **Why this exists.** `grep -rn "model_roles" services/composition-service/app` → **`internal_model_settings.py`
> and NOTHING else.** That file is a `/internal` route serving **chat-service's** cascade. composition-service's
> **own engine** reads the legacy scalar `critic_model_ref` **directly off the blob at 7 sites.** A Composition
> section that writes only `settings.model_roles.critic` leaves all 7 reading `None` → *"critique skipped: no
> distinct critic model configured"* — **forever** — while the GUI renders *"critic: gpt-4o · book"*. That is
> `silent-success-is-a-bug` / stored-but-unread, shipped by the very spec that cites the rule. **The fix is NOT
> "write both keys"** — that is two homes (SET-8 again). `model_roles` becomes the ONE home; the legacy scalar
> becomes the read-fallback shim.

**Files**
| File | Change |
|---|---|
| `services/composition-service/app/services/model_roles.py` | **NEW** |
| `services/composition-service/app/routers/internal_model_settings.py` | import the lifted helper; delete the local copy |
| `services/composition-service/app/routers/engine.py` | 7 read sites |
| `services/composition-service/tests/unit/test_model_roles_resolver.py` | **NEW** |
| `services/composition-service/tests/unit/test_engine_critic_reads_model_roles.py` | **NEW** |

**The change**

1. **NEW** `app/services/model_roles.py`:
   ```python
   """BE-21 — the ONE home of the Work's per-role model resolution (SET-8).

   `work.settings.model_roles.<role>` is the one home; the legacy scalars
   (`default_model_ref` → role `chat`, `critic_model_ref` → role `critic`) are a
   READ-FALLBACK SHIM for pre-Wave-6 books, never a second write target.

   This is the SAME dual-read `internal_model_settings._model_roles_from_settings`
   already performs — LIFTED, not copied. Two copies of a resolution rule is how the
   `css-var-duplicated-across-two-consumers-drifts` class gets re-shipped.

   🔴 C12 — NEVER DESTRUCTURE THIS POSITIONALLY. Return a NamedTuple and read it BY
   NAME (`rm.model_source` / `rm.model_ref`). Two of this plan's own sources disagreed
   on whether the order was (ref, source) or (source, ref) — a positional contract IS
   the bug, and it type-checks nowhere. Field order below matches the engine's existing
   `c_src, c_ref` sites, but no call site may rely on that.

   Precedent to mirror verbatim: services/knowledge-service/app/extraction/model_roles.py:32-103.
   """
   from __future__ import annotations
   from typing import Any, Mapping, NamedTuple

   _LEGACY_SCALAR: dict[str, tuple[str, str]] = {
       "chat":   ("default_model_ref", "default_model_source"),
       "critic": ("critic_model_ref",  "critic_model_source"),
   }

   def model_roles_from_settings(settings: dict[str, Any]) -> dict[str, dict[str, str]]:
       """The per-role map (new `model_roles` ▸ legacy scalars). Only well-formed
       {model_ref[, model_source]} entries survive. Verbatim behaviour of the former
       `internal_model_settings._model_roles_from_settings`."""
       roles: dict[str, dict[str, str]] = {}
       existing = settings.get("model_roles")
       if isinstance(existing, dict):
           for role, val in existing.items():
               if isinstance(val, dict) and val.get("model_ref"):
                   roles[role] = {
                       "model_ref": str(val["model_ref"]),
                       "model_source": val.get("model_source") or "user_model",
                   }
       for role, (ref_key, src_key) in _LEGACY_SCALAR.items():
           v = settings.get(ref_key)
           if v and role not in roles:
               roles[role] = {"model_ref": str(v),
                              "model_source": settings.get(src_key) or "user_model"}
       return roles

   class RoleModel(NamedTuple):
       model_source: str
       model_ref: str

   def resolve_model_role(
       settings: Mapping[str, Any] | None, role: str,
   ) -> RoleModel | None:
       """One role's model — `settings.model_roles.<role>` WINS; the legacy scalar is the
       fallback rung. `None` when unset at every layer. ONE HOME (SET-8).

       ⚠ `model_source` DEFAULTS to "user_model" when the map entry omits it — mirroring
       internal_model_settings.py:56. The gate at engine.py:1649 fails on a missing
       `critic_src` just as hard as on a missing ref, and the shipped drafter picker
       writes a BARE ref with no `_source`. A resolver that returned source=None here
       would silently re-trigger "critique skipped" and look like BE-21 never landed.
       (Q-36-CRITIC-SKIPPED-UNLESS-DISTINCT (C).)
       """
       entry = model_roles_from_settings(dict(settings or {})).get(role)
       if not entry:
           return None
       return RoleModel(entry["model_source"], entry["model_ref"])
   ```
2. `routers/internal_model_settings.py`: **delete** `_model_roles_from_settings`, add
   `from app.services.model_roles import model_roles_from_settings`; the route body becomes
   `return {"model_roles": model_roles_from_settings(settings)}`. **Behaviour must be byte-identical**
   — its existing tests (`test_internal_model_settings.py`) are the regression guard for the LIFT;
   they must stay green **UNCHANGED**. Do not touch them.
   🔴 **ONE-LINE ADDITIVE COMPANION** (`Q-36-DEFERRED-MODEL-ROLES-DEFAULT-REF` item 4): have the legacy
   `default_model_ref` fill **BOTH `chat` AND `composer`** when the map sets neither. The user's *"Default
   drafter model"* **IS** the book's composer; today book-tier `composer` is always empty, so chat-service
   (`settings_resolution.ModelRole.COMPOSER`) falls through to the account tier and the book setting is
   **invisible** to it. Back-compat-safe. Extend that file's test: *legacy scalar fills `chat` AND
   `composer`; an explicit `model_roles.composer` wins over it.*
3. `routers/engine.py` — **all 7 sites.** Add `from app.services.model_roles import resolve_model_role`.
   🔴 **READ BY NAME. NEVER POSITIONALLY** (C12).
   - **Six identical sites** (`465, 529, 1029, 1099, 1261, 1345`) currently read:
     ```python
     c_src, c_ref = sdict.get("critic_model_source"), sdict.get("critic_model_ref")
     ```
     → replace **each** with:
     ```python
     _c = resolve_model_role(sdict, "critic")
     c_src, c_ref = (_c.model_source, _c.model_ref) if _c else (None, None)
     ```
     Leave the following `distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))` line
     **byte-identical**. The sites **diverge downstream** (529 falls back to the drafter as judge; 1345
     passes `None`) — that behaviour must not change.
     ⚠ **Do NOT use `replace_all`** — verify each of the six by line number; the memory
     `stream-service-has-three-terminal-usage-yields` is exactly this class.
   - **The 7th site** (`1643-1644`, the "critique skipped" gate) reads `settings_dict`:
     ```python
     _c = resolve_model_role(settings_dict, "critic")
     critic_src = _c.model_source if _c else None
     critic_ref = _c.model_ref if _c else None
     ```
     The gate at `:1649` stays **byte-identical** — anti-self-reinforcement stands. (The `not critic_src`
     arm becomes dead-but-harmless since the helper defaults the source; **keep it defensively — do not
     "simplify" the gate.**)
   - **Re-point ONLY the `critic` sites** (OQ-8) — and note **there is nothing else to re-point in this
     service**: `composer` is taken **per-call** as `body.model_ref`, and `planner` resolves from
     provider-registry's pinned default (`plan_forge_service.py:127`), **never** from `work.settings`.
   - 🔴 **`Q-36-BE21-MODEL-ROLES-HAS-NO-READER` items 4-5 — TWO SITES THAT ARE *NOT* 8th SITES:**
     - **Do NOT touch the worker.** `worker/operations.py:291,349-350,471-472` reads
       `input["critic_source"/"critic_ref"]`, which the **router** writes into `job_input` at sites
       465/1029/1261 — **the 7-site fix propagates to every worker path for free.** Blast radius is
       `engine.py` only.
     - **Do NOT touch `services/authoring_run_service.py:574`.** It reads `params.get("critic_model_ref")`
       — the caller-supplied **RUN-PARAMS tier** (fed by `routers/authoring_runs.py:145`,
       `mcp/server.py:3619`), **not** `work.settings`. A different tier. **It is NOT an 8th site.**
   - 🔴 **The eval scripts keep working with ZERO edits.** `Q-36-OQ8` corrects the spec: the 8
     `scripts/eval_*.py` write **`critic_model_ref`** (not `default_model_ref`) — the legacy-scalar rung
     carries every one of them. **Do not "migrate" them.**

**Tests**
- `tests/unit/test_model_roles_resolver.py` (pure — no DB, no xdist mark):
  - `test_model_roles_map_wins_over_legacy_scalar` — settings with **both** ⇒ the map's ref.
  - `test_legacy_scalar_is_the_fallback` — settings with **only** `critic_model_ref` ⇒ that ref,
    source `user_model` when `critic_model_source` absent. *(The eval-scripts rung — it must not silently
    drop; the `nil-tolerant-decorator-needs-wiring-test` lesson.)*
  - `test_unset_returns_none`.
  - 🔴 `test_fields_are_read_by_NAME_not_position` — assert
    `resolve_model_role({...}, "critic").model_ref == "R"` **and** `.model_source == "S"`. **The C12
    guard: assert the FIELD NAMES, never a positional tuple equality.**
  - `test_malformed_entry_falls_through_to_the_scalar` — `{"model_roles":{"critic":{"model_source":"S"}},
    "critic_model_ref":"L"}` ⇒ the **legacy** ref, **not a crash**.
  - 🔴 `test_composer_and_planner_are_unchanged_by_BE21` —
    `resolve_model_role({"default_model_ref":"m"}, "composer")` and `…, "planner")` behave exactly as
    §2's companion defines. *(The assertion that BE-21 did NOT change composer/planner engine behaviour.)*
- 🔴 `tests/unit/test_engine_critic_reads_model_roles.py` — **the behaviour test, not a blob test**
  (`pytestmark = pytest.mark.xdist_group("pg")`; mirror `tests/unit/test_engine_router.py:546`):
  - `test_critique_is_skipped_when_no_critic_configured` — settings `{}` ⇒ *"critique skipped"*.
  - 🔴 `test_critic_set_via_model_roles_is_NOT_skipped` — settings
    `{"model_roles":{"critic":{"model_ref":"<distinct-uuid>","model_source":"user_model"}}}`, **NO legacy
    scalar**, and a drafter `model_ref` that is **DIFFERENT** ⇒ the critique **runs** (no "critique
    skipped"; `judge_prose` called with `model_ref=<that uuid>`). **This test REDS at HEAD and is the ONLY
    proof BE-21 landed.** It is also M4a's DoD.
    ⚠ **The critic MUST differ from the JOB's `input.model_ref`** — the gate compares against the job's
    model (`engine.py:1645`), **not** the composer setting. Setting critic == composer still yields
    "critique skipped": **that is CORRECT behaviour, not a BE-21 regression.**
  - 🔴 `test_critic_same_ref_as_drafter_STILL_skips` — the paired negative. BE-21 must **not weaken** the
    anti-self-reinforcement guard.
  - `test_critic_set_via_legacy_scalar_still_works` — the shim's regression guard. **The four EXISTING
    legacy-scalar tests (`test_engine_router.py:546, 557, 711, 727`) must stay green — that IS the proof
    the fallback rung survived.**

**DoD evidence:** `"test_model_roles_resolver.py: 6 passed (incl. test_fields_are_read_by_NAME_not_position) · test_engine_critic_reads_model_roles.py: 4 passed — incl. test_critic_set_via_model_roles_is_NOT_skipped (RED at HEAD 9262ed53e, GREEN after BE-21) and test_critic_same_ref_as_drafter_STILL_skips · grep -c 'critic_model_ref' routers/engine.py == 0 · test_internal_model_settings.py green UNCHANGED (the lift's regression proof)"`

---

### **W6-BE3** — BE-13a: a derivative gets a NAME
**Kind:** BE · **dependsOn:** — · **HARD PREREQUISITE of M3**

> **Why.** `useDivergenceWizard.submit()` **refuses to fire unless `name.trim().length > 0`** (`:169`)
> and `buildBody()` (`:106-121`) returns `{branch_point, divergence, entity_overrides}` — **no `name`.**
> The user is *forced* to type a label that goes nowhere. A LIST of unnamed UUID rows is not a surface.
> **NO DDL** — `settings` is a JSONB blob the Work already carries, and `create_derivative` **already
> takes a `settings` kwarg** (C5).

**Files**
| File | Change |
|---|---|
| `services/composition-service/app/routers/works.py` | `DeriveBody`, `derive_work`, `DerivativeContextResponse`, `get_derivative_context` |
| `services/composition-service/tests/integration/test_derive_name.py` | **NEW** |
| `frontend/src/features/composition/types.ts` | `DeriveBody` |
| `frontend/src/features/composition/hooks/useDivergenceWizard.ts` | `buildBody()` |

**The change**
1. `works.py:304` — `DeriveBody`. 🔴 **`name` is REQUIRED, no default** (`Q-36-BE13A-DERIVATIVE-NAME`
   item 1 — the plan originally made it `| None = None`; **the register wins**). A LIST of unnamed UUID
   rows is not a surface, and the wizard **already gates submit on a non-empty name**, so an optional
   field just re-opens the hole:
   ```python
   class DeriveBody(BaseModel):
       # BE-13a: the wizard has ALWAYS collected a name and thrown it away (step 4 gates
       # submit on it). Persist it — a derivative must be nameable before it can be listed.
       # NO DDL: composition_work.settings is an existing JSONB blob.
       name: Annotated[str, StringConstraints(min_length=1, max_length=200)]   # REQUIRED
       branch_point: int | None = None
       divergence: DivergenceSpecBody = DivergenceSpecBody()
       entity_overrides: list[EntityOverrideBody] = []

       @field_validator("name")
       @classmethod
       def _strip(cls, v: str) -> str:
           s = v.strip()
           if not s:
               raise ValueError("name must not be blank")
           return s        # the STRIPPED value is what persists
   ```
   🔴 **THE TRAP — `works.py:313` + `:340`.** The body is currently **optional**
   (`body: DeriveBody | None = None`) and line 340 does `body = body or DeriveBody()`. With `name`
   required, **that line raises `ValidationError` → a 500, not a 422.** **Change the signature to
   `body: DeriveBody` (required) and DELETE line 340.** A bodyless POST then **422s at FastAPI's
   boundary**, which is the intended contract.
2. `derive_work` (`:378-405`) — pass it through the existing kwarg:
   ```python
   work = await works.create_derivative(
       user_id, derivative_project_id, book_id, source.id,
       branch_point=body.branch_point,
       settings={"derivative_name": body.name} if body.name else {},
       conn=conn,
   )
   ```
3. `DerivativeContextResponse` (`:425`) — add 🔴 **`derivative_name: str | None = None`** (that exact
   key — the FE and the contract both name it that); `get_derivative_context` sets it from
   `(work.settings or {}).get("derivative_name")`. **Nullable BY DESIGN** — pre-existing derivative rows
   have `settings = {}`. **Do NOT backfill them.**
4. **The LIST needs NOTHING** (C5): `_serialize_resolution` already emits `w.model_dump()` per candidate,
   which includes `settings`. Add a code comment saying so, or the next agent will "fix" it twice.
5. `works.py:369` — while here, 🔴 **use the author's name for the knowledge project too**:
   `name = body.name` instead of `f"{book_obj.get('title') or 'Work'} — dị bản"`. Today **every**
   derivative of a book mints an **identically-named** project. (Sane default; PO may veto.)
6. FE `types.ts:41` — `DeriveBody` gains **`name: string`** (required, matching the BE).
7. FE `useDivergenceWizard.ts` `buildBody()` (`:106-121`) — add `name: name.trim()` to the returned object
   **AND add `name` to its `useCallback` dep array** (🔴 it is **currently missing** → `buildBody` would
   capture a **stale empty string**). The existing `canAdvance`/`submit` name-gates are already correct.

**Tests** — `services/composition-service/tests/unit/test_routers.py` (the existing file — these are
**edits**, not a new file) + `tests/integration/test_derive_name.py`
(`pytestmark = pytest.mark.xdist_group("pg")`):
- 🔴 **INVERT the existing `test_derive_works_with_empty_body` (`test_routers.py:713-724`)** — it asserts
  **201** on a bodyless POST **today**. It must now assert **422**. Rename it
  `test_derive_422_without_name`. **This is the `legacy-test-inverts` hazard: leaving it green means
  `name` is not actually required.**
- Update the `_derive_body(**kw)` helper (`:558`) to include a default `name`, so the other five derive
  tests keep passing.
- 🔴 Update `StubWorks.create_derivative` (`:96-99`) to **RECORD `settings`** into `derived_with` and
  reflect it on the returned work — it currently **swallows the kwarg** (`settings=None`, never stored),
  so a persistence assertion would **false-green**. *(The `fixtures-can-seed-a-field-the-writer-never-sets`
  class, inverted.)*
- `test_derive_persists_name_to_settings` — `works.derived_with["settings"] == {"derivative_name": "…"}`.
- `test_derive_422_on_whitespace_name` (`name="   "`).
- `test_derivative_context_returns_name` — stub work `settings={"derivative_name":"X"}` ⇒
  `derivative_name == "X"`; a **legacy** work with `settings={}` ⇒ **`null`, no crash.**
- 🔴 `test_work_resolution_candidates_carry_the_name` — after a derive, `GET /books/{bid}/work` returns
  `status:"candidates"` and the derivative candidate's `settings.derivative_name` is set. *(This is the
  LIST the divergence panel reads — assert it here, not in the FE.)*

FE: extend `frontend/src/features/composition/hooks/__tests__/useDivergenceWizard.test.ts` (exists) with
🔴 `test_buildBody_includes_the_trimmed_name` — the F-EC3a guard, asserting `buildBody().name === 'X'`
(and that a re-typed name is **not stale**, which is the dep-array guard).

**DoD evidence:** `"test_routers.py: test_derive_422_without_name (INVERTED from the old 201 assertion) + test_derive_persists_name_to_settings + test_derivative_context_returns_name pass; StubWorks.create_derivative now RECORDS settings · test_derive_name.py: test_work_resolution_candidates_carry_the_name passed · useDivergenceWizard.test.ts: buildBody includes the trimmed name (RED at HEAD — buildBody dropped it)"`

---

### **W6-BE4** — BE-10: the 6 style/voice MCP tools (**lists Tier-R, writes Tier-A**) — **the INVERSE gap**
**Kind:** BE · **dependsOn:** —

> **Why.** `grep '^ *name="composition_' services/composition-service/app/mcp/server.py` → **no
> `composition_style_*`, no `composition_voice_*`.** The agent **cannot set the two knobs that most
> directly shape its own output.** `pack()` folds density/pace and per-character voice tags into every
> draft prompt (`packer/pack.py:269-285`).

**Files**
| File | Change |
|---|---|
| `services/composition-service/app/mcp/server.py` | 6 `@mcp_server.tool` registrations |
| `services/composition-service/tests/unit/test_mcp_style_voice_tools.py` | **NEW** |
| `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md` | **AN-8 table: +2 rows** |

**The change** — mirror `composition_canon_rule_create` (`server.py:1080-1110`) **exactly**. For each tool:
`_ctx(ctx)` → `WorksRepo(get_pool())` → `pid = UUID(args.project_id)` → `await _book_or_deny(works, tc,
pid, GrantLevel.VIEW|EDIT)` → the repo call → `out["_meta"] = {"undo_hint": _undo(...)}`.

🔴 **CORRECTION — the "3-schema-source" caveat is a KNOWLEDGE-SERVICE trap and does NOT apply here**
(`Q-36-BE10-FASTMCP-3-SCHEMA-SOURCES`). **Do not go hunting for a `definitions.py` in composition —
there isn't one** (`grep -rn "TOOL_DEFINITIONS|def execute_tool" services/composition-service` → **0
hits**). composition-service has **exactly ONE schema source** (the FastMCP tool fn + its pydantic
`ForbidExtra` args model), and `extra='forbid'` means an undeclared arg **ERRORS** rather than being
silently stripped.

🔴 **THE REAL SILENT-DROP SURFACE HERE IS THE DEFAULT-DENY POLICY MAP.** Register each tool in **all
FOUR** places — miss one and it silently no-ops while every unit test stays green:

| # | Surface | Miss it ⇒ |
|---|---|---|
| 1 | `services/composition-service/app/mcp/server.py` — the `@mcp_server.tool` + `ForbidExtra` args model | the tool does not exist |
| 2 | `services/composition-service/tests/unit/test_mcp_server.py:48` — the **`EXPECTED_TOOLS` literal set** (an exact-set equality asserted at `:177-181`) | the suite **reds** (this one is loud — good) |
| 3 | 🔴 `services/mcp-public-gateway/src/scope/tool-policy.ts` — `TOOL_POLICY` (composition block at `:231-237`). `knownTool()` (`:341`) / `isToolAllowed()` (`:353`) are **DEFAULT-DENY** | the tool is **silently invisible at the public MCP edge** while every unit test stays green. **This is the composition analogue of the FastMCP-strip bug.** Lists ⇒ `{tier:'read', domains:['composition']}`; upserts/deletes ⇒ `{tier:'write_auto', …}` (Tier-A = `write_auto`). Update the counts in `test/tool-policy.spec.ts` if the narrow-scope assertions move. |
| 4 | 🔴 `services/composition-service/app/services/authoring_run_service.py:127` — `ALLOWLISTABLE_TOOLS` | **the authoring run — the very agent whose output these knobs shape — still cannot reach them.** (It stays user-opt-in per run; the allowlist just makes it *possible*.) |

**NOT required by hand:** `contracts/tool-liveness.json` + its two embedded copies are **GENERATED** by
`scripts/eval/tool_liveness/manifest.py` from a sweep run. **Never hand-edit them.** Absence = "unproven",
not broken.

🔴 **Tiering correction** (`Q-36-BE10-STYLE-VOICE-MCP-TOOLS` B): spec 36:493 blanket-labels the group
"Tier-A". **The two `_list` tools are Tier R**, not A (tier A = auto-write + `undo_hint`). Reads get
`require_meta("R","book")` + `GrantLevel.VIEW`; the four writes get `require_meta("A","book")` +
`GrantLevel.EDIT` + `_meta.undo_hint`.

🔴 **A missing repo method the builder WILL hit** (`Q-36-BE10-STYLE-VOICE-MCP-TOOLS` build item 1):
**neither repo has a point read**, and **both undo paths need the prior row BEFORE mutating.**
`style_voice.py:86` `resolve()` is **precedence-based** (wrong for undo — it may return a *parent's* row)
and `:149` `list_all` is whole-work. **Add** `StyleProfileRepo.get(project_id, scope_type, scope_id)` and
`VoiceProfileRepo.get(project_id, entity_id)` — plain SELECTs over the existing `_STYLE_COLS`/`_VOICE_COLS`.
*(The plan originally said "use `list_all` and find the row; do not add a `get_one`." Either works, but
**do not use `resolve()`** — that is the trap.)*

| Tool | Tier | Args | Grant | Returns | `undo_hint` |
|---|---|---|---|---|---|
| `composition_style_list` | **R** | `project_id` | VIEW | `{items:[…]}` | `None` |
| `composition_style_upsert` | **A** | `project_id`, `scope_type: Literal["work","chapter","scene"]`, `scope_id`, `density: int (0..100)`, `pace: int (0..100)` | EDIT | the row | **the PRIOR row's values** → `composition_style_upsert(…prior.density, prior.pace)`; **or `composition_style_delete(scope)` when there was NO prior row** (an upsert that CREATED a row is undone by a delete, not by a phantom "restore to nothing") |
| `composition_style_delete` | **A** | `project_id`, `scope_type`, `scope_id` | EDIT | `{removed: bool}` | `composition_style_upsert(…, prior.density, prior.pace)`; **`None` when nothing was removed** (no faithful inverse of a no-op) |
| `composition_voice_list` | **R** | `project_id` | VIEW | `{items:[…]}` | `None` |
| `composition_voice_upsert` | **A** | `project_id`, `entity_id`, `entity_name (1..200)`, `tags: list[str] (≤20, each 1..40)` | EDIT | the row | prior tags, or `composition_voice_delete` when new |
| `composition_voice_delete` | **A** | `project_id`, `entity_id` | EDIT | `{removed: bool}` | prior tags via `composition_voice_upsert`; `None` when nothing removed |

**Hard rules baked in:**
- 🔴 **`project_id` IS a legitimate tool arg** (`Q-36-BE10-STYLE-VOICE-MCP-TOOLS` A). **H13 does NOT mean
  "no `project_id` arg"** — in this repo H13 = the **uniform `not_accessible()`** (no enumeration oracle).
  `project_id` is the scoping arg, exactly as in all 30+ existing composition tools. What is
  **DERIVED-never-a-body-arg** is `book_id` (from `composition_work` inside the INSERT) and `created_by`
  (from `tc.user_id`, the envelope — `ForbidExtra` blocks smuggling; `test_mcp_server.py:213` fails if you
  declare it). **Do not invent a project-less signature.** *(BE-7c's "drop the un-knowable `project_id`"
  applies ONLY to `composition_get_mine_job` — a job id whose project the agent cannot know.)*
- `_delete` takes the row key and **derives its book/project FROM THE LOADED ROW** for the grant gate
  (`gate-must-derive-scope-from-the-loaded-row`). A denial and a missing row return the **SAME**
  `uniform_not_accessible()`.
- `scope_type` is a **closed set** ⇒ `Literal["work","chapter","scene"]` (matches `StyleScope`,
  `models.py:332`). A free string here is the Frontend-Tool-Contract bug class.
- To build the undo hint, **read the prior row first** — via the **new point `get()`** above.
  ⚠ **NOT `resolve()`** — it is precedence-based and would hand you a *parent scope's* row, producing an
  undo that writes a value the user never had at that scope.
- `density`/`pace` are `int = Field(ge=0, le=100)`; `entity_name` 1..200; `tags` max 20 × 1..40
  (`style_voice.py` router `:31,106-110`) — the REST route 422s out of range; the tool must too.
- Wrap `ReferenceViolationError` → `uniform_not_accessible(exc) from exc` (`server.py:802`).
- **No OCC** on these tables (no `version` column) — the PUT is an upsert, last-writer-wins **by design**.
  Do **not** invent an `expected_version` arg. The memory
  `instant-commit-control-over-occ-entity-needs-write-serialization` does **not** apply (no version ⇒ no
  self-412).

**Spec 28 AN-8 — write the 2 rows INTO the table, do not fork it** (plan 30 §8.1; PO-1's precedent).
Add to `28_agent_native_studio.md`'s AN-8 edit-discipline table, **in the same commit**:

| Object class | Agent channel | Tier | Undo path |
|---|---|---|---|
| `style_profile` | `composition_style_{upsert,delete}` | **A** | `_meta.undo_hint` — the prior density/pace, or a delete when the upsert created the row |
| `voice_profile` | `composition_voice_{upsert,delete}` | **A** | `_meta.undo_hint` — the prior tags, or a delete when the upsert created the row |

**Tests** — `tests/unit/test_mcp_style_voice_tools.py` (`pytestmark = pytest.mark.xdist_group("pg")`):
- `test_style_upsert_creates_and_undo_hint_is_a_delete` — no prior row ⇒ `_meta.undo_hint.tool ==
  "composition_style_delete"`.
- `test_style_upsert_over_existing_undo_hint_carries_prior_values` — prior `(60,40)`, upsert `(80,20)` ⇒
  `undo_hint.args.density == 60 and .pace == 40`.
- `test_style_delete_undo_hint_restores` · `test_style_delete_of_missing_row_has_no_undo_hint`
  (`undo_hint is None`, `removed is False`).
- `test_voice_upsert_and_delete_round_trip`.
- `test_style_upsert_density_101_is_rejected`.
- `test_foreign_project_is_uniform_not_accessible` — a project in another user's book ⇒ the **same**
  error as a nonexistent project (no enumeration oracle).
- 🔴 `test_the_emitted_schemas_carry_the_scope_type_enum` — read the **registered** tool's schema off
  `mcp_server` (not the pydantic class) and assert `scope_type` has an `enum` of exactly
  `["work","chapter","scene"]`. `tests/unit/test_mcp_server.py` **boots an in-process FastMCP server and
  asserts the LIVE `tools/list` inputSchema** — it is the drift guard. **Run it; do not assume.**
  *(knowledge's equivalent lived outside `tests/unit/` and got skipped. Composition's does not.)*
- 🔴 `test_undo_of_an_upsert_that_CREATED_a_row_is_a_DELETE` — and its inverse,
  `test_undo_of_an_upsert_OVER_an_existing_row_carries_the_PRIOR_values`. **An upsert that emits a blanket
  re-upsert hint WITHOUT reading the prior row would resurrect a row the user never had — a FAKE INVERSE,
  the AN-8 defect class.** Round-trip: **applying the `undo_hint` restores the pre-call `list` output
  byte-for-byte.**
- `test_public_gateway_policy_has_all_six` — in `services/mcp-public-gateway/test/tool-policy.spec.ts`:
  `knownTool('composition_style_upsert')` is **true**. *(Surface #3 — default-deny.)*

**Verify (all four, pasted output):**
```bash
cd services/composition-service && python -m pytest tests/unit/test_mcp_server.py tests/unit/test_mcp_style_voice_tools.py -q
cd services/mcp-public-gateway  && npx vitest run test/tool-policy.spec.ts
cd frontend                     && npx vitest run src/features/studio/agent/handlers/__tests__/compositionEffects.test.ts
# + ONE live smoke through the edge (see §8 DoD #4)
```

**DoD evidence:** `"test_mcp_style_voice_tools.py: 10 passed — incl. test_the_emitted_schemas_carry_the_scope_type_enum (LIVE tools/list) and test_undo_of_an_upsert_that_CREATED_a_row_is_a_DELETE · tool-policy.spec.ts: knownTool() true for all 6 · EXPECTED_TOOLS + ALLOWLISTABLE_TOOLS updated · spec 28 AN-8 table has style_profile + voice_profile rows"`

---

### **W6-BE4b** — 🔴 BE-10b: the 4 reference MCP tools (**C15 — un-deferred**)
**Kind:** BE · **dependsOn:** W6-BE7 · Source: `Q-36-DEFERRED-REFERENCES-MCP`

> **Why the defer row died.** Gate #3 ("naturally-next-phase") was **false — every prerequisite exists at
> HEAD**, and this wave is **already building six MCP tools of exactly this shape, in the same file, for
> the same reason** (plan 30 **GG-2**: *"a GUI whose domain has no agent tools is also a defect"*).
> **Shipping the reference GUI while consciously leaving its inverse half open, in the one wave whose job
> is closing tool↔GUI gaps, is the defect the plan exists to kill.** ~120 LOC against routes that already
> work. CLAUDE.md: *"if fixing is cheaper than writing + carrying its defer row, just fix it."*

**Files:** `services/composition-service/app/mcp/server.py` · **NEW**
`services/composition-service/app/services/reference_search.py` ·
`services/composition-service/app/routers/references.py` (call the extracted helper) ·
`services/composition-service/tests/unit/test_mcp_reference_tools.py` (**NEW**) · the **4 registration
surfaces** from W6-BE4.

| Tool | Tier | Grant | Body |
|---|---|---|---|
| `composition_reference_list` | **R** | VIEW | `ReferencesRepo.list(pid)` → `{references[], embed_model_set}` — mirrors `routers/references.py:79-93`. No `undo_hint`. |
| `composition_reference_add` | **A** | EDIT | 🔴 **NO `model_ref`/`model_source` args** (PO-vetoable default). The reference embed model is **set on first add and thereafter immutable** (EC-2a's one-way door) — **an agent must not silently pick the vector space for the whole Work.** If `reference_embed_model(work.settings) is None` ⇒ return a **structured refusal, never a raise**: `{"success": false, "error": "reference_embed_model_unset", "message": "Add the first reference from the reference-shelf panel — the first add permanently fixes this Work's embedding model."}`. Else embed via `get_embedding_client()` (`deps.py:228` — **the ONLY embedding path; provider-gateway invariant**); on `EmbeddingError` ⇒ `{"success": false, "error": "embed_failed", "retryable": exc.retryable}`. `undo_hint = _undo("composition_reference_delete", …)`. |
| `composition_reference_delete` | **A** | EDIT | **project-scope BEFORE mutating** (`refs.get(pid, rid)` is `None` ⇒ `uniform_not_accessible()`). `undo_hint = None`, **honestly** — re-adding **re-embeds and mints a new id** (the `canon_rule_delete` precedent, `server.py:1195-1197`). |
| `composition_reference_search` | **R** | VIEW | 🔴 **Do NOT re-implement the query-seed + degrade logic.** **LIFT** the body of `search_references` (`references.py:194-224`) into `app/services/reference_search.py::retrieve_for_scene`, called by **BOTH** the router and the tool (`css-var-duplicated-across-two-consumers-drifts`). Keep the **neutral-empty degrade** (`{"hits":[], "embed_model_set":…, "unavailable": true}`) — **never raise on a provider outage** — and the pin/exclude annotation from `GroundingPinsRepo.list_for_scene`. |

**Cost:** add/search embed **one** passage/query — the single cheap provider call spec 36 §Cost gates
already blesses as a **direct, non-Tier-W** call. **No confirm spine, no new AN-8 convention.**

**Lane-B (X-4):** in `compositionEffects.ts` add
`registerEffectHandler(/^composition_reference_/, …)` — 🔴 **a RegExp, never a string** (C10) —
invalidating `['composition','references']` and `['composition','references','search']`
(the keys at `useReferences.ts:16-17`; **prefix-invalidate WITHOUT the id** — see W6-M1 §8).

**Tests** — `tests/unit/test_mcp_reference_tools.py` (`pytestmark = pytest.mark.xdist_group("pg")`):
- 🔴 `test_add_with_the_model_unset_refuses_and_writes_NO_row` — returns `reference_embed_model_unset`
  **and** `ReferencesRepo.create` was never called.
- `test_add_returns_an_undo_hint_pointing_at_delete_and_the_row_appears_in_list`.
- `test_deleting_a_reference_of_another_work_is_uniform_not_accessible`.
- 🔴 `test_search_under_an_EmbeddingError_returns_unavailable_true_and_does_NOT_raise`.
- `test_the_router_and_the_tool_call_the_SAME_retrieve_for_scene` (spy the helper — the anti-fork guard).

**DoD evidence:** `"test_mcp_reference_tools.py: 5 passed — incl. test_add_with_the_model_unset_refuses_and_writes_NO_row and test_search_under_an_EmbeddingError_returns_unavailable_true · search_references + composition_reference_search both route through app/services/reference_search.py (one implementation) · all 4 registration surfaces updated"`

---

### **W6-BE5** — BE-20: cost-gate Decompose (Tier-W) — **gates M4b ONLY**
**Kind:** BE · **dependsOn:** —

> **Why.** `POST /works/{pid}/outline/decompose` takes a raw `model_ref` and runs an LLM. It is **not** in
> `_ALL_DESCRIPTORS` (`actions.py:96-101`) — **no descriptor, no `/actions/preview` estimate, no
> `_precheck_or_402` billing hold** — unlike its four Tier-W siblings. **The legacy planner has been
> spending un-precheck'd tokens since it shipped.** Porting the button as-is would ship a known cost-gate
> hole onto a new surface, in the wave whose thesis is *"the human deserves the agent's rails"*.
> It also **closes an INVERSE gap** — the agent cannot decompose today either.

**Files**
| File | Change |
|---|---|
| `services/composition-service/app/routers/actions.py` | descriptor · dispatch · `_execute_decompose` |
| `services/composition-service/app/mcp/server.py` | `composition_decompose` (Tier-W) |
| `services/api-gateway-bff/src/…/tools.controller.ts` | `FE_BRIDGE_TOOL_ALLOWLIST` += `composition_decompose` |
| `services/composition-service/tests/integration/test_decompose_action_gate.py` | **NEW** |

**The change**

1. `actions.py` — the descriptor + **the C2 fallthrough fix**:
   ```python
   # BE-20 (F-EC6) — decompose spends real LLM tokens and had NO cost gate. Tier-W:
   # the tool executes nothing, mints a confirm token; the effect lives HERE.
   _DECOMPOSE_DESCRIPTOR = "composition.decompose"

   _ALL_DESCRIPTORS = (
       _PUBLISH_DESCRIPTOR, _GENERATE_DESCRIPTOR,
       _MOTIF_ADOPT_DESCRIPTOR, _MOTIF_MINE_DESCRIPTOR,
       _ARC_IMPORT_DESCRIPTOR, _CONFORMANCE_RUN_DESCRIPTOR,
       _DECOMPOSE_DESCRIPTOR,
       *_AUTHORING_RUN_DESCRIPTORS,
   )
   ```
   🔴 **AND** rewrite the Work-scoped tail of `confirm_action` (currently ends at `:342` with an
   **unconditional** `return await _execute_conformance_run(...)`):
   ```python
   if claims.descriptor == _PUBLISH_DESCRIPTOR:
       return await _execute_publish(payload, project_id, work, envelope_user, outline, book)
   if claims.descriptor == _GENERATE_DESCRIPTOR:
       apply_public_key_attribution_headers(x_mcp_key_id, x_mcp_spend_cap_usd)
       try:
           return await _execute_generate(payload, project_id, work, envelope_user)
       finally:
           apply_public_key_attribution_headers(None, None)
   if claims.descriptor == _CONFORMANCE_RUN_DESCRIPTOR:
       return await _execute_conformance_run(payload, project_id, work, envelope_user,
                                             token=token, claims=claims)
   if claims.descriptor == _DECOMPOSE_DESCRIPTOR:
       return await _execute_decompose(payload, project_id, work, envelope_user,
                                       token=token, claims=claims)
   # C2 — the tail USED to fall through to _execute_conformance_run unconditionally. Any new
   # Work-scoped descriptor added to _ALL_DESCRIPTORS would have silently run the CONFORMANCE
   # effect. It is now explicit, and an unhandled descriptor is a clean 400.
   raise HTTPException(status_code=400, detail={"code": "action_error"})
   ```
2. 🔴 **EXTRACT THE JOB-INPUT BUILDER — do NOT call the route coroutine in-process.**
   (`Q-36-BE20-DECOMPOSE-COST-GATE` (c) + `Q-36-OQ3-BE20-VS-RAW-DECOMPOSE`. This plan originally called
   `plan_router.decompose_preview(...)` directly; **the register replaces that** — the route's
   enqueue-vs-inline branch is exactly what must NOT be inherited. See the ⚠ below.)

   In `app/routers/plan.py`, lift the arg-resolution block out of `decompose_preview` (`:508-610` — the
   `_require_work` / template-404 / `_book_chapter_ids` + `NO_CHAPTERS` / `TOO_MANY_CHAPTERS` guards /
   `_cast_roster` / `from_settings` / `ChapterPlan` build / `motif_genres` + `motif_applied_counts`,
   ending in the `job_input` dict) into ONE module-level coroutine:
   ```python
   async def build_decompose_job_input(
       *, work, project_id, user_id, bearer, body, book, kal, templates,
   ) -> tuple[str, dict]:
       """Returns (operation, job_input). ONE implementation, TWO callers: the REST route and
       actions._execute_decompose. Copy-pasting these 100 lines into actions.py is the
       `css-var-duplicated-across-two-consumers-drifts` class."""
   ```
   Rewrite **BOTH** the REST route (call it, then `jobs.create(...)` + `enqueue_job` exactly as today)
   **AND** `_execute_decompose` to call it. The `NO_CHAPTERS` / `TOO_MANY_CHAPTERS` 400s then protect the
   agent path **for free**.

   ```python
   async def _execute_decompose(
       payload: dict[str, Any], project_id: UUID, work: CompositionWork, envelope_user: UUID,
       *, token: str, claims: Any,
   ) -> dict[str, Any]:
       """composition.decompose effect — replay-claim → billing precheck → ALWAYS enqueue."""
       await _claim_or_replay(token, claims)          # FIRST — a replayed decompose double-enqueues PAID work
       await _precheck_or_402(                        # ← THE WHOLE POINT: 402 BEFORE any LLM runs
           owner_user_id=envelope_user, job_id=_billing_job_id(token),
           estimate_usd=float(payload.get("estimate_usd") or 0.0),
       )
       # The MCP/confirm path has NO user JWT — mint a service bearer (mirrors actions.py:370/431).
       bearer = mint_service_bearer(envelope_user, settings.jwt_secret, ttl=_GENERATE_BEARER_TTL_S)
       op, job_input = await plan_router.build_decompose_job_input(...)   # raises NO_CHAPTERS etc. verbatim
       job_id = await _enqueue_motif_job(
           envelope_user=envelope_user, project_id=project_id, operation=op, spec=job_input,
       )
       return {"outcome": "action_accepted", "descriptor": _DECOMPOSE_DESCRIPTOR,
               "job_id": str(job_id), "poll": "composition_get_generation_job"}
   ```
   🔴 ⚠ **ALWAYS ENQUEUE — do NOT gate on `settings.composition_worker_enabled`.** `plan.py` enqueues only
   when that flag is on and **otherwise runs the LLM INLINE in the request**. The Tier-W confirm must be
   **202 + poll unconditionally** (mirroring `motif_mine` / `arc_import` / `conformance_run`, which never
   consult the flag). *This is precisely the bug the "call the route in-process" version would have
   shipped: with the flag off, the confirm would run a paid LLM synchronously inside the confirm request.*
   🔴 ⚠ **The poll tool is `composition_get_generation_job`** (`server.py:524`) — **NOT
   `composition_get_mine_job`.** The row is a `generation_job` with `operation="decompose_preview"`, and
   the mine-job tool's own description says *"motif job"*. Both read `GenerationJobsRepo` with the same
   `project_id` IDOR check, so this is a **naming fix, not a behavior change**. **Amend spec 36:438** (it
   says `composition_get_mine_job`). ⇒ **Also verify `composition_get_generation_job` is in
   `FE_BRIDGE_TOOL_ALLOWLIST`** (`tools.controller.ts`); `composition_get_mine_job` is there at `:29`, the
   generation-job poller may not be. **If absent, add it in this slice** — a poll tool the FE cannot call
   is a job the user watches forever.
   ⚠ `build_decompose_job_input`'s `HTTPException`s (400 `NO_CHAPTERS` / `TOO_MANY_CHAPTERS`, 404
   template-not-found, **400 `NO_STRUCTURE_TEMPLATE`** — EC-5) must propagate **UNCHANGED**. Do **not**
   wrap them in a generic `action_error` (the *"something went wrong"* anti-pattern).

2b. 🔴 **MAKE THE JOB'S COMPLETION A REAL WRITE — or the Lane-B handler has nothing to refresh**
   (`Q-36-DECOMPOSE-EFFECT-ON-JOB-COMPLETION` (1)). **The code is stricter than the spec knew:**
   `run_decompose` (`operations.py:79-110`) **returns a plan and persists NOTHING**; the **only** outline
   write is `commit_decomposed_tree` inside `POST /outline/decompose/commit` (`plan.py:730`). So a
   confirm-gated, **cost-estimated**, `replace=false`-by-default job that **writes nothing** is a
   **PAID NO-OP** — the exact defect class this run's policy calls CRITICAL.
   - `_execute_decompose` enqueues with `input.auto_commit=true`, `input.replace=<tool arg>`,
     `input.arc_title=<template.name>`.
   - Extract `plan.py`'s commit body (`:660-760`: IDOR check → `EMPTY_DECOMPOSE_PLAN` guard → cast
     validation → story_order stride → `commit_decomposed_tree` → motif ledger) into a shared
     `_commit_decomposed(...)`, called by **BOTH** `decompose_commit` **and** `run_decompose` (when
     `input.get("auto_commit")`).
   - The job's terminal `result` becomes `{plan, committed: true, arc_id, scene_ids}`;
     `EMPTY_DECOMPOSE_PLAN` / **409** `CHAPTER_ALREADY_PLANNED` become the job's **failed-result error**,
     so the agent renders a **real reason** (M4b's DoD demands exactly those two).
   - ⚠ Grounding that this is what BE-20 already meant: **`replace` is a `CommitRequest` field
     (`plan.py:128`), NOT a `DecomposeRequest` field** — yet BE-20 lists `replace?` as a **tool arg**. The
     auto-commit is what reconciles that. (`replace` defaults **false** ⇒ 409 `CHAPTER_ALREADY_PLANNED`;
     safe by default, and the whole thing is Tier-W confirm-gated with a cost estimate.)
   - **PO veto point (recorded):** if the PO would rather the agent's decompose stay **preview-only**, then
     2b is dropped **AND** the Lane-B handler must **not invalidate outline/plan-hub at all** (nothing
     changed) **AND** BE-20 must drop `replace?` from its arg list. All three, together.

2c. 🔴 **ALSO ADD `composition_decompose_commit`** (Tier-A MCP write; **no confirm token, no cost gate** —
   it is a pure DB persist, **zero LLM spend**). Without it, BE-20 half-closes its own inverse gap: the
   agent can propose a tree and read the job result but **has no way to persist it** except ~N calls to
   `composition_outline_node_create`. Wrap `POST /works/{pid}/outline/decompose/commit` (`plan.py:647`) —
   `_book_or_deny(..., EDIT)` → the shared `_commit_decomposed(...)`, reusing the route's existing
   `idempotency_key` + already-planned guards **verbatim**. `meta=require_meta("A", "book",
   tool_name="composition_decompose_commit")`. Register on all 4 surfaces (W6-BE4's table).
3. `mcp/server.py` — `composition_decompose`, mirroring `composition_conformance_run` (`:3119-3175`):
   ```python
   class _DecomposeArgs(ForbidExtra):
       project_id: str
       structure_template_id: str
       premise: str                       # 1..4000 (mirror DecomposeRequest)
       model_ref: str
       model_source: str = "user_model"
       pipeline: bool = False
   ```
   Body: `_book_or_deny(works, tc, pid, GrantLevel.EDIT)` → verify the template exists
   (`StructureTemplatesRepo.get(tc.user_id, tid)`; `None` ⇒ `uniform_not_accessible()`) → `estimate =
   _mine_estimate(scope="book")` → `payload = {project_id, book_id, structure_template_id, premise,
   model_ref, model_source, pipeline, estimate_usd}` → `mint_confirm_token(...,
   _DECOMPOSE_DESCRIPTOR, payload)` → return `{confirm_token, descriptor, title: "Decompose chapters
   into scenes with a story structure", domain: "composition", requires: "human confirmation — this
   spends LLM tokens", estimate}`.
   `meta=require_meta("W", "book", synonyms=["decompose", "break chapters into scenes", "plan scenes",
   "apply a story structure", "beat sheet the book"], async_job=True, tool_name="composition_decompose")`.
4. `services/api-gateway-bff` — add **`composition_decompose`** to `FE_BRIDGE_TOOL_ALLOWLIST`
   (`src/tools/tools.controller.ts:24-30`), **exactly one new name**
   (`Q-36-BE20-MCPEXECUTE-ALLOWLIST`):
   ```ts
   'composition_decompose', // PROPOSE — mint a confirm token for a structure-decompose (BE-20)
   ```
   It belongs there **and only there**: it is a Tier-W **PROPOSE that executes nothing** (mints a token),
   so it does **not** violate the allowlist's own contract at `:19-23` (*"NOTHING here writes or
   deletes"*). ⚠ **Confirm is a REST write** (`POST /v1/composition/actions/confirm?token=`),
   auto-proxied by `gateway-setup.ts:354` — **never** an allowlist member. **The FE's propose call goes
   through `mcpExecute`** and gets a **403 from the BFF allowlist** without this line — G-MOTIF-SUGGEST's
   exact "this LOOKS FE-only and is not" trap.
   Add a `tools.controller.spec.ts` case mirroring `composition_conformance_run` at `:66-79`:
   membership is `true`, **and** `controller.execute({tool:'composition_decompose', args:{args:{project_id:'p1',…}}})`
   forwards once to `/internal/tools/execute` with a server-derived `x-user-id` + `x-project-id: p1`
   (the nested-`args` project-id lift at `:100-107` must find it — **propose tools nest under a single
   pydantic `args` param**; `motif/api.ts:251-252` records the live failure when they were flat).
   🔴 ⚠ **This makes M4b CROSS-SERVICE** (api-gateway-bff + composition-service) ⇒ per CLAUDE.md's VERIFY
   gate its **live-smoke is MANDATORY** (§8). **Amend spec 36:443-445** — it says *"no new
   FE_BRIDGE_TOOL_ALLOWLIST entry"*; it is *"exactly one — `composition_decompose`."*
   ⚠ **No `frontend/src/mcpBridge.ts` change** — it is tool-name-generic (`:15`).

**Tests** — `tests/integration/test_decompose_action_gate.py` (`pytestmark = pytest.mark.xdist_group("pg")`):
- 🔴 `test_decompose_confirm_402s_before_the_llm_runs_when_over_budget` — stub the billing client to
  refuse; assert **402** and that the LLM client was **never called** (spy) **and that
  `GenerationJobsRepo.create` was never called**. *This is the whole point — fail CLOSED.*
- `test_decompose_confirm_ALWAYS_enqueues_even_with_the_worker_flag_OFF` 🔴 — set
  `composition_worker_enabled = False` and assert the confirm **still** returns
  `{outcome:"action_accepted", job_id}` and that **no LLM ran inside the request**. *(The
  always-enqueue guard — the bug the in-process version would have shipped.)*
- `test_the_poll_tool_is_composition_get_generation_job` — assert the literal string in the response.
- `test_decompose_confirm_replays_409` — the same token twice ⇒ 409 `already_consumed`, **and
  `_enqueue_motif_job` called exactly ONCE**.
- `test_preview_returns_a_real_estimate` — `GET /actions/preview?token=` ⇒ `payload.estimate_usd > 0`.
- 🔴 `test_the_confirm_payload_carries_NO_chapters_or_cast_key` — the **small-payload invariant**: the
  payload is embedded in the **signed token**; a 40-chapter roster + cast would blow the token size. The
  effect **re-resolves** them at confirm time.
- 🔴 `test_an_unknown_work_scoped_descriptor_400s_and_does_NOT_run_conformance` — **the C2 guard**: mint a
  token with a descriptor not in `_ALL_DESCRIPTORS` and assert 400; and assert the conformance enqueue
  spy was **not** called.
- `test_no_chapters_400_propagates_verbatim` · `test_no_structure_template_400s` (EC-5) ·
  `test_foreign_project_confirm_400s_uniform`.
- 🔴 `test_build_decompose_job_input_is_byte_identical_to_the_pre_refactor_route` (in `tests/unit/test_plan.py`)
  — **pin the key set**, so the extraction cannot silently drop `thread_state` / `motifs_enabled` /
  `motif_genre_tags` / `book_id`.
- `test_auto_commit_persists_the_tree` — the job completes ⇒ `commit_decomposed_tree` ran and
  `result.committed is True`; and `EMPTY_DECOMPOSE_PLAN` surfaces as the **job's failed-result error**.

**DoD evidence:** `"test_decompose_action_gate.py: 11 passed — incl. test_decompose_confirm_402s_before_the_llm_runs_when_over_budget (LLM spy call_count == 0, GenerationJobsRepo.create call_count == 0), test_decompose_confirm_ALWAYS_enqueues_even_with_the_worker_flag_OFF, and test_an_unknown_work_scoped_descriptor_400s_and_does_NOT_run_conformance · test_plan.py: build_decompose_job_input key-set pinned · tools.controller.spec.ts: composition_decompose forwards with x-project-id"`

---

### **W6-BE6** — 🔴 BE-13: the divergence spec + overrides become EDITABLE (**C13 — un-deferred**)
**Kind:** BE · **dependsOn:** — · **Size S** (was M) · **HARD PREREQ of M3's spec section** ·
Source: `Q-36-DEFERRED-BE13-DIVERGENCE-SPEC-EDIT`

> **The falsifying line — `services/composition-service/app/packer/pack.py:153-157`** (the docstring of
> `build_derivative_context`): *"The `entity_override[]` is read **FRESH** here on every pack
> (self-syncing — no cache; **an edited override takes effect on the next pack**)."*
> **The architecture already anticipates editing. Only the WRITER is missing.** Every consumer goes
> through that one function (`engine.py:387,765,970`, `grounding.py:93`, `approve.py:107`,
> `critic_override.py:336`, `works.py:463`) — so an UPDATE/DELETE **propagates everywhere with zero extra
> work.** No migration (`migrate.py:146-176` — every column exists). No refactor (fresh reads self-sync).
> No cross-service contract. **"New write semantics" means, literally, an UPDATE statement.**
>
> **Why it matters, beyond cheapness:** `POST /derive` mints a **FRESH knowledge project**
> (`works.py:371`). A user who **mistypes their POV anchor** today **CANNOT fix it** — they must abandon
> the derivative and re-derive, **losing every drafted chapter.** And EC-3a's proposed inline note
> literally tells the user *"editing needs BE-13"* — **a UI that confesses a missing feature**, the
> inverse of the PO's own sealed GG-1 honesty axis.

**1 · `app/db/repositories/derivatives.py`** — 3 methods, mirroring `create_spec`/`create_override`
(conn-optional, `_SPEC_COLS`/`_OVERRIDE_COLS` RETURNING):
- `update_spec(work_id, fields: dict) -> DivergenceSpec | None` — 🔴 build the SET clause **DYNAMICALLY
  from the keys present in `fields`**. **Do NOT use `COALESCE`**: `pov_anchor=None` is a **LEGITIMATE
  value** (clear the anchor), and COALESCE **cannot distinguish "clear it" from "don't touch it."**
- `upsert_override(override) -> EntityOverride` — `INSERT … ON CONFLICT (work_id, target_entity_id) DO
  UPDATE SET overridden_fields = EXCLUDED.overridden_fields RETURNING …`. ⚠ **The ON CONFLICT target MUST
  match `uq_entity_override_work_target` exactly** (`migrate.py:175-176`) — the repo's own
  `postgres-partial-index-on-conflict-predicate-must-match` lesson.
- `delete_override(work_id, target_entity_id) -> bool` — return whether a row was removed (parse the
  `DELETE n` tag).

**2 · `app/routers/works.py`** — 2 routes (after `get_derivative_context`, ~`:480`). **BOTH must, IN THIS
ORDER:** (a) `work = await works.get(project_id)`; **404 `NOT_ACCESSIBLE_MESSAGE`** if None; (b)
`await _gate_book(grant, work.book_id, user_id, GrantLevel.EDIT)` — 🔴 **gate on the LOADED ROW's
`book_id`, never a client-supplied one** (copy `works.py:353`; `gate-must-derive-scope-from-the-loaded-row`);
(c) **409 `NOT_A_DERIVATIVE`** if `work.source_work_id is None`; (d) **409 `WORK_NOT_BACKED`** if
`work.id is None` (the pending/lazy-work trap already guarded at `works.py:354`).
- `PATCH /works/{project_id}/divergence-spec` — body `DivergenceSpecPatchBody(taxonomy?, pov_anchor?,
  canon_rule?)`; pass **`body.model_dump(exclude_unset=True)`** so an **EXPLICIT `pov_anchor: null`
  CLEARS** it while an **OMITTED key leaves it alone**. 404 if `update_spec` returns None.
- 🔴 **`PUT` + `DELETE /works/{project_id}/overrides/{target_entity_id}`** — **DEVIATION FROM THE SPEC
  TEXT (flagged for veto):** the spec proposed `POST|PATCH|DELETE /overrides`. Use a **single idempotent
  `PUT` keyed on `target_entity_id`**: the UNIQUE index means **one override per entity**, so POST-vs-PATCH
  is a distinction **the data model does not have**, and PUT collapses them (one name, one concept).
  **DELETE returns 404 when 0 rows matched** — **NOT a silent 204 no-op** (`silent-success-is-a-bug`).

**3 · Do NOT add an MCP tool here.** This is deterministic GUI CRUD — no LLM decides anything, so the
MCP-first invariant does not bite. *(The divergence **agent** surface is W6-BE8, which is a different
thing: `derive_work` is an irreversible fork.)*

**4 · `D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH` STAYS DORMANT** — none of these routes touch `outline_node`.
**Explicit instruction: do NOT copy `outline_node` rows into the derivative partition.** That, and only
that, is what fires it (plan 30 §10).

**Tests**
- `tests/unit/test_routers.py`: PATCH updates taxonomy/pov/canon_rule; 🔴 **explicit-null `pov_anchor`
  CLEARS it while an omitted key PRESERVES it** (the COALESCE trap); `canon_rule: []` clears the array;
  non-derivative ⇒ **409**; no-grant ⇒ 404.
- `tests/integration/db/test_repositories.py` (`xdist_group("pg")`): `update_spec`; `upsert_override` on
  **BOTH** paths (fresh insert **AND** the ON-CONFLICT update); `delete_override` returns `False` for an
  absent row.
- 🔴 **`tests/unit/test_pack_override.py` (EXTEND) — THE LOAD-BEARING ONE:** PUT an override → run the
  **pack path** → assert the **NEW value reaches `present`**. Then DELETE it → re-pack → assert the
  **base value is restored.** *This proves the new writer actually flows through `build_derivative_context`'s
  fresh read end-to-end — **a green repo test alone would NOT prove the edit reaches the prompt window.***

**Spec edits to land with the code:** `36_editor_craft_ports.md` — rewrite **EC-3a** (`:269`) to *"spec +
overrides are EDITABLE (BE-13)"*; **DELETE** the *"editing needs BE-13"* inline note from the panel table
(`:374`); flip the **BE-13 row** (`:439`) from *"DEFERRED to v2"* to *"MUST-BUILD (M3), size S"*; **DELETE
the defer row** (`:704`) → "Recently cleared". `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:307` — re-size BE-13
**M → S**.

**DoD evidence:** `"test_pack_override.py: PUT an override → the NEW value reaches `present` in the packed context; DELETE → the base value is restored (the end-to-end proof, not a repo-only green) · test_routers.py: explicit-null pov_anchor CLEARS, omitted key PRESERVES · non-derivative ⇒ 409 NOT_A_DERIVATIVE · D-DIVERGENCE-SPEC-EDIT moved to Recently cleared"`

---

### **W6-BE7** — 🔴 BE-17: reference LIST-widen + metadata PATCH (**C14 — un-deferred**)
**Kind:** BE · **dependsOn:** — · **HARD PREREQ of M2's embed-model header** ·
Source: `Q-36-DEFERRED-BE17-REF-UPDATE` · `Q-36-F-EC2-EMBED-MODEL-ONE-WAY-DOOR`

> **Why the defer row died.** `list_references` **already fetches the Work** (`references.py:87`) and
> **already calls `reference_embed_model(work.settings)`** (`:92`) — then **throws the `(source, ref)`
> tuple away** into an `is not None`. **That is not missing infrastructure; it is a DISCARDED VALUE**
> (CLAUDE.md anti-laziness rule). And v1-without-PATCH means **fixing a typo in a title costs a paid
> provider embed call** (delete + re-add).

**Slice BE-17a — widen LIST (XS, ~4 lines, ZERO new query).** `app/routers/references.py`,
`list_references` (`:78-93`). **ADDITIVE** — keep `embed_model_set` (`useReferences.ts:29` gates the
search query on it):
```python
rows  = await refs.list(project_id)
model = reference_embed_model(work.settings)          # -> (source, ref) | None
return {
    "references": [r.model_dump(mode="json") for r in rows],
    "embed_model_set": model is not None,
    "reference_embed_model_source": model[0] if model else None,   # e.g. "user_model"
    "reference_embed_model_ref":    model[1] if model else None,   # the user_model_id UUID
}
```

**Slice BE-17b — `PATCH /references/{reference_id}` — METADATA ONLY, NO RE-EMBED (S).**
1. Repo (`app/db/repositories/references.py`): `update_meta(project_id, reference_id, *, fields: dict)`
   with a 🔴 **HARDCODED column allowlist `{"title","author","source_url"}`** — build the SET clause **from
   the allowlist, NEVER from caller keys**. `WHERE project_id=$1 AND id=$2 RETURNING {_SELECT_COLS}`.
   Empty `fields` ⇒ return `self.get(...)` (idempotent no-op, still 200).
   🔴 **NEVER writes `content`/`embedding`/`embedding_model`/`embedding_dim`** — a content edit would
   **strand the vector**, which is exactly why this route is metadata-only.
2. Router: mirror `delete_reference` (`:148-168`) **VERBATIM** for scoping — `SELECT project_id FROM
   reference_source WHERE id=$1` → None ⇒ **404** (no existence oracle) → `_require_work(..., EDIT)` →
   `update_meta` → None ⇒ 404 → return the row.
   Body: `class ReferenceUpdate(BaseModel)` with 🔴 **`model_config = ConfigDict(extra="forbid")`** and
   `title/author/source_url: Annotated[str, StringConstraints(max_length=500)] | None = None`.
   **`extra="forbid"` is LOAD-BEARING: a caller sending `content` must get a 422, not a silently-dropped
   field that LOOKS like it re-embedded** (the `rest-write-mirror-drops-fields` bug class).
   Update the module docstring's route list (`references.py:1-18`).
3. **No gateway change** (`gateway-setup.ts:354` forwards all `/v1/composition/*`, all methods).

**Tests** — `tests/unit/test_references_router.py`:
- LIST before any add ⇒ `embed_model_set: false` and **both new fields `None`**.
- LIST after a first add with `model_ref=X` ⇒ `reference_embed_model_ref == X`, `_source == "user_model"`.
- 🔴 A **second** add passing a **DIFFERENT** `model_ref` ⇒ LIST is **unchanged** (proves the immutability
  the header claims — `references.py:54-57`: *"a differing value here is ignored"*).
- PATCH updates `title` only; `author`/`source_url`/`embedding_model` untouched.
- 🔴 PATCH with `content` ⇒ **422**.
- PATCH on another project's reference ⇒ 404/403 per the delete tests.
- 🔴 `test_the_EmbeddingClient_spy_is_NEVER_called_during_PATCH` — **that assertion IS the "no re-embed"
  contract.**

**Spec amendment (write it — do not leave the inconsistency):** `36_editor_craft_ports.md` — **EC-2a**
narrows from *"no edit"* to *"no **CONTENT** edit and no **model** change"*; its rationale (*"the model is
a permanent one-way door, and the panel says so"*) is **UNCHANGED and still governs**. Mark **BE-17**
(`36:440`) and plan 30's BE-17 row (`30:311`) as **IN M2**, not deferred; **DELETE the
`D-REF-UPDATE-AND-MODEL-SURFACE` defer row** (`36:703`).

**DoD evidence:** `"test_references_router.py: 7 passed — incl. test_the_EmbeddingClient_spy_is_NEVER_called_during_PATCH and test_a_second_add_with_a_different_model_ref_does_not_change_LIST (the one-way-door proof) · PATCH with `content` ⇒ 422 · D-REF-UPDATE-AND-MODEL-SURFACE moved to Recently cleared"`

---

### **W6-BE8** — 🔴 M6-D: the 3 divergence MCP tools (**C15 — un-deferred**)
**Kind:** BE · **dependsOn:** W6-BE3, W6-BE6 · Source: `Q-36-DEFERRED-DIVERGENCE-MCP`

> **Why the defer row died.** Its premise — *"an AN-8 Tier-W-shaped action that deserves its own confirm
> design"* — is **false on the code**: the AN-8 propose→confirm spine is **generic and already carries 11
> descriptors** (`actions.py:64-100`, `:214-330`, `:690`), and an **MCP tool path ALREADY mints a
> knowledge project cross-service** (`mcp/server.py:561-600`, `:583` — `composition_create_work` →
> `_resolve_or_create_default_project` → `knowledge.create_project` via `mint_service_bearer`).
> **Nothing structural is missing.** CLAUDE.md: *"missing infrastructure is unbuilt work, not a blocker."*

**1 · EXTRACT THE DERIVE CORE (no behaviour change).** Move the body of `derive_work`
(`works.py:310-406`, everything after the body-parse) into
`app/services/derive.py::derive_work_core(...) -> dict`. **Keep EVERY existing raise verbatim** (404
source/book, 403 grant, 409 `SOURCE_WORK_NOT_BACKED`, 502 `BOOK_SERVICE_UNAVAILABLE`/`PROJECT_CREATE_FAILED`,
**503 `PROJECT_CREATE_UNAVAILABLE`**) — spec 36 already promises the 503 is surfaced verbatim. The HTTP
route becomes a 5-line caller. **Two callers, one core.**

**2 · TWO READ TOOLS (Tier R, no confirm)** — `require_meta("R","user")`, like `composition_get_work`:
- `composition_list_derivatives(book_id)` → `_gate(tc, book_id, VIEW)` → `WorksRepo.resolve_by_book`;
  split canonical (`source_work_id IS NULL`) vs derivatives; per derivative attach
  `DerivativesRepo.get_spec_for_work` + `len(list_overrides_for_work)` as `override_count` **+ the
  BE-13a `settings.derivative_name`**. *(This is the LIST plan 30 BE-13 called absent — **the repo method
  exists**; only the projection is new.)* Synonyms: `["list dị bản","what-if versions","alternate
  universes","derivatives of this book"]`.
- `composition_derivative_context(project_id)` → mirror `GET /works/{pid}/derivative-context`. Return
  `{is_derivative: false}` for a greenfield Work, exactly as the route does.

**3 · ONE WRITE TOOL (Tier W)**, mirroring `composition_motif_adopt` (`server.py:2896-2955`) — **copy that
function's shape; do not invent one**:
- `composition_derive_work(source_project_id, **name**, branch_point?, taxonomy, pov_anchor?, canon_rule[],
  entity_overrides[])` as `ForbidExtra`. 🔴 **`name` is REQUIRED** (BE-13a made the route require it) and
  **`taxonomy` MUST be a `Literal[...]` closed set** matching `DivergenceSpecBody` (the IN-rule).
- **PROPOSE:** `works.get` → `_gate(tc, source.book_id, EDIT)` → `mint_confirm_token(..., _DERIVE_DESCRIPTOR,
  payload)`. Return `{confirm_token, descriptor, title:"Create a dị bản (derivative work)",
  domain:"composition", preview:{source_title, name, branch_point, taxonomy, canon_rule_count,
  override_count, forks_knowledge_partition: true, reversible:"archive only — a derivative has no delete"}}`.
  🔴 **NO `_precheck_or_402`** — derive makes **ZERO LLM calls**, so it is an **irreversibility gate, not a
  spend gate**. **Say so in the tool description.**
- **REGISTER the descriptor `composition.derive_work` in BOTH blocks** (`mcp/server.py:104-127` **and**
  `actions.py:64-100`) and add it to **`_ALL_DESCRIPTORS`** (`actions.py:96`) — 🔴 **a descriptor missing
  from `_ALL_DESCRIPTORS` is a silent 400.**
- **CONFIRM branch** in `actions.py::confirm_action`, next to `_MOTIF_ADOPT_DESCRIPTOR` (`:259`) — derive
  is **BOOK-scoped like adopt, not Work-scoped**: re-resolve the source → `authorize_book(..., EDIT)` (**a
  grant revoked between propose and confirm stops the fork**) → 🔴 `await _claim_or_replay(token, claims)`
  (**WITHOUT it a double-confirm mints TWO knowledge partitions**) → `derive_work_core(..., bearer=
  mint_service_bearer(envelope_user, settings.jwt_secret))`. Return `{"outcome":"action_done",
  "project_id":…, "work":…}`.

**4 · SPEC EDIT** (the *"confirm design"* the defer row asked for is **ONE TABLE ROW**, not a spine): add
to `28_agent_native_studio.md`'s AN-8 table — **Work (derivative)** · `composition_derive_work` · **W
(propose→confirm, no spend)** · undo = **archive (`PATCH /works {status:'archived'}`) — there is no delete;
the confirm preview MUST say so.**

**Tests** — `tests/test_mcp_divergence_tools.py` (`pytestmark = pytest.mark.xdist_group("pg")`):
- 🔴 (a) propose returns a token + descriptor `composition.derive_work` and creates **NO Work row** and
  **NO knowledge project** (assert `knowledge.create_project` was **never** called) — the *"nothing until
  confirm"* law.
- (b) confirm creates a derivative whose `project_id != source.project_id` and persists spec + overrides.
- 🔴 (c) **REPLAY** — confirming the **same token twice** returns the ledger result and calls
  `knowledge.create_project` **exactly ONCE**. *(This is the bug the defer row was afraid of. The ledger
  is the answer.)*
- (d) EDIT grant revoked between propose and confirm ⇒ 403, **no row**.
- (e) knowledge outage at confirm ⇒ **503 `PROJECT_CREATE_UNAVAILABLE`, no Work row** (txn).
- (f) the two read tools return the same shape as their REST siblings; a non-grantee gets the **uniform**
  not-accessible (no oracle).

**DoD evidence:** `"test_mcp_divergence_tools.py: 6 passed — incl. the replay test (confirm the same token twice ⇒ knowledge.create_project call_count == 1) and propose-writes-nothing · derive_work_core has TWO callers and ONE implementation · D-DIVERGENCE-MCP-TOOLS moved to Recently cleared"`

---

### **W6-BE9** — 🔴 X-10 / AN-C2: the discovery scent (**C16 — the hold is RELEASED**)
**Kind:** BE · **dependsOn:** W6-BE4, W6-BE4b, W6-BE5, W6-BE8 (name only REGISTERED tools) ·
Source: `Q-36-DISCOVERY-SCENT-BLOCKED-ON-TRACK-C`

> **The premise was FALSE.** This plan said *"`stream_service.py` is Track C's and it is UNCOMMITTED AND
> MID-EDIT — DO NOT TOUCH IT"* and called it *"the ONE genuinely-external blocker."* **At HEAD, Track C's
> edits to that file are COMMITTED** (`a23c3f15e`, `fd4702818`, `bac8802c2`, `a95f65378` — all ancestors
> of HEAD) and the working tree for it is **clean**. Seven new tools the model is never told about are
> **seven tools that will never be called** — spec 28 AN-11 calls *"shipped but never called"* a **FAIL**.

**MECHANICAL PRECONDITION, NOT A PARK.** Immediately before editing run
`git status --short services/chat-service/app/services/stream_service.py` (§2 cmd K). **Empty ⇒ edit.
Non-empty ⇒ pull/rebase and re-check.** 🔴 **A dirty file is a wait of MINUTES on a one-clause additive
change to an f-string block. It is NEVER a defer row.**

**SPLIT IT IN TWO, both in-wave:**
- **(a) NOW, zero dependency:** `composition_package_tree` (`mcp/server.py:3712`) and
  `composition_diagnostics` (`:3935`) **ALREADY EXIST** — add their scent **immediately**; this closes
  AN-C2's original FAIL (plan 30:214) with **zero waiting**.
- **(b)** The craft-port tool names (`composition_style_*`, `composition_voice_*`,
  `composition_reference_*`, `composition_decompose`) are appended to the **SAME clause** in the **SAME
  commit that registers them**. 🔴 **Never name a tool that is not yet registered — that manufactures a
  hallucination target.**

**THE EXACT CHANGE:** inside the existing `if _ctx_book_id:` block (`stream_service.py:3751-3765`), append
**ONE clause** to `book_context_note` after the current *"Use these exact ids … never pass a
placeholder."* sentence. **No new gate, no env flag, no setting** — it inherits the existing
`_ctx_book_id` guard. Cost: ~30 tokens on **book-scoped turns only** (the Context Budget Law tolerates it).

**TEST (mandatory — `grep book_context_note services/chat-service/tests` = **0 hits** today, so nothing
enforces this):** **NEW** `services/chat-service/tests/test_stream_service_context_note.py` asserting a
**book-scoped** turn's assembled system prompt **CONTAINS** the literal strings `composition_package_tree`
and `composition_diagnostics` (+ each craft-port tool name added in (b)), **and** that a **non-book-scoped**
turn does **NOT** get the clause. *This is the AN-11 "shipped but never called" FAIL made mechanical
(checklist ⇒ test-the-effect).*

**DOC RECONCILE in the same commit** (stale docs caused this stall): flip **plan 30:343** + its §9 row
(`:715`), **spec 36:512-515**, **spec 37:585-589** from *"sequence after Track C lands / DO NOT TOUCH"* to
*"RELEASED — Track C's `stream_service.py` edits are committed; X-10 builds in-wave."*

**DoD evidence:** `"test_stream_service_context_note.py: 2 passed — a book-scoped turn's system prompt contains composition_package_tree + composition_diagnostics + the craft-port tool names; a non-book-scoped turn does not · git status --short stream_service.py was EMPTY before the edit · D-WAVE6-DISCOVERY-SCENT deleted (premise refuted)"`

---

## 4 · Frontend slices

### **W6-FE0** — `source_work_id` is the predicate: `workSelect` + `useActiveWork` + all 12 sites 🔴
**Kind:** FS · **dependsOn:** — · **RUNS BEFORE EVERY PANEL**

> **Ordering note (a deliberate deviation from spec 36, which puts this in M3).** EC-3d says *"every panel
> calls `useActiveWork`, never `selectCanonicalWork` directly."* If the panels land first and this lands in
> M3, all three panels get **rewritten**. Land the resolver **first** — it is regression-free (with no
> active-work preference, `useActiveWork` === today's `candidates[0]` for every single-Work book) and
> every panel is then built on it from day one.

> **The bug it disarms.** `resolve_by_book` is `ORDER BY created_at, project_id` and a derive requires a
> pre-existing source — so `candidates[0]` is the canonical Work **only because the Studio cannot create a
> derivative today.** This wave arms it. **The predicate is `source_work_id IS NULL`, not "index 0."**
> ⚠ **The predicate must be NULLISH, not `=== null`.** `Work.source_work_id` is **optional** in the FE type
> (`types.ts:19`: `source_work_id?: string | null`) and absent from most fixtures. `w.source_work_id ===
> null` returns **no canonical work** for every pre-C23 book. **Write `!w.source_work_id`.**

**Files**
| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/composition/workSelect.ts` | **NEW** |
| 2 | `frontend/src/features/studio/host/types.ts` | `activeWorkProjectId` + `work:switch` on the bus |
| 3 | `frontend/src/features/studio/host/StudioHostProvider.tsx` | hydrate the pref on mount |
| 4 | `frontend/src/features/composition/hooks/useActiveWork.ts` | **NEW** |
| 5–11 | the **7 studio** `candidates[0]` sites | → `useActiveWork(bookId)` |
| 12–15 | the **4 legacy** `candidates[0]` sites | → `selectCanonicalWork(candidates)` |
| 16 | `services/composition-service/app/routers/internal_model_settings.py` | `rows[0]` → the predicate |
| 17 | `frontend/src/features/composition/__tests__/workSelect.test.ts` | **NEW** |
| 18 | `frontend/src/features/studio/__tests__/noPositionalWorkIdentity.test.ts` | **NEW — the hygiene guard** |
| 19 | `services/composition-service/tests/unit/test_book_model_settings_picks_canonical.py` | **NEW** |

**1 · `frontend/src/features/composition/workSelect.ts`** (NEW)
```ts
// EC-3c — "which Work am I in" is a PREDICATE, not an array index.
//
// `candidates[0]` was correct only because a derive requires a pre-existing source and
// resolve_by_book is ORDER BY created_at — i.e. it was correct because the Studio COULD NOT
// create a derivative. Wave 6 arms it. The predicate is `source_work_id IS NULL`.
//
// ⚠ NULLISH, not `=== null`. `Work.source_work_id` is OPTIONAL in the FE type (types.ts:19) and
// absent from most fixtures — `w.source_work_id === null` returns NO canonical work for every
// pre-C23 book, a silent "this book has no Work" on a book that plainly has one.
import type { Work } from './types';

export function selectCanonicalWork(candidates: Work[] | undefined): Work | null {
  return candidates?.find((w) => !w.source_work_id) ?? null;
}

export function selectDerivatives(candidates: Work[] | undefined): Work[] {
  return (candidates ?? []).filter((w) => !!w.source_work_id);
}

/** The display name for a derivative (BE-13a). Never a bare UUID in a list. */
export function derivativeName(w: Work): string {
  const n = (w.settings as { derivative_name?: unknown } | undefined)?.derivative_name;
  return typeof n === 'string' && n.trim() ? n : 'Untitled dị bản';
}
```

**2 · the bus** — `frontend/src/features/studio/host/types.ts`.
🔴 **CARRY BOTH IDENTIFIERS. The PERSISTED one is the SURROGATE `Work.id`, NOT `project_id`.**
(`Q-36-EC3D-STUDIO-BUS-HAS-NO-ACTIVE-WORK` (1) + `Q-36-OQ7-ACTIVE-WORK-HOME` correction 3 — this plan
originally persisted `project_id` and **that ships a NULL**.)
> **Why:** `composition_work.project_id` is **NULLABLE** (`models.py:52-59`) — a **lazy greenfield Work**
> whose knowledge project could not be created yet carries `project_id = NULL` pending backfill; `id` is
> the **surrogate PK**. **Persisting `project_id` therefore stores NULL for exactly the Works a user just
> created** — *Switch-to* would silently fail to restore them, and the "survives reload" DoD would fail
> **invisibly**. The EXISTING deep-link already matches on the surrogate:
> `(w.id ?? w.project_id) === deepLinkWorkId` (`CompositionPanel.tsx:148`). **ONE identity on the wire =
> the surrogate.** *(EC-3d's name `activeWorkProjectId` is a misnomer; keep the field for the panels that
> need the API key, but never persist it.)*
- `StudioBusEvent` += `| { type: 'work:switch'; workId: string; projectId: string | null }`
- `StudioBusSnapshot` += `activeWorkId?: string;` **and** `activeWorkProjectId?: string;`
- `StudioContextSlice` += `activeWorkProjectId?: string` (so the agent rack sees which Work the user is in)
- `applyBusEvent` case `'work:switch'`:
  ```ts
  case 'work:switch':
    if (e.workId === s.activeWorkId) return base;          // idempotent — no revision churn
    return { ...base,
      activeWorkId: e.workId,
      activeWorkProjectId: e.projectId ?? undefined,
      // 🔴 CLEAR the scene: a scene id is an `outline_node` id scoped to ONE PROJECT
      // (useSceneInspector.ts:26-32 fetches by projectId). Carried across a Work switch it
      // 404s or — worse — edits the wrong Work. Same discipline the 'chapter' case already
      // applies to activeSceneId (types.ts:98). activeChapterId is BOOK-scoped: KEEP it.
      activeSceneId: undefined, selectionRange: undefined, qualityIssueRef: undefined };
  ```

**3 · the persistence tier** — `StudioHostProvider.tsx`. Per **EC-3d + OQ-7**, the active Work is a
**per-user, per-book server preference**, NOT `work.settings` (that blob hangs off the **shared**
`CompositionWork` row whose `created_by` is annotated *"stored, never a scope key / filter (PM-5)"*
(`models.py:56`) — one user switching would move **every collaborator's** Editor: the `entity_kinds`
tenancy bug, re-shipped).
- 🔴 **KEY SHAPE IS LOAD-BEARING: a FLAT DOTTED TOP-LEVEL KEY** — `` `lw_active_work.${bookId}` `` —
  **NOT** a nested `{lw_active_work: {[bookId]: …}}` object. The server merge is **SHALLOW**:
  `prefs = user_preferences.prefs || $2` (`auth-service/internal/api/handlers.go:860` — a **top-level**
  JSONB merge). A nested object would be **REPLACED WHOLESALE**, silently wiping **every other book's**
  active Work on each switch. **Precedent to mirror verbatim:** `modelPicker.recents.<capability>`
  (`frontend/src/components/model-picker/recents.ts:13-15`), dotted-flat for exactly this reason.
- **New file `frontend/src/features/studio/activeWork.ts`**, mirroring `recents.ts`:
  `activeWorkPrefKey(bookId) => \`lw_active_work.${bookId}\`` · `loadActiveWork(bookId, token)` ·
  `saveActiveWork(bookId, workId, token)` → **`savePrefToServer`** (the **awaitable** variant, so the
  reload DoD can order the reload after the durable write — **not** fire-and-forget `syncPrefsToServer`).
- 🔴 **localStorage is CACHE-ONLY and MUST be USER-SCOPED** — copy `recents.ts:21-23`'s
  `cacheKey(..., userId)` guard **verbatim**. An unscoped cache key **leaks user A's active Work into user
  B's server prefs** across a logout/login on a shared browser. *(That exact bug was already caught once
  in a `/review-impl`.)*
- **Hydrate on mount** (a *synchronization* effect — allowed; it is not event handling). ⚠ The busStore is
  created inside `useMemo([bookId])` with a **literal** initial value (`StudioHostProvider.tsx:63-71`), so
  an async pref **cannot** seed it there — it must be an effect that **publishes**:
  ```ts
  useEffect(() => {
    // 🔴 GUARD: SKIP hydration entirely when `?work=` is present, or the late publish CLOBBERS
    // the deep-link (a silent C28 regression — the Living World Tree navigates to
    // /books/{bookId}?work={node.id}, LivingWorldTree.tsx:56-58).
    if (searchParams.get('work')) return;
    let alive = true;
    loadActiveWork(bookId, accessToken).then((workId) => {
      if (alive && workId) host.publish({ type: 'work:switch', workId, projectId: null });
    });
    return () => { alive = false; };
  }, [bookId, accessToken]);
  ```
  *(`projectId: null` on hydration is fine — `useActiveWork` re-derives it from the resolved candidate.)*
- The **write** happens in the divergence panel's *Switch to* handler (W6-M3) — an explicit callback,
  never a `useEffect` reacting to the bus.
- 🔴 **The bus alone is not a persistence tier.** A reload would silently drop the user back into canon
  while the `DerivativeBanner` was the only thing that ever said which Work they were in.

**3b · 🔴 DELETE THE OLD SOURCE OF TRUTH** (`Q-36-EC3D-STUDIO-BUS-HAS-NO-ACTIVE-WORK` (5)).
`CompositionPanel.tsx:134` holds `const [activeWorkOverride, setActiveWorkOverride] = useState<Work|null>(null)`
(used at `:153-157`). **That local `useState` IS the reload-drops-you-to-canon bug EC-3d exists to kill**;
leaving it is **two sources of truth**. `onDerivedWork` now **publishes `work:switch` + persists** instead
of setting local state, and `CompositionPanel` reads `useActiveWork(bookId)` like every other site.
⚠ **The `?work=` deep-link precedence is PRESERVED — it MOVES INTO `useActiveWork` (step 4), it is not
dropped.** D-04 shipped that behaviour; do not regress it.

**4 · `frontend/src/features/composition/hooks/useActiveWork.ts`** (NEW) — **the ONE resolver every panel calls**
```ts
// EC-3d — the resolver, and the reason it is not `selectCanonicalWork`.
//
// EC-3c and "Switch to" CONTRADICT each other if a panel calls selectCanonicalWork directly:
// selectCanonicalWork returns the CANONICAL Work, so a user who switched to a dị bản would have
// the Editor, the navigator, the quality panels and the scene-inspector EACH independently
// re-resolve back to canon. `useActiveWork` is the ONE resolver. `selectCanonicalWork` is the
// FALLBACK inside it, never a panel's entry point.
export type ActiveWorkState =
  | { kind: 'loading' }
  | { kind: 'unavailable' }          // composition-service is DOWN — UNKNOWN, not absent. Never a CTA.
  | { kind: 'no-work' }              // genuinely nothing here — the real answer
  | { kind: 'ready'; projectId: string; work: Work; isDerivative: boolean };

export function useActiveWork(bookId: string, token: string | null): ActiveWorkState;
```
Implementation — 🔴 **it owns the ONE precedence ladder** (`Q-36-EC3D-STUDIO-BUS-HAS-NO-ACTIVE-WORK` (2)):

> **`?work=` deep-link (explicit, THIS navigation) > bus `activeWorkId` (switch-to / hydrated pref) >
> `selectCanonicalWork(candidates)` (fallback).**

1. `const res = useWorkResolution(bookId, token)` (existing).
2. `const host = useOptionalStudioHost()` — 🔴 **optional**, so the SAME hook is safe on the legacy page
   (no host ⇒ no bus ⇒ canon). Subscribe via `useSyncExternalStore(host?._busStore…)`.
3. Build the candidate list: `res.data.status === 'found' ? [res.data.work] : res.data.candidates`.
   *(Every other status — `unmarked_single` / `unmarked_candidates` / `none` / `unavailable` — yields `[]`.
   See the gate note in step 5.)*
4. 🔴 **Match a candidate by the SURROGATE:** `(w.id ?? w.project_id) === id` — **reuse
   `CompositionPanel.tsx:148`'s expression verbatim; do not re-derive it.** `source_work_id` also
   self-refs the surrogate.
   ```ts
   const deepLinkId = searchParams.get('work');            // wins — D-04, already shipped
   const busId      = snapshot?.activeWorkId;
   const byId = (id?: string | null) =>
     id ? candidates.find((w) => (w.id ?? w.project_id) === id) ?? null : null;
   // VALIDATE the persisted id against the LIVE list: an archived/deleted derivative must not
   // strand the studio on a dead Work. Fall back to canon (and clear the stale pref).
   const chosen =
     byId(deepLinkId) ?? byId(busId) ?? selectCanonicalWork(candidates) ?? candidates[0] ?? null;
   ```
   The final `candidates[0]` is the **last-resort** fallback for a corrupt book with **no** canonical row
   (every row has a `source_work_id`; returning `null` would make `CompositionPanel` loop on *"set up
   co-writer"* forever — `CompositionPanel:150`). It must live **inside this one function**, with this
   comment, and **nowhere else in the codebase.**
   🔴 **A resolved deep-link ALSO writes through** (publish `work:switch` + persist), so the URL and the
   pref **converge** instead of fighting on the next reload.
5. `isLoading` ⇒ `loading`; `isError || status === 'unavailable'` ⇒ `unavailable`; no `chosen` ⇒
   `no-work`.
   🔴 **MAP TO `ready` ONLY WHEN A `projectId` ACTUALLY RESOLVES — NEVER by enumerating the Work-less
   statuses** (`Q-36-WORKLESS-STATE-FIRST-CLASS` correction 1). `work_resolution.py:94-109` has **SIX**
   statuses and **FOUR** are Work-less: `none`, `unmarked_single`, **`unmarked_candidates`** (the spec
   omits this one), and — separately — `unavailable` (*"we could not look"*). `if (status==='none' ||
   status==='unmarked_single')` lets **`unmarked_candidates` reach `ready` with an `undefined` projectId**
   — the exact crash this constraint forbids. **The shipped gate already does it by exclusion
   (`useQualityWork.ts:45-52`) — keep that shape.**
   **`unconsulted is not empty, and ambiguous is not absent`.**

**4b · 🔴 `useQualityWork` → `useWorkGate`, and the Work-less state gets a REAL CTA**
(`Q-36-WORKLESS-STATE-FIRST-CLASS` — this plan said *"keep its exported type"*; the register goes
further, and it is right: the gate is now **every** panel's, not just quality's).
1. `git mv frontend/src/features/studio/panels/useQualityWork.ts → useWorkGate.ts`; rename
   `useQualityWork` → `useWorkGate`, `QualityWorkState` → `WorkGateState`. Update the 5 quality call
   sites. Its `ready.projectId` now comes from **`useActiveWork(bookId)`**, not `candidates[0]`.
2. 🔴 **FIX ITS FALSE COMMENT in the same slice.** `useQualityWork.ts:15-17` claims *"`candidates` /
   `unmarked_*` — the book HAS Works."* **Per `work_resolution.py:107`, `unmarked_*` = ZERO marked
   Works.** Only `candidates` (>1 marked) means Works exist. **The code is right; the prose will mislead
   the next reader into treating `unmarked_single` as `ready`.**
3. **NEW `frontend/src/features/composition/components/WorkSetupCta.tsx`** — the ONE Work-less CTA
   (*"Set up the co-writer for this book"*) → `useCreateWork(bookId, token)`.
   🔴 **It MUST carry the `usePendingWorkResolver` handoff** (`useWork.ts:34-80`, D-C16): `onSuccess`, if
   `!created.project_id` ⇒ `pendingResolver.start(created.id)` and render its `resolving`
   (*"Finishing setup…"*) / `failed` (+Retry) states. **WITHOUT this, a create during a knowledge outage
   returns a pending Work that the resolution query EXCLUDES → the refetch says `none` → the button looks
   like it did nothing** — `silent-success-is-a-bug`. Takes an optional `onCreated?: (w: Work) => void` so
   `CompositionPanel.tsx:262-292` passes its guided-first-scene logic and **its inline copy is DELETED**
   (one name, one concept). **Do NOT copy the guided-scene auto-create into the shared component** — it
   needs a `chapterId` the new panels don't have.
4. `QualityNoWorkState.tsx` → `WorkGate.tsx`: `loading` ⇒ Skeleton; 🔴 **`unavailable` ⇒ keep
   `WorkUnavailableState` AS-IS — an ERROR, NEVER a CTA** (offering "create" while composition is down
   invites a **DUPLICATE Work**; the file already argues this at `:29-30`); `no-work` ⇒ **replace the
   dead-end sentence at `:21-23`** (*"start composing a chapter first"*) with `<WorkSetupCta bookId />`.
5. **All FIVE new panels + the plan-hub Decompose action render `<WorkGate state={useWorkGate(bookId,
   token)} testIdPrefix="…"/>`** and use `work.projectId` unconditionally after it. **No spinner, no
   crash, no empty list that reads as "you have none."**

**5–11 · the 7 studio sites** — each replaces its `candidates[0]` line with `useActiveWork(bookId, token)`:

| # | File:line | Today | After |
|---|---|---|---|
| 1 | `studio/manuscript/unit/ManuscriptUnitProvider.tsx:138` | `d.candidates[0]?.project_id ?? null` | `useActiveWork(bookId, token)` → `.projectId` |
| 2 | `studio/manuscript/useManuscriptJump.ts:48` | ″ | ″ |
| 3 | `studio/manuscript/useManuscriptTree.ts:55` | ″ | ″ |
| 4 | 🔴 `studio/panels/EditorPanel.tsx:189` | ″ | ″ — **the Editor itself** |
| 5 | 🔴 `studio/panels/useQualityWork.ts:49` | ″ | → **`useWorkGate.ts`**, delegating to `useActiveWork` (see 4b). **Do not fork a second gate** — its own header says three re-derivations of one gate is what SDK-First exists to stop. |
| 6 | 🔴 `studio/panels/useSceneInspector.ts:31` | ″ | `useActiveWork` |
| 7 | 🔴 `books/hooks/useChapterBrowserGroups.ts:89` | ″ | `useActiveWork` |

**12–15 · the 4 LEGACY sites — IN SCOPE.** The page is **not deleted this wave** (OQ-2), so leaving them on
`candidates[0]` ships the bug on the surface we refuse to delete.
🔴 **They call `useActiveWork` too — NOT `selectCanonicalWork` directly**
(`Q-36-EC3D-USEACTIVEWORK-CONTRADICTION`, the veto-able default the register picked and this plan adopts).
`useOptionalStudioHost()` returns `null` there ⇒ no bus ⇒ **canon**, which is **behaviour-identical** to
calling `selectCanonicalWork` — but it **removes the "which lane am I in" judgment call from the builder**,
which is precisely the mistake EC-3d exists to prevent. Sites:
`composition/components/CompositionPanel.tsx:156` · `composition/components/OutlineTree.tsx:118` ·
`composition/hooks/usePublishGate.ts:51` · `pages/ChapterEditorPage.tsx:218`.
Also re-express `useDerivativeContext.ts:66` (already `!!work?.source_work_id`) as `isDerivativeWork(work)`
so there is **ONE predicate**.

**16 · the BE site** — `internal_model_settings.py:82-86`. It even *documents* the assumption
(*"rows[0] is the canonical manifest… minted before any C23 derivative"*):
```python
    rows = await works.resolve_by_book(book_id)
    # EC-3c: the canonical manifest is the row with NO source_work_id — NOT index 0. `rows` is
    # ORDER BY created_at, so index 0 held only because a derive requires a pre-existing source.
    # Wave 6 lets a user create a derivative; the Book tier of the model cascade must not follow it.
    canonical = next((r for r in rows if r.source_work_id is None), None)
    settings = (canonical.settings if canonical else {}) or {}
    return {"model_roles": model_roles_from_settings(settings)}
```

**Tests**
- `frontend/src/features/composition/__tests__/workSelect.test.ts` (NEW):
  - 🔴 `test_a_derivative_sorted_FIRST_still_resolves_the_canonical_work` — a fixture where
    `candidates[0].source_work_id` is set. *(Impossible today; trivial in a fixture. This is the whole bug.)*
  - 🔴 `test_a_source_work_id_of_undefined_still_resolves` — `{project_id:'p1'}` with **no**
    `source_work_id` key ⇒ canonical. **The `=== null` trap.**
  - `test_selectDerivatives_excludes_canon` · `test_derivativeName_falls_back_when_unset`.
- `frontend/src/features/composition/hooks/__tests__/useActiveWork.test.tsx` (NEW):
  - `test_no_active_pref_resolves_the_canonical_work` · `test_no_host_resolves_the_canonical_work`
    (the legacy-page lane).
  - `test_active_pref_resolves_the_derivative`.
  - 🔴 `test_the_deep_link_WINS_over_the_persisted_pref` — pref `w2` **AND** `?work=w3` ⇒ **w3**.
    *(The anti-clobber guard — D-04 must not regress.)*
  - 🔴 `test_a_work_with_project_id_NULL_still_resolves_by_its_surrogate_id` — **the nullable-project_id
    trap.** A lazy greenfield Work must round-trip.
  - 🔴 `test_a_persisted_id_NOT_in_candidates_falls_back_to_canon` — the archived/deleted-derivative case;
    the studio must not strand on a dead Work.
  - `test_unavailable_is_not_no_work` · 🔴 `test_unmarked_candidates_is_no_work_NOT_ready` (the 4th
    Work-less status the spec omits — it must **never** reach `ready` with an undefined projectId).
  - `test_work_switch_clears_activeSceneId_but_KEEPS_activeChapterId` (the reducer).
- 🔴 `frontend/src/features/studio/host/__tests__/activeWorkPref.test.ts` (NEW) — **the flat-key guard,
  and a single-book test CANNOT catch this bug:** switch Work on **book A** → switch Work on **book B** →
  assert the PATCH body is `{prefs: {'lw_active_work.<B>': …}}` (a **FLAT** top-level key) **and that
  `lw_active_work.<A>` is still intact.** *(Under the nested shape, book B's write silently wipes book
  A's — and a single-book reload test passes anyway.)* Plus: the localStorage cache key is **user-scoped**.
- 🔴 **The reload test that a bus-only implementation FAILS** (`useActiveWork.test.tsx`): mount studio →
  switch to a derivative → **REMOUNT with a fresh bus** (no in-memory state), prefs GET stubbed to return
  `{'lw_active_work.<bid>': '<workId>'}` → **Editor, navigator, scene-inspector AND quality panels are ALL
  still on the derivative.** *(A mount IS a reload. Never call `switchTo` in this test.)*
- 🔴 `frontend/src/features/composition/__tests__/workSelectHygiene.test.ts` (**NEW — the FE hygiene
  guard; C1, refined by `Q-36-HYGIENE-GREP-IMPORT-NOT-LITERAL`**). **Scope it by the IMPORT, not by
  directory** — that is the discriminator that has **zero** false positives by construction:
  ```ts
  // EC-3c mechanized. A COUNT-based DoD is how 9 of the 12 sites were missed the first time — grep
  // for the PATTERN, not a number.
  //
  // ⚠ IN SCOPE iff the file imports `useWorkResolution`. ALL 11 work-resolution sites do; the 3
  // INNOCENT `candidates[0]` files do NOT — components/editor/SceneAnchor.ts:112 (prosemirror heading
  // positions), features/glossary/lib/resolveDisplayValue.ts:35 (attribute sort-order pick),
  // features/plan-forge/components/PlannerPanel.tsx:77 (a chat-safe model list). A repo-wide (or even
  // directory-wide) grep-for-zero reds on day one and teaches the next agent to DELETE the test.
  // Those three are NOT work-resolution. DO NOT "fix" them.
  const ALLOW = ['src/features/composition/hooks/useActiveWork.ts'];   // the ONE last-resort fallback
  it('no work-resolution file resolves "which Work am I in" by array position', () => {
    const inScope = walk('frontend/src', /\.tsx?$/)
      .filter(f => !/__tests__|\.test\.|\/e2e\//.test(f))
      .filter(f => /\buseWorkResolution\b/.test(read(f)))
      .filter(f => !ALLOW.includes(f));
    expect(inScope.length).toBeGreaterThan(0);   // 🔴 a selector that matches NOTHING must RED, not
                                                 //    silently green (the empty-glob guard). NOT toBe(11).
    for (const f of inScope) {
      // \d+, not 0 — a "clever" candidates[1] is caught too.
      expect(read(f), f).not.toMatch(/\bcandidates\s*\[\s*\d+\s*\]/);
    }
  });
  ```
- 🔴 `services/composition-service/tests/unit/test_canonical_work_hygiene.py` (**NEW — the BE guard**).
  ⚠ **A `candidates[0]` grep over `services/` finds ZERO of the real bug and FALSE-GREENS:** the
  server-side site **does not contain that string** — `internal_model_settings.py:85` is
  `rows = await works.resolve_by_book(book_id)` → `rows[0].settings`, and the comment at `:83-84` **states
  the false premise aloud**. (It would *also* red on 5 innocent BE lines: `prose_doc.py:77`,
  `pass2_writer.py:218/541/543`, `run_canon_check_eval.py:137`.) So:
  - (a) add `select_canonical_work(rows)` to composition-service (predicate `w.source_work_id is None`,
    mirroring the FE `workSelect.ts` — and the in-repo precedent `engine/scene_decompile.py:132`);
  - (b) rewrite `internal_model_settings.py:85` to use it **and DELETE the lying comment**;
  - (c) **the hygiene RULE:** grep `services/composition-service/app/**/*.py` — **any file matching
    `resolve_by_book\s*\(` MUST also match `select_canonical_work\s*\(`.**
- `services/composition-service/tests/unit/test_book_model_settings_picks_canonical.py` (NEW,
  `xdist_group("pg")`) — 🔴 **the real proof is a FIXTURE test, not the grep:** `resolve_by_book` returns
  **`[derivative, canonical]`** (derivative sorted **FIRST**) ⇒ `GET /internal/composition/books/{bid}/model-settings`
  returns the **CANONICAL** Work's `model_roles`. *(The server-side twin of EC-3c's `source_work_id:
  undefined` FE test. A fixture with the canon first passes either way and proves nothing.)*
- ⚠ `CompositionPanelDeepLink.test.tsx:84,89` (*"falls back to candidates[0]"*) **stays green only because
  its fixture puts the canon first.** **Rename those to *"…falls back to the CANONICAL work"* and FLIP the
  fixture order** so they actually assert the new behaviour.

**DoD evidence:** `"workSelect.test.ts: 4 passed (incl. test_a_derivative_sorted_FIRST_still_resolves_the_canonical_work and the source_work_id:undefined trap) · useActiveWork.test.tsx: 5 passed (deep-link > bus > canon; project_id:null surrogate; archived-derivative → canon) · workSelectHygiene.test.ts: 1 passed (inScope.length > 0, 0 candidates[N] hits, 1 allowlisted) · test_canonical_work_hygiene.py + test_book_model_settings_picks_canonical.py: 2 passed (derivative sorted FIRST still yields the canonical model_roles) · CompositionPanelDeepLink.test.tsx fixtures FLIPPED · full vitest + composition pytest green at the §2-M baseline counts"`

---

### **W6-M1** — `style-voice`: the CASCADE, not a slider pair (+1 panel)
**Kind:** FS · **dependsOn:** W6-BE4, W6-FE0

> **The two defects this closes.**
> 1. **`useDeleteStyleProfile` exists** (`useStyleVoice.ts:30`) **and `StyleVoicePanel` NEVER CALLS IT.**
>    The DELETE route is a live, tested, **unreachable** capability. There is no way to clear an override.
> 2. 🔴 **The most-specific-wins cascade is real and completely hidden.** `StyleProfileRepo.resolve()`
>    picks `scene > chapter > work`, and `None` ⇒ **the packer stays neutral**. The panel renders
>    `density={row?.density ?? 50}` (`StyleVoicePanel.tsx:131`): **a scene with NO row and a scene
>    explicitly set to 50/50 look IDENTICAL, and a scene inheriting 80/20 from its chapter renders as
>    50/50 — a value the packer will never use.** The GUI **lies about the effective value.** That is SET-1
>    breached in the one place a user can see it, and it is the
>    `a-dirty-signal-computed-but-not-surfaced-per-item-renders-false-fresh` class.
> 3. 🔴🔴 **THE DEFECT BOTH THE SPEC AND THIS PLAN MISSED — AND IT IS THE DANGEROUS ONE**
>    (`Q-36-F-EC1-GUI-LIES-ABOUT-EFFECTIVE-VALUE` §B). **The sliders COMMIT ON POINTER/KEY RELEASE**
>    (`StyleVoicePanel.tsx:34` `onPointerUp={() => onCommit(d, p)}`, `:44` same for pace) → `commitStyle`
>    → **PUT upsert.** So: a user opens a scene that **INHERITS chapter 80/20**, the panel shows the
>    phantom **50/50**, the user **merely TOUCHES a slider** → **an explicit scene row is written at
>    ~50/50, which SHADOWS the chapter's 80/20 PERMANENTLY** (`resolve()` is `LIMIT 1` by rank). And
>    because 50 lands in the **balanced band (34-66 ⇒ NO directive at all**, `profile.py:32-33`), the
>    lush/slow directive **silently vanishes from every future draft with no feedback.**
>    **The GUI does not just lie about the effective value — IT CONVERTS THE LIE INTO PERSISTED TRUTH AND
>    DESTROYS THE USER'S CHAPTER SETTING.**
>    🔴 **ANY FIX THAT ONLY CHANGES THE READOUT AND LEAVES THE COMMIT-ON-TOUCH PATH IS INCOMPLETE.**
>    This is why EC-1 is GG-3's **explicit exception** — a **re-design**, not a verbatim port. Porting it
>    as-is would ship a **data-corruption path** into the Studio.

**Files**
| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/chat-ai-settings/components/TierChip.tsx` | **+4 tier rows** — the ONE FE prerequisite |
| 2 | `frontend/src/features/studio/panels/StyleVoicePanel.tsx` | **NEW** — the dock panel (≤100 lines) |
| 3 | `frontend/src/features/studio/panels/useStyleVoicePanel.ts` | **NEW** — the controller (≤200 lines) |
| 4 | `frontend/src/features/studio/panels/catalog.ts` | 1 row |
| 5 | `frontend/src/i18n/locales/en/studio.json` (+17 locales) | `panels.style-voice.{title,desc,guideBody}` |
| 6 | `services/chat-service/app/services/frontend_tools.py` | enum + description clause |
| 7 | `contracts/frontend-tools.contract.json` | **regenerate** |
| 8 | `frontend/src/features/studio/agent/handlers/compositionEffects.ts` | **EXTEND** (create if Wave 1 hasn't) |
| 9 | `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` | X-3 assertion, if missing |
| 10 | `frontend/src/features/chat-ai-settings/components/__tests__/TierChip.test.tsx` | **NEW/extend** |
| 11 | `frontend/src/features/studio/panels/__tests__/StyleVoicePanel.test.tsx` | **NEW** |

**1 · TierChip — the ONE FE prerequisite of M1.** Its `CLS`/`LABEL`/`TITLE` maps (`:13-38`) know only
`session`/`book`/`account`/`system`/`unavailable`/`no_model_configured`. It **does not throw** on an
unknown tier — it falls back to the raw string with muted styling and no tooltip (C9) — which is **worse
than a crash: the panel ships looking done while every chip reads `scene` in grey.** Add to **all three**
maps:

| tier | `CLS` | `LABEL` | `TITLE` |
|---|---|---|---|
| `scene` | `bg-indigo-50 text-indigo-700 border-indigo-200` | `this scene` | `Set on this scene — the most specific scope; it overrides the chapter and the work.` |
| `chapter` | `bg-violet-50 text-violet-700 border-violet-200` | `this chapter` | `Inherited from this chapter's style. A scene override would win over it.` |
| `work` | `bg-teal-50 text-teal-700 border-teal-200` | `this book` | `Inherited from the book-wide style. A chapter or scene override would win over it.` |
| `neutral` | `bg-muted text-muted-foreground border-border` | **`unset`** | `No row at any scope — the packer adds no density/pace directive.` |

**Extending the ONE chip is the whole point; forking a second one is the defect.**

**2 · `useStyleVoicePanel.ts`** — the controller. It **must compute the cascade the way the SERVER does**
(`StyleProfileRepo.resolve()`: `scene > chapter > work`, `None` ⇒ neutral):
```ts
export type StyleTier = 'scene' | 'chapter' | 'work' | 'neutral';
export interface StyleResolution {
  density: number | null;      // null ⇒ neutral. NEVER default to 50.
  pace: number | null;
  sourceTier: StyleTier;
  /** A row exists at EXACTLY the selected scope ⇒ ClearOverride is offered. */
  hasOwnRow: boolean;
  /** What you'd inherit if you cleared — the value ClearOverride NAMES. */
  inherited: { density: number | null; pace: number | null; sourceTier: StyleTier };
}
```
Resolution, given `rows = useStyleProfiles(pid)` and the selected `scope`:
- Build the candidate chain **for the SELECTED scope**: `scene` ⇒ `[scene(sceneId), chapter(chapterId),
  work(projectId)]`; `chapter` ⇒ `[chapter, work]`; `work` ⇒ `[work]`.
- `effective` = the first chain entry with a row; its `scope_type` **is** the `sourceTier`. No row anywhere
  ⇒ `{density: null, pace: null, sourceTier: 'neutral'}`.
- `hasOwnRow` = a row exists at the chain's **head**.
- `inherited` = resolve the chain **minus its head** (what you'd get after a clear).
- 🔴 **THE ANTI-CLOBBER GATE (the §B fix — non-negotiable).** `onCommit` **MUST NOT FIRE** for a scope that
  has **no row** and **no explicit override opt-in**:
  - selected scope **HAS** a row (`hasOwnRow`) ⇒ sliders live, commit-on-release as today. **Plus** a
    **`Clear override`** button (`data-testid="style-clear-override"`) wired to the **already-built, ZERO-
    consumer** `useDeleteStyleProfile` (`useStyleVoice.ts:30` → the live `DELETE` route). **CONSUME the
    dead code; don't write a new one.**
  - selected scope has **NO** row ⇒ **seed the sliders from the EFFECTIVE (inherited) value** — *not* from
    50, *not* from zero — visually **marked as inherited** (muted + *"Inherited from {tier}"*,
    `data-testid="style-inherited"`), and 🔴 **the WRITE IS DISABLED until the user explicitly opts in via
    an `Override here` button** (`data-testid="style-set-override"`). **This is what kills §B.**
  - **Rationale for the seed (the veto-able default the register picked):** the user's mental model is
    *"I am nudging what is currently in force"*; **starting them at 50 is exactly the phantom that caused
    this bug.** The inherited seed is visually marked and **writes nothing** until `Override here` is
    pressed, so **no value is invented and nothing is silently persisted.**
- 🔴 **`show={!!hasOwnRow}` — ROW EXISTENCE ONLY, never value-equality** (`TierChip.tsx:8-11`). A scene row
  whose density/pace **EQUAL** the inherited chapter values **still** shows `Clear override` and the
  `scene` chip. *(That is the E5 anti-regression test below.)*
- **SERIALIZED, COALESCED, DEBOUNCED commits** (`Q-36-STYLE-VOICE-NO-OCC-CHAIN-WRITES`).
  `style_profile` has **no `version` column** (`migrate.py:513-524`) — the PUT is a true upsert
  (`ON CONFLICT … DO UPDATE`), last-writer-wins **by design**, and
  `instant-commit-control-over-occ-entity` does **not** apply (no version ⇒ nothing to self-412 against).
  🔴 **Do NOT "fix" that by adding a version column** — out of scope, and it breaks the shared-package
  upsert semantics (DA-11).
  **BUT the FE today WILL race:** `useSetStyleProfile`/`useSetVoiceProfile` are plain `useMutation`s
  (`useStyleVoice.ts:18-28, 51-60`) — **N rapid `mutate()` calls fire N PARALLEL PUTs** and the DB commits
  whichever lands last, so **a fast slider drag can persist 62 after the user released at 80.**
  Add an exported `useStyleVoiceWriter(projectId, token)` to `useStyleVoice.ts`:
  ```ts
  const chain   = useRef<Promise<unknown>>(Promise.resolve());   // ONE FIFO chain, panel-wide ⇒
                                                                 // at most ONE PUT in flight, strict order
  const pending = useRef(new Map<string, Body>());               // LATEST-WINS COALESCE, keyed
                                                                 // `style:${scope_type}:${scope_id}` /
                                                                 // `voice:${entity_id}` so a chapter commit
                                                                 // never clobbers a scene commit; a
                                                                 // superseded value is DROPPED, not queued
  const timer   = useRef<number>();                              // 250 ms TRAILING debounce
  // flush — the `.catch` is LOAD-BEARING: one 4xx/5xx must not wedge the chain forever.
  chain.current = chain.current.catch(() => {}).then(async () => {
    for (const [k, b] of drain(pending)) await putFor(k, b);
  });
  ```
  🔴 **INVALIDATE ONLY WHEN THE CHAIN DRAINS.** Move the `invalidateQueries(['composition','style-profiles',pid])`
  + `['composition','grounding',pid]` calls **OUT of the per-mutation `onSuccess`** (`useStyleVoice.ts:23-25,
  36-37, 56-57, 68-69`) and **into the flush tail** (`if (pending.size === 0)`) — otherwise **a mid-drag
  refetch snaps the slider back to a stale server value.** `StyleSliders` local state stays authoritative
  while `dirty`; re-sync from server props **only after the chain drains** — **EXCEPT on error**, where it
  **reverts to the server value** and shows the inline row-level error.
  **Commit on pointer-up / Enter** (`StyleVoicePanel.tsx:33-34, 44-45` already do this — **preserve it on
  the port**). **Never per-keystroke, never on `onChange`.**
  *(The agent path — BE-10's `composition_style_upsert` — **bypasses this chain by design**: a discrete
  human/agent action, last-writer-wins is correct there, and Lane-B's invalidation covers the re-render.)*

**3 · `StyleVoicePanel.tsx`** — render only. Root `data-testid="studio-style-voice-panel"`.
`const host = useStudioHost(); const { bookId } = host;` → `useActiveWork(bookId, token)` (W6-FE0) →
`projectId`. Scope comes off the bus: `activeChapterId` / `activeSceneId` (already published by
`StudioFrame` + `SceneRail`).

| State | Render (the draft ①–④ is the acceptance criterion) |
|---|---|
| loading | `<Skeleton/>` (the sibling convention) |
| **no Work** (`no-work`) | *"Set up the co-writer for this book"* CTA → `useCreateWork`. **Never** a spinner, never a crash, never an empty list that reads as "you have none." |
| **unavailable** | *"Composition service unreachable — this is unknown, not empty."* **NEVER a CTA** (it invites a DUPLICATE Work). |
| scope tabs | `[ Work ] [ Chapter N ] [ Scene M ]` — a tab is **disabled** when no chapter/scene is active |
| **inherited** | numbers **greyed** + the **source** `<TierChip tier="chapter"/>` + *"This scene inherits from Chapter 41. Editing here creates a scene-level override."* — **NO Clear button** |
| **overridden at this scope** | numbers solid + `<TierChip tier="scene"/>` + **`<ClearOverride show inherited={…} onClear={…} testId="style-clear-override"/>`** → `DELETE /style-profile?scope_type&scope_id` |
| **unset everywhere** | `<TierChip tier="neutral"/>` + *"the packer adds no density/pace directive"* — **NOT 50/50** |
| error | inline row-level error; the slider **reverts to the server value** |
| voice: no cast | *"No characters in the glossary yet"* → `host.openPanel('glossary')` |

Voice section: port `VoiceRow` from the legacy panel **verbatim** (it is already a clean props-only view).
Reuse `useCast`, `useVoiceProfiles`, `useSetVoiceProfile`, `useDeleteVoiceProfile` **as-is**.

🔴 **EC-6 — reuse the LEAVES, not `CompositionPanel`.** `CompositionPanel` takes a `soloPanel` prop
(`:89`) that mounts exactly one sub-tab, and it is **tempting** to make this panel
`<CompositionPanel soloPanel="style"/>` and call it DOCK-2 reuse. **DO NOT.** Its body calls **~20 hooks**
before it reaches the slot table (work resolution, cast, derivative context, polish proposals, publish
gate…) and depends on `WorkspaceLayoutContext`. **No new dock panel in this wave mounts `CompositionPanel`
in any mode.**

**8 · Lane-B (X-4) — `compositionEffects.ts`.** ⚠ **NOT a new file** — plan 30 §8.0b: spec 31 (Wave 1)
**CREATES** it; Wave 6 **EXTENDS** it. Two handler files for one domain **DOUBLE-FIRE**
(`matchEffectHandlers` returns EVERY match; `runEffectHandlers` awaits ALL). Add **inside its existing
`registerCompositionEffectHandlers()`**:
```ts
// 🔴 A RegExp, NOT the string 'composition_(style|voice)_'. registerEffectHandler's string branch is
// `tool === p || tool.startsWith(p)` (effectRegistry.ts:41) — NOT a pattern match. A string containing
// alternation matches NOTHING and ships a silent no-op handler that a unit test which registers and
// calls its own fake can never catch. (C10)
// 🔴 PREFIX-INVALIDATE WITHOUT THE ID. `EffectContext` carries only `bookId` (effectRegistry.ts:12) —
// and project_id is a field ON the Work (useWork.ts:56), i.e. bookId !== projectId. A handler that
// builds `[...,'style-profiles', bookId]` is a SECOND silent no-op stacked on the first. Prefix-
// invalidate exactly as the shipped `outlineEffect` does (bookEffects.ts:48-49).
// Grounding's full key is FIVE segments (['composition','grounding',projectId,nodeId,guide] —
// useWork.ts:145), so the prefix is REQUIRED, not incidental.
// Writes only — `_list` is excluded by the (upsert|delete) group.
registerEffectHandler(/^composition_(style|voice)_(upsert|delete)$/, ({ queryClient }) => {
  queryClient.invalidateQueries({ queryKey: ['composition', 'style-profiles'] });
  queryClient.invalidateQueries({ queryKey: ['composition', 'voice-profiles'] });
  // The resolved style surfaces in the GROUNDING preview — the human path already does this
  // (useStyleVoice.ts:24-25). The agent path must not be the one that goes stale.
  queryClient.invalidateQueries({ queryKey: ['composition', 'grounding'] });
});
```
(Over-invalidating another Work's cached profiles is **free** — one Work is open at a time. Widening
`EffectContext` with a `projectId` is a cross-cutting change M1 does not need. **Do not capture a project
id at registration time** — the handler outlives the panel.)
⚠ `registerDefaultEffectHandlers`-style files are guarded by a **module-level `registered` flag** — call
`clearEffectHandlers()` in `beforeEach` **and reset that flag**, or the second test in the file registers
nothing.

**9 · X-3** — if `panelCatalogContract.test.ts` has no `guideBodyKey` guard (§2 cmd B), **add it**:
```ts
it('every palette-openable panel has a guideBodyKey (#19 — agent-mode already eroded this once)', () => {
  expect(OPENABLE_STUDIO_PANELS.filter((p) => !p.guideBodyKey).map((p) => p.id)).toEqual([]);
});
```

**Registration (GG-8) — §6 is the full checklist. Steps 2, 5, 6 land in THIS commit.**

**Tests**
- `TierChip.test.tsx`: 🔴 `test_the_four_new_tiers_render_their_LABEL_not_the_raw_string` — render
  `<TierChip tier="scene"/>` and assert the text is **`this scene`**, not `scene`; likewise
  `chapter`/`work`/`neutral` (`neutral` ⇒ **`unset`**). **This is the C9 fallback trap** — a test that
  only asserts "it rendered" passes on the bug.
- `StyleVoicePanel.test.tsx`:
  - 🔴 `test_an_inherited_scope_renders_the_INHERITED_numbers_and_the_source_chip` — a scene with no row,
    a chapter row at 80/20 ⇒ the sliders read **80/20** (greyed) and the chip says **`this chapter`**.
    **NOT 50/50.** *(This test REDS against the legacy panel's `?? 50` — it is the whole point of M1.)*
  - 🔴 `test_unset_everywhere_renders_neutral_not_50_50` — no rows ⇒ the `neutral` chip + the
    "no directive" sentence, and **no `50`** in the DOM.
  - 🔴 `test_an_explicit_50_is_VISIBLY_DISTINCT_from_unset` — a scene row **at 50/50** renders the `scene`
    chip + *"balanced — no directive"*, visibly distinct from the unset case. **Same prompt, DIFFERENT
    cascade — this is the distinction the old GUI COLLAPSED.**
  - 🔴🔴 `test_ANTI_CLOBBER_touching_an_inherited_slider_writes_NOTHING` — scene **inherits** chapter
    80/20; fire `pointerUp` on the density slider **WITHOUT** clicking `Override here` ⇒ **assert the PUT
    mutation was NOT called.** ***Today this writes 50/50 and DESTROYS the chapter's 80/20.*** **This is
    the §B regression proof and the single most important test in M1.**
  - 🔴 `test_ClearOverride_calls_DELETE_and_the_row_falls_back_to_the_parent` — a scene row exists ⇒
    `ClearOverride` is present, **names the parent's value** (*"clear · inherit 80/20 (from chapter)"*),
    and its click issues `DELETE …/style-profile?scope_type=scene&scope_id=…` **with the exact scope of
    the selected tab** (spy the api module).
  - 🔴 `test_ClearOverride_keys_on_ROW_EXISTENCE_not_value_equality` — a scene row whose density/pace
    **EQUAL** the inherited chapter values **STILL** renders `style-clear-override` **and** the `scene`
    chip.
  - `test_ClearOverride_is_ABSENT_on_an_inherited_scope`.
  - `test_no_work_renders_the_setup_cta_and_unavailable_does_NOT`.
  - `test_rapid_commits_are_chained_not_raced` (`StyleVoicePanel.write.test.tsx`): (a) deferred-promise
    mock of `putStyleProfile`; pointer-up at **60, 70, 80 inside the debounce window** ⇒ **exactly ONE
    PUT, body `density: 80`**; (b) three commits **spaced past** the debounce ⇒ strictly **serial**
    (call #2's mock is not invoked until #1's promise resolves) and **never >1 in flight**; (c) **100
    `onChange` events with no pointer-up ⇒ ZERO PUTs**; (d) a **rejecting** PUT followed by a fresh commit
    ⇒ the second PUT **still fires** (the chain is not wedged) **and the slider reverted**.
  - **One pure unit test of `resolveStyle`** asserting `scene > chapter > work > neutral` and the
    **undefined-id skip** — so the FE mirror of `StyleProfileRepo.resolve()` is **pinned**.
- `handlers/__tests__/compositionEffects.test.ts` — 🔴 **exercise the REAL registration, not a fake.**
  *(A test that registers its OWN pattern and calls it cannot see this bug — that is the entire point.)*
  - `registerCompositionEffectHandlers(); expect(matchEffectHandlers('composition_style_upsert')).toHaveLength(1)`
    — and the same for `composition_voice_upsert`, `composition_style_delete`, `composition_voice_delete`.
    **This single assertion REDS if anyone swaps the RegExp for a string** (C10).
  - `expect(matchEffectHandlers('composition_style_list')).toHaveLength(0)` — effects fire after **writes**
    only.
  - 🔴 `test_the_invalidation_keys_have_NO_4th_element` — assert each key is exactly 3 segments. *(A test
    asserting `[...,'style-profiles', bookId]` would ENSHRINE the second silent no-op.)*
- 🔴 `frontend/src/features/studio/panels/__tests__/no-composition-shell.test.ts` (**NEW — EC-6
  mechanized**; `Q-36-EC6-DO-NOT-REUSE-COMPOSITIONPANEL` (2)). EC-6 is **prose-only today, which is why
  the misreading is live.** Glob every studio source file
  (`import.meta.glob('/src/features/studio/**/*.{ts,tsx}', { query: '?raw', eager: true })`) and assert
  **ZERO** files match the **IMPORT SPECIFIER** regex
  `/from\s+['"][^'"]*components\/CompositionPanel['"]/`.
  ⚠ **Match the SPECIFIER, not the bare token** — `useQualityWork.ts:16`, `popoutRelayContext.ts:3` and
  `StudioPopoutHost.tsx:9` mention `CompositionPanel` **in PROSE COMMENTS** and must not trip it
  (`hygiene-grep-literal-token-in-comment-false-positive`).
  Message: *"Studio panels reuse the LEAVES, not the CompositionPanel shell (spec 36 EC-6)."*
  *(Verified: the invariant HOLDS at HEAD — the only real importer is `pages/ChapterEditorPage.tsx:55`. The
  test goes green on day 1 and **fails the moment someone reaches for `soloPanel`.**)*

**DoD evidence:** `"TierChip.test.tsx: 4 new tiers render their LABEL (not the raw string) + three-way key equality of CLS/LABEL/TITLE · StyleVoicePanel.test.tsx: 9 passed incl. test_ANTI_CLOBBER_touching_an_inherited_slider_writes_NOTHING (RED at HEAD — it writes 50/50 and destroys the chapter row) and test_an_inherited_scope_renders_the_INHERITED_numbers_and_the_source_chip · StyleVoicePanel.write.test.tsx: 4 passed (one PUT for three in-window commits; zero PUTs for 100 onChange) · compositionEffects: matchEffectHandlers('composition_style_upsert').length === 1, keys are 3 segments · no-composition-shell.test.ts: 0 importers of the CompositionPanel shell under features/studio · panelCatalogContract + frontendToolContract + test_frontend_tools_contract green at N_before+1 three-way"`

---

### **W6-M2** — `reference-shelf` (NOT `references`) (+1 panel)
**Kind:** FE · **dependsOn:** W6-FE0

> 🔴 **EC-2 — the panel id is `reference-shelf`, NOT `references`.** This **amends plan 30 §5.2's proposed
> id**, and plan 30 §8.0 has adopted the amendment. **`composition_find_references`** (entity backlinks,
> spec 28 AN-3, `EntityReferencesRepo`) and **the reference shelf** (`routers/references.py`,
> `reference_source`, the author's research corpus) are **two different things sharing a word** — the repo
> itself acknowledges the collision (`entity_references.py:14`). Wave 7 ships a `find-references` lens.
> Two enum members called `references` and `find-references` next to each other, disambiguated only by an
> LLM's guess, is **the exact silent-no-op class the `panel_id` enum was added to kill.** One name for one
> concept.

**Files**
| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/ReferenceShelfPanel.tsx` | **NEW** — a thin studio host over the ported leaf |
| 2 | `frontend/src/features/composition/components/ReferencesPanel.tsx` | **reuse AS-IS** — plus the embed-model header row (below) |
| 3 | `frontend/src/features/studio/panels/catalog.ts` · i18n × 18 · `frontend_tools.py` · the contract | registration |
| 4 | `frontend/src/features/studio/panels/__tests__/ReferenceShelfPanel.test.tsx` | **NEW** |

**The change.** `ReferencesPanel` + `useReferences` are **already clean props-only views over a
self-contained hook** — port the **leaf**, not the shell (EC-6). The studio panel is:
```tsx
export function ReferenceShelfPanel(props: IDockviewPanelProps) {
  useStudioPanel('reference-shelf', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const work = useActiveWork(host.bookId, accessToken);
  const sceneId = useStudioBus().activeSceneId;
  const { data: models = [] } = useUserModels(accessToken);   // the existing ai-models hook
  // … loading / unavailable / no-work states (identical discipline to M1) …
  return (
    <div data-testid="studio-reference-shelf-panel" className="h-full min-h-0 overflow-auto">
      <EmbedModelHeader projectId={work.projectId} />
      <ReferencesPanel projectId={work.projectId} sceneId={sceneId ?? ''} token={accessToken} models={models} />
    </div>
  );
}
```

**`EmbedModelHeader` — EC-2a, v1 is add / **edit-metadata** / delete / retrieve, and it SAYS SO.**
The Work's embedding model is **write-through on the first add** (`references.py:134-137`) and thereafter
**authoritative and immutable** — *"a differing value here is ignored"* (`:54-57`). **This is correct
engineering (one Work = one vector space) reported dishonestly (an invisible, permanent choice made by a
first click).**

🔴 **BE-17 IS IN (C14 — W6-BE7 is a hard prereq of this header).** The plan originally said *"the `_ref` is
NOT exposed by the LIST route today — do not invent a model name"*. **W6-BE7 EXPOSES IT** (the value was
already computed and thrown away). So render the **real** model:
- **set** ⇒ a **read-only** row: `{name} · {source} · set on first add` — **no control that looks
  clickable.** Name-resolution cascade (**all three sources are already in the payload/component**):
  `models.find(m => m.user_model_id === reference_embed_model_ref)?.alias` → else
  `references[0]?.embedding_model` (the provider's own model name, already projected —
  `repositories/references.py:31`) → else the raw ref string.
  🔴 **The 2nd fallback is REQUIRED, not decorative:** DELETE is a **hard** delete while `settings` keeps
  the model, so `references` can be **empty** with `embed_model_set: true`.
  Read it from **the LIST response**, **NOT** by reaching into `work.settings` (one home, one name).
- 🔴 **THE COUNT IS LIVE — NEVER A LITERAL** (`Q-36-OQ4-REFERENCE-COUNT-N`, **OQ-4 is CLOSED: measured
  N = 0** across the whole dev DB). *"Re-embeds all ~50"* would **fabricate the very figure the clause
  exists to make truthful**, and *"re-embed all **0** references"* (the true state for every Work today)
  **reads as a bug.** `ReferencesRepo.list()` has **no LIMIT**, so `references.length` **IS** the exact N
  at render time. Branch on `embed_model_set` with i18n **plural** (`_one`/`_other`):
  - `false` ⇒ `panels.reference-shelf.embedModelUnset`: *"No embedding model yet — the first reference you
    add sets it for this work, permanently."* **(the string "0" appears NOWHERE)**
  - `true` ⇒ `panels.reference-shelf.embedModelLocked` with `{{count}} = references.length`:
    *"All {{count}} references in this work are embedded with {{model}}; changing the model would re-embed
    all {{count}}."* **Do not concatenate a bare number into an English sentence.**
- **unset** ⇒ the picker the panel already renders, **plus** the `embedModelUnset` sentence.
- **X-1 has landed** (W6-M0), so `references-no-embed-model` (`ReferencesPanel.tsx:76`) 🔴 **KEEPS its
  outer `<div data-testid="references-no-embed-model">`** (the existing assertion at
  `ReferencesPanel.test.tsx:62` must keep passing), keeps its sentence, and renders
  **`<AddModelCta capability="embedding" variant="link"/>` INSIDE it.** **Do NOT add a raw `<Link>` and do
  NOT hand-roll a second `openPanel` call here** — the fix lives in the shared component only.
  🔴 **A raw `<Link>` in a dock panel TEARS DOWN THE WHOLE WORKSPACE** (DOCK-7).
  *(Safety valve — only if X-1 somehow did not land: leave `:76` exactly as-is (plain warning div, no
  `AddModelCta` import) and write a defer row. **Never a raw `<Link>` in a dock panel.**)*

🔴 **FIX-NOW — a REAL BUG the shelf/grounding split created** (`Q-36-OQ6-SHELF-VS-GROUNDING-SPLIT` item 2;
**1 line**, and it must land **inside M2**). In `frontend/src/features/composition/hooks/useReferences.ts`,
the `pin` mutation's `onSettled` (~`:61-63`) invalidates **ONLY**
`['composition','references','search',projectId,sceneId]`. It must **ALSO** invalidate
`['composition','grounding', projectId, sceneId]` — the key `useGrounding` feeds `GroundingPanel`.
**Today:** pin a reference in the shelf → the BE **will** pack it (`pack.py:688-703`) → but the grounding
preview keeps rendering a **stale `token_count` / `blocks` / `grounding_available`.** *Shared pin store,
unshared cache.* Mirror `useGroundingPins.ts:30`'s own `onSettled` re-pack.
⚠ **Do NOT add the symmetric invalidation to `useGroundingPins`** — `GroundingPanel` never renders a
reference row, so it cannot flip a reference's pin state. That would be cargo-cult.
**Test (mandatory):** `useReferences.test.tsx` — render the hook with a real `QueryClient`, spy on
`queryClient.invalidateQueries`, call `setPin(hit,'pin')`, assert it was called with **BOTH** keys.

🔴 **DEEP-LINK BOTH WAYS** (`Q-36-OQ6` item 3 — what *"both panels deep-link to each other"* cashes out to):
- In `ReferenceShelfPanel.tsx`'s *"For this scene"* retrieval header, add a text button
  `data-testid="reference-shelf-open-grounding"`, label *"What this scene actually uses →"*, onClick
  `host.openPanel('scene-inspector', { focus: true })`.
  ⚠ **The target id is `scene-inspector`, NOT `grounding`** — **there is no `grounding` panel in the
  catalog**; `GroundingPanel` is a **Section INSIDE** `SceneInspectorPanel` (`catalog.ts:185`;
  `SceneInspectorPanel.tsx:188-192`). **Passing a non-catalog id is exactly the closed-set silent-no-op
  class.**
- In `SceneInspectorPanel.tsx`, on the Grounding `<Section>` header (`:188`), add
  `data-testid="grounding-open-reference-shelf"`, label *"Reference shelf →"*, onClick
  `host.openPanel('reference-shelf', { focus: true })`.
  ⚠ **Put it in `SceneInspectorPanel`, NOT inside `GroundingPanel.tsx`** — `GroundingPanel` is **ALSO**
  mounted by the legacy non-Studio `CompositionPanel.tsx:795`, which has **no StudioHost**; calling
  `useStudioHost()` inside it would **crash/no-op there.**
- **Test:** one vitest per direction asserting `host.openPanel` was called with the **string literal**
  `'scene-inspector'` / `'reference-shelf'` (so a typo reds).

**OQ-6 — the split STANDS, and it is stronger than the spec's framing.** The question's premise
(*"the pinned references GroundingPanel shows"*) is **FALSE: GroundingPanel does NOT show reference items
at all** — it **hard-filters** them (`GroundingPanel.tsx:13` `ADDRESSABLE = ['present','canon','lore']`;
`:17` `ITEM_GROUPS` excludes `'reference'`), even though the backend **DOES** emit `type:"reference"` rows
(`pack.py:702`). **There is nothing to "surface again." DO NOT MERGE THE PANELS**, and **do NOT** add
`'reference'` to `ADDRESSABLE`/`ITEM_GROUPS`. **One concept, one home.**

| State | Render (draft ⑤) |
|---|---|
| no embed model set | the picker + *"this choice is permanent for this book"* |
| embed provider down | `references-unavailable` — *"Retrieval unavailable (embedding provider down)."* The BE already returns a **neutral empty with `unavailable: true`** (`references.py:208-211`) — **render it, do NOT 500.** |
| **no active scene** | library only; the retrieval block is **ABSENT (not empty)** with *"select a scene to see what it retrieves."* |
| empty library | *"No references yet — add influences above."* |
| add in flight | 🔴 **PORT THE EXISTING GUARD — DO NOT DROP IT.** `ReferencesPanel.tsx:82` already has `disabled={!canAdd \|\| refs.add.isPending}` and `:86` already swaps the label to *"Adding…"*. Carry **both** into `ReferenceShelfPanel.tsx` **verbatim**, **plus a first-line `if (refs.add.isPending) return;` in `submit()`** (kills Enter-key/double-fire). **This is a PAID embed call — one at a time. No queue, no batch add in v1.** |
| edit metadata | 🔴 **NEW (BE-17b):** `title`/`author`/`source_url` are **inline-editable** via `PATCH /references/{rid}` — **free, no LLM spend, no re-embed.** *(Today a typo costs a paid delete + re-add.)* |
| delete | immediate; **no undo**. |

🔴 **DELETE MUST GO THROUGH THE SHARED `ConfirmDialog`** (`Q-36-REFERENCE-DELETE-NO-UNDO`; DOCK-9 — **do
NOT hand-roll a `fixed inset-0` overlay**; `dockablePanelHygiene.test.ts` scans for exactly that):
- `const [pendingDelete, setPendingDelete] = useState<ReferenceSource | null>(null)`.
- The library row's ✕ (`data-testid={\`references-delete-${r.id}\`}`) calls `setPendingDelete(r)` — 🔴 **it
  MUST NOT call `refs.remove.mutate(...)`.** *(That is exactly `ReferencesPanel.tsx:132` today, which
  **deletes with no confirm at all** — the defect that must NOT be ported.)* Add
  `disabled={refs.remove.isPending}` to every ✕ so two deletes cannot be in flight.
- `<ConfirmDialog>` from `@/components/shared` with `variant="destructive"`,
  `loading={refs.remove.isPending}`. **NO `confirmationPhrase`** — the typed-phrase escalation is reserved
  for **mass** destruction (a KG rebuild deleting thousands). One row + an honest cost sentence is the
  right ceiling.
- 🔴 **THE COPY — and this is the adjudication that matters:** the cost of deleting **ONE** reference is
  **ONE paid embed call to restore it**, **NOT** *"re-embed all N"*. **That sentence belongs ONLY to the
  read-only embed-model header (EC-2a). Writing it into the delete dialog would be FALSE.**
  - `panels.reference-shelf.deleteConfirm.title` = *"Delete this reference permanently?"*
  - `panels.reference-shelf.deleteConfirm.body` = *"“{{label}}” and its embedding are deleted immediately.
    There is no undo and no trash. To get it back you must paste the passage again — and that costs **one**
    paid embedding call ({{model}}, the model this book is locked to)."*
  - `{{label}}` = `r.title || r.content.slice(0,60)`; `{{model}}` = the **real**
    `reference_embed_model_ref` from the header row (BE-17a put it on the wire) — **never a fabricated
    name**; fall back to the literal *"your embedding model"* only if the LIST somehow lacks it.

**OQ-4: CLOSED — do NOT re-measure.** N = 0 on the dev DB ⇒ **no constant is honest** ⇒ the count is
**live** (see `EmbedModelHeader` above).

**Tests** — `frontend/src/features/studio/panels/__tests__/ReferenceShelfPanel.test.tsx` (**all required
for M2's DoD**):
- 🔴 `test_clicking_the_X_calls_deleteReference_ZERO_times_and_opens_the_dialog` — and the dialog text
  contains **"no undo"** and the **model name**.
- `test_clicking_Confirm_deletes_exactly_once_with_that_rows_id_and_closes` ·
  `test_clicking_Cancel_deletes_ZERO_times`.
- 🔴 `test_while_the_add_is_pending_the_submit_is_disabled_reads_Adding_and_a_second_click_issues_no_second_POST`.
- `test_no_active_scene_hides_the_retrieval_block_entirely` (**absent**, not empty).
- `test_provider_down_renders_references_unavailable_not_a_500` — the BE already returns a **neutral empty
  with `unavailable: true`** (`references.py:208-211`). **Render it; do NOT 500.**
- 🔴 `test_the_header_interpolates_the_LIVE_count` — `embed_model_set:false, references:[]` ⇒
  `embedModelUnset` renders and **the string "0" appears NOWHERE** in the header row; with
  `embed_model_set:true` + **3** refs ⇒ the header interpolates **"3"**. *(That test is what makes the copy
  honest **by construction** instead of honest-by-a-number-someone-measured-once.)*
- `test_the_header_shows_the_real_model_alias_and_has_NO_enabled_edit_control_for_it`.
- 🔴 `test_the_empty_model_state_is_NOT_a_router_Link` — with 0 embedding models **inside a
  `StudioHostProvider`**, `references-no-embed-model` renders and contains **NO anchor element**.
  *This is the DOCK-7 guard — a raw `<Link>` inside the dock destroys the whole workspace.*
- `test_the_two_deep_links_call_openPanel_with_scene_inspector_and_reference_shelf`.

**DoD evidence:** `"ReferenceShelfPanel.test.tsx: 10 passed incl. test_clicking_the_X_calls_deleteReference_ZERO_times_and_opens_the_dialog, test_the_header_interpolates_the_LIVE_count (no literal N), and test_the_empty_model_state_is_NOT_a_router_Link · useReferences.test.tsx: pin invalidates BOTH the references-search key AND the grounding key (the stale-preview fix) · registration green at N_before+1 three-way (M2's own baseline)"`

---

### **W6-M3** — `divergence`: a MANAGE panel, not a wizard launcher (+1 panel)
**Kind:** FS · **dependsOn:** W6-BE3, W6-FE0

> **F-EC3 — the audit is WRONG on all three counts. 🔴 UPDATE included (C13).**
> - 🔴 **UPDATE — REFUTED (this plan was wrong).** It said *"an `entity_override` editor is UNBUILDABLE on
>   today's backend. THE SPEC MUST NOT PROMISE ONE."* **`pack.py:153-157`'s own docstring says the
>   opposite:** *"an edited override takes effect on the next pack."* **The writer is what's missing — and
>   W6-BE6 writes it.** The tables, the UNIQUE index, the repo pattern and the EDIT gate all exist.
>   **The spec section is EDITABLE.** *(See C13; `Q-36-DEFERRED-BE13-DIVERGENCE-SPEC-EDIT`.)*
> - **DELETE — REFUTED. It exists.** `status` ∈ `_UPDATABLE_COLUMNS` (`repositories/works.py:42`) and
>   `WorkPatch` (`works.py:61`), and `resolve_by_book` filters `status = 'active'` (`:268`). So
>   **`PATCH /works/{pid} {status:'archived'}` IS the sibling-consistent soft-delete, today, with If-Match
>   OCC.**
> - **LIST — REFUTED. It is derivable today with ZERO backend work.** `GET /books/{bid}/work` returns
>   `{status, work, candidates[]}`; with >1 marked Work the response is `status:"candidates"` + **every**
>   Work row (`work_resolution.py:93-97`), each carrying `source_work_id` + `branch_point` + **`settings`**
>   (⇒ the BE-13a name — C5). **The canonical Work is the one with `!source_work_id`; the derivatives are
>   the rest.**

**Files**
| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/DivergencePanel.tsx` | **NEW** (≤100 lines) |
| 2 | `frontend/src/features/studio/panels/useDivergencePanel.ts` | **NEW** (≤200 lines) |
| 3 | `frontend/src/features/composition/hooks/useArchiveWork.ts` | **NEW** — the 5th `patchWork` call site |
| 4 | `frontend/src/features/studio/panels/EditorPanel.tsx` | mount `<DerivativeBanner>` in the chrome |
| 5 | `frontend/src/features/studio/panels/catalog.ts` · i18n × 18 · `frontend_tools.py` · the contract | registration |
| 6 | `frontend/src/features/studio/panels/__tests__/DivergencePanel.test.tsx` | **NEW** |

**Reads.** `GET /books/{bid}/work` → `selectCanonicalWork(candidates)` + `selectDerivatives(candidates)`
(W6-FE0). Per **selected** derivative, `GET /works/{pid}/derivative-context` (existing
`useDerivativeContext`).
**Writes.** `POST /works/{pid}/derive` (the ported wizard — **`DivergenceWizard` + `DivergenceWizardSteps`
+ `useDivergenceWizard` port VERBATIM**; the button is replaced by the panel's `+ New divergence`) ·
`PATCH /works/{pid} {status:'archived'}` **with `If-Match`**.

**`useArchiveWork.ts`** — the **only** new `ifMatch` adopter besides the Composition section:
```ts
// EC-4b: a human-paced, conflict-meaningful write ⇒ If-Match is REQUIRED here. It must CHAIN its
// writes and RE-SEED `version` from the response (the plan-hub `onSuccess: qc.setQueryData(fresh)`
// pattern — `instant-commit-control-over-occ-entity`). A 412 is NOT "your edit was lost": reload and
// SAY SO — "changed elsewhere — reloaded" (the SceneRail recovery wording, PH20, verbatim).
export function useArchiveWork(bookId: string, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { projectId: string; version: number }) =>
      compositionApi.patchWork(v.projectId, { status: 'archived' }, token!, { ifMatch: v.version }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] }),
  });
}
```

| State | Render (draft ①–⑥) |
|---|---|
| canonical row | `● <book title> — canonical  [ active ]` |
| **no derivatives** | the canonical row + *"A dị bản branches your book at a chapter and diverges — the source stays read-only."* + the New button. **Not an empty list.** |
| a derivative row | `○ "<derivativeName(w)>"   <taxonomy> · from ch. <branch_point>` + `N entity overrides · M added canon rules` + `[ Switch to ] [ Archive ]` |
| **spec section** | 🔴 **EDITABLE (BE-13 / W6-BE6) — this REPLACES the plan's original "READ-ONLY + the EC-3a note".** `taxonomy` (a closed-set `<select>`) · `pov_anchor` (an entity picker; **clearable** — an explicit `null` CLEARS) · `canon_rule[]` (add/remove). Per-override rows: **edit** (`PUT /overrides/{eid}`) and **remove** (`DELETE`, which **404s on a no-op**, never a silent 204). 🔴 **DELETE the "editing needs BE-13" inline note** — *"a UI that confesses a missing feature"* is the inverse of the sealed GG-1 honesty axis. |
| archive | `ConfirmDialog`: *"Archive this dị bản? Its chapters and knowledge partition are kept; it disappears from this list."* — 🔴 **VERIFIED TRUE: it is a SOFT delete.** `status` is a plain column and `resolve_by_book` filters `WHERE book_id=$1 AND status='active'` (`repositories/works.py:268`) — chapters and the knowledge `project_id` are **untouched**. **Do not soften it, do not imply destruction: the words "Delete"/"Remove"/"Permanently" MUST NOT appear.** Confirm label = **"Archive"**. |
| **412 on archive** | 🔴 **REUSE THE EXISTING i18n KEY `sceneRail.stale`** (`locales/en/studio.json:488` — *"changed elsewhere — reloaded"*), the same key `SceneRail.tsx:63` renders. **Do NOT re-type the literal into a new key** — a duplicated shared string drifts (`css-var-duplicated-across-two-consumers-drifts`). On 412: refetch the works list, **re-seed `version` from the response**, retry sends the fresh `If-Match`. |
| **switch-to** | 🔴 `savePrefToServer('lw_active_work.'+bookId, **work.id**, token)` (the **SURROGATE** — see W6-FE0 §2) **AND** publish `{type:'work:switch', workId, projectId}`. **PERSIST-THEN-PUBLISH** — a fire-and-forget publish that outruns a failed PATCH is the **false-fresh** bug class. The Editor's `DerivativeBanner` lights up. **This is the ONE cross-panel effect in the wave — spec it in the BUS, not in a singleton.** |
| derive in flight | the wizard's own `isSubmitting`. A derive **mints a fresh knowledge project** (`works.py:363-376`) and can **503 `PROJECT_CREATE_UNAVAILABLE`** — **surface that verbatim** (see the error trap below). |
| 🔴 **canon at the branch point** | **`canonview`'s SECOND home** — see below. The wizard's branch-point step renders `CanonAtChapterPanel` for the chapter right before the divergence. **If M3's wizard port silently drops it, the writer branches BLIND.** |
| no Work / unavailable | the `WorkGate` discipline (W6-FE0 §4b), identical |

🔴 **THE ERROR TRAP THAT WOULD MAKE "SURFACE IT VERBATIM" IMPOSSIBLE** (`Q-36-DERIVE-503-PROJECT-CREATE`).
`apiJson` (`frontend/src/api.ts:159-163`) throws `Object.assign(new Error(msg), { status, code: err?.code,
body })` where `err?.code` is the **TOP-LEVEL** body `code`. **FastAPI/composition NEVER sends that** — it
raises `detail={"code": "..."}`. **So `err.code` is `undefined` for EVERY composition error.**
🔴 **The builder MUST read `err.body?.detail?.code`, with `err.status` as the fallback discriminator.
NEVER `err.code`.**
**NEW `frontend/src/features/composition/hooks/deriveError.ts`** — `deriveErrorCode(e)` =
`(e as {body?:{detail?:{code?:string}}})?.body?.detail?.code`, and `deriveErrorMessage(e, t)` switching on
it. Map **ALL FOUR** derive failures (`works.py:355/359/373/375`), not just the 503 — *a bare
`PROJECT_CREATE_FAILED` string is just as user-hostile*:
`PROJECT_CREATE_UNAVAILABLE` (503) · `PROJECT_CREATE_FAILED` (502) · `BOOK_SERVICE_UNAVAILABLE` (502) ·
`SOURCE_WORK_NOT_BACKED` (409) → each a **human sentence with the literal code token inside it** (so a bug
report is greppable) + *"Nothing was created."* Copy lives under `studio.json` → `divergence.error.*`.
**Wire it:** in `useDivergenceWizard.ts`, replace `error:`'s
`(derive.error as Error)?.message ?? 'derive failed'` with
`derive.isError ? deriveErrorMessage(derive.error, t) : null`.

**The `DerivativeBanner` in the Editor** (`EditorPanel.tsx`) — mount `<DerivativeBanner>` (the existing
component) above the editor body, fed by `useActiveWork(bookId).isDerivative` + `useDerivativeContext`
**called with the ACTIVE `projectId`**. 🔴 **Never conditionally unmount the editor** to do it (CLAUDE.md:
it destroys hook state). Render the banner **beside** it, or `hidden` it. **No module-level "current work"
singleton; no local `useState` in the divergence panel** — it is **derived**, always.

---

#### 🔴 `canonview` — THE HOMELESS SUB-TAB THIS SLICE ADOPTS (**home #1 of 2; NO new panel id**)

**What it is:** `CanonAtChapterPanel` — the *"what does canon KNOW as of chapter N"* inspector: **glossary
PRESENCE** and **knowledge CANON-STATE** for that chapter window, **labelled by source distinctly** (two
stores, which **may disagree**), graded major/appears/mentioned.
⚠ **Do NOT confuse it with the two canon panels that DO have homes:** `quality-canon` (shipped) = canon
**ISSUES/violations**; `quality-canon-rules` (Wave 1) = canon **RULE authoring**. **This is neither — it is
a read-only canon SNAPSHOT at a chapter boundary**, and it is mounted **TWO ways** today.

**HOME (a) — HERE, in M3's wizard (LOAD-BEARING).** The wizard port (`DivergenceWizard` +
`DivergenceWizardSteps` + `useDivergenceWizard`, ported **VERBATIM**) **must carry `CanonAtChapterPanel`
into the branch-point step** — canon **right before** the divergence.
🔴 **Add it to the Files table as a row.** **If M3's wizard port silently drops it, the writer branches
BLIND.**
**Test:** `test_the_branch_point_step_renders_the_canon_at_branch_view` (and that it shows the chapter
**before** the branch, not after).

**HOME (b) — a SECTION inside the existing `scene-inspector` panel** (the standalone per-scene use).
**Zero new panel id, zero registration-count change** — it sits beside the already-ported `GroundingPanel`
(`SceneInspectorPanel.tsx:190`), passing the selected node's `chapter_id`.
🔴 **Gate its fetch on the section being OPEN** — it is **4 windowed cross-service reads.**
**Test:** `SceneInspectorPanel.test.tsx` asserts the *"canon as of chapter N"* section renders **and does
NOT fetch while collapsed.**

---

**Tests** — `DivergencePanel.test.tsx`:
- 🔴 `test_a_derivative_is_created_named_listed_switched_to_and_archived` — the end-to-end panel path,
  MSW-mocked. **The name must render** (BE-13a).
- 🔴 `test_switch_to_persists_the_pref_AND_publishes_the_bus_event` — assert **both** the
  `PATCH /v1/me/preferences` body (`{prefs:{'lw_active_work.<bid>': '<WORK.ID>'}}` — 🔴 **the SURROGATE, a
  FLAT dotted key**) **and** the bus snapshot's `activeWorkId`. *(A bus-only implementation passes half of
  this and fails the reload smoke.)*
- 🔴 `test_the_spec_section_is_EDITABLE` — **REPLACES the old `test_the_spec_section_is_read_only_and_names_BE_13`.**
  Editing `taxonomy` PATCHes `/divergence-spec`; **clearing `pov_anchor` sends an EXPLICIT `null`** while
  an untouched field is **OMITTED**; removing an override calls `DELETE /overrides/{eid}`.
- `test_archive_confirm_text_matches_/chapters and knowledge partition are kept/ and does NOT match /delete|permanently|destroy/i`.
- `test_archive_412_renders_exactly_the_sceneRail_stale_value_refetches_and_retries_with_If_Match_2`.
- 🔴 `test_derive_503_surfaces_PROJECT_CREATE_UNAVAILABLE_verbatim` — mock `deriveWork` rejecting with
  `Object.assign(new Error('x'), { status: 503, body: { detail: { code: 'PROJECT_CREATE_UNAVAILABLE' } } })`;
  assert the rendered error **matches `/PROJECT_CREATE_UNAVAILABLE/`** **and does NOT equal `'derive
  failed'`**. ***This is the test that catches the `err.code === undefined` trap.*** Repeat for the
  502/409 codes.
- `test_no_derivatives_renders_the_explainer_not_an_empty_list`.
- 🔴 `test_the_branch_point_step_renders_the_canon_at_branch_view` (canonview home (a)).

**DoD evidence:** `"DivergencePanel.test.tsx: 8 passed incl. test_switch_to_persists_the_pref_AND_publishes_the_bus_event (FLAT key, SURROGATE id), test_the_spec_section_is_EDITABLE (BE-13), test_derive_503_surfaces_PROJECT_CREATE_UNAVAILABLE_verbatim, and test_the_branch_point_step_renders_the_canon_at_branch_view · SceneInspectorPanel.test.tsx: the canon-at-chapter section renders and does NOT fetch while collapsed · registration green at N_before+1 three-way (M3's own baseline) · LIVE: derived a named dị bản in the browser, switched to it, RELOADED — the Editor, navigator, scene-inspector and quality panels are ALL still on the derivative"`

---

### **W6-M4a** — Story structure, the free half: the Composition section + `active_template_id` + the Beats facet
**Kind:** FS · **dependsOn:** W6-BE1, W6-BE2, W6-FE0

> 🔴 **BE-21 (W6-BE2) is a HARD PREREQUISITE, not a nicety.** Without it this section is a **write-only
> editor** and this milestone's own behaviour test reds. Do not start M4a until W6-BE2's
> `test_critic_set_via_model_roles_is_NOT_skipped` is green.

**Part A — the Composition section (NOT a new panel).**
`book-settings` is a **DOCK-2 wrapper over `pages/book-tabs/SettingsTab.tsx`**. The section goes **INTO
`SettingsTab`** — so the **classic book page gets it too** (GG-1 is about *human* surfaces, not *Studio*
surfaces) — as a self-contained `<CompositionSettingsSection bookId />` **with its own save path**
(`PATCH /works`), **NOT folded into the book form's dirty-save bar** (two resources, two saves).

**Files**
| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/composition/components/CompositionSettingsSection.tsx` | **NEW** (≤100 lines) |
| 2 | `frontend/src/features/composition/hooks/useCompositionSettings.ts` | **NEW** (≤200 lines) |
| 3 | `frontend/src/pages/book-tabs/SettingsTab.tsx` | mount it + a `<Divider/>`, after `BookWorldSection` (`:358`), before the save bar |
| 4 | `frontend/src/features/composition/components/CompositionSettingsView.tsx` | **leave it alone** — it is the legacy sub-tab; deleting it is spec 16's job, not this wave's |
| 5 | `frontend/src/features/composition/hooks/__tests__/useCompositionSettings.test.tsx` | **NEW** |

**The rows (draft ⑦).** Every row carries its **source tier** chip. **No row shows a value the engine will
not use.**

| Row | Control | Writes | Tier shown |
|---|---|---|---|
| **Story structure** | `<select>` ← `GET /templates` | `PATCH /works {active_template_id}` | `book` |
| **Prose composer model** | `<ModelPicker capability="chat" …/>` | `settings.model_roles.composer` | `book`, **inheriting `account`** |
| **Critic model** | `<ModelPicker …/>` | `settings.model_roles.critic` | `book`, inheriting `account` — **with the honest warning:** *"the critic is skipped unless it is a **different** model from the drafter"* (`engine.py:1649`) |
| **Planner model** | `<ModelPicker …/>` | `settings.model_roles.planner` | `book` |
| **Assembly mode** | `<select>` `per_scene \| chapter` — **closed set, 422 at the boundary** (`works.py:64-72`) | `settings.assembly_mode` | `book` |
| **Track narrative threads** | toggle | `settings.narrative_thread_enabled` | `book` |
| 🔴 **Capture correction prose** | toggle — **defaults OFF, and SAYS WHAT IT DOES**: *"store the verbatim before/after prose of each correction so the model can learn your taste. Off = structural signal only."* | `settings.capture_correction_prose` | `book` |
| **Reference embedding model** | **read-only** + *"set on first add; changing re-embeds all references"* | — | `book` |

🔴 **EC-4 — this section is the Book-tier WRITER of the model cascade.** It writes
`settings.model_roles.{composer,critic,planner}` through the **existing** role vocabulary. It does **NOT**
add a fourth bespoke `critic_model_ref` picker — that is **SET-8 (one home, one name) violated in the same
commit that cites SET-8.** And **writing BOTH keys to dodge BE-21 is TWO HOMES — the same violation
wearing a hat.** After BE-21: `model_roles` is the one home; the legacy scalar is the read-fallback shim.
The *"Default drafter model"* control is **REUSED as the `composer` writer** — one concept, one control,
one key. It **no longer writes `default_model_ref` at all.**

---

#### 🔴 **FE-21b — THE FRONTEND READ GAP. This slice is NOT optional, and this plan MISSED it.**
(`Q-36-EC4-NO-BESPOKE-CRITIC-PICKER` item 3 + `Q-36-DEFERRED-MODEL-ROLES-DEFAULT-REF` — which also
**DELETES the `D-WORK-MODEL-ROLES-DEFAULT-REF` defer row**; see §9.)

> **The bug this closes.** The legacy scalar has a live FE **writer** *and* **two live FE readers** today:
> writer `CompositionSettingsView.tsx:47` (`patch({ default_model_ref })`, labelled *"Default drafter
> model"*); readers **`EditorPanel.tsx:199`** and **`ChapterEditorPage.tsx:243`** (+ `CompositionPanel.tsx:310`)
> — `work.settings?.default_model_ref` → `persistedDefaultModel` → **the `model_ref` the compose/continue
> call actually POSTs.**
> 🔴 **If the section starts writing `model_roles.composer` and those readers keep reading
> `default_model_ref`, the composer key is WRITE-ONLY IN THE FRONTEND — the identical stored-but-unread
> bug, one layer up — and every existing book SILENTLY LOSES ITS DRAFTER DEFAULT on the M4a deploy.**
>
> 🔴 **AND THE DEFER ROW'S PREMISE WAS FALSE.** It claimed *"8 `scripts/eval_*.py` still read the legacy
> scalar."* **`grep -rn "default_model" scripts/` returns 6 hits, ALL of them `user_default_models`** — a
> provider-registry TABLE, an **unrelated concept**. **No file named `scripts/eval_*.py` exists.** OQ-8's
> author conflated the two. **There is no eval-script blast radius**, so gate #2 has nothing under it and
> the row is **not defer-eligible.** The **real** residual work is **4 frontend lines**, and they are a
> **HARD PREREQUISITE of EC-4** — deferring them ships the exact F-EC4b write-only bug this plan
> congratulates itself for catching, **on the FE side.**

1. **NEW `frontend/src/features/composition/lib/modelRoles.ts`** — the ONE home of the FE dual-read (the
   mirror of BE-21). **Do not re-write the fallback at each call site.**
   ```ts
   export function resolveModelRole(
     settings: Record<string, unknown> | undefined,
     role: 'chat' | 'composer' | 'planner' | 'critic',
   ): { model_ref: string; model_source: string } | null
   ```
   Precedence: `settings.model_roles[role]` → 🔴 **(for `composer` ONLY) `settings.model_roles.chat`** →
   the legacy scalar (`default_model_ref` for chat|composer, `critic_model_ref` for critic) → `null`.
   🔴 **The composer→chat hop is LOAD-BEARING:** the BE shim maps the legacy scalar to role **`chat`**
   (`internal_model_settings.py:61`) while EC-4 writes **`composer`** — **without the hop, every pre-M4a
   book loses its drafter default.** *(W6-BE2 §2's one-line companion closes the other half server-side.)*
2. **Re-point the 3 readers** (preserving each site's downstream logic **verbatim**):
   - `CompositionPanel.tsx:310` → `resolveModelRole(work.settings, 'composer')?.model_ref ?? ''`
     (**keep** the `defaultIsAvailable` stale-model guard and the `inheritedChatModel` /
     `guided.soleModelId` cascade at `:317-321` untouched)
   - `EditorPanel.tsx:199` → `resolveModelRole(composeWork?.settings, 'composer')?.model_ref ?? soleChatModel`
   - `ChapterEditorPage.tsx:243` → identical change.
3. `CompositionSettingsView.tsx:30,47` — the select's `onChange` now patches
   `{ model_roles: { ...settings.model_roles, composer: { model_ref: v, model_source: 'user_model' } } }`.
   ⚠ **Send the WHOLE `model_roles` sub-object** — BE-18's shallow `||` merge operates at the **top-level
   key** `model_roles`, so a partial sub-object **replaces it wholesale** (exactly like `world_map`).
   🔴 **After EC-4 there must be ZERO writers of `default_model_ref` in `frontend/src`** (grep is the check).
4. 🔴 **`model_source` MUST default to `"user_model"` when the picker writes a bare ref**
   (`Q-36-CRITIC-SKIPPED-UNLESS-DISTINCT` (C)) — the engine gate at `:1649` fails on a missing
   `critic_src` **just as hard** as on a missing ref, and the **shipped** drafter picker writes a bare ref
   with no `_source`. **A ModelPicker that writes only `model_ref` would silently re-trigger *"critique
   skipped"* and look like BE-21 never landed.**

**Tests (FE-21b):** `lib/__tests__/modelRoles.test.ts` — map wins; **legacy-only fills composer AND chat**;
explicit composer beats the scalar; empty ⇒ null. **Plus the behaviour twins:**
🔴 `CompositionPanel`/`EditorPanel` with settings `{model_roles:{composer:{model_ref:'m9'}}}` and **NO**
`default_model_ref` ⇒ the posted `model_ref` **is `m9`** *(**this test REDS today** — it is the FE twin of
M4a's critic gate)*; and the **back-compat** test: `{default_model_ref:'m2'}` (no map) ⇒ still `m2` at
**all 3 sites**.

---

#### 🔴 The Critic row's RUN-TIME truth (`Q-36-CRITIC-SKIPPED-UNLESS-DISTINCT` (B)) — the load-bearing half

The config-time warning (below) is only a **PREDICTION**: the engine gate compares the critic against
**`job.input.model_ref`** — *the model the JOB ran with* (`engine.py:1645`) — **not** the composer setting.
**The BE `warning` string is the truth, and TODAY IT IS DROPPED ON THE FLOOR:** `api.ts:557` types
`warning?` and **no consumer reads it**, so a skipped critique resolves `verdict → null`
(`CriticPanel.tsx:42-49`) and falls into the **`critic-empty`** branch (`:82-87`), which renders *"No
verdict yet — generate a scene (**or re-check the current draft**)…"*
🔴 **i.e. the user clicks "Re-check current draft", it runs, and the panel tells them to re-check the
current draft.**

**FIX (in this slice):** in `CriticPanel`, when `critique.data?.warning` is present, render a **distinct**
state `data-testid="critic-skipped"` **INSTEAD OF** `critic-empty`:
*"Critique skipped — the critic model is not set, or is the same model as the drafter. Set a different
Critic model in Book settings → Composition."* **+ a deep-link to that section. This state MUST WIN over
`critic-empty`.**

**Config-time copy (the Critic row):** (1) the always-on honest hint *"The critic is skipped unless it is a
different model from the drafter."* (2) a **LIVE predictive warning** — when the selected critic
`model_ref` **===** the effective composer `model_ref`, an inline amber note
`data-testid="composition-critic-same-as-composer"`: *"Same model as the drafter — critiques will be
SKIPPED. Pick a different model."* 🔴 **WARN, DO NOT BLOCK the write** (a user with one BYOK model can
still save critic == drafter and gets an honest "skipped" everywhere, rather than being locked out).

**Source tiers** come from `useChatAiSettingsOptional()?.effective.models[role]` — `ModelRole` already
includes `composer | planner | critic` and `ModelResolution` already carries `source_tier` + `tier_stack`
(C7). Render `<TierChip tier={res.source_tier}/>` + `<ClearOverride show={res.source_tier === 'book'}
inherited={res.tier_stack.account?.model_ref} onClear={…}/>` — and **clearing writes
`settings_unset: ['model_roles']`**… ⚠ **no.** `settings_unset` removes a **top-level** key. To clear ONE
role, read the current `model_roles`, delete the role, and PATCH the whole `model_roles` sub-object
(shallow-merge replaces it wholesale — exactly like `world_map`). Write that in the hook's comment.

**`useCompositionSettings.ts` — the save path (EC-4b):**
```ts
// EC-4b — this is a HUMAN-PACED, CONFLICT-MEANINGFUL write ⇒ If-Match REQUIRED, and it CHAINS.
// It must RE-SEED `version` from the response after every write (the plan-hub usePlanNodeWrites
// pattern): without that, the controls re-enable while `work.version` is still the PRE-write
// value, the next toggle sends a stale If-Match, 412s, and blames a phantom collaborator for your
// own click (`instant-commit-control-over-occ-entity-needs-write-serialization`).
//
// ⚠ Do NOT put If-Match on `patchWork` itself. It is a SHARED writer with 5 call sites, one of
// which (useWorldMap → node drag) is an instant-commit control. A blanket If-Match makes the world
// map 412 against ITSELF on the second drag.
const versionRef = useRef(work.version);
const chain = useRef<Promise<unknown>>(Promise.resolve());
const save = (patch: Record<string, unknown>) => {
  chain.current = chain.current.catch(() => {}).then(async () => {
    const fresh = await compositionApi.patchWork(
      projectId, { settings: patch }, token!, { ifMatch: versionRef.current },
    );
    versionRef.current = fresh.version;                 // RE-SEED — the whole point
    qc.setQueryData(['composition', 'work', bookId], /* merge fresh */);
  });
};
// A 412 ⇒ refetch + "changed elsewhere — reloaded" (PH20 wording). NEVER a silent overwrite.
```
**No blob spread needed** — BE-18's server-side shallow merge means `{settings: {critic: …}}` no longer
clobbers siblings. (Keep sending only the changed key; do **not** re-introduce a hand-merge.)

**Part B — `active_template_id` becomes the ONE home of the book's story structure (EC-5).**
> **`composition_work.active_template_id` is a WRITE-ONLY COLUMN.** Declared (`migrate.py:39`), updatable
> (`repositories/works.py:42`), accepted by `PATCH /works` (`works.py:60`), typed in the FE (`types.ts:7`)
> — and **read by NOTHING**: zero hits in `routers/`, `engine/`, `packer/`, and zero non-test hits in
> `frontend/src`. Decompose takes `structure_template_id` in the request body **every single time**
> (`plan.py:71`). **The book's story structure has a home in the schema and no resident. FILL IT.**

- the Composition section **PICKS** it (`PATCH /works {active_template_id}`);
- the Decompose action (M4b) **DEFAULTS** to it and **writes it back on commit**;
- the Beats facet **READS** it.
- `structure_template_id` stays on the decompose request (a per-run override) — but it is no longer the
  only place the answer lives.

**EC-5a — user-authored structure templates (BE-12) are OUT of v1** (§9 OQ-1, DECIDED: **defer**). The
picker renders the **6 System-tier built-ins** and — where a real user would expect *"save my own"* — an
**honest empty affordance**, not a disabled button with no explanation: *"Custom structures aren't
authorable yet — the 6 built-ins are read-only (they're shared by everyone)."*
⚠ **Tenancy is the whole job of BE-12**: the 6 built-ins are `owner_user_id IS NULL` = **System tier**; a
regular user must **CLONE**, never mutate the shared row (the `entity_kinds` bug). Do **not** ship a
half-measure.

**Part C — the Beats facet in `PlanDrawer` (PH16, F-EC5a). ZERO backend.**
> Spec 24 **PH16** names the chapter/scene facet set as *Overview · **Beats** · Canon here · References ·
> Critic*. What shipped (`PlanDrawer.tsx:232-293`) is Overview · Cast & Setting · Craft · Canon here ·
> Open threads · References (empty) · Critic (empty). **Beats is ABSENT**, and `beat_role` is a read-only
> `<Field>` inside Overview (`:236`). Yet `beat_role` **IS** REST-writable today (`NodePatch`,
> `outline.py:88`, If-Match guarded) **and `NodeEdit` already declares it and `patchNode` already sends
> `If-Match`** (C6).

**Files:** `frontend/src/features/plan-hub/components/PlanDrawer.tsx` (+ a `PlanDrawerBeats.tsx` if it
pushes past ~100 lines) · `frontend/src/features/plan-hub/components/__tests__/PlanDrawerBeats.test.tsx`.

- A new `<Section title="Beats" testid="plan-drawer-section-beats">`, placed **immediately AFTER Overview**
  (PH16 order, draft ⑧). **DELETE the read-only `<Field label="Beat role">` at `:236`** (it moves here).
- **NEW `frontend/src/features/plan-hub/hooks/useBeatsFacet.ts`** (controller, no JSX) — composes two
  **EXISTING** hooks: `useWorkResolution(bookId, token)` + `useStructureTemplates(token)`. Resolve
  `activeTemplate = templates.find(t => t.id === work.active_template_id) ?? null`. Expose
  `setActiveTemplate(id)` → `patchWork(work.project_id, { active_template_id: id })` → invalidate
  `['composition','work',bookId]`.
  ⚠ Call it in the `PlanDrawer` body **BEFORE** the `if (!selectedId) return null` guard (Rules of Hooks).
- 🔴 **`no active_template_id` ⇒ AN IN-PLACE TEMPLATE PICKER, *NOT* A DEEP-LINK**
  (`Q-36-F-EC5A-BEATS-FACET-MISSING`). **This plan originally deep-linked to `host.openPanel('book-settings')`
  — DO NOT.** *Today `active_template_id` is NULL for **every real book** (nothing writes it), so the facet
  would show its empty state **100% of the time**, and `book-settings` (`BookSettingsPanel.tsx:25`) is the
  **BOOK-service** tab (title/cover/genre/world) — it has **no structure control** and does not own the
  composition Work, so that deep-link would **do nothing** (the PH7 dead-link/lie class, the exact thing
  `PlanDrawer.tsx:9-12` exists to prevent).*
  ⇒ render an in-place `<select>` (reuse `BeatSheetView.tsx:104`'s pattern), options = templates by name,
  placeholder *"— choose a story structure —"*, copy: *"No story structure chosen for this book — pick one
  to enable beats."* → `setActiveTemplate`. **NO deep-link.**
  *(M4a Part A's Composition-section picker writes the **same one home** — `PATCH /works {active_template_id}`
  — so this is **one KEY with two controls**, not two homes. SET-8 governs the DATA, not the affordance
  count.)*
- **`activeTemplate` present ⇒ a CLOSED-SET beat `<select>`, NEVER free-text.** Options =
  `activeTemplate.beats` sorted by `order`, `value=beat.key` / text=`beat.label`, plus a *"— no beat —"*
  option (`''` → `null`). Render the selected beat's `purpose` (`migrate.py:1629` carries it) as helper text.
  🔴 **When `node.beat_role` is set but NOT in this template's key set**, render an extra
  `<option value={node.beat_role}>{node.beat_role} (not in this structure)</option>` **as the selected
  value** (mirroring `PlanDrawerEdit.tsx:151`'s unknown-status pattern) — **so a template switch never
  silently rewrites the row.**
- Writes `writes.edit(node.id, node.version, { beat_role: v || null })` — the **existing**
  `usePlanNodeWrites.edit`, which already sends `If-Match` and already recovers a 412 with *"That node
  changed elsewhere — the drawer reloaded."* **Nothing new** (C6).
- **`writes` absent (no EDIT grant)** ⇒ render the beat's label as a plain read-only `<Field>`, **no
  control** (`PlanDrawer.tsx:47-48` convention: **never render a control that would 403**).
- 🔴 `frontend/src/features/composition/components/BeatSheetView.tsx:69` — **seed its local `templateId`
  state from `work.active_template_id`** (keep the local override). Today it persists nothing, so the
  drawer and the Beat Sheet would **disagree on which structure the book uses** — one concept under two
  names (DA-10).
- **Keep the shipped Cast & Setting / Craft / Open-threads facets** — they are strictly *more* than PH16
  lists and are REST-writable. **Only ADD Beats.**
- ⚠ **`PlanDrawer.tsx` is the Book-Package track's file** (plan 30 §9). **Read its git history first**;
  coordinate before editing.

**Tests**
- `useCompositionSettings.test.tsx`:
  - 🔴 `test_two_concurrent_patches_to_two_different_keys_both_survive` (the BE-18 merge, through the hook).
  - 🔴 `test_a_stale_same_key_patch_412s_and_reloads` — and the message is **"changed elsewhere — reloaded"**.
  - 🔴 `test_a_world_map_drag_does_NOT_412` — **the EC-4b regression guard.** Drive `useWorldMap`'s
    `persistPositions` twice in a row with a stale cached `work.version`; assert **zero 412s** (it must
    send **no** `If-Match`).
  - `test_the_section_writes_model_roles_and_NOT_critic_model_ref` — assert the PATCH body has
    `settings.model_roles.critic` and **no** `critic_model_ref` key.
  - `test_every_row_renders_a_source_tier_chip`.
  - `test_clearing_a_role_patches_model_roles_without_that_role`.
- 🔴 **DoD-3 — A BEHAVIOUR TEST PER SETTINGS KEY (SET-4 — "consumed, proven by effect"). *Writing the blob
  is NOT evidence.*** `Q-36-BEHAVIOUR-TEST-PER-SETTINGS-KEY` settles this as an **EXACT 8-ROW MATRIX — no
  more, no less.** **Rows A–C ALREADY EXIST at HEAD: CITE them in the VERIFY evidence, do NOT rewrite them.**

  | Row | Key | Test | Status |
  |---|---|---|---|
  | **A** | `capture_correction_prose` | `tests/unit/test_correction_router.py:198` `test_raw_prose_captured_when_opted_in` (+ the default-off assert at `:195`). Consumer: `engine.py:1766`. | ✅ **ALREADY GREEN — cite it.** *(This plan proposed writing a NEW `test_capture_correction_prose_effect.py`. **Don't** — it exists.)* |
  | **B** | `assembly_mode` | `tests/unit/test_assembly_mode.py` (override > setting > default + the 422 closed set). Consumer: `engine/assembly.py:29`. | ✅ **ALREADY GREEN — cite it.** |
  | **C** | `narrative_thread_enabled` | `tests/unit/test_pack.py:364/384/393`. Consumer: `packer/pack.py:318`, `engine.py:254,272`. | ✅ **ALREADY GREEN — cite it.** |
  | **D** | `model_roles.critic` | **W6-BE2's** `test_critic_set_via_model_roles_is_NOT_skipped` + `test_critic_same_ref_as_drafter_STILL_skips` + the legacy-fallback + the `critic_model_ref`-absent hygiene assert. | 🔨 **NEW (W6-BE2)** |
  | **E** | `model_roles.composer` / `.planner` | 🔴 **Their consumer is NOT composition — it is chat-service.** `ai_settings.py:194` reads the book's `model_roles` into the **Book tier** of the resolve cascade (role set closed at `settings_resolution.py:28-39`). So the behaviour test lives in **`services/chat-service/tests/`**: with the composition client stubbed to return `{"composer":{"model_ref":"X","model_source":"user_model"}}`, the effective-settings read returns `models.composer.effective_value == "X"` and `source_tier == "book"`. Same for `planner`. **⇒ These keys are NOT write-only. SET-4 is satisfiable with no extra BE work.** | 🔨 **NEW (chat-service)** |
  | **F** | BE-18 merge | `tests/unit/test_works_repo_settings_merge.py` (W6-BE1). | 🔨 **NEW** |
  | **G** | EC-4b guard | `useWorldMap.test.tsx`: the drag write sends **NO `If-Match`**; the section's save **DOES** pass `ifMatch: work.version`. **A blanket-ifMatch implementation must RED here.** | 🔨 **NEW** |
  | **H** | `active_template_id` + `beat_role` | `PlanDrawer.beats.test.tsx` (below) + *"every row of the §4 table renders its effective value AND its source-tier chip"* (the *no silent hidden default* half of SET-4). | 🔨 **NEW** |

  **Not in the matrix (deliberately):** `reference_embed_model_ref` is a **READ-ONLY display row** — its
  consumer is already proven (`references.py:92`) and **a read-only display row is not a settings write.**
  `derivative_name` is covered by M3's DoD.
- `PlanDrawer.beats.test.tsx`:
  - `test_the_beat_selector_is_fed_by_the_template_not_free_text` — a `<select>` whose options are exactly
    the template's `beats[]` + *"— no beat —"*, and **NO text input in the section**.
  - `test_changing_the_beat_role_patches_the_node_with_If_Match` · `test_no_beat_sends_beat_role_null`.
  - `test_a_412_says_changed_elsewhere_reloaded`.
  - 🔴 `test_a_beat_role_not_in_the_active_template_renders_not_in_this_structure_and_fires_NO_write`.
  - 🔴 `test_no_active_template_renders_the_IN_PLACE_picker_and_picking_one_PATCHes_active_template_id` —
    **REPLACES `test_no_active_template_deep_links_to_book_settings`** (that deep-link is dead; see above).
  - `test_no_writes_prop_renders_a_read_only_label_and_NO_select`.

**DoD evidence:** `"useCompositionSettings.test.tsx: 6 passed incl. test_a_world_map_drag_does_NOT_412 and test_the_section_writes_model_roles_and_NOT_critic_model_ref · modelRoles.test.ts + the FE behaviour twins: a work with ONLY model_roles.composer posts that model_ref (RED at HEAD) and {default_model_ref:'m2'} still resolves at all 3 sites · DoD-3 matrix: A/B/C cited as already-green (test_correction_router.py:198, test_assembly_mode.py, test_pack.py:364), D/E/F/G/H new and passing · test_critic_set_via_model_roles_is_NOT_skipped GREEN · CriticPanel renders critic-skipped (not critic-empty) when the BE returns a warning · PlanDrawer.beats.test.tsx: 6 passed · grep 'default_model_ref' frontend/src ⇒ 0 WRITERS · LIVE: set the critic model in book-settings → a critique run no longer returns 'critique skipped'"`

---

### **W6-M4b** — the Decompose action in `PlanDrawer`
**Kind:** FS · **dependsOn:** W6-BE5, W6-M4a · **CROSS-SERVICE ⇒ mandatory live-smoke**

> **EC-5b — the Decompose action goes through the generic Tier-W spine (BE-20). It does not ship before
> that spine exists.** Shipping a new button that spends LLM tokens with no estimate and no billing
> precheck, in the wave whose whole thesis is *"the human deserves the same rails the agent has"*, would be
> **self-refuting.** M4 is split precisely so the free half (Beats facet, structure one-home) is not held
> hostage.

**Files:** `frontend/src/features/plan-hub/components/PlanDrawerDecompose.tsx` (**NEW**) ·
`frontend/src/features/plan-hub/hooks/useDecomposeAction.ts` (**NEW**) · `PlanDrawer.tsx` (mount it on the
**chapter** variant) · `handlers/compositionEffects.ts` (the decompose Lane-B handler) · tests.

**The flow (draft ⑧):**
*"Decompose with a structure…"* on a **chapter** node's drawer →
`FormDialog` (structure ▾ **defaulting to `active_template_id`** · premise · model via `<ModelPicker>`) →
**`mcpExecute('composition_decompose', args)`** → `{confirm_token, estimate}` →
**`GET /v1/composition/actions/preview?token=`** → the confirm card renders the **real estimate** →
**`POST /v1/composition/actions/confirm?token=`** →
`202 + job_id` → 🔴 **`ui_watch_job` → the `job-detail` panel** (PO-3 — `ui_watch_job` is now a studio tool
+ intercepted; it must **NOT** route-navigate and tear down the dock) →
on success, a **preview tree** the user accepts → `POST /works/{pid}/outline/decompose/commit` →
**and write `active_template_id` back on commit** (EC-5's one-home).

🔴 **NEVER a bespoke per-action estimate route.** Plan 30 §3.3: **three such invented routes 404 in
production today** (`/actions/conformance_run/estimate`, `/actions/conformance_run/confirm`,
`/scenes/{nid}/regenerate-to-beat`). The gateway is a **pure path-preserving proxy** — an FE path with no
BE route 404s and nothing saves it. **Use the GENERIC `/actions/preview` + `/actions/confirm` pair.**

| State | Render |
|---|---|
| **Work-less book** | the action renders **DISABLED WITH A REASON** (PH7 visible-fallback): *"Decompose needs a co-writer Work — set one up first"* **AND an inline `<WorkSetupCta>`** (W6-FE0 §4b) — **PH7's visible-fallback means the user can ACT, not just read a reason.** Gate it on the SAME `useWorkGate(bookId)`. `unavailable` ⇒ disabled + *"Could not reach the co-writer service."* `loading` ⇒ disabled. **Never a dead button.** |
| **already-planned chapter** | 🔴 **409 `CHAPTER_ALREADY_PLANNED`, NOT 400** (`plan.py:734-739` — **spec 36 says 400 and is WRONG; fix that line while building**). Handle it **BOTH ways**, and **PORT the working pattern — do not invent one**: **(a) REACTIVE (authoritative)** — the guard runs **INSIDE `commit_decomposed_tree`'s Tx** (a **TOCTOU-closed** race), so it can fire **even when the tree looked unplanned at dialog time**. Copy `usePlanner.ts:38-48` (`asPlannerError` — reads `err.body.detail.code` + `.chapter_ids`) and `:115-133` (`doCommit(replace)` → `onError`: `409 + CHAPTER_ALREADY_PLANNED` ⇒ `setNeedsReplace(pe.chapterIds)`). Render like `PlannerView.tsx:105-114`. 🔴 **The i18n keys ALREADY EXIST** (`locales/en/composition.json:416-419` — `plan.replace_title` / `replace_prompt` / `replace_confirm`) — **reuse them, do not mint new ones.** **(b) PROACTIVE** — a *"Replace the existing N scenes"* **checkbox, default UNCHECKED, rendered ONLY when the chapter node has ≥1 scene child.** **It is a convenience, NOT the gate** — the 409 handler stays, because **a checkbox cannot see a concurrent write.** ⚠ `replace` is on `CommitRequest`, **not** `DecomposeRequest`. |
| **empty plan** | 🔴 **TODAY IT RENDERS THE LITERAL STRING `EMPTY_DECOMPOSE_PLAN` — that IS the "something went wrong" bug, and it is REAL AT HEAD.** The BE puts its prose under `detail.**detail**` (`plan.py:682-687`), but **`frontend/src/api.ts:152` picks `o.message ?? o.code` — `.detail` is NEVER read**, so the thrown Error's message is the **bare code**. And `PlannerView.tsx:26-32`'s `errorText` maps only NO_CHAPTERS / TOO_MANY_CHAPTERS / BAD_ENTITY / BAD_CHAPTER — **`EMPTY_DECOMPOSE_PLAN`, `BAD_REFERENCE` and `CONSTRAINT` all fall through.** **TWO fixes, BOTH required:** ① 🔴 `frontend/src/api.ts:152` → `const picked = o.message ?? o.detail ?? o.code;` (**widens the FastAPI `{code, detail}` picker — fixes the whole class in ONE line**; add a unit test asserting a `{detail:{code,detail}}` 400 throws with the **prose**, not the code). ② Port `errorText` into `plan-hub/components/` and **ADD the missing arms**: `EMPTY_DECOMPOSE_PLAN → t('plan.err_empty_plan')` · `BAD_REFERENCE → t('plan.err_bad_reference')` · `CONSTRAINT → e.message`. New `en` key: *"The planner produced no scenes for any chapter — it likely degraded. **Nothing was committed.** Try again, or pick a different model."* (+ the sibling locales via `scripts/i18n_translate.py`). |
| **empty plan — PREVENT it, don't just report it** | 🔴 `EMPTY_DECOMPOSE_PLAN` is raised at **COMMIT**, so an all-empty preview tree **can still be submitted today** (`PlannerView.tsx:122` disables Commit only on `committing \|\| needsReplace`). **Disable Commit when `totalScenes === 0`** and show the same prose inline under the preview tree (each chapter's preview `warning` says WHY). Keep the 400 handler as the backstop. |
| **no chapters** | 400 `NO_CHAPTERS` — *"decompose maps onto existing chapters — create chapters first."* Render verbatim. |
| **no structure** | 🔴 **NEW 400 `NO_STRUCTURE_TEMPLATE`** (EC-5) — *"no story structure chosen for this book — pick one in the Composition section, or pass one for this run."* |
| **402** | *"Not enough budget for this run"* + the estimate. The precheck fired **before** the LLM. |

🔴 **THE 202 PATH MUST NOT REUSE THE LEGACY SELF-POLLER (a PO-3 conflict).**
`frontend/src/features/composition/api.ts:273-288` (`decomposePreview`) **swallows the job by polling
internally and throws the opaque literal `'decompose failed'`** — **exactly** the banned *"something went
wrong."* For M4b add a **NEW `decomposeStart(projectId, body, token): Promise<{job_id}>`** in the plan-hub
api that returns the **202 envelope WITHOUT polling**; the drawer hands `job_id` to **`ui_watch_job` →
`job-detail`** (PO-3), which renders the **real** failure reason. **Leave the legacy `decomposePreview`
untouched** (the legacy page still uses it). On job `completed`, `job.result` **IS** the `DecomposePreview`
→ render the preview tree → the user accepts → `POST /outline/decompose/commit` with
`{replace, idempotency_key, structure_template_id}` (the EC-5 write-back).

**Lane-B** (`Q-36-DECOMPOSE-EFFECT-ON-JOB-COMPLETION`): **register NO handler on `/^composition_decompose$/`
and NONE on `confirm_action`** — the propose returns a **token** (nothing happened) and the confirm returns
`action_accepted` (**only ENQUEUED** — still nothing happened). 🔴 **Register on the POLL tool, gated
TWICE:**
```ts
registerEffectHandler(/^composition_get_generation_job$/, decomposeJobEffect);

export function decomposeJobEffect(ctx: EffectContext): void {
  const job = unwrapToolResult(ctx.result) as { status?: string; operation?: string; project_id?: string } | null;
  if (!job || job.status !== 'completed') return;                    // pending/running/failed ⇒ NO effect
  if (job.operation !== 'decompose_preview' && job.operation !== 'plan_pipeline') return;
  // ^ 🔴 the SAME poll tool serves motif_mine / arc_import / conformance_run — WITHOUT this guard a
  //   completed CONFORMANCE run would blow away the outline cache.
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'outline'] });
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'decompose', job.project_id] });
  ctx.queryClient.invalidateQueries({ queryKey: ['plan-hub'] });
}
```
🔴 **`unwrapToolResult` (`resultEnvelope.ts`) is MANDATORY** — the live stream nests the domain payload
inside the `{ok,result}` envelope, and **reading it bare returns `undefined` while unit tests stay green**
(`bookEffects.ts:19-28` documents that exact bug).
**The HUMAN plan-hub dialog is untouched by Lane-B** — no chat tool call ⇒ the reconciler never sees it ⇒
**no double-refresh.**

**Tests** — `useDecomposeAction.test.ts` + `PlanDrawerDecompose.test.tsx` + `compositionEffects.test.ts`:
- `test_the_structure_select_defaults_to_active_template_id`.
- `test_a_work_less_book_disables_the_action_WITH_A_REASON_AND_AN_ACTIONABLE_CTA`.
- 🔴 `test_the_estimate_comes_from_the_GENERIC_actions_preview` — assert the fetch URL is
  `/v1/composition/actions/preview?token=…` and that **no** `/actions/decompose/estimate` request is ever
  made. *(The §3.3 guard: **three such invented routes 404 in production today.**)*
- 🔴 `test_409_CHAPTER_ALREADY_PLANNED_sets_needsReplace_and_confirmReplace_re_POSTs_with_replace_true`
  (mirror `usePlanner.test.tsx:91-98`). **409, not 400.**
- 🔴 `test_EMPTY_DECOMPOSE_PLAN_renders_the_HUMAN_SENTENCE_and_NOT_the_string_EMPTY_DECOMPOSE_PLAN`.
- 🔴 `test_apiJson_picks_detail_over_code` (in `api.test.ts`) — a `{detail:{code,detail}}` 400 throws with
  the **prose**.
- `test_a_preview_with_0_scenes_DISABLES_commit`.
- `test_commit_writes_active_template_id_back`.
- 🔴 `test_Lane_B_fires_ONLY_on_a_completed_decompose_job` — feed the reconciler
  `[composition_decompose {confirm_token}, confirm_action {action_accepted}, composition_get_generation_job
  {status:'running'}]` ⇒ `invalidateQueries` called **0 times**. Then
  `composition_get_generation_job {status:'completed', operation:'decompose_preview'}` ⇒ the **3** keys.
  **Negative:** `{status:'completed', operation:'motif_mine'}` ⇒ **0 times.**

**DoD evidence:** `"PlanDrawerDecompose.test.tsx + useDecomposeAction.test.ts + compositionEffects.test.ts: 10 passed incl. test_the_estimate_comes_from_the_GENERIC_actions_preview, test_409_CHAPTER_ALREADY_PLANNED_sets_needsReplace, test_EMPTY_DECOMPOSE_PLAN_renders_the_HUMAN_SENTENCE, and test_Lane_B_fires_ONLY_on_a_completed_decompose_job · api.test.ts: apiJson picks .detail over .code · LIVE (cross-service, composition+gateway+chat+FE): decomposed a chapter from plan-hub — /actions/preview returned a real estimate, confirm enqueued, job-detail opened IN THE DOCK (no route-nav), the tree committed"`

---

### **W6-M6** — 🔴 `scene-compose`: the home for the legacy `compose` sub-tab (+1 panel)
**Kind:** FE · **dependsOn:** W6-FE0 · **NEW — this plan had no home for it**

> 🔴 **WITHOUT THIS SLICE, GG-4's RETIREMENT GATE DELETES A SHIPPED FEATURE.**
> `ComposeView` is the **scene-scoped draft loop** and it exists on **no other surface**:
> guide box → **Generate** → **FE-local ghost stream** (never autosaved) → `CandidatesView`
> (diverge → converge **rerank**) → **Accept** (`onAccept` → editor + a **provenance mark**) → **inline
> critic** → 🔴 **`useCorrection` human-gate capture** (edit / regenerate / reject →
> `POST /jobs/{id}/correction`).
> **AND it carries the ONLY adapt-from-source affordance for derivative Works** (`useAdaptFromSource`,
> `canAdapt` / `adaptSourceEmpty`).
>
> 🔴 **The Chat-based `compose` panel is NOT a stand-in for it.** `ComposePanel.tsx:12` renders `<Chat>` —
> an agent conversation, **not** the deterministic diverge→converge→accept→correct loop. **DO NOT let the
> map row point `compose → 'compose'`.** *(If the PO instead rules `ComposeView` superseded by the chat,
> that ruling **MUST also name a home for `useAdaptFromSource`** — it exists on **no other surface** and
> retirement **deletes it outright**.)*

**Files:** `frontend/src/features/studio/panels/SceneComposePanel.tsx` (**NEW**) · `catalog.ts` (1 row) ·
i18n × 18 · `frontend_tools.py` (enum + gloss) · the contract (regenerate) ·
`__tests__/SceneComposePanel.test.tsx` (**NEW**).

**The shape — 🔴 LEAF-REUSE, per Wave 6's OWN EC-6 rule.** Mount `ComposeView` **as a LEAF**.
**NEVER `<CompositionPanel soloPanel="compose"/>`** — ~20 hooks fire and `WorkspaceLayoutContext` is
missing. (`no-composition-shell.test.ts` from W6-M1 enforces this **mechanically**.)

| Input | Source |
|---|---|
| `projectId` | `useWorkGate` / `useActiveWork` (W6-FE0) — **the ONE Work gate** |
| `sceneId` | **the studio bus** — `host/types.ts:36-37` **already carries `activeSceneId`** |
| `modelRef` | the shared `ModelPicker` (+ `resolveModelRole(settings,'composer')` — FE-21b) |
| `onAccept` | `ManuscriptUnitProvider.applyProposedEdit(text, ProvenanceAttrs)` |

**Tests:** the panel mounts `ComposeView` (not the shell); `onAccept` calls `applyProposedEdit` **with the
provenance attrs**; a **rejected** candidate fires `useCorrection` → `POST /jobs/{id}/correction`; on a
**derivative** Work the **adapt-from-source** affordance renders (and `adaptSourceEmpty` degrades honestly).

**DoD evidence:** `"SceneComposePanel.test.tsx: 4 passed — ComposeView mounts as a LEAF (no CompositionPanel import; no-composition-shell.test.ts green), onAccept → applyProposedEdit with provenance, a reject POSTs /jobs/{id}/correction, and useAdaptFromSource renders on a derivative · registration green at N_before+1 three-way"`

---

### **W6-M7** — 🔴 `chapter-assemble`: the home for the legacy `assemble` sub-tab (+1 panel)
**Kind:** FE · **dependsOn:** W6-FE0 · **NEW — this plan had no home for it**

> 🔴 **`ChapterAssembleView` is chapter-granularity generation** — single-pass (B2) **or stitch** (B3),
> gated on `scenesAllDone`; the **`assembly_mode` setter**; the **`CanonGatePanel` result**; an **editable
> preview generated with `persist=false`** (**never clobbers the editor draft**); **Accept** → `onAccept`;
> and 🔴 **`useCorrection` human-gate capture** → `composition.generation_corrected` → learning-service.
>
> 🔴 **`agent-mode` is NOT a substitute.** `authoringRuns/` is an **autonomous multi-chapter runner** — not
> the **interactive stitch-with-human-gate** surface. **DO NOT let the map row point `assemble → 'agent-mode'`.**
>
> 🔴 **AND THIS IS THE SECOND PRODUCER SPEC 30's `G-CORRECTION-FLYWHEEL` ROW NAMES.** That row says
> corrections are *"written only from the legacy `ComposeView`"* — **which UNDERSTATES it:
> `ChapterAssembleView` calls `useCorrection` too. Wave 1's capture seam is INCOMPLETE while this is
> homeless.**

**Files:** `frontend/src/features/studio/panels/ChapterAssemblePanel.tsx` (**NEW**) · `catalog.ts` ·
i18n × 18 · `frontend_tools.py` · the contract · `__tests__/ChapterAssemblePanel.test.tsx` (**NEW**).

**The shape — LEAF-REUSE of `ChapterAssembleView` (EC-6 applies).**

| Input | Source |
|---|---|
| `projectId` + `bookId` + `chapterId` | 🔴 the manuscript hoist's **active chapter**, using **the ONE convention spec 31 QC-10 locks** — `QualityCriticPanel.tsx:33-59`'s picker, **including the `chaptersTruncated` no-silent-cap notice** |
| `assembly_mode` | `work.settings` (the M4a Composition-section row is its writer) |
| `scenesAllDone` | `useChapterScenes` |
| `onAccept` | `applyProposedEdit` |

**Tests:** the preview is generated with **`persist=false`** and **does NOT clobber the editor draft**;
`scenesAllDone === false` ⇒ the stitch action is **disabled with a reason**; `CanonGatePanel`'s result
renders; **Accept** → `applyProposedEdit`; a **correction** POSTs `/jobs/{id}/correction`; the
`chaptersTruncated` notice renders when the chapter list is capped.

**DoD evidence:** `"ChapterAssemblePanel.test.tsx: 6 passed — preview uses persist=false and leaves the editor draft untouched, scenesAllDone=false disables the stitch WITH a reason, Accept → applyProposedEdit, a correction POSTs /jobs/{id}/correction (the SECOND correction producer, closing G-CORRECTION-FLYWHEEL's real surface) · registration green at N_before+1 three-way"`

---

### **W6-M5** — the GG-4 gate: the MECHANICAL guard 🔴
**Kind:** TEST · **dependsOn:** W6-M1, W6-M2, W6-M3, W6-M4a, **W6-M6, W6-M7**

> **This is the section the wave exists to earn.**
>
> 🔴 **The retirement is not "pending" — it was CANCELLED.** Spec 16's own status line reads *"Phase 4b
> (M9 — **kept** `ChapterEditorPage.tsx`, marked deprecated, **not deleted**)"*, and the file's banner says
> *"a decision to keep it around, **not** a decision pending removal (spec 16 Phase 4b, 2026-07-05: kept
> indefinitely)."* **This wave does NOT unblock a queued deletion; it REOPENS A CLOSED DECISION.**
> **Do not "resume" a retirement nobody re-authorized.**
>
> 🔴 **M6 (mobile) is still unresolved and is a REAL blocker on deletion.** `MobileEditorShell.tsx` +
> `MobilePanelSwitcher.tsx` exist **only** on the legacy path. The Studio's entire mobile concession is
> *"collapse the sidebar by default"* (`useStudioChrome.ts:13-16`). **Deleting the page deletes the only
> mobile chapter-editing surface in the product.** This wave does not close it.
>
> **The mechanical guard IS the deliverable.** A comment is the weakest available guard
> (`built-mounted-unreachable-duplicated-nav-list`). Spec 16's only enforcement today is an **18-line
> prose banner**: no lint rule, no hygiene test, no route assertion.

**Files:** 🔴 `frontend/src/features/composition/components/CompositionPanel.tsx` (**the prerequisite
export — see M5a**) · `frontend/src/features/studio/panels/__tests__/legacyParityContract.test.ts`
(**NEW**) · `frontend/src/pages/WritingStudioPage.tsx` (**M5c — the mobile redirect**) ·
`frontend/src/pages/__tests__/chapterEditorRetirementHygiene.test.ts` (**NEW**) ·
`frontend/src/features/chat/__tests__/editorBridge.test.ts` (**+1 hygiene test**) ·
`docs/specs/2026-07-01-writing-studio/16_*.md` + `36_*.md` (status amendments).

---

#### 🔴 **M5a — THE PREREQUISITE. WITHOUT IT THE ENTIRE GATE DOES NOT COMPILE.**

The parity test as written imports
`import { ALL_TABS, type SubTab } from '@/features/composition/components/CompositionPanel'`.
**Verified at HEAD:**
- 🔴 `type SubTab` (`CompositionPanel.tsx:87`) is **NOT EXPORTED.**
- 🔴 **`ALL_TABS` DOES NOT EXIST AT ALL** — the 25 names live in a **local `stripIds` array inside the
  component body** (`~:450`), and that array is **conditionally filtered** (`...(threadsEnabled ? ['threads'] : [])`).
- *(Plan 30 §10's REFUTED table **wrongly asserts `ALL_TABS` exists**. It does not.)*

**⇒ FIRST STEP OF M5, before the test file:**
```ts
// CompositionPanel.tsx — hoist to MODULE level and EXPORT both.
export type SubTab = 'compose' | 'cowriter' | … ;                  // was: unexported, line 87
export const ALL_TABS = [                                          // NEW — all 25, unconditional
  'compose','cowriter','assemble','planner','beats','graph','cast','relmap','timeline','arc',
  'worldmap','grounding','canonview','references','style','canon','critic','threads','progress',
  'quality','polish','flywheel','motifs','conformance','settings',
] as const satisfies readonly SubTab[];
```
Then `stripIds` **derives** from it: `const stripIds = ALL_TABS.filter(t => t !== 'threads' || threadsEnabled)`
— **the runtime feature-flag filter stays; the CONTRACT list does not.** *(A hand-copied list silently rots
the moment a 26th sub-tab appears — that is exactly what the `Record<SubTab, Home>` type is for.)*

---

#### 🔴 **M5b — THE MAP. ALL 25 ROWS. Two of this plan's rows were FALSE-HOMES.**

```ts
// frontend/src/features/studio/panels/__tests__/legacyParityContract.test.ts
//
// THE GG-4 GATE, MECHANIZED. Every legacy CompositionPanel sub-tab maps to a Studio panel id (or
// carries an explicit, reviewed retirement reason). Retiring ChapterEditorPage while any row still
// reads UNPORTED DELETES A SHIPPED FEATURE. This test is the gate — not a comment.
//
// 🔴 The identifier is OPENABLE_STUDIO_PANELS — `OPENABLE_STUDIO_PANEL_IDS` DOES NOT EXIST.
import { ALL_TABS, type SubTab } from '@/features/composition/components/CompositionPanel';   // M5a
import { OPENABLE_STUDIO_PANELS } from '../catalog';

// 🔴 THREE variants, and the third is LOAD-BEARING. Wave 6 runs BEFORE Wave 8, so the three sub-tabs
// Wave 8 homes (`cast` · `character-arc` · `canon-growth`) are NOT openable when this test first runs.
// Without a `pending` variant those rows RED at Wave 6's close with no instruction — and the tempting
// fix is a FALSE home, which is precisely the "gate goes GREEN on a feature being deleted" failure this
// file exists to prevent (master C-8: "the next agent would delete the guard to get green").
// A `pending` row is HONEST: the home is named, the wave that builds it is named, and GG-4 stays SHUT
// until zero pending rows remain. W8-16/17/18 FLIP these three to plain string homes.
type Home = string | { retired: string } | { pending: string };
const LEGACY_SUBTAB_HOME: Record<SubTab, Home> = {
  // ── this wave ────────────────────────────────────────────────────────────────
  style:       'style-voice',          // M1
  references:  'reference-shelf',      // M2   (NOT `references` — EC-2)
  settings:    'book-settings',        // M4a  (the Composition SECTION — no new id)
  beats:       'plan-hub',             // M4a  (the drawer FACET — no new id)
  compose:     'scene-compose',        // 🔴 M6 — NEW. NOT the Chat panel (see W6-M6).
  cowriter:    'scene-compose',        // 🔴 same surface (the co-writer IS the compose loop)
  assemble:    'chapter-assemble',     // 🔴 M7 — NEW. NOT `agent-mode` (see W6-M7).
  canonview:   'scene-inspector',      // 🔴 M3 — CanonAtChapterPanel as a SECTION (+ the wizard's
                                       //    branch-point step). No new panel id.
  // ── already ported / a successor already ships: MAP ONLY, no new work ────────
  grounding:   'scene-inspector',      // ALREADY PORTED — SceneInspectorPanel.tsx:9 imports
                                       // GroundingPanel, mounts it at :190. The ONLY one.
  planner:     'planner',              // catalog.ts:116 — spec 35 owns any residual gap
  graph:       'plan-hub',             // SceneGraphCanvas superseded — plan-hub IS the whole book's
                                       // plan on a graph canvas (catalog.ts:190)
  relmap:      'kg-graph',             // KgGraphPanel.tsx:10,39 already wraps ProjectGraphView →
                                       // RelationshipMap
  timeline:    'kg-timeline',          // catalog.ts:155
  critic:      'quality-critic',       // catalog.ts:268 (Wave 1 completes it — dismiss-violation)
  quality:     'quality',              // QualityHubPanel. 🔴 NEVER port QualityPanel WHOLE (spec 31:63,
                                       // QC-3/F-Q11: it double-mounts a PAID action). Its halves are
                                       // quality-corrections + quality-coverage.
  // ── Waves 1/3 ────────────────────────────────────────────────────────────────
  canon:       'quality-canon-rules',  // Wave 1
  polish:      'quality-heal',         // Wave 1
  progress:    'progress',             // Wave 1
  motifs:      'motif-library',        // Wave 3 (its Motifs|Arcs toggle half → Wave 4 arc-templates)
  conformance: 'quality-conformance',  // Wave 3
  // ── Wave 8 — PENDING. 🔴 Wave 8 runs AFTER Wave 6: these ids are NOT openable yet. ───
  //    W8-16/17/18 FLIP each of these three to a plain string home. Do NOT re-point them at an
  //    existing panel to get green — every "close enough" candidate is a DIFFERENT THING:
  cast:        { pending: 'Wave 8 / W8-16 → panel `cast` (CastCodexPanel). NOT `kg-entities` — that is a '
                        + 'thin wrapper over a FLAT, cross-project entity LIST with NO kind-grouping and '
                        + 'NO spoiler-safe story-state join.' },
  arc:         { pending: 'Wave 8 / W8-17 → panel `character-arc` (CharacterArcView: ONE character\'s '
                        + 'events in event_order, spoiler-cut at the current chapter). NOT `arc-templates` '
                        + '(Wave 4 = structure-TEMPLATE library + 拆文) and NOT `arc-inspector` (Wave 2 = '
                        + 'the narrative-arc SPEC tree; 32_arc_inspector.md:75 says verbatim "there is no '
                        + 'legacy component to move").' },
  flywheel:    { pending: 'Wave 8 / W8-18 → panel `canon-growth` (FlywheelPanel = knowledge-graph growth, '
                        + 'knowledgeApi.getFlywheel). NOT `quality-corrections` — that is CorrectionStatsTable '
                        + '(composition correction RATES). Two services, two datasets. The name collides; '
                        + 'the thing does not. (Wave 1\'s own plan says so at :2445.)' },
  // ── retired — a REVIEWED won't-port, not a shrug ─────────────────────────────
  threads:     { retired: 'duplicate of quality-promises — delete, do not port (00C Q-3c)' },
  worldmap:    { retired: 'the legacy PLACE-GRAPH is SUPERSEDED, by adjudication (wave-8 §5.4, '
                        + 'Q-38-OQ9-LEGACY-WORLDMAP-PLACE-GRAPH-NOT-PORTED). Its AUTHORING leg (add place / '
                        + 'link places — useWorldMap.ts:129,134, the FE\'s only human callers of '
                        + 'createEntity/createRelation) is absorbed by kg-entities/kg-graph (W8-02/03); its '
                        + 'SPATIAL leg (drag + backdrop) by the NEW `world-map` panel (W8-13), on a better '
                        + 'model (world-scoped, versioned, MCP-paired, real entity FKs). 🔴 There is NO '
                        + '`place-graph` panel and NO wave builds one — do not invent the id to get green. '
                        + 'D-WORLDMAP-PLACE-GRAPH-WONTPORT, gate #5.' },
};   // 🔴 25/25. A MISSING KEY IS A TYPE ERROR (Record<SubTab, …>) — that is the whole point.

const OPENABLE = OPENABLE_STUDIO_PANELS.map((p) => p.id);

it('every legacy sub-tab has a Studio home, a reviewed retirement reason, or a NAMED pending wave', () => {
  for (const [tab, home] of Object.entries(LEGACY_SUBTAB_HOME)) {
    if (typeof home === 'string') expect(OPENABLE, `sub-tab "${tab}"`).toContain(home);
    else if ('retired' in home) expect(home.retired.length).toBeGreaterThan(20);  // a reason, not a shrug
    else expect(home.pending, `sub-tab "${tab}"`).toMatch(/Wave \d/);             // name the wave that builds it
  }
});

// 🔴 THE GG-4 GATE ITSELF. This is the assertion that keeps ChapterEditorPage alive.
// It is EXPECTED TO FAIL at Wave 6's close (3 pending rows) and that is CORRECT — GG-4 is SHUT.
// W8-16/17/18 flip the last three; only then does this go green. Even then, deletion is ALSO
// blocked on D-STUDIO-MOBILE-SHELL (E-3, a PO decision). Do not delete this test to get green.
it.fails('GG-4: zero pending rows — the legacy editor may be retired', () => {
  const pending = Object.entries(LEGACY_SUBTAB_HOME)
    .filter(([, h]) => typeof h === 'object' && 'pending' in h)
    .map(([tab]) => tab);
  expect(pending).toEqual([]);   // Wave 6: ['cast','arc','flywheel'] — flipped by W8-16/17/18
});

it('the map covers every sub-tab the legacy panel actually has', () => {
  expect([...Object.keys(LEGACY_SUBTAB_HOME)].sort()).toEqual([...ALL_TABS].sort());
});

it("this wave's five ports are openable", () => {
  expect(OPENABLE).toEqual(expect.arrayContaining([
    'style-voice', 'reference-shelf', 'divergence', 'scene-compose', 'chapter-assemble',
  ]));
});
```

🔴 **THE TWO FALSE-HOMES THIS PLAN SHIPPED — and why they were the most dangerous lines in the file:**
| Row | This plan said | Why it was a **lie that makes the gate GO GREEN on a feature being DELETED** |
|---|---|---|
| `flywheel` | `'quality-corrections'` | **Wave 1's own plan contradicts it in writing** (:2445, its *"Recorded so it stops re-surfacing"* list) and spec 31:64 repeats it. `FlywheelPanel` = the **canon-growth** flywheel (`knowledgeApi.getFlywheel`, knowledge-service): *"+N entities / +N relations / +N events"* an extraction run **ADDED to canon**, each stat deep-linking to Cast / Timeline / Relations. `quality-corrections` = `CorrectionStatsTable` (**composition** correction rates). **The name collides; the thing does not.** |
| `arc` | `'arc-templates'` | `arc-templates` (Wave 4) = the structure-**TEMPLATE** library + 拆文 deconstruct. `arc-inspector` (Wave 2) = the narrative-arc **SPEC** tree. **Neither is a character's event arc over the knowledge graph.** `CharacterArcView`'s launcher (`onViewArc` / `setArcEntityId`) lives inside `CompositionPanel` **and dies with it.** |
| `cast` / `worldmap` | `kg-entities` / *(retire)* | `kg-entities` has **no kind-grouping and no spoiler-safe story-state join** — it is not `CastCodexPanel`. And `worldmap` was a **CIRCULAR DEFER**: spec 38 OQ-9 says *"it belongs to plan 30's Wave 6"* — **and Wave 6 does not contain it.** Wave 8 ports only the **WRITE leg** (`useWorldMap` is the FE's only human caller of `createEntity`/`createRelation`); **the place-graph VIEW has no home.** |

✅ **ACTION — DONE. Wave 8's plan gained THREE panel slices** (`docs/plans/2026-07-13-studio-wave-8-kg-world.md`
§5.4): **`cast` (W8-16)** · **`character-arc` (W8-17)** · **`canon-growth` (W8-18)** — all knowledge-service
reads, and Wave 8 is **already editing those files**. **`cast` uses `category: 'storyBible'`** (Wave 8's G3
confirms `storyBible` is already in `CATEGORY_ORDER` — **no X-2 dependency**); `canon-growth` uses
`category: 'knowledge'`. 🔴 **Wave 8's panel delta is +2 → +5** (not +6).

🔴 **`place-graph` is NOT the fourth slice — it does NOT EXIST and NO WAVE BUILDS IT.** Wave 8 §5.4
adjudicated the legacy `worldmap` place-graph a **conscious won't-port**
(`Q-38-OQ9-LEGACY-WORLDMAP-PLACE-GRAPH-NOT-PORTED` / `D-WORLDMAP-PLACE-GRAPH-WONTPORT`, gate #5): its
**authoring** leg is absorbed by `kg-entities`/`kg-graph` (W8-02/03 — `useWorldMap` was the FE's only human
caller of `createEntity`/`createRelation`) and its **spatial** leg by the new `world-map` panel (W8-13), on a
strictly better model. ⇒ its row is `{ retired: … }`, **not a home and not a pending**. *(An earlier cut of
this section told the builder to invent a `place-graph` panel id. That would have been a phantom panel
nobody ships.)*

🔴 **WAVE 6 RUNS BEFORE WAVE 8 — so `cast` / `arc` / `flywheel` ship as `{ pending: 'Wave 8 / W8-1x' }` rows,
and `it.fails('GG-4: zero pending rows')` is RED at Wave 6's close BY DESIGN.** That is the gate **holding**,
not a failure to fix: it red-lists what is still unported, machine-checked instead of argued. **File
`D-GG4-PARITY-ROWS-PENDING` (§9); W8-16/17/18 flip all three.** 🔴 **Do NOT delete the rows. Do NOT re-point
one at a panel that is not the thing. Do NOT abuse `{retired:…}` to silence a pending row** — `retired` means
*reviewed won't-port*, and using it as a mute button is exactly the "gate goes green on a feature being
deleted" failure this table documents.

---

#### 🔴 **M5c — THE MOBILE REDIRECT (~20 LOC + 1 test). IN SCOPE, because M5 IS the GG-4 gate.**
(`Q-36-GG4-MOBILE-BLOCKER` — **the concern MIS-STATES the bug, and the TRUE bug is LIVE TODAY.**)

> **Deletion is not what strands mobile users — THE NAV ALREADY DID.** Every in-app door to a chapter goes
> to the Studio (`BooksPage.tsx:143`, `BookDetailPage.tsx:113`, `book-tabs/ChaptersTab.tsx:153` →
> `/books/${bookId}/studio?chapter=…`). And **`WritingStudioPage.tsx:11-19` has NO mobile branch
> whatsoever** — it mounts `StudioFrame` unconditionally, whose entire mobile concession is *"collapse the
> sidebar"* (`useStudioChrome.ts:13-16`). **So a phone user tapping a chapter row gets a 68-panel dockview
> on a 390px screen**, while `MobileEditorShell` — **built, mounted (`ChapterEditorPage.tsx:844`), and
> tested** — is reachable **only by hand-typing a URL.** *This is the repo's `built-mounted-unreachable`
> class, SHIPPED.*

1. `WritingStudioPage.tsx` — `const isMobile = useIsMobile();` **after** `useParams`/`useSearchParams` and
   **before any return** (no conditional hooks). Then, before `return <StudioFrame…/>`:
   ```tsx
   if (isMobile && bookId)
     return <Navigate replace to={initialChapterId
       ? `/books/${bookId}/chapters/${initialChapterId}/edit`
       : `/books/${bookId}`} />;
   ```
   *(No `?chapter` ⇒ the book's Chapters tab, whose rows link back through `/studio?chapter=…` and
   therefore **re-enter this same redirect** — **the loop composes, it does not cycle.**)*
2. **Test** `frontend/src/pages/__tests__/WritingStudioPage.mobile.test.tsx`: mock `window.matchMedia` to
   `(max-width: 767px) => matches:true`, mock `StudioFrame`, render at `/books/B1/studio?chapter=C9` inside
   a `MemoryRouter` with a catch-all echoing the location ⇒ the landed path is
   `/books/B1/chapters/C9/edit` **and `StudioFrame` was NOT rendered**. Desktop (`matches:false`) ⇒
   `StudioFrame` **IS** rendered with `initialChapterId="C9"`.
3. 🔴 **MACHINE-CHECK THE GATE** (same parity file):
   ```ts
   it('the Studio has no mobile shell → the legacy editor route must stay mounted', () => {
     expect(readFileSync('src/App.tsx', 'utf8')).toContain('/books/:bookId/chapters/:chapterId/edit');
   });   // D-STUDIO-MOBILE-SHELL — whoever deletes the route REDS this and is FORCED to confront the
         // mobile hole instead of discovering it in production. "A gate is a test, not a comment."
   ```
4. **Rewrite `ChapterEditorPage.tsx`'s banner** (`:1-18`): keep the *do-not-port / do-not-edit* clauses,
   **strike *"never linked to from the app UI"*** (no longer true — see 1), and add: *"KEEP — this page is
   ALSO the ONLY mobile chapter-editing surface (`MobileEditorShell`, line 844). `WritingStudioPage`
   redirects mobile viewports here. It may not be deleted until a Studio mobile shell exists —
   D-STUDIO-MOBILE-SHELL."*

---

#### 🔴 **M5d — THE RETIREMENT HYGIENE TESTS. Both of this plan's greps were WRONG.**
(`Q-36-HYGIENE-GREP-IMPORT-NOT-LITERAL` + `Q-36-GG4-EDITORBRIDGE-SINGLETON`.)

**NEW `frontend/src/pages/__tests__/chapterEditorRetirementHygiene.test.ts`:**
- Match an **IMPORT STATEMENT, never the token**:
  `/(?:^|\n)\s*import\s[^;\n]*?from\s*['"][^'"]*ChapterEditorPage['"]/` (+ the dynamic `import(...)` and
  `require(...)` forms). ⚠ **A literal-token grep hits ~25 PROVENANCE COMMENTS in live Studio code**
  (`EditorPanel.tsx:55`, `EditorPublishGate.tsx:1`, `MediaVersionHistoryPanel.tsx:5`,
  `ManuscriptUnitProvider.tsx:32`, `CompositionPanel.tsx` ×5, `ComposePanel.tsx:44`, …) — **those are the
  port's audit trail and MUST survive.**
- 🔴 **ASSERT `App.tsx` IS THE *SOLE* IMPORTER — `expect(importers).toEqual(['App.tsx'])` — NOT "zero
  importers."** **This plan's sketch says `it('nothing IMPORTS ChapterEditorPage')`, which CONTRADICTS A
  SEALED DECISION** (OQ-2 *"Keep"*; spec 16 Phase 4b *"kept indefinitely, not deleted"*; the file's own
  banner). The single import at `App.tsx:27` (route at `:134`) is **CORRECT and STAYS.**
- **SECOND assertion** — the claim the banner actually makes: in every scanned file **except `App.tsx`**,
  `expect(src).not.toMatch(/['"\`][^'"\`]*\/chapters\/[^'"\`]*\/edit/)` — **no `<Link to>` / `navigate()`
  into the legacy route.** *(⚠ M5c's redirect is a `<Navigate>` in `WritingStudioPage` — allowlist that ONE
  file, or scope the assertion to exclude it.)*

**`frontend/src/features/chat/__tests__/editorBridge.test.ts` — +1 hygiene test.**
🔴 **THE DEFER ROW'S PREMISE IS FALSE: `editorBridge` does NOT "die with the page."** **There are TWO
registrants and ONE IS THE STUDIO:** `features/studio/panels/EditorPanel.tsx:100` registers
`{bookId, chapterId, handleRef, applyProposedEdit}` (the **checkpoint-wrapped hoist action**);
`pages/ChapterEditorPage.tsx:284` registers the legacy one. The consumer is `ProposeEditCard.tsx` at
`:55`, `:70`, `:100`. **Deleting `editorBridge.ts` with the page BREAKS Studio `propose_edit` Apply on
every AI edit** (`getEditorTarget() → null → "no editor"`). **The row as written instructs a future builder
to do exactly that.**
⇒ Add: collect files **IMPORTING** `registerEditorTarget` (match the import, not the token) and assert
**at least one is OUTSIDE `src/pages/`**, with the failure message:
*"editorBridge has a non-legacy registrant (Studio EditorPanel) — do NOT delete it with ChapterEditorPage;
migrate ProposeEditCard to ManuscriptUnitProvider context first (D-EDITORBRIDGE-SINGLETON)."*
**Do NOT do the context migration in this wave** — it is a pure refactor, zero user-visible gain, touching
the shared chat chain that serves three surfaces, **and it is blocked anyway while the legacy page lives.**

**The route-retirement test (`legacyEditorRouteRetired.test.tsx`) lands WITH the deletion, NOT in this
wave** (OQ-2 — spec 36 §GG-4 itself says so). 🔴 **DO NOT WRITE IT.** There is no deletion.

**Spec amendments to land with M5:** `36_editor_craft_ports.md` — **OQ-2 → ANSWERED: KEEP** (it leaves the
open-questions table); rewrite §10 item 2 and the **`editorBridge`** paragraph (items ~630-633) with the
corrected two-registrant fact; **reclassify `D-STUDIO-MOBILE-SHELL` from gate #4 → gate #2** (it is a
real, buildable, multi-slice track — *"a Studio mobile shell"* — **not a blocker on a PO decision**).

**DoD evidence:** `"CompositionPanel.tsx now EXPORTS `type SubTab` + a module-level `ALL_TABS` (25 names; stripIds derives from it) — WITHOUT THIS THE GATE DID NOT COMPILE · legacyParityContract.test.ts: 4 passed — the map is EXHAUSTIVE over ALL_TABS (25/25; a missing key is a TS error), style-voice / reference-shelf / divergence / scene-compose / chapter-assemble are all openable, and App.tsx's legacy route is still mounted · WritingStudioPage.mobile.test.tsx: 2 passed (mobile lands on /chapters/C9/edit; desktop renders StudioFrame) · chapterEditorRetirementHygiene.test.ts: App.tsx is the SOLE importer (not zero) · editorBridge.test.ts: a non-legacy (Studio) registrant EXISTS"`

---

## 5 · Migrations

**NONE.** This wave adds **no table, no column, no index, no enum value, no CHECK block.**

- BE-13a's derivative **name** rides in the **existing** `composition_work.settings` JSONB blob
  (`create_derivative` already accepts a `settings` kwarg — C5).
- BE-18 changes **one SQL expression** in an existing UPDATE. No schema.
- BE-21 adds a **Python helper**. No schema.
- BE-20 adds a **descriptor string** to a Python tuple. No schema.

⚠ **If a future slice thinks it needs one, re-read these CLAUDE.md memories first:**
`ADD COLUMN IF NOT EXISTS` **never revisits a bad default** on an already-migrated DB · a new enum value
must backfill **EVERY** historical CHECK block · a partial UNIQUE index must **exempt soft-delete
tombstones** and its `ON CONFLICT` must **repeat the partial index's predicate.**

---

## 6 · The registration checklist per new panel (GG-8) — 🔴 **5 panels** (was 3)

**The drift-lock is an EQUALITY, not a number: `py enum == contract enum == openable`.** This wave moves it
by **exactly +5**: `style-voice` · `reference-shelf` · `divergence` · **`scene-compose`** ·
**`chapter-assemble`**.
*(`book-settings`, `plan-hub` and `scene-inspector` are **existing** ids — the Composition **section**, the
Beats **facet** and the canon-at-chapter **section** add **no** enum members.)*

🔴 **Do NOT hard-code an absolute count.** At HEAD `9262ed53e` the baseline is **57 == 57 == 57**. Wave 6
sits **downstream of Waves 1–5**, which add **9** panels — so the baseline **will be ~66** by the time this
wave starts, and a DoD asserting `58/58/58` would **send a builder hunting a phantom regression.**
**Six of the eight batch specs got this wrong by each computing from 57.**
🔴 **RE-MEASURE `N_before` PER MILESTONE, not per wave** (`Q-36-PANEL-COUNT-NEVER-A-LITERAL` item 3). Read
each milestone's `+1` as *"this milestone's own `N_before` + 1"*, **not** as a cumulative-from-wave-start
target — that **dissolves the ordering coupling** if a milestone slips:
```bash
python -c "import json;print(len(json.load(open('contracts/frontend-tools.contract.json'))['ui_open_studio_panel']['args']['panel_id']['enum']))"
```
Paste `N_before=<x> N_after=<y> delta=+1` into **each milestone's** VERIFY evidence. **Never a literal, and
never a committed count assertion** — the set-equality tests **already are** the lock
(`panelCatalogContract.test.ts:28,33-34,40-42`; `test_frontend_tools.py:153-156` records that a hand-copied
literal list *"drifted stale at least twice"* and was **deliberately deleted — do not resurrect it**).

**All five panels are openable by a BARE ID** (they resolve their own scope from `bookId` + the bus), so
**none is `hiddenFromPalette`** and **all five enter the enum.** The X-12 params trap does not apply.

| # | File | Add |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/{StyleVoicePanel,ReferenceShelfPanel,DivergencePanel,SceneComposePanel,ChapterAssemblePanel}.tsx` | root `data-testid="studio-<id>-panel"` |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | **5 `STUDIO_PANELS` rows** — `{ id, component, titleKey, descKey, category: 'editor', guideBodyKey }`. **`category` AND `guideBodyKey` are BOTH mandatory** (X-2/X-3). ⚠ `STUDIO_PANEL_COMPONENTS` (`:275`) and `OPENABLE_STUDIO_PANELS` (`:279`) are **DERIVED — never hand-edit them.** |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.<id>.{title,desc,guideBody}` × 5 (+ `panels.reference-shelf.embedModelUnset` / `embedModelLocked` with i18next **`count`** pluralization, + `panels.reference-shelf.deleteConfirm.*`, + `divergence.error.*`) |
| 4 | `frontend/src/i18n/locales/{17 others}/studio.json` | 🔴 **`python scripts/i18n_translate.py --ns studio`** — **NO `--force`** (it is **gap-fill**: it carries every existing translation and translates **only the new keys**; `--force` re-translates the whole namespace × 17 and **clobbers prior hand-fixes**) and **no `--langs`** (all 17 is the default). **NEVER hand-write a locale value.** If LM Studio (:1234) is down: 🔴 **DO NOT BLOCK and DO NOT hand-translate** — `i18n/index.ts:48` sets `fallbackLng:'en'`, so a missing key **renders English (degraded, never broken)**. File `D-36-I18N-LOCALES` (gate #4) and **drain it in ONE batched run at wave close**; check for residual `_FAILED.json` before closing. |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **TWO edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: **(a)** append the **5** ids to the `panel_id` **enum** (`:402`); **(b)** append a per-panel clause to the **description** (`:403-481`) — **that gloss is the model's ONLY hint.** 🔴 It MUST say: *"`reference-shelf` = the author's research corpus — influence texts the book's generation retrieves from. **NOT entity backlinks: for 'where is this entity referenced', use the `composition_find_references` tool, not this panel.**"* ⚠ **The full registered name is `composition_find_references`** (`mcp/server.py:3867`) — **spec 36:467's bare `find_references` DOES NOT EXIST**, and naming a non-existent tool **invites a hallucinated tool call**. |
| 5b | `services/chat-service/tests/test_frontend_tools_contract.py` | 🔴 **NEW GUARD** (*"the description must say X"* is a **self-report** until a test asserts it): assert `UI_OPEN_STUDIO_PANEL_TOOL`'s description contains **BOTH** `"reference-shelf"` **AND** `"composition_find_references"`. **Without it, any later description rewrite silently drops the disambiguation and nothing reds.** |
| 6 | `contracts/frontend-tools.contract.json` | 🔴 **REGENERATE, NEVER HAND-EDIT:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py` (it **skips by design** — it *writes* the file), **then RE-RUN IT WITHOUT the env var and require GREEN** — that second run is the **only proof** the contract matches the live schemas. **Commit the JSON in the SAME COMMIT as steps 2 + 5.** |
| 7 *(cond.)* | `frontend/src/features/studio/host/studioLinks.ts` | 🔴 **SKIP — do not add rows.** `PATH_PANELS` (`:46`) maps **bare app paths** only, and `App.tsx:109-136` gives chapters exactly five routes — **the composition sub-tabs have NEVER been URL-addressable**, and `/edit` is already absorbed by `CHAPTER_RE` → `focusManuscriptUnit`. *(If a later wave adds a notification `metadata.link` that must land here, that is an additive one-line `PATH_PANELS` row **at that time** — not Wave 6 work.)* ⚠ **The one-line `{ params: { tab } }` bug at `:111` IS fixed — in W6-M0.** |
| 8 **(MANDATORY)** | `frontend/src/features/studio/agent/handlers/compositionEffects.ts` | ⚠ **NOT NEW** — spec **31** (Wave 1) **CREATES** it. **EXTEND it; ONE file, ONE export, ONE call site** (plan 30 §8.0b: two handler files for one domain **DOUBLE-FIRE** — `matchEffectHandlers` returns EVERY match and `runEffectHandlers` awaits ALL). Add `registerEffectHandler(/^composition_(style\|voice)_(upsert\|delete)$/, …)`, `/^composition_reference_/`, and `/^composition_get_generation_job$/` — 🔴 **RegExps, never strings** (C10). ⚠ **spec 36:509 says *"the same `compositionEffects.ts` **Wave 0** creates"* — that is a TYPO; its own step-8 row (`:470`) and plan 30 §8.0b both say **Wave 1**. Fix the word while you're there.** |
| 9 *(cond.)* | `tours.ts` / `tourCatalog.ts` | 🔴 **SKIP** — `studio/onboarding/` contains **zero** references to the new ids; none is a role-tour step in v1. |
| 10 **(new — EC-3d)** | `frontend/src/features/studio/host/types.ts` (+ its reducer) | 🔴 **The bus has NO active-Work concept today.** *Switch to* needs `activeWorkId` **(the SURROGATE)** + `activeWorkProjectId` + a `work:switch` event, hydrated on mount from `/v1/me/preferences`. **This is the SANCTIONED exception to the Do-Not-Touch list** — change it **ONCE, in W6-FE0**, and make every consumer read `useActiveWork()`. |

**Verify (all four green — the first two are the drift-locks):**
```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

### 🔴 The DO-NOT-TOUCH fence — and it is MECHANICAL, not a promise

**Do NOT edit these 6 files in Wave 6** (the first four are **pure consumers of `catalog.ts`** — adding the
5 rows + their i18n makes all of them pick the panels up **for free**: dock mount, palette command,
user-guide row; the last two are **panel-id-agnostic**):
`StudioDock.tsx` · `StudioFrame.tsx` · `palette/useStudioCommands.ts` · `panels/UserGuidePanel.tsx` ·
`agent/studioUiNav.ts` · `agent/useStudioUiToolExecutor.ts`
**If you find yourself editing one of these, STOP: you have introduced a per-panel special case where the
catalog was supposed to be the only registry** (a DOCK-1 violation — `/review-impl` should flag it).

🔴 **Make it a literal DoD step** (*"an item is DONE only when a test asserts its effect"*):
```bash
git diff --name-only main...HEAD -- \
  frontend/src/features/studio/components/StudioDock.tsx \
  frontend/src/features/studio/components/StudioFrame.tsx \
  frontend/src/features/studio/palette/useStudioCommands.ts \
  frontend/src/features/studio/panels/UserGuidePanel.tsx \
  frontend/src/features/studio/agent/studioUiNav.ts \
  frontend/src/features/studio/agent/useStudioUiToolExecutor.ts \
  frontend/src/features/studio/host/studioLinks.ts
# REQUIRE EMPTY OUTPUT. Non-empty ⇒ revert the edit and push the change into catalog.ts, or (if it is
# genuinely necessary) it is a scope breach that must be RAISED, not absorbed.
```
⚠ **`host/types.ts` is deliberately ABSENT from that list — it is the sanctioned W6-FE0 exception.**
⚠ **`useStudioCommands.ts` gets ONE exception too: X-2 (W6-M0) adds `'quality'` to `CATEGORY_ORDER`.** Run
the fence check **after** W6-M0's commit, or allowlist that one line.

---

## 7 · Agent surface after this wave (recorded honestly — the INVERSE gaps that REMAIN)

| Domain | Tools today | After this wave |
|---|---|---|
| style / voice | **none** | `composition_style_{list,upsert,delete}` · `composition_voice_{list,upsert,delete}` (BE-10 — 🔴 **lists Tier-R, writes Tier-A**, `_meta.undo_hint`) |
| story structure | **none** | `composition_decompose` (BE-20, **Tier-W** — executes nothing; the effect lives in `actions.py` keyed on `composition.decompose`) 🔴 **+ `composition_decompose_commit`** (Tier-A — a pure DB persist, **zero** spend). *Without the commit tool the agent can propose a tree and **never persist it** — a paid no-op.* |
| references | **none** | 🔴 **`composition_reference_{list,add,delete,search}` — BE-10b (C15, UN-DEFERRED).** *The defer row's gate #3 was **false**: every prerequisite exists at HEAD, and this wave was **already building six tools of exactly this shape, in the same file**. GG-2: shipping the reference GUI while leaving its inverse half open, **in the one wave whose job is closing tool↔GUI gaps**, is the defect the plan exists to kill.* |
| divergence | **none** | 🔴 **`composition_list_derivatives` (R) · `composition_derivative_context` (R) · `composition_derive_work` (W) — M6-D (C15, UN-DEFERRED).** *The row claimed derive **"deserves its own confirm design."** It does not: the AN-8 spine is **generic and already carries 11 descriptors**, and an MCP path **already mints a knowledge project cross-service**. **NO cost gate** — derive makes **zero LLM calls**; it is an **irreversibility** gate, and the confirm preview must say **"archive only — a derivative has no delete."*** |
| work settings | `composition_get_work` (read) | 🔴 **still NONE — a CONSCIOUS WON'T-FIX (gate #5), and it STANDS.** The blob holds **BYOK MODEL REFS** (`critic_model_ref`, `reference_embed_model_ref`) — **spend-causing, user-owned choices** — and spec 28's AN-8 table gives settings **no agent channel** (*"a reviewer finding a new confirmation convention here has found a defect"*). ⚠ This does **NOT** violate GG-2: GG-2 fires only when a domain has **NO** agent tools, and `composition_get_work` gives the agent read access, so it can **advise** while the **user** makes the change. 🔴 **ANTI-RESURFACING — the one concrete edit this earns:** add a comment block immediately after the `composition_get_work` handler (`mcp/server.py` ~`:302` — **the point of temptation where the next agent would add the sibling write tool**): *"# NO composition_update_work — CONSCIOUS WON'T-FIX (spec 36 F-EC4; AN-8 gives settings no agent channel). The settings blob holds BYOK model refs = the user's own spend choices. Writes go through the book-settings GUI only. If an agent channel is ever wanted, it must be Tier-W propose→confirm (an FE card), never a direct tool."* **A future agent reads `server.py`, not the spec — this is what actually stops it re-surfacing.** |

🔴 **The discovery scent (AN-C2 / X-10) — BUILT IN-WAVE (W6-BE9). "Blocked on Track C" was FALSE** (C16).
Track C's `stream_service.py` edits are **committed** (`a23c3f15e`, `fd4702818`, `bac8802c2`, `a95f65378`
— all ancestors of HEAD) and `git diff HEAD -- <file>` is **empty**. **Fourteen** new tools the model is
never told about are **fourteen tools that will never be called** (spec 28 AN-11 calls *"shipped but never
called"* a **FAIL**). One clause in `book_context_note` + one test + the doc reconcile.
**`D-WAVE6-DISCOVERY-SCENT` is DELETED — its premise was refuted.**

---

## 8 · Wave Definition of Done

A literal checklist. **Every box must be a pasted artifact, not a claim.**

- [ ] **0 · 🔴 THE CONTRACT IS FROZEN FIRST (W6-C0).** `contracts/api/composition/v1/openapi.yaml` carries
      **every** route this wave adds/changes, `redocly lint` is clean, and `test_openapi_contract.py`
      passes — **BEFORE any FE slice consumes them.** CLAUDE.md: *"Contract-first: API contract frozen
      before frontend flow."*
- [ ] **1 · All four drift-locks green** (the §6 commands), with all three counts moving **🔴 +5 in
      lockstep**: `N_before + 5 == N_after` across **py enum == contract enum == openable**
      (`style-voice`, `reference-shelf`, `divergence`, **`scene-compose`**, **`chapter-assemble`**).
      🔴 **Assert the DELTA, never a literal**, and **re-measure `N_before` PER MILESTONE** (C8 — an
      earlier cut of spec 36 said `60 == 60 == 60`, which is **wrong**: Waves 1–5 land 9 panels first.
      A literal here is exactly the phantom regression §6 warns about.)
- [ ] **2 · Unit + integration suites green, per service** — at or above the §2-J baseline counts:
      - `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup`
      - `cd services/chat-service && python -m pytest tests -q -n auto --dist loadgroup`
      - `cd frontend && npx vitest run`
      ⚠ Every **new** test that touches a real DB/port carries `pytestmark = pytest.mark.xdist_group("pg")`
      — or parallel workers interleave and **the counts lie.**
- [ ] **3 · A BEHAVIOUR TEST PER SETTINGS KEY** (SET-4 — *"consumed, proven by effect"*).
      **Writing the blob is NOT evidence.** (M4a's list.)
- [ ] **4 · Cross-service live-smoke** (composition + chat-service + frontend ⇒ ≥2 services): an agent turn
      calling **`composition_style_upsert` CHANGES THE NEXT DRAFT PROMPT.**
      🔴 **THE ASSERTION SEAM DOES NOT EXIST YET — AND THAT IS UNBUILT WORK, NOT A BLOCKER.** There is **no
      `prompt` column** in `composition-service/app/db/migrate.py`, so no packed prompt is persisted.
      **The builder WRITES the seam** (`Q-36-LIVE-BROWSER-SMOKE-MANDATORY` (5)). **Default (PO may veto):**
      the style row must round-trip through the **REAL REST route**, the **REAL DB** and the **REAL
      packer**; 🔴 **the ONLY mock permitted is the provider call itself** — **capture the OUTBOUND
      provider-registry request payload and assert the density directive string is present in it.**
      **Asserting against a mocked packer does NOT satisfy DoD 4. A green mock is not proof.**
      *(Also live-smoke `composition_reference_add` (BE-10b): an agent tool-call puts a reference in the
      open `reference-shelf` library **without a reload** — the Lane-B leg.)*
- [ ] **5 · 🔴 LIVE BROWSER SMOKE — MANDATORY, NON-NEGOTIABLE.**
      (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream` — a green unit suite has hidden *"the FE
      could not actually execute it"* **four times in this repo.**)
      🔴 **TWO DEFECTS IN THIS PLAN'S OWN INSTRUCTIONS WOULD HAVE MADE THIS GATE A SILENT NO-OP**
      (`Q-36-LIVE-BROWSER-SMOKE-MANDATORY`) — **fixed by rule, before any wave runs:**
      1. 🔴 **THE PATH WAS WRONG — the gate would execute ZERO tests.** `frontend/playwright.config.ts:6`
         sets `testDir: './tests/e2e/specs'`. **`frontend/e2e/` DOES NOT EXIST** (`ls` → exit 2). A spec
         written at this plan's prescribed path is **collected by NOTHING**, and the *"mandatory"* smoke
         **reports green having run nothing** — the repo's own `silent-success-is-a-bug` class.
         **CORRECT ROOT: `frontend/tests/e2e/specs/`.**
      2. 🔴 **THE FILENAME COLLIDES WITH SHIPPED COVERAGE.** **DO NOT write
         `studio-editor-craft.spec.ts`** — **it already exists** (136 lines, 4 tests, commit `87e8508cd`)
         and **guards a prior `/review-impl` HIGH** (the real-OS-window popout Apply drop). **Writing this
         wave's scenarios there CLOBBERS it.** Instead **split per feature** (CONVENTIONS.md §5,
         `<scope>-<intent>.spec.ts`), each landing **IN the wave that builds its feature**, not batched at
         the end:
         `studio-style-voice.spec.ts` · `studio-reference-shelf.spec.ts` · `studio-divergence.spec.ts`
         (⚠ **FIRST read `creation-unblock-divergence.spec.ts`** — if it covers the same surface, **EXTEND
         it rather than fork**) · `studio-critic-model.spec.ts` · `studio-plan-hub-beats.spec.ts`.
      3. 🔴 **SKIP POLICY — a skipped test still reports GREEN.** Use the established
         `test.skip(cond, reason)` gate (`composition-engine.spec.ts:44`). **BUT the DoD is NOT "suite
         green"** — the VERIFY evidence must **PASTE the Playwright summary line showing the new specs
         `passed` with `0 skipped`.** If the stack is genuinely down, that is the
         `live infra unavailable: <reason>` token **plus** a tracked `D-36-LIVE-SMOKE` row —
         **never a silent green.**
      4. **REUSE, don't rebuild:** `loginViaUI` · `getAccessToken`/`createBook`/`createChapter`/`trashBook`
         · the `StudioPage` PoM. For the **$0 bge-m3 embed**, add `listEmbedModels` to `helpers/api.ts`
         mirroring `listChatModels` (`api.ts:289`; `?capability=chat` → `?capability=embed`).
      Run against the **baked nginx build on :5174** (⚠ a host `vite dev` **SHADOWS** it —
      `frontend-5174-is-baked-prod-nginx-not-vite`; **rebuild the image first** —
      `live-smoke-rebuild-stale-images-first`; `playwright.config.ts:3` **already** defaults `baseURL`
      there — no config change needed), driving the dock via **`evaluate` + `data-testid`** (refs go stale
      — `playwright-live-dockview-automation-recipe`) and **`page.mouse` for any drag**
      (`playwright-cdp-mouse-drives-d3-drag`), signed in as **`claude-test@loreweave.dev` /
      `Claude@Test2026`**. Prefer a **local lm_studio** chat model for **$0 spend**; pass an explicit
      `model_ref` (the account's `user_default_models` is **empty**).
      - [ ] `ui_open_studio_panel {panel_id:"style-voice"}` **from the agent chat** mounts the dock tab →
            move the density slider → **reload** → it persisted **and the source chip says `work`**.
      - [ ] `ui_open_studio_panel {panel_id:"reference-shelf"}` → add a reference with a **local** embed
            model (`bge-m3`, $0) → it appears in the library → select a scene → **it is retrieved**.
      - [ ] `ui_open_studio_panel {panel_id:"divergence"}` → run the wizard → the **NAMED** derivative
            appears in the list → **Switch to** → the `DerivativeBanner` renders in the Editor →
            🔴 **RELOAD — the Editor, navigator, scene-inspector and quality panels are ALL still on the
            derivative** *(this is the test that proves EC-3d, and the one a bus-only implementation
            FAILS)* → **Archive** → it leaves the list.
      - [ ] `book-settings` → Composition → set the **critic model** → a critique run **no longer** returns
            *"critique skipped."*
      - [ ] `plan-hub` → a chapter's drawer → **Beats** → change `beat_role` → **reload** → it persisted.
      - [ ] `plan-hub` → **Decompose** → the estimate card renders a **real number** → confirm → the job
            opens in **`job-detail` IN THE DOCK** (**not** a route-nav that tears the dock down).
- [ ] **6 · OQ-5 — the Book tier of the model cascade, live. 🔴 THIS PLAN'S VERSION IS WRONG ON THREE
      COUNTS AND WOULD HAVE BURNED THE BUILDER** (`Q-36-OQ5-BOOK-TIER-CASCADE-UNEXERCISED`):
      - 🔴 **(a) The premise is HALF-FALSE — the Book tier is NOT unexercised.** The transport
        (chat-service → composition `/internal` → grant check → `resolve_by_book` → resolver) is
        **ALREADY LIVE in production**: `_model_roles_from_settings` **dual-reads** the legacy scalar
        `settings.default_model_ref` into role `chat` (`internal_model_settings.py:59-61`), and
        `default_model_ref` **HAS a real GUI writer today** (`CompositionSettingsView.tsx:47`). **M4a is
        NOT the first writer of the Book tier — it is the first writer of the `model_roles` KEY and of the
        `composer`/`planner`/`critic` roles.** A *partially* new contract, not a virgin one.
      - 🔴 **(b) THE ROUTE THIS PLAN NAMES DOES NOT EXIST.** `GET /v1/chat/ai-settings/effective` **404s.**
        The real route is **`GET /v1/chat/effective-settings?book_id=<uuid>`**
        (`chat-service/app/routers/ai_settings.py:34`, mounted `main.py:175`). *Copied verbatim it 404s and
        the builder "fixes" a resolver that was never broken.*
      - 🔴 **(c) IT IS A TWO-LEG SMOKE. LEG A ALONE SHIPS THE HEADLINE BUG.** Write it as a **committed,
        re-runnable script** (`services/chat-service/scripts/smoke_book_tier_cascade.py`, following the
        `composition-service/scripts/eval_*.py` pattern), run it **as the CLAUDE.md test account**, and
        paste its stdout as `live smoke: book-tier cascade <one-liner>`:
        - **LEG A (the resolver):** resolve a **REAL active** model
          (`SELECT user_model_id FROM user_models WHERE owner_user_id='019d5e3c-…' AND is_active`) → PATCH
          the book's **canonical** Work with `model_roles.critic = {"model_ref": "<that uuid>",
          "model_source": "user_model"}` → `GET /v1/chat/effective-settings?book_id=<uuid>` → assert **ALL
          THREE**: `models.critic.source_tier === "book"`, `.effective_value.model_ref === <that uuid>`,
          and `"book" NOT IN models.critic.skipped`.
        - **LEG B (the consumer that actually matters — this is what makes M4a TRUE rather than a write-only
          editor):** run the critique on that book with a **drafter `model_ref` DIFFERENT from the critic
          ref**, and assert the response body does **NOT** contain *"critique skipped: no distinct critic
          model configured"*. 🔴 **Leg B is RED until BE-21 lands.** **Leg A green + Leg B red IS the
          stored-but-unread shape** — *shipped by the very spec that cites the rule.* **Treat Leg B as the
          PASS CONDITION of M4a's DoD, not a bonus.**
      - 🔴 **Two traps to write into the script's docstring, so a 3am builder does not misread a CORRECT
        result as a bug:**
        1. **Liveness is OWNER-SCOPED and it SILENTLY DEMOTES.** `resolve_model_role` liveness-checks
           **every** tier; a 404 from provider-registry ⇒ the book tier is **SKIPPED** (recorded in
           `skipped[]`) and resolution falls through to **Account** (`provider_client.py:47-62`). So a
           **placeholder/fake ref** — exactly what the existing unit test injects (the literal string
           `"book-model"`, `test_ai_settings_router.py:170`) — yields `source_tier: "account"`. **That is
           the resolver working CORRECTLY.** The ref **MUST** be a `user_model_id` the **calling user
           owns** and that is **active**. *(`is_live` fails **OPEN** on any non-404, so a flaky registry
           will not demote — only a genuine 404 will.)*
        2. **`book_id` MUST be a well-formed UUID.** The composition route signature is `book_id: UUID`,
           and `CompositionClient.get_book_model_roles` **swallows EVERYTHING into `{}`**
           (`composition_client.py:44-47`) — so a non-UUID `book_id` yields a **silent no-book-override,
           indistinguishable from "no model set."**
      - **Why the unit suite cannot substitute:** the only existing Book-tier test **monkeypatches a
        `_FakeComposition` client** (`test_ai_settings_router.py:161-178`). **A mock encodes the author's
        assumption of the contract** — it cannot catch the wrong route path, the owner-scoped liveness
        demotion, or **the fact that the engine never reads what the panel writes.**
      - ⚠ **PATCH is a WHOLE-BLOB merge FE-side** (`patchWork` spreads `{...currentSettings, ...patch}`) —
        **spread the current settings** or a partial PATCH **CLOBBERS**.
- [ ] **7 · No new global `*_ENABLED` / `*_MODE` env flag** gates any of this (CLAUDE.md Settings
      boundary). **There are none — keep it that way.** Every knob here is a **user/book setting**.
- [ ] **8 · 🔴 `/review-impl` RUN ON THE WAVE'S DIFF, and EVERY bug it finds FIXED before the wave closes.**
      (PO policy #2. This is a literal step, not a suggestion. Proactively in scope because the wave
      touches a **tenancy boundary** (per-user active Work), a **paid action** (decompose), and an
      **OCC/lost-update** seam.)
- [ ] **9 · `docs/sessions/SESSION_HANDOFF.md` updated** — the ▶ NEXT SESSION block + the §9 Deferred rows
      filed — **and committed in the SAME COMMIT as the code.**
- [ ] **10 · The wave committed.** Stage **only** changed files. 🔴 **NEVER `git add -A`** — this is a
      shared checkout with three live tracks on this branch (plan 30 §9); enumerate paths. And remember:
      **`git commit -- <path>` commits the WORKING TREE, not the index**, and **the index may already
      carry another agent's pre-staged changes** — check `git diff --cached` first.

---

## 9 · Defer register — the starting rows

**File these in `docs/sessions/SESSION_HANDOFF.md` (Deferred Items) in the SESSION commit.**
Every row: ID · origin · what · gate (CLAUDE.md's 5) · target.

> 🔴 **RECONCILED. FIVE ROWS ARE DELETED — each was REFUTED BY CODE, not re-scoped.** A defer row costs
> real money (it is re-read at every PLAN and re-evaluated every session), and CLAUDE.md's gate is
> explicit: *"if fixing the bug is cheaper than writing + carrying its defer row, just fix it."*
> **A run that only grows its defer list is applying the gate too loosely.**

#### ✅ Recently cleared — DELETED from the register (the premise was false)

| ID (was) | Why it is NOT defer-eligible | Now |
|---|---|---|
| ~~`D-DIVERGENCE-SPEC-EDIT`~~ | *"UNBUILDABLE — needs new write semantics."* **FALSE.** `pack.py:153-157`: *"an edited override takes effect on the next pack."* Tables, index, repo pattern, EDIT gate all exist. *"New write semantics"* = **an UPDATE statement.** | 🔨 **W6-BE6** (C13) |
| ~~`D-REF-UPDATE-AND-MODEL-SURFACE`~~ | The `(source, ref)` tuple is **already computed and thrown away** (`references.py:92`). **A discarded value is not missing infrastructure.** ~4 lines + a 40-line route. | 🔨 **W6-BE7** (C14) |
| ~~`D-REFERENCES-MCP-TOOLS`~~ | Gate #3 false — **every prerequisite exists at HEAD**, and this wave **already builds six tools of exactly this shape in the same file.** **GG-2.** | 🔨 **W6-BE4b** (C15) |
| ~~`D-DIVERGENCE-MCP-TOOLS`~~ | *"Deserves its own confirm design."* **FALSE.** The AN-8 spine is **generic, 11 descriptors**, and an MCP path **already mints a knowledge project.** | 🔨 **W6-BE8** (C15) |
| ~~`D-WAVE6-DISCOVERY-SCENT`~~ | *"`stream_service.py` is uncommitted and mid-edit."* **FALSE at HEAD** — Track C's edits are **committed**; the tree is **clean**. **A dirty file is a wait of minutes, never a defer row.** | 🔨 **W6-BE9** (C16) |
| ~~`D-WORK-MODEL-ROLES-DEFAULT-REF`~~ | *"8 `scripts/eval_*.py` still read the legacy scalar."* **FALSE.** `grep -rn "default_model" scripts/` = **6 hits, ALL `user_default_models`** (an unrelated provider-registry table); **no `scripts/eval_*.py` file exists.** Gate #2 has **nothing under it**. The real residual is **4 FE lines** and they are a **HARD PREREQ of EC-4**. | 🔨 **FE-21b, inside W6-M4a** |

#### The rows that STAND

| ID | Origin | What | Gate | Target |
|---|---|---|---|---|
| `D-STRUCTURE-TEMPLATE-AUTHORING` | W6-M4a | **BE-12** — `POST /templates` · `PATCH\|DELETE /templates/{id}` · `POST /templates/{id}/clone` + a **beats-array authoring editor**. 🔴 **Grounding (not taste): `grep -c structure_template …/mcp/server.py` = 0** — **NO MCP tool authors a template either**, so this is **NOT a GG-1 gap** (no capability is trapped behind the chat window); it is **net-new product scope**. **Explicitly NOT gate #4 — it is buildable in-repo; it is scoped out, not blocked.** **BUILD CONTRACT WHEN IT LANDS (binding, so it is never re-litigated):** (a) **CLONE-TO-USER ONLY** — a write sets `owner_user_id = caller`; (b) `PATCH`/`DELETE` MUST return **403 (not 404)** when the target row has `owner_user_id IS NULL` (**System tier — the `entity_kinds` bug**); (c) every write filters `WHERE id=$1 AND owner_user_id=$2`; (d) uniqueness is `UNIQUE(owner_user_id, name)`, **never `UNIQUE(name)`**; (e) required test: user A cannot PATCH/DELETE a built-in (403) and cannot see/mutate user B's template (404); (f) its own tenancy review + `/review-impl`. **v1 mitigation ALREADY SHIPPED:** the picker renders an **honest static hint** (`data-testid="structure-template-custom-note"`) — 🔴 **NO disabled button, NO control that opens nothing** (that would be the `silent-success-is-a-bug` class shipped into the picker). **Also: do NOT modify `StructureTemplatesRepo`** — its `list_for_user`/`get` already union `owner_user_id IS NULL OR = $1` and already 404-not-leak; the dead `= $1` branch is **forward-compat, not a bug.** | **#5** (conscious won't-fix) + **#1** (out of scope) | the first real request for a custom structure, **OR** the moment any MCP tool gains a `structure_template` write (**that would instantly make it a GG-1 violation and force the GUI**) |
| `D-STUDIO-MOBILE-SHELL` | W6-M5 | 🔴 **The Studio has NO mobile editing surface.** `MobileEditorShell.tsx` + `MobilePanelSwitcher.tsx` exist **only** on the legacy path. **M5c ships the redirect** (mobile → the legacy editor) **and the machine-check** that the route stays mounted — so the product is no longer *stranded*, but the Studio still has no mobile shell. **A HARD BLOCKER on any deletion.** 🔴 **RECLASSIFIED #4 → #2:** nothing is waiting on the PO. **A Studio mobile shell is a real, buildable, multi-slice track** (a mobile group-bar over the dock: Editor / panel switcher / History, mirroring `MobileEditorShell`'s three-group pattern, driven by `useIsMobile()` at `StudioFrame`). **It is unbuilt work, not a blocker.** | **#2** (large/structural) | before any deletion of `ChapterEditorPage` |
| `D-EDITORBRIDGE-SINGLETON` | W6-M5 | 🔴 **THE ROW'S PREMISE WAS FALSE AND IS NOW FIXED.** It does **NOT** *"die with the page"*: **there are TWO registrants and ONE IS THE STUDIO** — `features/studio/panels/EditorPanel.tsx:100` registers the **checkpoint-wrapped `applyProposedEdit`**; `pages/ChapterEditorPage.tsx:284` registers the legacy one. Consumer: `ProposeEditCard.tsx:55,70,100`. **Deleting `editorBridge.ts` with the page BREAKS Studio `propose_edit` Apply on every AI edit.** 🔴 **RECLASSIFIED #3 → #2:** killing the singleton is a **REPLACEMENT REFACTOR** — point `ProposeEditCard`'s three `getEditorTarget()` reads at `ManuscriptUnitProvider` context (**reachable**: `StudioFrame.tsx:137` hoists the provider **above** `StudioDock`) — **not a delete.** The popout relay path is **unaffected** (a separate JS realm; it has neither the singleton nor the context). **M5d ships a hygiene test that FAILS if a future builder deletes it with the page.** | **#2** (large/structural — a replacement refactor across 3 surfaces) | **AFTER** the page is deleted **AND** `ProposeEditCard` is migrated to context |
| `D-WORK-BLIND-PATCH-NO-VERSION-BUMP` | W6-BE1 (**C4**) | `WorksRepo.update` bumps `version` **only when `expected_version` is passed** — a **blind** PATCH is **invisible** to a later If-Match write. A real OCC hole. **Do NOT "fix" it inside this wave**: bumping on blind writes would **412 every If-Match caller after any world-map drag.** Needs a design (probably: make `useWorldMap` If-Match + chain, **then** bump unconditionally). | **#2** (structural — it changes OCC semantics for 5 call sites) | with `D-WORLDMAP-OCC` |
| 🔴 `D-COMP-PLANNER-BOOK-TIER` | W6-M4a (**NEW**) | composition-service resolves the **planner** model from provider-registry's **account-tier** `/internal/planner-model` (`clients/llm_client.py:161-184`) and **never consults the book's `model_roles.planner`**. The GUI's planner row **is** legitimately CONSUMED (chat-service's cascade reads the Book tier), so it is **not write-only at platform level** — **but composition's own planner ignores it.** | **#2** (large/structural — wider blast radius) | its own slice |
| `D-GG4-PARITY-ROWS-PENDING` | W6-M5 | 🔴 **FILE THIS ROW — it is NOT conditional. Wave 6 runs BEFORE Wave 8**, so **exactly three** `legacyParityContract` rows ship as `{ pending: 'Wave 8 / W8-1x' }`: **`cast` → `cast` (W8-16)** · **`arc` → `character-arc` (W8-17)** · **`flywheel` → `canon-growth` (W8-18)**. The `it.fails('GG-4: zero pending rows')` assertion is **RED at Wave 6's close BY DESIGN** — that is the gate holding. **W8-16/17/18 flip all three; only then does it go green** (and deletion is *still* blocked on `D-STUDIO-MOBILE-SHELL` / E-3). ⚠ **`worldmap` is NOT on this list** — it is a `{retired:…}` won't-port (wave-8 §5.4). **There is NO `place-graph` panel and no wave builds one; do not invent the id to get green.** **Do NOT delete the rows, and do NOT re-point one at a panel that is not the thing.** | **#3** (naturally-next-phase) | **Wave 8 / W8-16·17·18** |
| 🔴 `D-36-I18N-LOCALES` | §6 step 4 (**NEW, conditional**) | *(File ONLY if LM Studio :1234 is down at build time.)* The 17-locale fill for the new `studio` keys. `fallbackLng:'en'` means a missing key **renders English — degraded, never broken.** **Drain it in ONE batched `--ns studio` run at wave close**; check for residual `_FAILED.json`. | **#4** (blocked — needs a local model process) | wave close |
| 🔴 `D-36-LIVE-SMOKE` | §8 DoD 5 (**NEW, conditional**) | *(File ONLY if the stack is genuinely un-bootable.)* The five Playwright specs. **A skipped test reports GREEN — so this row, plus the `live infra unavailable: <reason>` token, is the ONLY honest alternative to a pasted `0 skipped` summary.** | **#4** (blocked — infra) | when the stack boots |

⚠ **`D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH` stays DORMANT** as long as **no builder copies `outline_node`
rows into the derivative partition** (plan 30 §10). W6-BE6 explicitly does not.

### The open questions, DECIDED

🔴 **The adjudication register EXISTS: [`docs/plans/studio-adjudication/wave-6-decisions.md`](studio-adjudication/wave-6-decisions.md)
(64 items · 56 DECIDED). IT IS THE SOURCE OF TRUTH — this table is a summary index, not a substitute.
Do not re-open a decision from memory: RE-READ THE REGISTER.**

| # | Question | **DECIDED** | Register |
|---|---|---|---|
| **OQ-1** | Is structure-template authoring (BE-12) in v1? | **NO — defer.** The picker renders the 6 built-ins + an **honest static hint**; 🔴 **NO disabled button, NO dead control.** The binding build-contract is in the defer row above. | `Q-36-OQ1-BE12-TEMPLATE-AUTHORING` |
| **OQ-2** | Delete `ChapterEditorPage`? | **KEEP — and it was never de-authorized.** *"A decision to keep it around, not a decision pending removal"* (spec 16 Phase 4b, sealed 2026-07-05). **Deletion is NOT in this wave and is NOT queued for a later one.** M5 ships the parity contract **as a machine-checked INVENTORY**, not a pre-deletion gate. 🔴 **DO NOT write `legacyEditorRouteRetired.test.tsx`** — spec 36 says it *"lands WITH the deletion, not before."* There is no deletion. | `Q-36-OQ2-CHAPTEREDITORPAGE-DELETE` · `Q-36-GG4-MOBILE-BLOCKER` |
| **OQ-3** | Point Decompose at the existing route instead of building BE-20? | **NO — BUILD BE-20**, and it is **CHEAPER than feared**: the Tier-W spine is **already built and already carries 10 descriptors**. Porting a known cost-gate hole onto a new surface is **self-refuting**. | `Q-36-OQ3-BE20-VS-RAW-DECOMPOSE` |
| **OQ-4** | How many references does a typical Work hold? | 🔴 **CLOSED — MEASURED: N = 0** (0 rows / 0 works / 0 books; 0 works have `reference_embed_model_ref`). **⇒ NO CONSTANT IS HONEST.** The count is **LIVE** (`references.length`, i18n-pluralized). **Do NOT re-measure; do NOT hardcode.** | `Q-36-OQ4-REFERENCE-COUNT-N` |
| **OQ-5** | Does the Book tier reach chat-service end-to-end? | 🔴 **PARTIALLY EXERCISED ALREADY** (the legacy scalar dual-reads into role `chat` and **has a live GUI writer**). M4a is the first writer of the **`model_roles` KEY**. **TWO-LEG live smoke** (DoD #6) — and 🔴 **the route this plan named DOES NOT EXIST**; it is `GET /v1/chat/effective-settings?book_id=`. | `Q-36-OQ5-BOOK-TIER-CASCADE-UNEXERCISED` |
| **OQ-6** | Should `reference-shelf` surface the pinned refs `GroundingPanel` shows? | **NO — the split STANDS, and it is stronger than the question's premise:** 🔴 **`GroundingPanel` does NOT show reference items at all** — it **hard-filters** them. **There is nothing to "surface again."** Both panels **deep-link to each other** (and a **1-line cache bug** in `useReferences` is fixed in M2). | `Q-36-OQ6-SHELF-VS-GROUNDING-SPLIT` |
| **OQ-7** | Where does the per-user active Work live? | **`/v1/me/preferences`, FLAT dotted key `lw_active_work.<book_id>`** — 🔴 **the merge is SHALLOW, so a NESTED object would wipe every other book's active Work on each switch.** 🔴 **Store the SURROGATE `work.id`, NOT `project_id`** (which is **NULLABLE** for a lazy greenfield Work ⇒ persisting it stores **NULL for exactly the Works a user just created**). **Never `work.settings`** (per-book, SHARED — the `entity_kinds` bug). | `Q-36-OQ7-ACTIVE-WORK-HOME` · `Q-36-PREFERENCES-ARBITRARY-KEY` |
| **OQ-8** | Does BE-21 re-point `composer`/`planner` too? | **ONLY the 7 `critic` sites** — and 🔴 **there is literally nothing else to re-point in this service**: `composer` is taken **per-call** as `body.model_ref`; `planner` resolves from provider-registry's pinned default, **never** from `work.settings`. 🔴 **The eval scripts write `critic_model_ref`, NOT `default_model_ref`** — the legacy rung carries them with **zero edits**. | `Q-36-OQ8-BE21-SCOPE-CRITIC-ONLY` · `Q-36-DEFERRED-MODEL-ROLES-DEFAULT-REF` |

---

## 10 · Risks — and the TELL that each has happened

| Risk | The tell |
|---|---|
| 🔴 **The Composition section is a WRITE-ONLY editor** (BE-21 skipped or half-done). | The GUI proudly renders *"critic: gpt-4o · book"* **and every critique still returns *"critique skipped: no distinct critic model configured."*** **The tell is `test_critic_set_via_model_roles_is_NOT_skipped` staying red** — which is why it is M4a's gate, not a nice-to-have. |
| 🔴 **The Lane-B handler is a silent no-op** — someone writes `registerEffectHandler('composition_(style\|voice)_', …)` as a **string**. | The unit test **passes** (it registers and calls its own fake) and **the panel never refreshes after an agent write.** The tell is `matchEffectHandlers('composition_style_upsert').length === 0`. **That assertion is in W6-M1's test list for exactly this reason.** |
| 🔴 **`selectCanonicalWork` is called directly by a panel** instead of `useActiveWork`. | *Switch to* "works" — and then the Editor, the navigator, the quality panels and the scene-inspector **each independently snap back to canon.** The tell: the live smoke's **reload** step. A bus-only or `selectCanonicalWork`-direct implementation **fails it and passes everything else.** |
| 🔴 **Adding `composition.decompose` to `_ALL_DESCRIPTORS` without an explicit dispatch branch** (C2). | A decompose confirm **silently runs the CONFORMANCE effect** and enqueues the wrong worker op. The user pays. The tell: `test_an_unknown_work_scoped_descriptor_400s_and_does_NOT_run_conformance`. |
| **The `candidates[0]` hygiene test is written repo-wide** and reds on 5 unrelated sites (C1). | The next agent **deletes the test** to get green — and the guard is gone forever. The tell: the test file has no `SCOPES` array. |
| **A blanket `If-Match` on `patchWork`.** | The **world map 412s against itself on the second drag.** The tell: `test_a_world_map_drag_does_NOT_412` reds — it is in M4a's list. |
| **`TierChip` ships without the 4 new rows.** | The panel **looks done** and every chip reads a grey, tooltip-less `scene`. It **does not crash** (C9) — that is what makes it dangerous. The tell: the label test asserts `this scene`, not `scene`. |
| **`<CompositionPanel soloPanel="style"/>`** is used "for DOCK-2 reuse" (EC-6). | ~20 hooks fire per panel mount and `WorkspaceLayoutContext` is missing ⇒ a crash, or worse, a silent degrade. The tell: an import of `CompositionPanel` in `features/studio/panels/`. |
| **The panel-id enum count is asserted as a literal.** | A builder hunts a **phantom regression** after a wave re-order. The tell: any digit in a count assertion. |
| **`PlanDrawer.tsx` edited without reading its history.** | A silent merge conflict with the Book-Package track (plan 30 §9) — the file is **shared**. |
| **`stream_service.py` touched** for the discovery scent. | A collision with **Track C's uncommitted mid-edit.** It is on the explicit **DO NOT TOUCH** list. `D-WAVE6-DISCOVERY-SCENT` exists so it stays untouched. |
| **The live smoke is run against a host `vite dev` on :5174.** | It **SHADOWS** the baked nginx build and the smoke proves nothing about what ships. Rebuild the image first. |
| **A new DB-touching test lands without `xdist_group("pg")`.** | Parallel workers interleave, the counts lie, and the suite is flaky-green. |
| 🔴 **The style panel ships the READOUT fix and leaves COMMIT-ON-TOUCH.** | **A user opens an inherited scene, TOUCHES a slider, and their chapter's 80/20 is silently overwritten with a 50/50 row that emits NO directive at all.** *The GUI converts the lie into persisted truth.* The tell: `test_ANTI_CLOBBER_touching_an_inherited_slider_writes_NOTHING` is missing or red. |
| 🔴 **`ALL_TABS` / `SubTab` are not exported first (M5a).** | **The entire GG-4 gate — the thing this wave exists to earn — DOES NOT COMPILE.** The tell: `import { ALL_TABS } from '…/CompositionPanel'` fails to resolve. |
| 🔴 **The parity map keeps `flywheel: 'quality-corrections'` or `arc: 'arc-templates'`.** | **The machine-checked gate goes GREEN on a feature being DELETED.** These are the single most dangerous lines in the whole gate: they *look* like homes and are not. The tell: the map has fewer than 25 rows, or a row points at a panel whose data comes from a different service. |
| 🔴 **`compose` / `assemble` get no panel.** | GG-4's retirement deletes `ComposeView` (the **only** diverge→converge→accept→**correct** loop, and the **only** `useAdaptFromSource` surface) and `ChapterAssembleView` (the **second** correction producer). **The chat `compose` panel and `agent-mode` are NOT substitutes.** The tell: the map row points at `'compose'` or `'agent-mode'`. |
| 🔴 **The Playwright spec is written to `frontend/e2e/`.** | `testDir` is `./tests/e2e/specs` ⇒ **the "mandatory" smoke collects ZERO tests and reports green having run nothing.** And `studio-editor-craft.spec.ts` **already exists** — writing there **clobbers a prior `/review-impl` HIGH regression guard.** |
| 🔴 **A builder writes a defer row for BE-13 / BE-17 / the reference-or-divergence MCP tools / the discovery scent.** | **All five premises were REFUTED BY CODE** (C13–C16). Re-deferring them means the register was not read. The tell: any of those five IDs re-appearing in `docs/deferred/DEFERRED.md`. |
| 🔴 **`_execute_decompose` gates on `composition_worker_enabled`.** | With the flag **off**, the confirm **runs a paid LLM synchronously inside the request** — no 202, no poll, no job row. The tell: `test_decompose_confirm_ALWAYS_enqueues_even_with_the_worker_flag_OFF` is missing. |
| 🔴 **The active Work is persisted as `project_id`.** | It is **NULL** for exactly the Works a user just created (lazy greenfield) ⇒ *Switch-to* **silently fails to restore them** and the reload DoD fails **invisibly**. The tell: the pref value is not `work.id`. |
| 🔴 **The `lw_active_work` pref is written as a NESTED object.** | The server merge is a **shallow** top-level `||` ⇒ switching Work on book B **silently wipes book A's**. **A single-book reload test passes anyway.** The tell: no two-book test. |
| 🔴 **`resolve_model_role` is destructured positionally.** | Two of this plan's own sources disagreed on `(ref, source)` vs `(source, ref)`. **It type-checks nowhere** and silently swaps the model with its provider tag. The tell: any `a, b = resolve_model_role(...)` instead of `.model_ref` / `.model_source`. |
