# 33 · Motif Studio — the narrative-craft layer (套路/爽点/打脸), ported and made real

> **Status:** 📐 SPECCED 2026-07-13 · 🔎 **ADVERSARIALLY REVIEWED + AMENDED 2026-07-13** · no implementation this phase (plan 30 **PO-4**) · branch `feat/context-budget-law` (studio track)
>
> **⚠ WHAT THE REVIEW CHANGED — read §1.1 before you plan or build anything.** The first draft of this
> spec asserted **four** live bugs. Verification against the code found that **two of them cannot occur**
> (**M-BUG-2** and **M-BUG-3** are now **REFUTED**, with the evidence), because every writer of
> `motif_application` replaces a node's row rather than appending — an invariant the spec had not
> noticed and the schema does not enforce. The **real** defect (**M-BUG-1**) is that four readers depend
> on that unenforced invariant, so **BE-M1 is now a DDL change** (a partial UNIQUE index), not a repo
> rename. Also corrected: **§8.4** claimed all four paid actions are confirm-gated — **Regenerate is
> not** (OQ-5, now closed: `POST /works/{pid}/generate` spends with no gate, exactly like the shipped
> ComposePanel); **§3.0** was missing its **X-2** dependency; **§7.2**'s *"call its `refresh()`"* was not
> implementable; **§3.1**'s Book/Shared tabs shared one unfiltered route.
> **Type:** FS · **Size: XL** — split into **3 shippable milestones** (3a library+graph · 3b binding lens + suggest · 3c conformance trace + the 404 fixes). Each ends at a POST-REVIEW and is independently revertable (GG-7).
> **Wave:** 3 of [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §7.
> **Gaps closed:** **G-MOTIF-LIBRARY** (L) · **G-MOTIF-BINDING** (M) · **G-CONFORMANCE-TRACE** (M) · **G-MOTIF-SUGGEST** (S). Absorbs deferred rows `D-MOTIF-LIBRARY-CRUD-GUI`, `D-QUALITY-MOTIF-ROLLUP`.
> **New panels:** `motif-library` (category `storyBible`) · `quality-conformance` (category `quality`, DOCK-8 sibling). **Enum `N_before + 2`.** ⚠ **Never assert a literal count.** 57 is the count at HEAD `9262ed53e`, but **Waves 1 and 2 land 5 panels before this one** (`quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`, `arc-inspector`), so the baseline when this wave starts is **62**, not 57. Assert the **three-way equality + the delta** (`N_before + 2 == N_after` across py enum == contract enum == openable), never `59 == 59 == 59` — a literal sends the next builder hunting a phantom regression (the framing [`36`](36_editor_craft_ports.md) §Registration gets right).
> **Not new panels:** a **Motifs section** in `scene-inspector` + a bind affordance on PlanDrawer's chapter variant (spec 21 classifies motifs as a *cross-ref lens*; **24-PH19 already specs this verbatim** and only the READ half shipped) · **2 suggest BUTTONS**.
> **🔴 HARD GATE:** **X-7 (`gather_motifs` packer lens) must be green before ANY panel in this wave ships.** Without it the whole wave is decoration — see §2.1.
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), plan 30 §8 (GG-8) + §8.1 (spec-28 constraints — **not re-litigated here**).
> Design drafts (GG-6, must exist before BUILD — both WRITTEN 2026-07-13): `design-drafts/screens/studio/screen-motif-library.html` · `design-drafts/screens/studio/screen-motif-binding-and-conformance.html`.

---

## 1 · Why this exists

The entire narrative-craft layer of this product — the motif library (套路), the beat/tension
targets (爽点), the reversal machinery (打脸) — is **built, tested, and unreachable**. It lives on
`ChapterEditorPage`, the page spec 16 slates for deletion, mounted at
[`CompositionPanel.tsx:879`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L879)
(`MotifLibraryView`) and [`:886`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L886)
(`ConformanceTraceView`). **86 files** under `frontend/src/features/composition/motif/**` — ~30
components, 26 test files — and a Studio user can reach **none of it**.

What the Studio shows instead: a **non-interactive `<span>`**. `NodeBadges.tsx:124-145` renders
`case 'motif'` as a chip with a `title=` tooltip and no `onClick`. That is the sum total of motif in
the Writing Studio.

**This is a PORT, not a build.** The shape of this spec is *what changes*, not *what to build*.

### 1.1 The defects this wave must fix (all verified against code, none in the audit)

The audit named three live 404s. Reading the code found **two more real defects** (M-BUG-1, M-BUG-4)
— and **refuted two that an earlier draft of this spec asserted as live** (M-BUG-2, M-BUG-3). The
refutations are recorded here rather than deleted, because they are exactly the kind of claim a later
agent will "rediscover" from the SQL alone.

> **⚠ THE INVARIANT THAT REFUTES TWO OF THEM — verify it before trusting any of the four predicates.**
> **An `outline_node_id` can hold AT MOST ONE `motif_application` row.** Every writer maintains this:
> `_bind_scene_motif` ([`plan.py:843-844`](../../../services/composition-service/app/routers/plan.py#L843)) and
> `apply_motif_swap` ([`motif_select.py:470`](../../../services/composition-service/app/engine/motif_select.py#L470)) and
> `arc_apply` ([`:438`](../../../services/composition-service/app/engine/arc_apply.py#L438)) **`delete_for_nodes` before they insert**;
> every other `insert_many` call site (`plan.py:774`, `plan.py:1377`, `motif_select.py:491`, `arc_apply.py:485`)
> writes onto scene nodes **created in the same transaction**. There is **no append-only re-bind path.**
> **`motif_application` is therefore NOT a per-node ledger — it is a per-node CURRENT-binding table
> with a ledger-shaped API over it.** That mismatch is the real defect (M-BUG-1); the "superseded row"
> symptoms it *appears* to imply (M-BUG-2, M-BUG-3) **cannot occur**.
> **And nothing ENFORCES the invariant** — `motif_application` has an ordinary
> `INDEX idx_motif_application_node ON motif_application(outline_node_id)`
> ([`migrate.py:882`](../../../services/composition-service/app/db/migrate.py#L882)), **no UNIQUE constraint**.
> It holds by convention across 5 writers. That is what BE-M1 closes.

| # | Bug | Verdict + evidence |
|---|---|---|
| **M-BUG-1** | 🔴 **Four predicates answer "which motif is bound to this node," they return four different SHAPES, and the invariant they all depend on is enforced nowhere.** | **CONFIRMED (as a latent-invariant defect, not a live wrong-answer).** `MotifApplicationRepo.by_nodes()` ([`motif_application.py:94-111`](../../../services/composition-service/app/db/repositories/motif_application.py#L94)) returns a **list**, `ORDER BY created_at` ASC, and its docstring calls it *"the bound motif per node"* — **singular language over a plural return**. `ConformanceTraceReader.apps_by_nodes()` ([`conformance.py:95-113`](../../../services/composition-service/app/routers/conformance.py#L95) — a private reader **inside a router**) returns a **dict**, `DISTINCT ON (outline_node_id) … ORDER BY created_at DESC`. `plan.py:1035` takes `bound[0]`. `_MOTIF_CHIPS_SQL` takes them all. **All four are CORRECT TODAY and only because of the unenforced invariant above.** The day any writer appends instead of replacing, they break in **four different directions**, and two of them (`bound[0]`, the chips) fail **silently and wrongly**. This is the `close-legacy-window-in-writer` shape inverted: the writers are right and the readers are defensive-in-name-only. **BE-M1 = make the invariant explicit (a partial UNIQUE index) + collapse the four predicates to one.** |
| **M-BUG-2** | ~~The re-role write guard reads the OLDEST binding.~~ | 🚫 **REFUTED — DO NOT RE-RAISE.** The reasoning *looks* airtight: `plan.py:1035-1036` does `bound = await apps.by_nodes(…); app = bound[0]` over an ASC list, and 160 lines later the same file comments *"by_nodes is created_at ASC → **last** wins on a re-bind"* ([`plan.py:1196`](../../../services/composition-service/app/routers/plan.py#L1196)) and builds a dict so the last wins — **the file does disagree with itself, stylistically.** But `by_nodes(project_id, [node_id])` on a single node returns **≤ 1 row** (the invariant above), so `bound[0]` **IS** the current binding and the re-role guard validates against the **right** motif. Likewise `set_role_binding`'s `UPDATE … WHERE project_id = $1 AND outline_node_id = $2` with **no id filter** ([`:137-163`](../../../services/composition-service/app/db/repositories/motif_application.py#L137)) updates **exactly one row**. ⚠ **A regression test for this CANNOT be written to red on the old code** — the behavior is correct. It is a **readability + robustness** defect, folded into BE-M1. |
| **M-BUG-3** | ~~The plan-hub motif chips render superseded bindings.~~ | 🚫 **REFUTED — DO NOT RE-RAISE.** `_MOTIF_CHIPS_SQL` ([`plan_overlay.py:112-123`](../../../services/composition-service/app/db/repositories/plan_overlay.py#L112)) genuinely has **no `DISTINCT ON`** and the FE genuinely does not de-dupe (`motifChipsFor()` is a bare `.filter` at [`nodePresentation.ts:152`](../../../frontend/src/features/plan-hub/components/nodePresentation.ts#L152), `MOTIF_CHIP_CAP = 2` at [`:157`](../../../frontend/src/features/plan-hub/components/nodePresentation.ts#L157)) — **but there are no superseded rows to render.** `node_ref` is `COALESCE(outline_node_id, structure_node_id)`, and **every** row carrying a `structure_node_id` also carries an `outline_node_id` (`arc_apply.py:485` sets both), so `node_ref` always resolves to the outline node ⇒ **≤ 1 chip row per node.** A node "re-bound twice" renders **one** chip, the current one, today. The `MOTIF_CHIP_CAP = 2` truncation is for a node with **multiple distinct** motifs, which the write path also cannot produce. **No fix, no regression test.** *(The `DISTINCT ON` is still worth adding as belt-and-braces alongside BE-M1's UNIQUE index — but as hardening, not a bug fix, and it changes nothing a user can see.)* |
| **M-BUG-4** | 🔴 **Arc-conformance is dead on both transports — the FE still sends `arc_template_id` after spec 23's BA4 retarget renamed it `arc_id`.** | **CONFIRMED — verified on both paths.** The MCP tool's `_ConformanceRunArgs` is `ForbidExtra` ([`server.py:3104-3117`](../../../services/composition-service/app/mcp/server.py#L3104)) with `arc_id: str \| None` and **no** `arc_template_id` → `motifApi.arcConformanceRunPropose` ([`api.ts:257`](../../../frontend/src/features/composition/motif/api.ts#L257)) sends `arc_template_id` → **422 on every call**. The REST GET ([`conformance.py:339`](../../../services/composition-service/app/routers/conformance.py#L339)) takes `arc_id` (a **`structure_node.id`**); `motifApi.arcConformance` ([`api.ts:215`](../../../frontend/src/features/composition/motif/api.ts#L215)) sends `arc_template_id`, FastAPI **silently drops the unknown query param**, `arc_id` is `None` → `_resolve_book_arc` raises **422 `ARC_ID_REQUIRED`** ([`conformance.py:326-327`](../../../services/composition-service/app/routers/conformance.py#L326)). And `ArcConformancePanel` passes `arcTemplateId={openArc.id}` — **an arc_template id, which is the wrong entity class entirely.** The old template comparison moved to `scope=arc_template_drift`. A `cross-service-normalization` bug: a value crossing a boundary was renamed on one side. Not in the audit. **This one has a real regression test that reds on the old code.** |

### 1.2 The 404s — the audit found three; **there is a FOURTH, and it is in THIS wave's Mine button**

| FE call | Caller | Backend |
|---|---|---|
| `POST /v1/composition/actions/conformance_run/estimate` | [`api.ts:224`](../../../frontend/src/features/composition/motif/api.ts#L224) ← `useConformanceTrace.ts:32` | **MISSING** |
| `POST /v1/composition/actions/conformance_run/confirm` | [`api.ts:230`](../../../frontend/src/features/composition/motif/api.ts#L230) ← `useConformanceTrace.ts:36` | **MISSING** |
| `POST …/scenes/{node_id}/regenerate-to-beat` | [`api.ts:301`](../../../frontend/src/features/composition/motif/api.ts#L301) + `useMotifBinding.ts:66` ← `ConformanceTraceView.tsx:69` | **MISSING** — appears nowhere in `services/**/*.py` |
| 🔴 **`GET /v1/composition/jobs/{id}` as the MINE poll** | [`motifApi.mineConfirm`](../../../frontend/src/features/composition/motif/api.ts#L164) → `compositionApi.getJob(resp.job_id)` ← `useMotifMine` ← **`MotifMinePanel` — a component THIS WAVE ports in 3a** | 🔴 **EXISTS BUT 404s ON EVERY MINE JOB.** `_execute_motif_mine` ([`actions.py:644`](../../../services/composition-service/app/routers/actions.py#L644)) enqueues with **`project_id=None`** → `_enqueue_motif_job` ([`:552`](../../../services/composition-service/app/routers/actions.py#L552)) stamps a **synthetic `uuid4()`** → `GET /jobs/{id}`'s `_gate_work(…, job.project_id, VIEW)` → `works.get(<synthetic>)` → `None` → **404 `work not found`, always.** |

The first two are a **pure FE invented-URL bug**, and the file *contains its own fix*:
`arcConformanceRunPropose` ([`api.ts:245-273`](../../../frontend/src/features/composition/motif/api.ts#L245))
already does it correctly — `mcpExecute('composition_conformance_run')` → `POST /actions/confirm?token=`.
The chapter-scope twin was hand-rolled against two routes nobody wrote. **Delete both; mirror the sibling.**

The third is §5's decision **BE-5**, and the audit's proposed fix is wrong. See §5.1.

🔴 **The fourth was found by the spec-34 review (its §0.1) and is CORRECTED INTO THIS SPEC** — because the
broken component is **ours**, not Wave 4's. Plan 30 §10 REFUTED *"`composition_motif_mine` has no FE reach"*
on the grounds that `MotifMinePanel` + `useMotifMine` + `motifApi.minePropose/mineConfirm` ship *"with a
passing test"* — **the test mocks the poll.** The propose→confirm half works; **the poll has never
resolved.** A user clicks ⛏ Mine, pays for the LLM run, and watches a spinner forever.

⇒ **`GET /v1/composition/motif-jobs/{job_id}` (the owner-scoped job read) is a HARD PREREQUISITE OF 3a,
not of Wave 4.** It is specced once, in [`34_arc_templates_and_deconstruct.md`](34_arc_templates_and_deconstruct.md) §5
as **BE-7c** (owner gate on `created_by`, uniform H13 404, **XS**) — *that row is the contract; do not
re-spec it here*. **This wave BUILDS it** (3a), because this wave is the first to ship a GUI that polls a
Work-less job. Wave 4 then consumes it for 拆文. ⚠ The same row also changes `composition_get_mine_job`
(drop the un-knowable `project_id` arg → gate on `created_by`); that change lands **here**, in 3a, so
Wave 4 inherits a working tool rather than breaking this wave's consumer. `_execute_conformance_run`
([`actions.py:723`](../../../services/composition-service/app/routers/actions.py#L723)) passes a **real**
`project_id`, so **conformance is unaffected** — this is a mine/import-only defect.

---

## 2 · What is already built (be specific — this is what makes the estimate trustworthy)

### 2.1 🔴 The hard gate: generation does not read motifs

```
$ grep -rn "motif" services/composition-service/app/packer/
$ echo $?
1
```

**Zero hits.** The packer — `lenses.py`, `pack.py`, `assemble.py`, `budget.py` — has never heard of a
motif. The Hub **renders** motif chips (`NodeBadges.tsx:124`), the binder **writes**
`motif_application` rows, the conformance engine **grades** the prose against them, and `pack()`
**never injects them into a prompt**. The author binds 打脸 to chapter 41 and the drafter is never
told.

This is the *stored-but-unread ⇒ write-only-behavior* class CLAUDE.md's Settings & Configuration
Boundary bans by name. **Every panel in this wave authors data with no consumer until X-7 lands.**
Spec 21 filed it as **G1**; plan 30 filed it as **X-7 / BE-19**. It is a **prerequisite, not a
nice-to-have** — see §5.

The mirror already exists and is proven: **`gather_arc`** ([`lenses.py:257-300`](../../../services/composition-service/app/packer/lenses.py#L257)),
gated + best-effort at [`pack.py:331-337`](../../../services/composition-service/app/packer/pack.py#L331),
emitted as an `<arc>` block at [`pack.py:522-524`](../../../services/composition-service/app/packer/pack.py#L522),
and proven-by-effect by [`tests/integration/db/test_pack_arc_wired.py`](../../../services/composition-service/tests/integration/db/test_pack_arc_wired.py)
(⚠ **`integration/db/`, not `tests/` — and it is `skipif(not TEST_COMPOSITION_DB_URL)`**) — a **real-DB** test that drives the real
`pack()` through the real repos, written *because* the unit test injected a fake at the chokepoint
and therefore proved nothing (`test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired`).
**Copy that test's shape, not just the lens's.**

### 2.2 The FE that already exists (the port surface)

`frontend/src/features/composition/motif/**` — **86 files.** Split by wave:

**Ships in THIS wave (3a/3b/3c):**

| Slice | Files |
|---|---|
| library shell | `MotifLibraryView.tsx` · `MotifScopeTabs` · `MotifFacetRail` · `MotifCard` · `MotifDetailDrawer` · `MotifQuickCreateForm` · `MotifEditorForm` · `MotifEmptyState` · `MotifPanelBoundary` · `MotifStateBoundary` · `MotifLibraryKindToggle` |
| mine / adopt / sync | `MotifMinePanel` · `AdoptTargetModal` · `SyncDiffDrawer` · `CostConfirmCard` · `useMotifMine` · `useAdoptFlow` · `useMotifSync` · `useMotifDraftActions` |
| binding lens | `MotifBindingCard` · `SwapMotifPopover` · `RoleBindingRow` · `ChapterMotifBindings` · `CommittedSceneBindings` · `ChainItHint` · `OveruseBanner` · `InfoAsymmetryCard` · `useMotifBinding` · `useMotifBindings` · `useMotifCandidates` · `useRoleResolver` |
| conformance | `ConformanceTraceView` · `ConformanceSceneRow` · `useConformanceTrace` |
| shared | `api.ts` · `types.ts` · `simpleMode.ts` · `currentUser.ts` · `context/MotifSimpleModeContext.tsx` |

**Belongs to Wave 4 (`34_arc_templates_and_deconstruct.md`) — DO NOT PORT HERE:**
`ArcTemplateLibraryView` · `ArcApplyPreview` · `ArcMaterializeAction` · `ArcTimelineEditor` /
`Grid` / `MobileList` · `arcApi.ts` · `arcTypes.ts` · `applyArcEdit.ts` · `useArcLibrary` ·
`useArcApplyPreview` · `useArcMaterialize` · `useArcTimeline`.

**Ambiguous, decided here:** `ArcConformancePanel` + `useArcConformance` + `useArcConformanceRun`
are **arc-scope conformance** → they belong to **3c** (`quality-conformance`), not Wave 4. They are
currently mounted inside `ArcTemplateLibraryView.tsx:39`, which is why they *look* like arc-template
files. **M-BUG-4 lives here** — fix it in 3c, in the panel that owns the question.

### 2.3 🔴 The port trap the file layout hides

`MotifLibraryView.tsx` **is not a motif library.** [`:16`](../../../frontend/src/features/composition/motif/components/MotifLibraryView.tsx#L16)
imports `ArcTemplateLibraryView`, and [`:44`](../../../frontend/src/features/composition/motif/components/MotifLibraryView.tsx#L44)
holds `const [kind, setKind] = useState<'motifs' | 'arcs'>('motifs')` — a top-level tab switching the
whole panel between the motif library and **Wave 4's arc-template library**.

**A naive port of `MotifLibraryView` into a `motif-library` panel silently ships Wave 4's panel
inside it**, including `ArcConformancePanel` and M-BUG-4. **3a must SPLIT the component:** drop the
`kind` toggle, render the motifs half only. Wave 4 lifts `ArcTemplateLibraryView` into its own
`arc-templates` panel. This is a **breaking change to a legacy-page component**, which is fine —
`GG-4` says the legacy page dies *after* the ports, and a `kind` toggle whose "arcs" half moved to a
sibling dock panel is exactly what a port looks like.

### 2.4 Two more port traps

- **`useMotifSimpleMode()` degrades to a NO-OP outside its provider.**
  [`MotifSimpleModeContext.tsx:66-70`](../../../frontend/src/features/composition/motif/context/MotifSimpleModeContext.tsx#L66)
  returns `{ simple: true, setSimple: () => {}, toggle: () => {} }` when there is no `Ctx`. So if
  `MotifLibraryPanel` forgets to mount `MotifSimpleModeProvider`, the **Simple/Expert toggle renders
  and does nothing** — `silent-success-is-a-bug`, shipped. **Mount the provider inside the panel.**
- **`currentUserId()` reads `localStorage['lw_user']` directly**
  ([`currentUser.ts:8-17`](../../../frontend/src/features/composition/motif/currentUser.ts#L8)) to
  dodge an `AuthProvider` requirement in the legacy unit tests. In the dock, `useAuth()` is always
  available. **Pass `meUserId` from `useAuth()`** and leave the shim for the legacy tests. The
  tenancy tier (`motifTier`, `simpleMode.ts:19`) is derived from it — a null id silently downgrades
  every owned motif to the read-only `public` tier.

### 2.5 The backend that already exists (10 REST routes, 14 MCP tools)

| Capability | REST | FE today |
|---|---|---|
| list / get / create / patch / archive | `GET\|POST /motifs` · `GET\|PATCH\|DELETE /motifs/{id}` | ✅ `motifApi` |
| public catalog | `GET /motifs/catalog` | ✅ |
| **the book's library** (⚠ **NOT "the shared tier"** — it returns the caller's globals **+** the book's private labels **+** the `book_shared` rows, **merged, with no tier filter**; every row carries `book_id` + `book_shared` so the FE partitions it — §3.1) | `GET /motifs/book/{book_id}` | ❌ **NO-FE-CONSUMER** — 3a wires it, feeding **both** the Book and Shared tabs from **one** fetch |
| adopt (quota-gated) | MCP propose → `POST /actions/confirm` | ✅ (`mcpExecute`) |
| mine (LLM, async) | MCP propose → `POST /actions/confirm` → poll | ✅ |
| upstream-diff / sync | `GET /motifs/{id}/upstream-diff` · `POST /motifs/{id}/sync` | ✅ |
| bind / unbind / re-role / chain | `PATCH\|DELETE …/outline/{nid}/motif` · `PATCH …/motif/role` · `POST …/motif/chain` | ✅ `useMotifBinding` (legacy-only) |
| bindings read | `GET …/outline/motif-bindings` | ✅ |
| conformance read | `GET /works/{pid}/conformance?scope=chapter\|arc\|arc_template_drift` | ✅ (M-BUG-4) |
| conformance run (LLM) | MCP propose → `POST /actions/confirm` | ⚠ half-right (§1.2) |
| **the motif GRAPH** | **NONE** | ❌ `composition_motif_link_{list,create,delete}` — **no REST route, no GUI, agent-only** |
| **ranked suggest** | **NONE** | ❌ `composition_motif_suggest_for_chapter` · `composition_arc_suggest` — **agent-only** |

**The suggest gap, concretely.** `useMotifCandidates.ts` — the hook behind the shipped
`SwapMotifPopover` — is `motifApi.list({ scope: 'all', limit: 100 })`. **A flat, unranked list of 100
motifs.** The ranked, `match_reason`-explained suggest the backend already computes
(`MotifRetriever`, wired at [`deps.py:205`](../../../services/composition-service/app/deps.py#L205))
is reachable **only by asking the chat agent for it by name**. That is GG-1's Determinism +
Discoverability failure in one hook.

---

## 3 · The design

### 3.0 Shared rules for every surface in this wave

- **OCC.** `motif` carries `version`; `motifApi.patch` sends `If-Match: <version>`. On **412** the
  panel does **not** clobber: it re-fetches, renders a `MotifStateBoundary` conflict strip
  ("This motif changed elsewhere — reload to see the new version"), and keeps the user's edits in
  the form for copy-out. **Every chip/select over a motif serializes its writes** — a select fired
  twice rapidly self-412s the second write
  (`instant-commit-control-over-occ-entity-needs-write-serialization`).
- **Cost gates.** Every paid action goes through the **generic** spine:
  `mcpExecute(<propose tool>)` → `confirm_token` → `GET /v1/composition/actions/preview` (human-readable
  descriptor) → `POST /v1/composition/actions/confirm?token=` → poll `composition_get_mine_job`.
  **Never a per-action estimate/confirm route** (plan 30 §8.1; the two 404s in §1.2 are that exact
  mistake, already shipped).
- **Model picker.** Mine, conformance-run and regenerate are **BYOK** (`model_ref` + `model_source`).
  Each renders a `ModelPicker`, whose empty state renders `AddModelCta` → **Wave-0 X-1 is a hard
  dependency**: without it, that button `<Link>`s out of the SPA and **tears down the entire dock**
  (DOCK-7).
- 🔴 **Wave-0 X-2 is ALSO a hard dependency of this wave — and it was missing from the first draft of
  this spec.** `CATEGORY_ORDER` ([`useStudioCommands.ts:20-22`](../../../frontend/src/features/studio/palette/useStudioCommands.ts#L20))
  lists **nine** categories and **omits `'quality'`** — the category `quality-conformance` (§3.4) is
  registered under. `indexOf` returns **-1**, so the panel sorts **above `editor`** (index 0), i.e.
  **to the top of the Command Palette**. Note the inverted failure mode: a *missing* category sorts
  LAST; an *unlisted* one sorts FIRST. `panelCatalogContract.test.ts` asserts a category is *present*,
  **not** that it is a member of `CATEGORY_ORDER` — so nothing reds. **X-2 must land before 3c**, and
  its membership assertion is what stops this recurring.
- **Archived rows** are hidden by default behind a `Show archived` toggle in `MotifFacetRail`, and
  render with `.strike` + a Restore action. Archive is soft (`status='archived'`); the ledger row in
  `motif_application` survives (history).
- **Every panel root** carries `data-testid="studio-<id>-panel"`.

### 3.1 `motif-library` — a NEW dock panel (category `storyBible`) · **3a**

The hub. Detail is a **drawer**, create is an **inline form**, adopt is a **modal**, the graph is a
**section** — **none of them is a panel**. This is deliberate and load-bearing: plan 30 **X-12** says
`ui_open_studio_panel` carries a **bare id only**, so any panel needing a `motif_id` would have to be
`hiddenFromPalette` ⇒ out of the enum, out of the palette, out of the User Guide. **Keeping detail a
drawer sidesteps X-12 entirely.** A future agent who "improves" this by extracting a `motif-editor`
panel has introduced the bug, not fixed it.

**Layout** (mirrors the shipped `MotifLibraryView`, minus the `kind` toggle):

```
┌ MOTIF LIBRARY ────────────────────────────────── ⟳ ⌄ ✕ ┐
│ [ Mine │ Book │ Shared │ System │ Catalog │ Drafts ]     │  ← MotifScopeTabs (6, was 4)
│ [Simple⇄Expert]                        [⛏ Mine] [+ New]  │
│ ┌─ search ───────────────────────────┐ [Filters ▾]       │
│ │ kind · genre · status · language   │                   │  ← MotifFacetRail
│ ├──────────────────────────────────────────────────────┤ │
│ │ MotifCard × N   (tier chip + glyph + word, never hue │ │
│ │                  alone — a11y §5.3)                  │ │
│ └──────────────────────────────────────────────────────┘ │
│ ▸ Graph — composed_of · precedes · variant_of  (section) │  ← NEW (3a)
└ 42 motifs · 3 drafts ───────────────────────────────────┘
```

**Scope tabs — 6, and two are new.** The shipped component has `mine / system / all / drafts`. The
`book_shared` tier (`GET /motifs/book/{book_id}` — **NO-FE-CONSUMER today**) and the public `catalog`
get their own tabs. Tiers are §8.1's table; the tab is the tier.

⚠ **But ONE route feeds TWO of those tabs, and it is not filtered by tier — say how they split or the
Book tab duplicates Mine.** `GET /motifs/book/{book_id}` ([`motif.py:219`](../../../services/composition-service/app/routers/motif.py#L219))
returns, **merged in one list**: the caller's **global** motifs *(the Mine tier!)* **+** this book's
**private labels** **+** the book's **SHARED** tier. There is **no `tier` / `scope` query param.**
Its projection `_book_view` ([`:207-216`](../../../services/composition-service/app/routers/motif.py#L207)) *does*
return `book_id` + `book_shared` on every row — so **the split is a free client-side partition and needs
ZERO backend work**, provided 3a actually does it:

| Tab | Source | Filter applied in the FE |
|---|---|---|
| **Mine** | `GET /motifs?scope=mine` | — |
| **Book** | `GET /motifs/book/{book_id}` | `row.book_id === bookId && !row.book_shared` — **the `book_id` test is load-bearing**: without it the caller's globals (already on the Mine tab) are duplicated here. |
| **Shared** | the **same response** (one fetch, two views — do **not** call it twice) | `row.book_shared === true` |
| **System** | `GET /motifs?scope=system` | — |
| **Catalog** | `GET /motifs/catalog` | — |
| **Drafts** | `GET /motifs?status=draft` — ⚠ `draft` is a **`status`**, not a `scope` (`scope` is `^(mine\|system\|all)$`) | — |

**A reviewer who finds two `GET /motifs/book/{book_id}` fetches, or an un-`book_id`-filtered Book tab,
has found a defect.**

**The graph section (NEW, 3a).** `composition_motif_link_*` has **no REST route and no GUI** — the
motif relationship graph is invisible to humans. Render it as a **collapsed section inside the
drawer's motif** and as a book-wide section at the library foot:

- **Reads** `GET /motifs/{id}/links?direction=both` (BE-M3) → `composed_of` members · `precedes`
  successors · `variant_of` siblings, each with the neighbor's `code` + `name`.
- **Writes** `POST /motifs/{id}/links` (pick kind + neighbour from the library) and
  `DELETE /motif-links/{link_id}`.
- **Renders as a list, not a canvas.** A force-directed graph is a Wave-4/5 ask; the data is
  3 typed edge lists and a list is honest, cheap, and keyboard-navigable. A `.callout.bad` in the
  draft must say so, or the next agent will "fix" it with d3.
- **409 from the DB trigger** (`motif_link_guard`: self-link / cycle / cross-tier) renders inline on
  the form: *"A motif cannot precede itself, and a cycle would make the succession chain
  unresolvable."* **Do not swallow it into a generic toast** — the trigger is the spec.

**States (all must be rendered in the draft):**

| State | Render |
|---|---|
| empty (no motifs, `scope=mine`) | `MotifEmptyState` → two CTAs: *Adopt from the catalog* · *⛏ Mine your corpus* |
| loading | skeleton rows (`MotifStateBoundary`) |
| error | `MotifPanelBoundary` — the message + Retry. **Never an empty list on error** (`FE fallback ⇒ LIST omits field`) |
| OCC 412 on patch | conflict strip + re-fetch; edits preserved |
| archived | hidden unless `Show archived`; `.strike` + Restore |
| cost-gate (adopt) | `AdoptTargetModal` → `CostConfirmCard` (quota, `est_usd = 0` — adopt is quota-metered, not token-metered) |
| cost-gate (mine) | `MotifMinePanel` → ModelPicker + `CostConfirmCard` (`est_usd` from the propose envelope) |
| paid action in flight | mine job polling — progress + **Cancel is not offered** (the worker is not cancellable; say so, don't fake it) |
| mined drafts | `Drafts` tab; Promote (`PATCH status='active'`, OCC) / Discard (archive) |
| adopted + upstream moved | `SyncDiffDrawer` — per-field 3-way diff, accept-per-field |
| no BYOK model | `ModelPicker` empty → `AddModelCta` (**must** use `useOptionalStudioHost()` — X-1) |

**⚠ A known sub-gap, carried forward, not silently dropped:** the FE never sends `promote_target` on
mine, so **`book_shared` mined drafts are unreachable from the GUI** (plan 30 §10). 3a adds the
target selector to `MotifMinePanel` — it is a two-line arg and the tier now has a tab.

### 3.2 The binding lens — **NOT a new panel** · **3b**

Spec 21 classifies motifs as a **cross-ref lens**; **spec 24-PH19 already specs this verbatim** and
only the READ half (`NodeBadges`) shipped. Two surfaces, zero new panel ids:

**(a) A `Motifs` section in `scene-inspector`.** The panel already sections
Identity · Intent · Cast & Setting · Craft · Links · Grounding
([`SceneInspectorPanel.tsx:116-190`](../../../frontend/src/features/studio/panels/SceneInspectorPanel.tsx#L116)).
Add **Motifs**, between Craft and Links:

```
── MOTIFS ──────────────────────────────────────────
  打脸 · Face-slap  [system]        pin v3  ⚠ live v5 ↑
  ┌ Beat: the reversal lands ───────────────────────┐
  │ Roles:  aggressor → 李慕白   ·  target → (unset) │  ← RoleBindingRow (entity picker)
  │ Tension target: 4/5                             │
  └─────────────────────────────────────────────────┘
  [Swap…]  [Suggest a motif ✨]  [Unbind]  [Chain to next →]
```

- Reuses `MotifBindingCard` · `SwapMotifPopover` · `RoleBindingRow` · `ChainItHint` ·
  `InfoAsymmetryCard` · `useMotifBinding` **verbatim**.
- **Stale pin** (`live_version > pinned_version`) renders amber + `↑` with a **Re-pin** action
  (re-bind to the live version). This is the drift `NodeBadges` already *shows* and no one can *act* on.
- **Unbind uses the `undo_token` round-trip** (`composition_motif_unbind` with `undo_token` = the
  exact inverse; `undo_token` has **zero** frontend consumers today). ⚠ **`undo_token` is
  CHAPTER-scope only — a scene bind returns none.** Do **not** advertise token-undo on a scene node;
  the scene's inverse is a re-bind. Getting this wrong ships an Undo button that silently does
  nothing.

**(b) A bind affordance on PlanDrawer's chapter variant.** `PlanDrawer.tsx` today has zero motif
content (`grep motif PlanDrawer.tsx` → nothing); the chips live on the graph nodes. Add a
**Motifs** section to the chapter/scene facet, same component, plus a `Suggest` button. `NodeBadges`'s
`case 'motif'` `<span>` gains an `onClick` → `host.openPanel('scene-inspector')` focused on that node
(the `resource_ref` contract, Wave-0 **X-6**).

### 3.3 The two suggest buttons — **buttons, not panels** · **3b**

Spec 21: *"a button, not a panel."*

| Button | Host | Route | Wave |
|---|---|---|---|
| **Suggest a motif ✨** | `scene-inspector` Motifs section · PlanDrawer chapter facet | `GET /works/{pid}/motifs/suggest?chapter_id=` (**BE-M4**) | **3b — THIS WAVE** |
| **Suggest an arc ✨** | `arc-inspector` · `arc-templates` | **`POST /v1/composition/arc-templates/suggest`** — spec [`34`](34_arc_templates_and_deconstruct.md) **BE-7b**, *not* this spec's ~~BE-M5~~ | 🔴 **NOT THIS WAVE — Wave 4** |

🔴 **Arc-suggest is OUT OF SCOPE for Wave 3** *(cross-spec sweep, 2026-07-13)*. This spec's original
**BE-M5** (`GET /books/{bid}/arcs/suggest`) was a **duplicate of spec 34's BE-7b** — and the **wrong**
contract: `composition_arc_suggest` ([`server.py:2288`](../../../services/composition-service/app/mcp/server.py#L2288))
takes **`project_id`**, not a `book_id` path segment, and defaults **`limit=5`**, not 10. Two specs each
picked up one half of plan 30's own duplicate (its BE-6 *and* BE-7 both listed arc-suggest). **One tool,
one route, one owner: spec 34.** This wave ships **motif-suggest only**. The *Suggest an arc* button rides
34's route from `arc-inspector`/`arc-templates` — **do not build a second one here.**

Renders the ranked list the tools already return, **with the `match_reason` breakdown**
(tension / genre / precondition / semantic) via the shipped `MatchReasonChip`. Picking a row calls
the existing bind. This **replaces** `useMotifCandidates`'s flat 100-row list inside
`SwapMotifPopover` — keep the flat list as the "Browse all" fallback tab.

### 3.4 `quality-conformance` — a NEW dock panel (category `quality`, DOCK-8 sibling) · **3c**

The Studio's answer to *"did the prose actually realize the plan?"* is currently **a red/green dot**
(`useConformanceStatus.ts` — a book-level rollup). The full beat-by-beat trace is legacy-only.

Registers as the **5th card** in `QualityHubPanel`'s `CARDS`
([`QualityHubPanel.tsx:14-19`](../../../frontend/src/features/studio/panels/QualityHubPanel.tsx#L14))
— the same DOCK-8 hub pattern as `quality-canon`, `quality-critic`, `quality-coverage`,
`quality-promises`. **Do not build a 6th tab in a monolith.**

```
┌ CONFORMANCE ──────────────────────────────────── ⟳ ⌄ ✕ ┐
│ Scope: ( • Chapter  ○ Arc )   Ch.41 「反目」   [Re-run…] │
│ ⚠ Advisory — coarse, not causally verified (calibrated:no)│
├──────────────────────────────────────────────────────────┤
│ ✓ Scene 1  beat "setup"     realized  · tension 3→3      │
│ ⚠ Scene 2  beat "escalate"  realized  · tension 4→2  ↓   │
│ ✗ Scene 3  beat "reversal"  NOT realized             [↻] │  ← Regenerate
│ ✓ Scene 4  beat "aftermath" realized  · tension 2→2      │
└ 3/4 beats realized · last run 2 days ago · dirty ⚠ ─────┘
```

- **Reads** `GET /works/{pid}/conformance?scope=chapter&chapter_id=` (exists, consumed) and
  `?scope=arc&arc_id=<structure_node.id>` (exists — **fix M-BUG-4's arg name**).
- **`arc_template_drift`** (*"how far has my arc drifted from the template it came from"*) is a
  **separate question and a separate scope**. It belongs to **Wave 4** (`arc-templates`). This panel
  answers *spec vs prose*, not *spec vs template*. Say so in a `.callout.bad`.
- **Freshness** comes from `useConformanceStatus` (already shipped): a chapter is **dirty** when it is
  in a dirty arc's `stale_chapters`. Render the chip; do not recompute the predicate.
- **Honesty is a required render.** `calibrated: false` ⇒ the panel stamps **"Advisory — unverified"**
  at the top. The engine says the signal is coarse and never gates anything; the GUI must not imply
  otherwise.
- **Re-run** is Tier-W + BYOK: `mcpExecute('composition_conformance_run', {project_id, scope,
  chapter_id | arc_id, model_ref, model_source})` → `/actions/preview` → `/actions/confirm?token=` →
  poll. **Delete `conformanceRunEstimate` / `conformanceRunConfirm`** (`api.ts:223-235`) and mirror
  `arcConformanceRunPropose`.
- **Regenerate** — see §5.1. It becomes `composition_generate {outline_node_id}` through the same
  spine.

**States:** empty (no bindings on this chapter → "Bind a motif to a scene to trace it", deep-linking
to `scene-inspector`) · loading · error (`MotifPanelBoundary`) · **dirty/stale** (amber "canon moved
since this run" + Re-run CTA) · cost-gate (ModelPicker + `CostConfirmCard`) · run-in-flight (polling,
no fake cancel) · no BYOK model (X-1).

---

## 4 · Backend prerequisites — a contract; a later agent builds from this

Nothing here is blocked on anything external. Every row is **buildable now** (CLAUDE.md: *"missing
infrastructure is NOT blocked — it is unbuilt work"*).

| # | Route / unit | METHOD + path | Request | Response | Errors | Size | Status |
|---|---|---|---|---|---|---|---|
| **BE-M1** | 🔴 **ENFORCE the one-row-per-node invariant, then collapse the four predicates to one.** **(a) The DDL is the fix** — add `CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_application_node ON motif_application(outline_node_id) WHERE outline_node_id IS NOT NULL;` (partial — `structure_node`-only rows are exempt). This is the *only* change that makes the readers safe by construction rather than by convention; today the invariant lives in 5 writers and nowhere else (§1.1). ⚠ **Back-fill check first:** the index will fail to build if any node already holds >1 row. Run `SELECT outline_node_id, count(*) FROM motif_application WHERE outline_node_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;` on dev **and** state the result in VERIFY. A non-empty result **refutes §1.1's invariant** and re-opens M-BUG-2/M-BUG-3 — in which case STOP and re-plan, do not force the index. **(b)** Add `MotifApplicationRepo.current_for_nodes(project_id, node_ids) -> dict[UUID, MotifApplication]` = `DISTINCT ON (outline_node_id) … ORDER BY outline_node_id, created_at DESC` (correct with or without the index) and repoint `ConformanceTraceReader.apps_by_nodes` (**delete it** — a router-private duplicate), `plan.py:1035` (`bound[0]` → `current_for_nodes`), `plan.py:1193` (the dict-collapse → the repo). **(c)** Add `DISTINCT ON (COALESCE(outline_node_id, structure_node_id)) … ORDER BY …, created_at DESC` to `_MOTIF_CHIPS_SQL` (belt-and-braces; changes nothing visible today — see M-BUG-3). **(d)** Keep `by_nodes` for the genuine multi-node read (`arc_apply.py:590`) and **rename it `history_by_nodes`** so the next agent cannot pick the wrong one by autocomplete. **(e)** Scope `set_role_binding`'s UPDATE to the **current** application id (redundant under the index; free, and it makes the intent legible). | repo + DDL + 4 call sites | — | — | — | **S** | **MUST-BUILD** — closes M-BUG-1. ⚠ **Does NOT "fix" M-BUG-2/M-BUG-3 — those are REFUTED (§1.1).** Do not budget regression tests for them. |
| **BE-M2** | 🔴 **`gather_motifs` packer lens (X-7 / spec 21-G1) — THE HARD GATE.** Mirror `gather_arc`: `async def gather_motifs(motif_app_repo, motif_repo, *, project_id, node, chapter_id) -> str`. Resolve **scene binding → else the chapter's → else the arc's** (mirror `gather_arc`'s scene→chapter→arc chain). Render: motif name + kind · the **bound beat** (`annotations.beat_key`) + its `intent` + `tension_target` · the resolved `role_bindings` (role → cast name) · `preconditions` / `effects` · `info_asymmetry` when set. **Sanitize every author string** (`sanitize_lore`, SEC3 — a crafted motif name must not forge a block delimiter). **Best-effort**: any repo failure → `""` (the frame THINS, never fails a pack). Gate exactly like `arc_gated` ([`pack.py:331`](../../../services/composition-service/app/packer/pack.py#L331)); emit as a `<motifs>` block beside `<arc>` ([`pack.py:522`](../../../services/composition-service/app/packer/pack.py#L522)). **Cap it** (≤3 bindings, ≤N chars each) — the arc block rides *outside* `enforce_budget`, so an uncapped motif block is a Context-Budget-Law hole. | `app/packer/lenses.py` + `pack.py` | — | — | — | **M** | **MUST-BUILD — BLOCKS THE WHOLE WAVE** |
| **BE-M3** | Motif-link REST (the graph). **The FE bridge is NOT an option here** — `tools.controller.ts:20-23` states its own contract: *"NOTHING here writes or deletes"*, and `motif_link_create/delete` are writes. REST is the only path. | `GET /v1/composition/motifs/{motif_id}/links` · `POST /v1/composition/motifs/{motif_id}/links` · `DELETE /v1/composition/motif-links/{link_id}` | GET: `?direction=out\|in\|both` · POST: `{to_motif_id, kind: 'composed_of'\|'precedes'\|'variant_of', book_id?}` · DELETE: `?book_id=` | `{links:[{id, from_motif_id, to_motif_id, kind, neighbor:{id, code, name}}]}` · POST → `201 {link}` · DELETE → `204` | **404** uniform `NOT_FOUND` (H13 — no existence oracle for a foreign motif) · **403** insufficient grant on a `book_shared` edge · **409** from the `motif_link_guard` trigger (self-link / cycle / cross-tier) — **relay the trigger's reason, do not flatten it to 500** | **S** | **MUST-BUILD** — thin wrappers over **`MotifRepo.list_links` ([`motif_repo.py:215`](../../../services/composition-service/app/db/repositories/motif_repo.py#L215)) · `.create_link` ([`:275`](../../../services/composition-service/app/db/repositories/motif_repo.py#L275)) · `.delete_link` ([`:320`](../../../services/composition-service/app/db/repositories/motif_repo.py#L320))**. ⚠ There is **no `MotifLinkRepo`** — the links live on `MotifRepo`. Already built + tested; the routes are ~40 lines. |
| **BE-M4** | Motif suggest, REST mirror of `composition_motif_suggest_for_chapter`. Engine exists (`MotifRetriever`, [`deps.py:205`](../../../services/composition-service/app/deps.py#L205)). Reuse the MCP handler's body. | `GET /v1/composition/works/{project_id}/motifs/suggest` | `?chapter_id=&limit=10&detail=summary\|full` | `{candidates:[{motif, score, match_reason:{tension, genre, precondition, semantic}}]}` | 404 uniform · 422 missing `chapter_id` | **S** | **MUST-BUILD** |
| **BE-7c** | 🔴 **Owner-scoped job read — the MINE poll (§1.2's fourth 404).** Specced in [`34`](34_arc_templates_and_deconstruct.md) §5; **BUILT HERE, in 3a**, because this wave ships the first GUI that polls a Work-less job. Also drops `composition_get_mine_job`'s un-knowable `project_id` arg (gate on `created_by`) — landing it here means Wave 4 inherits a working tool instead of breaking this wave's consumer. | `GET /v1/composition/motif-jobs/{job_id}` | path `job_id` | the `generation_job` row (`{status, result, cost, …}`) | **404 uniform H13** when missing **or** not the caller's (`created_by != user` — no existence oracle) | **XS** | **MUST-BUILD (3a)** — ⚠ **Do NOT back-fill a real `project_id`**: a mine is genuinely not Work-bound; the row's scope key is its **owner**. Repoint `motifApi.mineConfirm` off `compositionApi.getJob`. |
| **BE-M5** | ~~Arc suggest, REST mirror of `composition_arc_suggest`~~ | ~~`GET /v1/composition/books/{book_id}/arcs/suggest`~~ | — | — | — | — | 🔴 **DELETED — DUPLICATE. `arc_suggest`'s REST mirror is owned by [`34`](34_arc_templates_and_deconstruct.md) §5 `BE-7b` (`POST /v1/composition/arc-templates/suggest`).** This row was **wrong on the contract**, not merely redundant: `composition_arc_suggest` ([`server.py:2288`](../../../services/composition-service/app/mcp/server.py#L2288)) takes **`project_id`** (→ `_book_or_deny`), **not** a `book_id` path segment, and its default is **`limit=5`**, not 10. **Arc-suggest is Wave 4's; this wave ships the MOTIF suggest only (BE-M4).** The *"Suggest an arc"* button belongs to `arc-inspector` / `arc-templates` (plan 30 G-MOTIF-SUGGEST), i.e. Waves 2/4 — **not to `motif-library`.** |
| **BE-5** | `POST …/scenes/{node_id}/regenerate-to-beat` | — | — | — | — | — | 🔴 **DO NOT BUILD — REFUTED. See §5.1.** |
| — | conformance read (chapter + arc + arc_template_drift) | `GET /works/{pid}/conformance` | — | — | — | — | ✅ **EXISTS** — the FE arg name is wrong (M-BUG-4) |
| — | conformance run, adopt, mine (all Tier-W) | `GET /actions/preview` · `POST /actions/confirm` | — | — | — | — | ✅ **EXISTS** — the generic spine dispatches `composition.conformance_run` / `.motif_adopt` / `.motif_mine` ([`actions.py:75`](../../../services/composition-service/app/routers/actions.py#L75)) |
| — | motif CRUD · catalog · book-shared tier · sync · bind/unbind/role/chain | 10 REST routes | — | — | — | — | ✅ **EXISTS** (`GET /motifs/book/{book_id}` has no FE consumer — 3a wires it) |
| — | gateway | — | — | — | — | — | ✅ **ZERO CHANGES.** `gateway-setup.ts:354` proxies `/v1/composition/*` on a generic `pathFilter` — a new composition route is auto-proxied. |

**Cross-service? NO — and this is a deliberate design choice, not an accident.** Every BE row above is
composition-service-only, and **`api-gateway-bff` is not touched at all**:

- BE-M4/M5 are **REST**, not two names in `FE_BRIDGE_TOOL_ALLOWLIST`. Same cost; avoids the ≥2-service
  live-smoke requirement *and* the 403-fail-closed trap the audit warned about.
- Regenerate re-points at an **existing REST route** (§5.1), not at `composition_generate` through the
  bridge.

**⇒ this wave never edits `tools.controller.ts`.** If a later agent finds themselves adding a tool to
the allowlist for this wave, they have taken a wrong turn — re-read §5.1.

**Fallback if REST is rejected at PLAN:** add `composition_motif_suggest_for_chapter` +
`composition_arc_suggest` to `tools.controller.ts:25` — but then the wave becomes cross-service and
**a live cross-service smoke is mandatory** (VERIFY token `live smoke: …`).

---

## 5 · The two decisions this spec makes

### 5.1 🔴 BE-5 `regenerate-to-beat`: **DO NOT BUILD IT. Re-point at `composition_generate`.**

The audit says: *"Mirror `POST /scenes/{nid}/prose` (`engine.py:1522`)."* **That is wrong.**
`engine.py:1522` is `persist_scene_prose` — a **WS-B3 divergence-promote PERSIST** that writes a
synthetic completed job into a derivative project's store. **It generates nothing.** There is no
per-scene generate route to mirror.

There is, however, a per-scene **generate**, and it has been there all along:
`composition_generate` ([`server.py:1345-1361`](../../../services/composition-service/app/mcp/server.py#L1345))
takes an **XOR target: `outline_node_id` (a SCENE) or `chapter_id`**, is Tier-W (cost-gated through
`/actions/preview` + `/actions/confirm`), and its effect
([`actions.py:388`](../../../services/composition-service/app/routers/actions.py#L388)) runs the full
grounded drafter through `pack()`.

**And once BE-M2 lands, that scene generate IS "regenerate to beat"** — because `pack()` will inject
the scene's bound motif and its target beat into the prompt. The "to-beat" semantics are not a route;
they are the packer lens. Building a bespoke `regenerate-to-beat` route would be a **per-action route
for a Tier-W op** — the exact violation plan 30 §8.1 forbids and the two 404s in §1.2 already
committed.

**And the REST route for it already exists too.**
`POST /v1/composition/works/{project_id}/generate` ([`engine.py:326`](../../../services/composition-service/app/routers/engine.py#L326))
takes `GenerateBody` ([`:91-105`](../../../services/composition-service/app/routers/engine.py#L91)) —
**`outline_node_id: UUID`**, `model_ref`, `model_source`, `operation='draft_scene'`,
`mode='cowrite'|'auto'`. It is **already a scene-targeted generate**, it is the route the Studio's
shipped ComposePanel drives, and it already receives `structures: StructureRepo` (`:334`) — i.e. it is
the production caller that feeds the arc lens, and **the same one `gather_motifs` will ride.**

⇒ **Delete `motifApi.regenerateToBeat` and `useMotifBinding.regenerateScene`.** The Regenerate button
calls `POST /works/{pid}/generate` with `{outline_node_id, model_ref, model_source,
operation:'draft_scene', mode:'auto'}`.

**Consequences, stated plainly:**
- **No new route. No allowlist change. No gateway change. 3c stays composition-only.**
- **Do not invent a second confirmation convention.** Spec 28 **AN-8**: *"a reviewer finding a new
  confirmation convention here has found a defect."* Regenerate is the **same spend, on the same
  route,** as the Studio's existing scene-generate — so it wears **whatever cost UX ComposePanel
  already wears**, reusing that component.
  ⚠ **And what ComposePanel wears is: NOTHING.** *(Verified while reviewing this spec — this was
  OQ-5, now closed.)* `POST /works/{pid}/generate` has **no `/actions` confirm gate, no estimate, no
  spend guardrail** in the route; the confirm-gated path is the **MCP tool's** effect
  (`actions.py:388`), and the **REST twin bypasses it.** So Regenerate ships **ungated**, exactly like
  the Compose button beside it. That is **pre-existing** and it is **not this wave's licence** to bolt
  a bespoke gate onto one button — that would be the AN-8 defect. It is filed as
  **D-COMPOSE-GENERATE-UNGATED** (§11) and belongs to the compose path, where fixing it once fixes
  both. **§8.4 states this plainly; do not let a builder read "cost-gated" into it.**
- It gains the **model picker** it never had (X-1 / `AddModelCta`).

### 5.2 `motif-library` splits from `arc-templates` at 3a

§2.3. The `kind` toggle dies; `ArcTemplateLibraryView` stays in the legacy page until Wave 4 lifts it
into `arc-templates`. **3a must not port it.** A reviewer who finds `ArcTemplateLibraryView` imported
from `MotifLibraryPanel.tsx` has found a defect.

---

## 6 · Registration checklist (GG-8) — exact files, in order, per new panel id

Two new ids: **`motif-library`** · **`quality-conformance`**. Enum **`N_before + 2`** (⚠ *not* a literal — Waves 1+2 land 5 panels first; see the header). Both are openable by a
**bare id** (no `params`) ⇒ both go into the enum. The drawer/modal/section decisions in §3.1/§3.2 are
what make that true.

| # | File | Edit |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/MotifLibraryPanel.tsx` · `QualityConformancePanel.tsx` | The components. Root `data-testid="studio-motif-library-panel"` / `studio-quality-conformance-panel`. `MotifLibraryPanel` **must** wrap its tree in `MotifSimpleModeProvider` (§2.4) and pass `meUserId` from `useAuth()` (§2.4). |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | Two `STUDIO_PANELS` rows. `motif-library` → `category: 'storyBible'` (beside `glossary`, `catalog.ts:128`). `quality-conformance` → `category: 'quality'` (beside `quality-canon`, `catalog.ts:270`). **`category` and `guideBodyKey` are both MANDATORY** (X-2 / X-3 add the assertions). |
| 3 | `frontend/src/features/studio/panels/QualityHubPanel.tsx` | Append `{ panelId: 'quality-conformance', icon: '🧭', titleKey: 'conformanceTitle', descKey: 'conformanceDesc' }` to `CARDS` (`:13-18`). ⚠ **The hub is NOT 4 cards when this wave starts — it is 7.** [`31`](31_quality_completion.md) (Wave 1) already takes `CARDS` 4 → **7** (`quality-canon-rules` ⚖️, `quality-corrections` 📈, `quality-heal` ✨), so this row makes it **7 → 8**. ⚠ **Icon uniqueness across all 8** is the constraint (the icon is the hub's only visual differentiator): **NOT `🎯`** (`quality-critic` owns it, [`:15`](../../../frontend/src/features/studio/panels/QualityHubPanel.tsx#L15)), and **not ⚖️ / 📈 / ✨** (Wave 1 owns those). `🧭` is free. **A DOCK-8 sibling that is not on the hub is unreachable** (`built-mounted-unreachable-duplicated-nav-list`). |
| 4 | `frontend/src/i18n/locales/en/studio.json` | `panels.motif-library.{title,desc,guideBody}` · `panels.quality-conformance.{title,desc,guideBody}` · `quality.conformanceTitle` / `.conformanceDesc`. |
| 5 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | Same keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written. |
| 6 | `services/chat-service/app/services/frontend_tools.py` | **Two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append both ids to the `panel_id` **enum** ([`:400-402`](../../../services/chat-service/app/services/frontend_tools.py#L400)); (b) append a per-panel clause to the tool **description** prose (`:479`-ish) — that gloss is the model's **only** hint the panel exists. |
| 7 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, and **commit the regenerated JSON in the same commit** as steps 2 + 6. |
| 8 | `frontend/src/features/studio/host/studioLinks.ts` | Deep-links: a motif chip → `scene-inspector`; a conformance row → the editor at that scene. Uses the **X-6 `resource_ref`** contract. |
| 9 | **MANDATORY (X-4)** `frontend/src/features/studio/agent/handlers/motifEffects.ts` | New Lane-B file. See §7. |
| 10 | `frontend/src/features/studio/onboarding/tours.ts` | Only if `motif-library` joins the author tour. Needs `tourAnchor` from step 2. Optional. |

**Keeping the two machine guards green** (assert the **three-way equality and the +2 delta** — `py enum == contract enum == openable`, all three moving by exactly 2. **Never a literal**: the count at HEAD is 57, but Waves 1+2 land 5 panels before this wave starts):

```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

Steps 2, 6 and 7 **must land in one commit**, or the contract test reds.

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx`
(all derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## 7 · Agent surface

### 7.1 The MCP tools that drive this domain (all exist; none is new)

`composition_motif_{search, get, book_list, create, patch, archive, bind, unbind, adopt, mine,
link_list, link_create, link_delete, suggest_for_chapter}` · `composition_arc_suggest` ·
`composition_conformance_run` · `composition_get_mine_job` · `composition_generate`.

**No new MCP tool is needed.** This wave is the *human* half of GG-1.

### 7.2 Lane-B effect handlers (X-4) — **MANDATORY**

The Lane-B registry covers **none** of these domains today
(`bookEffects` / `glossaryEffects` / `knowledgeEffects` / `translationEffects` only). Without this
file, **every agent write to a motif leaves every panel in this wave stale.**

`frontend/src/features/studio/agent/handlers/motifEffects.ts`:

| Pattern | Invalidates |
|---|---|
| `/^composition_motif_(create\|patch\|archive\|adopt\|mine)/` | the library key (`useMotifLibrary.ts` — **read its key, don't guess**) · `['composition','motif-candidates']` |
| `/^composition_motif_link_/` | the links key |
| `/^composition_motif_(bind\|unbind)/` | `['composition','motif-bindings', projectId, chapterId]` · `['composition','conformance', projectId, chapterId]` · the plan-hub **overlay** key (the chips are overlay-sourced — `plan-hub/api.ts:61`) |
| `/^composition_conformance_run/` | `['composition','conformance',…]` · `['composition','arc-conformance',…]` · **plus** `useConformanceStatus` — see the trap below |
| `/^composition_generate/` | the prose/draft keys — **already covered** by `bookEffects.ts:60`'s `/^composition_.*(prose\|draft)/`. Do not double-register. |

🔴 **THE TRAP — and the first draft of this spec hand-waved it. `useConformanceStatus` cannot be
reached from a Lane-B handler as the registry stands.**
[`useConformanceStatus`](../../../frontend/src/features/studio/panels/useConformanceStatus.ts#L22) is a
hand-rolled `useState` loader (*"no cache to invalidate"* — its own comment) exposing a **component-scoped
`refresh()`**. A handler registered via `registerEffectHandler` receives only
`EffectContext = { tool, result, bookId, host, queryClient, isChapterDirty?, reloadChapter?, reloadScenes? }`
([`effectRegistry.ts:10-26`](../../../frontend/src/features/studio/agent/effectRegistry.ts#L10)) — **there is
no `refresh()` on it, and `queryClient.invalidateQueries` provably cannot touch a `useState` hook**
(`invalidatequeries-cannot-reach-hand-rolled-state`). *"Call its `refresh()`"* is **not implementable**.
**Pick ONE and build it — this is real work, not a line of glue:**

| Option | Shape | Cost |
|---|---|---|
| **(A) — RECOMMENDED, it mirrors the shipped precedent** | Add `refreshConformance?: () => void` to `EffectContext`, supplied by `useStudioEffectReconciler` from the `useConformanceStatus` instance it owns — **exactly how `reloadChapter` / `reloadScenes` already bridge to hand-rolled Tier-4 state.** | **XS** — 1 field + 1 wire-up. |
| **(B)** | Migrate `useConformanceStatus` to react-query so `invalidateQueries` reaches it. | **S** — but it touches **two shipped panels** (`SceneBrowserPanel:110`, `SceneInspectorPanel:86`) ⇒ re-smoke both. |

**Do not skip this.** Without it, an agent runs a conformance check and the dirty chip on every scene
surface keeps showing the old answer — the exact staleness X-4 exists to kill, shipped in the one panel
this wave is *about*.

⚠ **`useStudioEffectReconciler.ts`'s header comment is Wave-0 X-4's to fix, NOT this wave's — and
"delete it" is wrong.** Only its `authoring_run` clause is stale. Its `composition_generate` clause is
**TRUE** and this spec's own table above **agrees with it** ("already covered by `bookEffects.ts:60`").
Deleting the whole comment deletes a correct fact. **Amend the stale clause; leave the true one.**

### 7.3 INVERSE gap (GG-2) — the agent can do things the human still cannot

**After this wave: none, in the motif domain.** Every one of the 14 motif MCP tools has a human
surface. Recorded so the next audit can confirm it.

**Two remaining asymmetries, deliberately out of scope, tracked:**
- `composition_arc_apply` and `composition_arc_template_drift` are honest-failure **stubs**
  (`_pending_engine`) — the *agent* cannot apply a template the human can. **Wave 4 / BE-8.**
- `composition_motif_mine`'s `promote_target='book_shared'` is reachable by the agent and (until 3a's
  target selector) not by the human. **Closed in 3a.**

---

## 8 · Tenancy · Settings · OCC · Cost gates — explicitly

### 8.1 Tenancy — every row's scope tier

| Table | Tier | Scope key | Who may WRITE |
|---|---|---|---|
| `motif` (System) | **System** | `owner_user_id IS NULL` · `uq_motif_system(code, language)` | **seed/migration only.** A regular user **clones down** (adopt); they never mutate the shared row. This is the `entity_kinds` bug, pre-fixed by the DDL. |
| `motif` (per-user, global) | **Per-user** | `owner_user_id` · `uq_motif_user(owner_user_id, code, language) WHERE book_id IS NULL` | the owner |
| `motif` (per-book private label) | **Per-book** | `(owner_user_id, book_id)` · `uq_motif_user_book(…) WHERE book_id IS NOT NULL AND NOT book_shared` | the owner, EDIT-gated on the book |
| `motif` (per-book **SHARED**) | **Per-book, collaborative** | `book_id` + `book_shared` · `uq_motif_book_shared(book_id, code, language)` | **any EDIT-grantee** (owner = attribution only). `CHECK motif_book_shared_shape` forbids a shared row from ever being `visibility='public'` — the shared axis and the public axis are orthogonal, so a collaborator's motif can never leak into global discovery. |
| `motif_application` | **Per-book** | `book_id NOT NULL` + `project_id` | EDIT on the book. A DB `BEFORE INSERT` trigger (`motif_application_scope_guard`) rejects a cross-project node bind. |
| `motif_link` | inherits its endpoints' tier | — | both endpoints yours, **or** both `book_shared` in a book you EDIT. `motif_link_guard` blocks self-link / cycle / **cross-tier**. |

**The panel must render the tier, and gate on it.** `simpleMode.ts:29` `isReadOnly()` — a System or
another user's public motif is **clone-to-edit only**. The `MotifCard` shows a tier chip
(**glyph + word + hue, never hue alone** — a11y). Edit/Archive are **absent**, not disabled-with-a-tooltip,
on a row the user does not own.

### 8.2 Settings (SET-1..8)

**One setting, already compliant, one trap.** `motif_simple_mode` (`MotifSimpleModeContext`) is a
**per-user** preference: read from `/v1/me/preferences` on mount, write-through on change,
localStorage as a **cache only**. It is server-side, one home, one name. ✅

**The trap (§2.4):** outside its provider `useMotifSimpleMode()` returns a **no-op**. The toggle then
renders and does nothing — a stored-but-unread setting with a button on it. **`MotifLibraryPanel`
must mount `MotifSimpleModeProvider`,** and a test must assert the toggle **changes a rendered label**
(`checklist-is-self-report-enforce-by-tests` — assert the effect, not the call).

**No new toggle, no new env flag.** Nothing in this wave gates user-facing behavior on a global
`*_ENABLED`.

### 8.3 OCC

`motif.version` + `If-Match` on `PATCH /motifs/{id}`. §3.0 states the 412 handling. `motif_application`
has **no version** — and, contrary to its name and its repo's API, **it is not an append-only ledger
either**: every writer replaces the node's row rather than appending (§1.1). It is a **current-binding
table with a ledger-shaped API**, and that mismatch is M-BUG-1. BE-M1 closes it at the DDL (a partial
UNIQUE index) so the four readers stop depending on a convention nothing enforces.

### 8.4 Cost gates

**Three of the four paid actions ride the generic spine. The fourth does not, and pretending
otherwise would be the lie this spec exists to stop.**

| Action | Gate | Path |
|---|---|---|
| Adopt | **quota** (`est_usd = 0`) | `mcpExecute` propose → `GET /actions/preview` → `POST /actions/confirm?token=` |
| Mine | **LLM** | same generic spine → poll `composition_get_mine_job` |
| Conformance-run | **LLM** | same generic spine → poll |
| **Regenerate** | ⚠ **NONE — and that is pre-existing, not this wave's invention** | `POST /works/{pid}/generate` ([`engine.py:326`](../../../services/composition-service/app/routers/engine.py#L326)) — a **direct JWT-authed spend path with no `/actions` confirm gate** (verified: no estimate/preview/guardrail in the route). It is the **same route the shipped ComposePanel already drives**, so Regenerate inherits **exactly** the cost UX ComposePanel wears — no more, no less. |

**Zero bespoke estimate routes.** The two invented routes in §1.2 are deleted, not reimplemented.

⚠ **Do NOT "fix" Regenerate by inventing a confirm gate for it inside this wave.** Spec 28 **AN-8**:
*"a reviewer finding a new confirmation convention here has found a defect."* One button on one panel
must not spend differently from the Compose panel that drives the same route. If the ungated scene-generate
path is judged wrong, it is wrong for **ComposePanel first** — raise it as its own row
(**D-COMPOSE-GENERATE-UNGATED**, below), fix it at the route, and Regenerate inherits the fix for free.
*(The MCP `composition_generate` tool **is** Tier-W cost-gated — `actions.py:388` `_execute_generate` is
its confirm effect. The **REST twin is not.** That asymmetry is the row.)*

---

## 9 · Milestones

### **3a — the library + the graph** (size **L**)

**Gate:** 🔴 **BE-M2 (`gather_motifs`) green with its real-DB effect test, and BE-M1 landed.** Without
BE-M2 this milestone ships a beautiful editor for a field no consumer reads.

Build: BE-M1 · BE-M2 · BE-M3 → `motif-library` panel (split from `ArcTemplateLibraryView`, §2.3) +
the 6 scope tabs (incl. `book_shared`) + the graph section + the mine `promote_target` selector.
GG-8 steps 1,2,4,5,6,7 for `motif-library` + step 9 (motif handlers).

**DoD:** the packer effect test proves a bound motif **changes the prompt** · the panel opens from the
palette · create/patch/archive/adopt/mine/sync all work in a **live browser** · a System motif has no
Edit button · `enum 58 == contract 58 == openable 58`.

### **3b — the binding lens + suggest** (size **M**)

Build: **BE-M4 only** (~~BE-M5~~ — arc-suggest is **Wave 4's**, spec 34 BE-7b; §3.3) → the `Motifs`
section in `scene-inspector` · the PlanDrawer chapter-facet affordance · `NodeBadges`'s motif chip
becomes clickable · **the ONE suggest button this wave owns — *Suggest a motif*** (the *Suggest an arc*
button lands in Wave 4, on `arc-templates`/`arc-inspector`) · the stale-pin Re-pin action · the
`undo_token` unbind (chapter scope **only**).

**No new panel id.** ⚠ Touches `PlanDrawer.tsx` / `NodeBadges.tsx` — **coordinate with the
Book-Package track** (plan 30 §9).

**DoD:** the **invariant test** — a scene re-bound twice holds **exactly one** `motif_application` row,
and `current_for_nodes` returns it (this is the test that would have caught M-BUG-2/3 *if they had been
real*, and it is the one that protects the four readers going forward) · re-role after a re-bind
resolves against the **current** motif · suggest returns ranked rows with `match_reason` ·
unbind-with-undo restores the prior binding, and **no Undo button is offered on a scene node**.

⚠ **Do NOT budget a "M-BUG-2 regression test" or a "M-BUG-3 regression test."** Both are **REFUTED**
(§1.1) — the behavior is already correct and **no test can red on the old code.** A builder who spends
a day failing to make one red has found the refutation the hard way. Read §1.1 first.

### **3c — the conformance trace + the 404 fixes** (size **M**)

Build: `quality-conformance` panel + the QualityHub 5th card · **delete** `conformanceRunEstimate` /
`conformanceRunConfirm` / `regenerateToBeat` / `useMotifBinding.regenerateScene` · **fix M-BUG-4**
(`arc_template_id` → `arc_id` = a `structure_node.id`, on both the GET and the MCP propose; re-point
`ArcConformancePanel` at a structure node) · Regenerate → the **existing**
`POST /works/{pid}/generate {outline_node_id}` (§5.1).

**Zero backend work in 3c.** No new route, no allowlist, no gateway. It is a panel port + a delete +
an arg-name fix. **Composition-service-only ⇒ not cross-service ⇒ no cross-service smoke token needed**
(the live BROWSER smoke in §10.5 is still mandatory).

**DoD:** the 3 live 404s are gone (**a network-tab assertion, not a grep**) · arc-scope conformance
returns a report instead of a 422 · Regenerate re-generates the scene **and the new prose reflects the
bound beat** (the end-to-end proof that BE-M2 is real, and the only thing that proves it) ·
`enum 59 == contract 59 == openable 59`.

---

## 10 · Definition of Done

**Per milestone.** A milestone is not done until every row is true.

1. **The unit suites are green** — `frontend`: the 26 existing motif tests still pass **after the
   split** (§2.3); `composition-service`: `python -m pytest tests -q -n auto --dist loadgroup`.
2. **The packer effect test is green WITH A REAL DB.** `test_pack_motifs_wired.py` (BA12 shape) is
   gated on `TEST_COMPOSITION_DB_URL`, and a skipped test is a **green suite that lies**
   (`env-gated-integration-tests-skip-and-the-green-suite-lies`). **VERIFY must paste the output
   showing it RAN**, not that it was collected. It asserts: change a scene's motif binding ⇒ the
   packed prompt **CHANGES**.
3. **The regression + invariant tests.**
   - **M-BUG-4 (arc conformance answers instead of 422)** — a real regression test that **reds on the
     old code.** This is the only one of the four that does.
   - **The BE-M1 invariant test** — a scene re-bound twice holds **exactly one** `motif_application`
     row; `current_for_nodes` returns it; the partial UNIQUE index **rejects** a hand-crafted second
     row. This does **not** red on the old code (the behavior is already correct) — it **locks in** the
     invariant the four readers silently depend on. Say so in VERIFY; do not dress it up as a bug fix.
   - **The back-fill probe** (BE-M1(a)) — paste the actual output of
     `SELECT outline_node_id, count(*) FROM motif_application WHERE outline_node_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;`
     into VERIFY. **Empty = the invariant holds and §1.1's refutations stand. Non-empty = STOP** —
     M-BUG-2/M-BUG-3 are real after all and this spec is wrong.
   - ⚠ **NO M-BUG-2 test. NO M-BUG-3 test.** Both are REFUTED (§1.1). A test claimed for either is a
     test that cannot red, i.e. a green suite that lies.
4. **The four contract guards are green** (§6), with **all three counts moving by exactly +2 in lockstep** (py enum == contract enum == openable). **Assert the delta and the three-way equality, never a literal** — the baseline depends on how many prior waves have landed.
5. 🔴 **A LIVE BROWSER smoke** (Playwright, the `studio-compose.spec.ts` / `studio-palette.spec.ts`
   pattern), on the **baked** frontend or `vite dev :5199` — **never** assumed from `:5174`
   (`frontend-5174-is-baked-prod-nginx-not-vite`). It must prove, by **effect**:
   - `ui_open_studio_panel {panel_id:"motif-library"}` **mounts a dock tab** — the agent half.
   - A human creates a motif, **binds it to a scene**, opens `quality-conformance`, and the trace
     shows that beat. The dock does **not** unmount at any point (the X-1 / DOCK-7 proof).
   - Drive it with `page.evaluate` + `data-testid` — dockview refs go stale
     (`playwright-live-dockview-automation-recipe`).
   **A green unit suite has repeatedly hidden "the FE could not actually execute it."** This row is
   not skippable; if the stack will not boot, the VERIFY evidence must say
   `live infra unavailable: <reason>` and the milestone does **not** close.
6. **No wave is cross-service** as specced (§4, §5.1) — every service edit is composition-service, and
   `api-gateway-bff` is never touched. If BUILD finds itself editing a second service, **it has
   deviated from this spec** and owes a `live smoke: …` token.
7. **A real LLM smoke** for mine / conformance-run / regenerate, on the test account's **local
   lm_studio** model ($0). `user_default_models` is empty for that account — **pass an explicit
   `model_ref`** (a `user_model_id` UUID).
8. **SESSION_HANDOFF updated** in the same commit as the code.

---

## 11 · Open questions · Deferred · UNVERIFIED

| # | Item | Status |
|---|---|---|
| ~~OQ-1~~ | ~~`composition_generate` in the FE bridge allowlist?~~ **RESOLVED while writing this spec — the answer is NO, and no allowlist change is needed.** `POST /works/{pid}/generate` already takes `outline_node_id`. §5.1. |
| ~~OQ-4~~ | ~~`MotifLinkRepo`'s method names.~~ **RESOLVED — there is no `MotifLinkRepo`.** The links live on `MotifRepo` (`list_links` :215 · `create_link` :275 · `delete_link` :320). BE-M3 updated. |
| **OQ-2** | **The motif graph as a list, not a canvas** (§3.1). Deliberate. If a force-directed view is wanted, it is a Wave-4/5 ask with a real cost. Recorded so it is not "fixed" by accident. |
| ~~OQ-3~~ | ~~`_MOTIF_CHIPS_SQL`'s user-visible symptom.~~ 🚫 **RESOLVED — REFUTED. There is no symptom.** The SQL and the FE are exactly as described (no `DISTINCT ON`; `motifChipsFor` is a bare `.filter`; `MOTIF_CHIP_CAP=2`) — **and it does not matter**, because no `outline_node_id` ever holds a second row (§1.1's invariant: every writer `delete_for_nodes` before insert, or inserts onto scenes created in the same txn). A node re-bound twice renders **one** chip, the current one, **today**. **Do not write the M-BUG-3 regression test — it cannot red.** See §1.1. |
| ~~OQ-5~~ | ~~Is the shipped scene-generate spend-gated at all?~~ **RESOLVED — NO, IT IS NOT.** `POST /works/{pid}/generate` ([`engine.py:326`](../../../services/composition-service/app/routers/engine.py#L326)) has **no `/actions` preview/confirm, no estimate, no spend guardrail**. The cost-gated path is the **MCP tool's** confirm effect (`actions.py:388`); the **REST twin bypasses it entirely.** ⇒ §8.4 rewritten; Regenerate ships **ungated, exactly like ComposePanel**, and the asymmetry is filed below. |
| **D-COMPOSE-GENERATE-UNGATED** *(NEW — raised by this spec's review)* | 🔴 **`POST /works/{pid}/generate` spends LLM tokens with no confirmation gate, while its own MCP twin (`composition_generate`) is Tier-W confirm-gated.** The shipped `ComposePanel` drives the ungated route. This wave's Regenerate button inherits it (§5.1) and **must not fork a private gate** (AN-8). → Deferred (gate #1: **out of scope** — it is a defect of the *compose* path, not the motif cluster; fixing it there fixes both call sites at once). **Do not close this by gating Regenerate alone.** |
| **D-MOTIF-BOOKSHARED-QUOTA** | Adopt into `book_shared` counts against **whose** quota — the adopter's or the book owner's? The confirm effect stamps `owner_user_id` = the adopter (attribution), and the quota check is on the caller. Probably right; **not verified against the ledger.** → Deferred (gate #4: needs the usage-billing owner). |
| **D-MOTIF-GRAPH-CANVAS** | A visual motif graph (composed_of / precedes / variant_of as a DAG). → Deferred (gate #2: a real design + a layout engine). |
| **D-ARC-TEMPLATE-DRIFT-VIEW** | `scope=arc_template_drift` has a route and no surface. → **Wave 4**, with `arc-templates`. Not this wave (§3.4). |
| **Absorbed** | `D-MOTIF-LIBRARY-CRUD-GUI` → 3a · `D-QUALITY-MOTIF-ROLLUP` → 3c. Move both to "Recently cleared" when the milestones land. |

**Sequencing (plan 30 §9):** nobody is in `features/composition/motif/**` — **the cleanest large lane
in the batch.** But 3b touches `PlanDrawer.tsx` / `NodeBadges.tsx` (Book-Package track) and 3a/3c
touch `catalog.ts` + `frontend_tools.py` + `contracts/frontend-tools.contract.json` (every wave
touches these). **Never `git add -A`** — enumerate files, and remember `git commit -- <path>` commits
the **working tree**, not the index.
