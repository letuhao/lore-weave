# Wave 7 — The Issues feed · Jobs · Generation · the find-references lens

> **Type:** FS (backend + frontend; 4 services touched — composition · jobs · chat · translation) · **Size: L**
> (⚖ ADJ re-classified: files ≈ 45, **logic ≈ 11** — the payload widening, the filter relocation, the source/panel
> maps, the 3-part always-mounted refactor, the shared router, the reveal path, the poll-driven paid action, the
> jobs stamp+filter, the discovery scent — **side_effects = 4** (2 new REST routes + an OpenAPI contract + a jobs
> index migration). It was drafted **M**; the adjudication surfaced the real depth. **Write the plan file (this
> one), take no PLAN skip.**)
> **Branch:** `feat/context-budget-law` (shared checkout — see §11 Collisions)
> **Spec:** [`docs/specs/2026-07-01-writing-studio/37_issues_feed.md`](../specs/2026-07-01-writing-studio/37_issues_feed.md)
> **Master plan:** [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) — §0 SEALED PO decisions · §5.2 gap register · §6 BE prereqs · §7 waves · §8.0 panel-id ledger · §8.0b Lane-B handler homes · §8 GG-8 · §9 collisions · §10 REFUTED
> **Draft (the acceptance criterion for the UI):** [`design-drafts/screens/studio/screen-issues-feed.html`](../../design-drafts/screens/studio/screen-issues-feed.html)
> **Closes:** **G-DIAGNOSTICS-ISSUES** (§5.2)
> **Unblocked by:** **PO-1** (§0 of plan 30) — spec 28's AN-12 "no new GUI surface" clause is **AMENDED**, and the amendment is already written into `28_agent_native_studio.md`. Its *architecture* stands: **ZERO new dock panels.**
> **Written for a fresh agent with no memory of the planning conversation.** Everything you need is in this file.
> **🔴 ADJUDICATION FOLDED IN (2026-07-13).** 586 open questions across the spec set were adjudicated
> **against source code**. Wave 7's 61 rulings live in
> [`docs/plans/studio-adjudication/wave-7-decisions.md`](studio-adjudication/wave-7-decisions.md).
> **That file OUTRANKS this one.** This plan was written *before* the rulings were recovered; every place
> the two disagreed has been corrected below and the correction is marked **⚖ ADJ**. When in doubt, open the
> decisions file and read the `*Evidence:*` line — every ruling names the file:line it was settled from.

---

## 0 · The policy this plan is written under (BINDING — quoted from the PO)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** A slice that says "wire the panel" is a FAILURE;
   a slice says WHICH FILE, WHAT CHANGE, WHICH TEST.
2. **`/review-impl` runs at the completion of the wave**, and any bug it finds is fixed before the wave
   closes. It is a literal step in the Definition of Done (§10).
3. **DEFERRAL POLICY — "blocked ≠ stopped".** When the build hits a blocker: write a tracked defer row
   (§12) and **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss, a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing.**
   Everything else — a missing route, an awkward refactor, an ugly seam — is a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates),
   target wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** *"missing infrastructure is NOT blocked — it is unbuilt
   work to implement."* A route that does not exist is a route you **WRITE**.

---

## 1 · What this wave is, in one paragraph

`composition_diagnostics` (`services/composition-service/app/mcp/server.py:3934-4132`) ranks **everything
wrong with a book** across **SIX sources / EIGHT kinds**, error→warn→info, for **$0** and with **zero LLM calls**. It is
**MCP-only**: the only way a human reaches it is to ask a chat agent to call it by name and pay for the
turn. Meanwhile the human surface designed to hold exactly this — the **Issues** tab of
`StudioBottomPanel.tsx` — has been a **stub string since day one** (`bottomStub.issues`: *"Quality issues
appear here once wired."*). This wave wires it, plus its two equally-dark siblings (Jobs, Generation, same
file), plus a **right-click find-references lens** on entity badges. It adds **ZERO new dock panels** and
**ZERO new panel ids**.

**Two hard truths this wave exists around:**

- **The engine is DONE and review-hardened.** `app/services/agent_native.py` (216 lines) composes the
  engines that already own their numbers. It never recomputes. Its `Block.failed()` / `Block.into()` types
  enforce **absent ≠ zero** — a source that could not be read is **OMITTED** from the payload and named in
  `warnings[]`. **Do not rewrite any of it.**
- **The payload is NOT done.** The MCP handler builds `node_ref` for an *agent*, which reads prose. A *GUI*
  has to **navigate** on it, and three fields it needs are dropped on the floor. That is §3 (IF-1/IF-2/IF-3),
  and it is the actual work.

### ⚖ ADJ — **SIX sources · EIGHT kinds.** Not seven. Not five. (`Q-37-SOURCE-COUNT-INCONSISTENT`)

The spec, this plan's first draft, and the FE empty-state copy all said **"7 sources"**. **It is SIX.**
`SEVERITY` (`agent_native.py:60-73`) has **8 keys**; the `composition_diagnostics` fanout has **6
independently-degradable producer blocks** (`server.py:3978 / 4013 / 4033 / 4060 / 4075 / 4106`).
`conformance_dirty`, `conformance_never_run` **and** `index_stale` all fall out of the **one**
`compute_conformance_status` call — they cannot degrade independently, so they are **one source, not three**.

| # | Source id | Producer | Kinds it can emit |
|---|---|---|---|
| 1 | `conformance` | `compute_conformance_status` | `conformance_dirty` · `conformance_never_run` · `index_stale` |
| 2 | `canon_contradiction` | `OutlineRepo.canon_issues` | `canon_contradiction` |
| 3 | `canon_rule` | `OutlineRepo.rule_violations` | `broken_canon_rule` |
| 4 | `thread_debt` | `NarrativeThreadRepo.list_open` | `open_thread_debt` |
| 5 | `prose_deleted` | `compute_prose_deleted` | `prose_deleted_spec_node` |
| 6 | `coverage` | `compute_coverage` | `unplanned_chapter` |

🔴 **NEVER hardcode `6` or `8` in code, copy, or a test.** BE-1a exports `DIAGNOSTIC_SOURCES` (the 6-tuple)
and `KIND_SOURCE` (the 8→6 map); the payload carries `sources` and `degraded_sources`; the FE copy renders
`{{count}} = data.sources.length`. A test asserts `set(KIND_SOURCE) == set(SEVERITY)` and
`set(KIND_SOURCE.values()) == set(DIAGNOSTIC_SOURCES)`, so a 7th source is **unwritable** without updating both.

---

## 2 · Hard gates — what must be true before this wave starts

| Gate | Why | Verify (§3 pre-flight) |
|---|---|---|
| **X-1 (`AddModelCta` DOCK-7 fix)** landed | The Run-conformance button needs a `ModelPicker`, whose empty state renders `AddModelCta`, which **today route-navigates and destroys the user's entire dock layout**. | `grep -n "useOptionalStudioHost" frontend/src/components/shared/AddModelCta.tsx` |
| **The two drift-locks are green** | This wave asserts they are **byte-identical** before and after. | `panelCatalogContract.test.ts` + `test_frontend_tools_contract.py` |
| **Nothing else** | The diagnostics + entity-references engines and the composition gateway proxy are all shipped. `gateway-setup.ts:354` is `pathFilter: (p) => p.startsWith('/v1/composition')`, **no rewrite** ⇒ a new composition route is **auto-proxied**. **Zero gateway work.** | — |

### ⚖ ADJ — **X-1 is a prerequisite to BUILD, not a reason to CUT scope.** (`Q-37-X1-DOCK7-HARD-PREREQ`)

The first draft said *"if X-1 has not landed, ship M1 without the Run button + defer row"*. **That is
overruled.** X-1 is **~15 lines in ONE shared component** and it is **fix-now, not a defer**. If pre-flight
**G5 is EMPTY** (X-1 unlanded), **BUILD IT AS SLICE `W7-S0`** — the exact recipe is in §5. Do **not** ship
the degraded no-Run-button variant, and do **not** write a defer row for it.
*(The defer row `D-W7-RUN-BUTTON-X1` is retired in §12 — it is now slice W7-S0.)*

**What this wave unblocks downstream:** nothing is gated on it. Wave 7 is a leaf in plan 30 §9's
sequencing graph.

### ⚖ ADJ — **M1 → M2 is SEQUENTIAL, not parallel.** (`Q-37-M1-M2-DISJOINT-CLAIM`)

The first draft's *"M1/M2/M3 are independently shippable and touch disjoint files"* is **FALSE**. M2 (the
lens, `W7-S8`) **consumes M1's row→panel router** (`host/issueRouting.ts` — §4.1.1's table *including the
FE-1 inert rule*, which spec 37:385 explicitly requires the lens to honour) **and the same `studio.json`
locale family**. Two surfaces hand-rolling their own routing = the second fork of a table that must have
exactly one home.

**Ship order: `S0 → S1 → S2 → S3 → S3b(contract) → S4 → S5 → S6 → S7 → S8 → S9 → (S10 → S11 → S12) → S12b → S12c → S13`.**
`S8` **dependsOn `S5`** (for the router) as well as `S3`. **Do not parallelize S5 and S8.** M3 (S10-S12)
remains independently deferrable; M1b (`S9`) does not (see the ownership ruling below).

### ⚖ ADJ — **The Book-Package handoff HAS happened. The files are FREE.** (`Q-37-TRACK-OWNERSHIP-HANDOFF`, `Q-37-OQ2-CLOSED-DO-NOT-RELITIGATE`, `Q-37-IF4-INERT-ROW-RULE`)

The first draft gated `W7-S9` (FE-1) and half of `W7-S8` (NodeBadges) on a **coordination handoff with the
Book-Package track**, with defer row `D-W7-FE1-BOOKPKG` as the fallback. **That gate is GONE.** Verified four
ways, not taken from a doc note:

1. Plan 30 §9:716 marks the Book-Package track **"DECLARED COMPLETE 2026-07-12"**, severity 🟡 (*verify-then-go*)
   — **not** the 🔴 in that same table reserved for the one genuinely live collision (Track C's D8).
   **A builder must not read 🟡 as 🔴.**
2. `PlanHubPanel.tsx`, `ChapterBrowserPanel.tsx` and `NodeBadges.tsx` are **CLEAN in the working tree**; their
   last commits (`d662bd97d`, `09f2d29b1`, `58e89720f`) are **merged ancestors of HEAD**. Nobody is mid-edit.
3. The 7 `lane/*` worktrees are **STALE** (0 ahead / ~1860 behind / 0 dirty). They hold nothing.
4. The track's one open "PO-DECIDE (SC11/PH12)" is a **data-derivation policy** question, already resolved
   (`docs/plans/2026-07-12-book-package-RUN-STATE.md:366-386`) — **not an ownership hold**.

**⇒ `W7-S9` and `W7-S8` are UNBLOCKED. Edit `PlanHubPanel.tsx`, `ChapterBrowserPanel.tsx`, `NodeBadges.tsx`
and `PlanDrawer.tsx` directly. No coordination step, no handoff request, no parking.** *This adjudication IS
the handoff record — cite it and proceed.* `D-W7-FE1-BOOKPKG` is retired in §12.

**The one constraint that DOES survive** (unrelated to ownership): this is a **shared multi-agent checkout**.
**NEVER `git add -A`** — enumerate paths; and remember `git commit -- <path>` commits the **WORKING TREE**,
not the index.

---

## 3 · Pre-flight — run these EXACTLY, read the output, then start

```bash
cd d:/Works/source/lore-weave-mvp

# G1 — the diagnostics engine exists and is the one we compose (must be NON-empty)
grep -n "class Diagnostics\|def ranked\|REFERENCE_SOURCES\|^SEVERITY" services/composition-service/app/services/agent_native.py

# G2 — there is NO diagnostics REST route today (must be EMPTY)
grep -rn "diagnostics" services/composition-service/app/routers/

# G3 — the entity-backlinks repo exists (must be NON-empty; 8 sources)
grep -n "def find\|outline_pov\|structure_roster\|narrative_thread" services/composition-service/app/db/repositories/entity_references.py

# G4 — FE-1 is still open: plan-hub / chapter-browser are PARAM-BLIND (must be EMPTY)
grep -rn "focusNodeId\|focusArcId" frontend/src

# G5 — X-1 status. NON-empty ⇒ X-1 landed ⇒ SKIP W7-S0, build W7-S7 directly.
#      EMPTY     ⇒ X-1 open   ⇒ ⚖ ADJ: BUILD W7-S0 (it is ~15 lines). NOT a defer, NOT a scope cut.
grep -n "useOptionalStudioHost\|openPanel" frontend/src/components/shared/AddModelCta.tsx

# G6 — the drift-locks are green BEFORE we touch anything (record the number N_before)
cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts ; cd ..
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py -q ; cd ../..

# G7 — the WAVE-BASE SHA. DoD-5 diffs the contract file against THIS, not against a bare working tree.
#      (A bare `git diff` false-REDs if a concurrent track legitimately lands a panel + regenerates.)
git rev-parse HEAD    # ← record as <wave-base-sha>

# G8 — ⚖ ADJ (Q-37-X10-DO-NOT-TOUCH-STREAM-SERVICE): Track C's "mid-edit" no-go zone is LIFTED.
#      This MUST come back EMPTY. If it does, chat-service is FREE and W7-S12b (X-10) is IN SCOPE.
#      If it is NON-empty, someone is genuinely mid-edit: skip W7-S12b and defer it. Verify, do not assume.
git status --porcelain services/chat-service frontend/src/features/chat

# G9 — ⚖ ADJ (Q-37-TRACK-OWNERSHIP-HANDOFF): the Book-Package files are FREE. Confirm, then EDIT THEM.
#      Expect: EMPTY. The plan-30 §9 "coordinate first" note is 🟡 verify-then-go, NOT 🔴 do-not-touch.
git status --porcelain -- frontend/src/features/studio/panels/ frontend/src/features/plan-hub/

# G10 — the SEED for DoD-7 does not exist and CANNOT be found: 0 canon_rules, 0 scenes, 0 critic rows
#       in the whole dev DB (verified live). Do NOT hunt for a fixture book — W7-S12c SEEDS one in SQL.
docker exec infra-postgres-1 psql -U loreweave -d loreweave_composition -c \
  "SELECT count(*) FILTER (WHERE active AND NOT is_archived) AS rules FROM canon_rule;"
```

---

## 4 · The three payload bugs — read this before writing any code

The audit's estimate ("a mechanical lift of the MCP handler") is **right about the engine and wrong about
the payload.**

### IF-1 🔴 `node_ref.kind:"chapter"` names TWO DIFFERENT ID SPACES

Verified at `server.py`:

| Diagnostic | `node_ref` emitted today | The `id` actually IS |
|---|---|---|
| `unplanned_chapter` (`server.py:4125`) | `{kind:"chapter", id: str(ch["chapter_id"])}` | a **book-service `chapter_id`** |
| `prose_deleted_spec_node` (`server.py:4099`) | `{kind: n["kind"] or "chapter", id: n["id"]}` | a composition **`outline_node.id`** — and a chapter-kind outline node's `kind` column is *literally the string* `"chapter"` |

Two rows, identical shape, **disjoint id spaces**. A frontend that trusts `kind` sends an `outline_node`
UUID where a `chapter_id` belongs → a 404, or worse, a collision. This is the repo's own
`cross-service-normalization-bug-class`, pre-loaded into a payload nobody has consumed yet.

**THE FIX (BE-1a):** `node_ref` gains an explicit **`ref_kind`** naming the **ID SPACE**, from a closed set
of exactly **THREE** members — the three id spaces that exist:

| `ref_kind` | The id is | Emitted by |
|---|---|---|
| `chapter` | a **book-service** `chapter_id` | `unplanned_chapter` |
| `outline_node` | a composition `outline_node.id` (its `kind` column may be `chapter` **or** `scene`) | `canon_contradiction`, `broken_canon_rule`, `prose_deleted_spec_node` |
| `structure_node` | a composition `structure_node.id` (saga/arc) | `conformance_dirty`, `conformance_never_run` |

`kind` stays as the **display** label (`"scene"`, `"chapter"`, `"arc"`). `ref_kind` is the **routing** key.

> ⚠ **`scene` and `canon_rule` are NOT members, and that is deliberate.**
> - **`scene` IS an `outline_node`** — verified: both canon lanes `SELECT n.id AS scene_id … FROM outline_node n`
>   (`outline.py:1214` canon_issues, `outline.py:1338` rule_violations). A set carrying both would name **one
>   id space with two names** — the exact ambiguity IF-1 exists to kill, re-introduced inside its own fix.
> - **No diagnostic emits a `canon_rule` node_ref.** `broken_canon_rule` gains `rule_id` as a **sibling
>   field** (IF-2), not a node_ref. A closed-set member nothing emits is dead enum surface.
>
> **Three id spaces exist. The set has three members. DO NOT re-add the other two.**

### IF-2 🔴 `broken_canon_rule` drops `rule_id` — the deep-link's ONLY key

`OutlineRepo.rule_violations` (`outline.py:1338-1350`) returns `{scene_id, scene_title, chapter_id, job_id,
created_at, rule_id, span, why, rule_text}`. Its own docstring says *"the rule→violation link the Plan Hub's
canon badge needs already exists; it lives here."*

The diagnostics handler (`server.py:4043-4050`) keeps `rule_text` (buried inside a **string title**) and
**throws `rule_id` and `chapter_id` away**.

**Consequence:** the one row whose owning panel is already built and already accepts a focus param
(`quality-canon` takes `focusRuleId` — `useQualityCanon.ts:74,107`) **cannot be deep-linked**, because the
payload no longer carries the key.

### IF-3 🔴 `scene-inspector` selects from the BUS, not from `params`

`useSceneInspector.ts:24` — `const activeSceneId = useStudioBusSelector((s) => s.activeSceneId)`. It ignores
panel params entirely. So `openPanel('scene-inspector', {params:{nodeId}})` opens an inspector showing
**whatever scene was last selected** — a silent wrong-target.

The bus event requires **both** ids (`host/types.ts`: `{type:'scene'; sceneId: string; chapterId: string}`).
`canon_issues` returns `chapter_id` (`outline.py:1214`) — and the diagnostics handler **drops it**, same as
IF-2.

**In this wave we do NOT route to `scene-inspector`** (§6.1 routes canon rows to `quality-canon`, which
takes `focusChapterId`). But `chapter_id` must ride on the payload regardless, because `quality-canon`'s
entity lane keys on it (`useQualityCanon.ts:111`).

---

## 5 · Backend prerequisite slices (these land FIRST — a panel slice may not precede its route slice)

### ── W7-S0 · X-1 — `AddModelCta` stops destroying the dock (⚖ ADJ — was a defer, is now a slice)

**dependsOn:** none. **Kind:** FE. **RUN ONLY IF PRE-FLIGHT G5 IS EMPTY** (X-1 has not landed yet).
If G5 is non-empty, X-1 already shipped in Wave 0 — **skip this slice and go to W7-S1.**

**WHY IT IS A SLICE AND NOT A DEFER** (`Q-37-X1-DOCK7-HARD-PREREQ`): the Run-conformance button (W7-S7)
needs a `ModelPicker`; the picker's empty state renders `AddModelCta` (`ModelPicker.tsx:388`); `AddModelCta`
renders an **unconditional `<Link to={…}>`** (`AddModelCta.tsx:33-68`) which **route-navigates and tears the
whole dock down**. The fix is **~15 lines in ONE shared component** — cheaper than writing and carrying its
defer row. **Fix at the shared component, NEVER at the ~8 call sites.**

**FILES**

| Path | Action |
|---|---|
| `frontend/src/components/shared/AddModelCta.tsx` | **EDIT** |
| `frontend/src/components/shared/__tests__/AddModelCta.test.tsx` | **EDIT** — keep all 3 existing cases (they now assert the OUTSIDE-studio branch), add 2 |

**THE CHANGE**

1. `import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';`
   *(the hook exists — `StudioHostProvider.tsx:143`; 6 call sites already use it, e.g.
   `features/glossary-translate/StepConfig.tsx:44`.)*
2. In `AddModelCta({ returnTo, capability, label, variant, className })` add
   `const studioHost = useOptionalStudioHost();`
3. Hoist the inner markup ONCE:
   `const inner = (<><Plus className={variant === 'link' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />{text}</>)`
   and hoist the two existing className strings into
   `const cls = variant === 'link' ? '<the link classes at :47>' : '<the button classes at :61>'`.
4. Branch **before** the `<Link>`:
   ```tsx
   if (studioHost) {
     return (
       <button type="button" className={cn(cls, className)}
         onClick={() => studioHost.openPanel('settings', { focus: true, params: { tab: 'providers' } })}>
         {inner}
       </button>
     );
   }
   return <Link to={to}>{inner}</Link>;   // ← the EXISTING branch, VERBATIM. The `?return=` round-trip
                                          //    is the correct non-studio behaviour and must be preserved.
   ```
   Seams verified: `StudioHostProvider.tsx:52` (`openPanel(panelId, {focus?, title?, params?, component?})`)
   · `catalog.ts:120` (panel id `settings` is real) · `SettingsPanel.tsx:31` (seeds + follows `params.tab`).
   `returnTo` is **inert inside the studio** (no navigation happens) — **leave the prop alone**, do not delete it.

**TESTS**

| Test name | Asserts |
|---|---|
| *(3 existing)* | unchanged — they now cover the **outside-studio** `<Link>` branch. |
| `test_inside_the_studio_it_does_not_render_a_link` | Render inside a `StudioHostProvider` (or `vi.mock` the module so `useOptionalStudioHost` returns `{openPanel: vi.fn()}`): `screen.queryByRole('link')` is **null**; `getByRole('button')` exists. |
| `test_inside_the_studio_it_opens_settings_on_the_providers_tab` | Click ⇒ `openPanel` called with `('settings', expect.objectContaining({ params: { tab: 'providers' } }))`. 🔴 This is a **DOCK-7 effect** test: assert the dock is **NOT torn down** (no navigation), not merely that a handler fired. |

**DoD evidence:** `cd frontend && npx vitest run src/components/shared/__tests__/AddModelCta.test.tsx` → 5 passed;
`grep -n "useOptionalStudioHost" frontend/src/components/shared/AddModelCta.tsx` → non-empty.

---

### ── W7-S1 · BE-1a — extract `build_diagnostics()` + widen the payload

**dependsOn:** none. **Kind:** BE.

**FILES**

| Path | Action |
|---|---|
| `services/composition-service/app/services/agent_native.py` | **EDIT** — `REF_KINDS` (+ its `__post_init__` guard), `DIAGNOSTIC_SOURCES` / `KIND_SOURCE`, `Diagnostic.{chapter_id,rule_id,panel_id,source}`, `Diagnostics.{has_work,degraded_sources,source_failed}`, `ranked()`'s filter+`computed_at`+`severity_counts`+`matched`, and the new `async def build_diagnostics(...)`. |
| `services/composition-service/app/services/coverage.py` | **EDIT** — `read_spine()` (the ONE spine read; ⚖ ADJ `Q-37-FRESHNESS-PULL-ONLY`). |
| `services/composition-service/app/mcp/server.py` | **EDIT** — `composition_diagnostics` becomes a ~10-line shell; its **description gains the routing sentence** (⚖ ADJ `Q-37-OQ1-AGENT-OPENS-ISSUES`). |
| `services/composition-service/tests/unit/test_agent_native.py` | **EDIT** — new tests **and** the 4 source-text guards get **RE-POINTED** (see 🔴 below). |
| `services/composition-service/tests/unit/test_coverage.py` | **EDIT** — the spine-read-once counter test. |

**THE CHANGE — `agent_native.py`**

1. Add, next to `SEVERITY`:

```python
#: IF-1 — the ID SPACE a node_ref's `id` lives in. THREE members, because three id spaces exist.
#: `kind` is the DISPLAY label ("scene"/"chapter"/"arc"); `ref_kind` is the ROUTING key. A scene IS an
#: outline_node (outline.py:1214 / :1338 both SELECT n.id FROM outline_node) — do NOT add a `scene`
#: member, and do NOT add `canon_rule` (no diagnostic emits one; rule_id is a SIBLING field, IF-2).
RefKind = Literal["chapter", "outline_node", "structure_node"]
REF_KINDS: Final[frozenset[str]] = frozenset({"chapter", "outline_node", "structure_node"})

#: ⚖ ADJ (Q-37-SOURCE-COUNT-INCONSISTENT) — the fanout's SOURCE set: one entry per INDEPENDENTLY-
#: DEGRADABLE producer block. SIX, not seven: compute_conformance_status is ONE call emitting THREE kinds.
DIAGNOSTIC_SOURCES: tuple[str, ...] = (
    "conformance",          # compute_conformance_status → conformance_dirty | _never_run | index_stale
    "canon_contradiction",  # OutlineRepo.canon_issues
    "canon_rule",           # OutlineRepo.rule_violations
    "thread_debt",          # NarrativeThreadRepo.list_open
    "prose_deleted",        # compute_prose_deleted
    "coverage",             # compute_coverage
)
KIND_SOURCE: dict[str, str] = {
    "conformance_dirty": "conformance", "conformance_never_run": "conformance",
    "index_stale": "conformance", "canon_contradiction": "canon_contradiction",
    "broken_canon_rule": "canon_rule", "open_thread_debt": "thread_debt",
    "prose_deleted_spec_node": "prose_deleted", "unplanned_chapter": "coverage",
}

#: ⚖ ADJ (Q-37-OQ1-AGENT-OPENS-ISSUES) — WHICH Studio panel owns each kind. ONE home for this map:
#: the BE row. The FE reads `panel_id` OFF THE ROW; it does NOT keep a second kind→panel table
#: (`css-var-duplicated-across-two-consumers-drifts`). `None` = no panel owns the fix ⇒ the row is INERT
#: on BOTH surfaces (the agent must STATE it, never try to open one). One inert contract, two surfaces.
KIND_PANEL: dict[str, str | None] = {
    "canon_contradiction": "quality-canon", "broken_canon_rule": "quality-canon",
    "open_thread_debt": "quality-promises",
    "prose_deleted_spec_node": "plan-hub",
    "conformance_never_run": "plan-hub", "conformance_dirty": "plan-hub",
    "unplanned_chapter": "chapter-browser",
    "index_stale": None,   # the sweeper heals it — no panel owns the fix. INERT FOREVER (⚖ Q-37-OQ4).
}
```

2. Extend `Diagnostic` (keep every existing field) **and give it a closed-set guard**:

```python
@dataclass
class Diagnostic:
    kind: str
    severity: str
    title: str
    detail: str = ""
    node_ref: dict[str, Any] | None = None   # {kind, id, title, ref_kind}
    at: str | None = None
    chapter_id: str | None = None            # IF-2/IF-3 — quality-canon's entity lane keys on this
    rule_id: str | None = None               # IF-2 — quality-canon's rule lane keys on this

    def __post_init__(self) -> None:
        # ⚖ ADJ (Q-37-IF1-REFKIND-ID-SPACE-COLLISION §1) — a 4th id space must be IMPOSSIBLE to add
        # silently. This guard, not the enum, is what makes the closed set closed.
        if self.node_ref is not None and self.node_ref.get("ref_kind") not in REF_KINDS:
            raise ValueError(f"node_ref.ref_kind must be one of {sorted(REF_KINDS)}")
```

`source` and `panel_id` are **derived, not stored** — `ranked()` emits `KIND_SOURCE[d.kind]` and
`KIND_PANEL[d.kind]`, so no emitter can forget them and no emitter can disagree with the map.

3. `Diagnostics` gains the degrade bookkeeping:

```python
@dataclass
class Diagnostics:
    ...
    has_work: bool = True                                  # ⚖ ADJ Q-37-NO-WORK-SCOPE-STATE
    degraded_sources: list[str] = field(default_factory=list)   # ⚖ ADJ Q-37-SOURCE-COUNT-INCONSISTENT

    def source_failed(self, source: str, warning: str) -> None:
        """A SOURCE could not be read. Appends the warning AND records the source id.

        🔴 The FE must NEVER derive "N sources could not be read" from len(warnings) — `warnings[]` also
        carries NON-failures (the broken-canon-rule cap notice, server.py:4053). Counting them
        over-reports. `degraded_sources` is the only honest count.
        """
        if source not in self.degraded_sources:
            self.degraded_sources.append(source)
        self.warnings.append(warning)
```

4. **`ranked()` — the filter lives HERE, not in the route** (⚖ ADJ `Q-37-D2-SERVER-SIDE-FILTERS`,
   `Q-37-COUNTS-MUST-STAY-UNFILTERED`). New signature and **this exact order — sort → filter → cap**:

```python
def ranked(self, cap: int = _DIAG_CAP, *, severity: str | None = None,
           kind: str | None = None) -> dict[str, Any]:
    ordered = sorted(self.items, key=lambda d: (_RANK[d.severity], _neg_ts(d.at)))     # 1. SORT
    matched = [d for d in ordered                                                       # 2. FILTER
               if (severity is None or d.severity == severity)
               and (kind is None or d.kind == kind)]
    shown = matched[:cap]                                                               # 3. CAP
    return {
        "items": [ … + **({"chapter_id": d.chapter_id} if d.chapter_id else {}),
                       **({"rule_id": d.rule_id} if d.rule_id else {}),
                       "source": KIND_SOURCE[d.kind],
                       "panel_id": KIND_PANEL[d.kind],            # may be None — that IS the inert signal
                   for d in shown],
        "counts": dict(self.counts),          # KIND-keyed. EXACT. NEVER filtered, NEVER capped.
        "severity_counts": {s: sum(1 for d in self.items if d.severity == s)
                            for s in ("error", "warn", "info")},  # ⚖ ADJ — see 🔴 below
        "total": len(self.items),             # EXACT, book-wide. Never narrowed by a filter.
        "matched": len(matched),              # how many the filter selected, BEFORE the cap
        "refs_capped": len(matched) > cap,    # ⚖ ADJ — relative to the FILTERED set, not `ordered`
        "has_work": self.has_work,
        "sources": list(DIAGNOSTIC_SOURCES),
        "computed_at": datetime.now(timezone.utc).isoformat(),    # ⚖ ADJ — see 🔴 below
        **({"warnings": self.warnings} if self.warnings else {}),
        **({"degraded_sources": self.degraded_sources} if self.degraded_sources else {}),
    }
```

> 🔴 **THE `severity_counts` BUG THE SPEC SHIPPED** (⚖ ADJ `Q-37-REFS-CAPPED-FIELD-SHAPE` error 1).
> `counts` is **KIND-keyed** (`self.counts[d.kind]`, `agent_native.py:126`). Spec 37 §4.1 says the toolbar
> renders *"Error 2 · Warn 5 · Info 1 — counts from the exact `counts` map"*. **That is impossible:
> `counts["error"]` is `undefined`.** A builder following it literally renders **"Error 0"** on a book with 2
> canon contradictions — the exact false-clean lie the module exists to prevent. **BE emits
> `severity_counts`; the FE renders it. The FE does NOT re-derive a kind→severity map** (that fork is the
> `css-var-duplicated-across-two-consumers-drifts` class).
>
> 🔴 **`computed_at` DID NOT EXIST** (⚖ ADJ `Q-37-FRESHNESS-PULL-ONLY` §2 / `Q-37-REFS-CAPPED` error 3).
> §4.1.2's *"computed N ago"* footer had **no field to bind to**. Stamp it **in `ranked()`** (not in the
> router) so the MCP tool gets freshness too. The FE footer renders **the SERVER's** `computed_at`, **never**
> React-Query's `dataUpdatedAt` (a client clock is not when the book was checked).
>
> ✅ **Default args keep the sole existing caller (`server.py:4132`) byte-identical.** The payload is a strict
> **superset** of today's; no MCP consumer breaks. (`composition_diagnostics` declares `-> dict` and FastMCP
> advertises **`outputSchema: null`** — verified — so there is **no output schema, no contract regen, no
> `WRITE_MCP_SHAPES=1`**. The "MCP back-port" is **zero schema work**: `Q-37-BE1A-MCP-BACKPORT`.)

5. **`limit` is CLAMPED IN EXACTLY ONE FUNCTION** (⚖ ADJ `Q-37-LIMIT-CLAMP-ONCE`).
   The clamp **moves out of `server.py:3966` and into `build_diagnostics`**:

```python
async def build_diagnostics(
    *, pool: Any, book_client: Any, book_id: UUID, bearer: str,
    project_id: UUID | None, limit: int | None = None,
) -> Diagnostics:
    cap = max(1, min(int(limit or _DIAG_CAP), 100))   # ← THE ONLY clamp arithmetic in the codebase.
    # After this line the RAW `limit` is NEVER referenced again. `cap` feeds every slice:
    # pd.nodes[:cap], cov.unplanned[:cap], and the caller's Diagnostics.ranked(cap=...).
```
   - **MCP tool:** **DELETE** its local `cap = max(1, min(...))` and pass the **raw** `limit` through. An LLM
     sending `limit=0`/`-5`/`500` must be **coerced, never errored** — that is why the clamp is the shared
     function's job.
   - **REST route:** `Query(25, ge=1, le=100)` **VALIDATES** — FastAPI **422s** out-of-range, it does **not**
     clamp, and **that is correct and intentional** (an HTTP client that sends `limit=500` gets *told*).
     The route must **NOT** re-implement the clamp; `build_diagnostics`'s clamp is a proven no-op for
     anything FastAPI let through. **Do not hand-roll a `parse_limit()` helper** — that is the
     `chapter-list-limit100-fallback-20-bug` (a helper silently substituting a different default).

6. **Move the fanout.** Copy `server.py:3950-4132` into `build_diagnostics` **VERBATIM**, changing ONLY the
   five things below. **Do not "improve" it while moving it** — it is review-hardened and **every per-source
   `try/except Exception → warnings.append(...)` IS the "never 500 on a degraded source" contract. Deleting
   one to "clean up" is the bug.** Keep the imports **function-local** (as `server.py` does) — hoisting them
   to module scope is an import-cycle risk for a cosmetic gain.

**The five changes while moving:**

| # | Was (in `server.py`) | Becomes (in `build_diagnostics`) |
|---|---|---|
| 1 | `_work, pid = await resolve_scope(WorksRepo(pool), bid)` | **removed** — `project_id` is a parameter. Callers resolve. |
| 2 | `mint_service_bearer(tc.user_id, settings.jwt_secret)` (×2 — `compute_prose_deleted`, `compute_coverage`) | `bearer` (the parameter) |
| 3 | `get_book_client()` (×3) | `book_client` (the parameter) |
| 4 | `return {"book_id": str(bid), **diag.ranked(cap=cap)}` | `return diag` (the object; callers call `.ranked()`) |
| 5 | The `node_ref` dicts + `Diagnostic(...)` constructions | **the payload widening below** |

7. 🔴 **FIX THE DEGRADE — DO NOT COPY IT VERBATIM** (⚖ ADJ `Q-37-NO-WORK-SCOPE-STATE`,
   `Q-37-WARNINGS-STRIP-MANDATORY` C). Today the three **project-keyed** sources are skipped with
   `if pid is None: raise LookupError("no project")` **inside their `try`** (`server.py:4015-16 / 4038-39 /
   4062-63`) — so `except Exception` appends **three MISLEADING** *"could not be read"* warnings,
   indistinguishable from a real DB failure, **on top of** the no-Work umbrella warning at `:3973`.
   **⇒ 4 warnings for 3 unread sources on the most common degraded book.** In `build_diagnostics`:
   - **DELETE** the umbrella append (`:3973-3976`) **and** the three `raise LookupError("no project")` lines.
   - Guard sources (2)/(2b)/(3) with a **plain `if project_id is not None:`** wrapping the block, **outside**
     the try. On `project_id is None`, call
     `diag.source_failed("<source>", "<source> could not be read — this book has no composition work (absent, not zero)")`
     once per source, and set `diag.has_work = False`.
   - **Result on a no-Work book: exactly 3 warnings, `degraded_sources == ["canon_contradiction",
     "canon_rule", "thread_debt"]`, `has_work: false`, 200 OK — and the BOOK-keyed sources (conformance,
     prose_deleted, coverage) STILL RUN** (they take `book_id`, not `project_id` — do **not** gate them on
     the Work row).
   - Every other `except` block **and** the two explicit degrade branches (`pd.degraded` :4089,
     `cov.degraded` :4117) call `diag.source_failed(<source id>, <its existing warning string>)`.
     ⚠ The **cap notice** at `:4053` (*"showing X of Y broken canon rules"*) keeps a plain
     `warnings.append` — **it is a truncation, not a failure**, and counting it as one is the dishonesty
     the strip exists to kill.

8. **READ THE SPINE ONCE** (⚖ ADJ `Q-37-FRESHNESS-PULL-ONLY` §1). `compute_coverage` (`coverage.py:135`) and
   `compute_prose_deleted` (`coverage.py:188`) **each** issue their own exhaustive
   `book.list_chapters(..., raise_on_404=True)`, and `book_client.py:328-340` paginates at **100 rows/page** —
   so a 400-chapter book costs **8 book-service round-trips per diagnostics call**. In `coverage.py` add:

```python
@dataclass(frozen=True)
class Spine:
    chapters: list[dict[str, Any]] = field(default_factory=list)
    unreadable: bool = False     # BookClientError / 404 — today's `degraded` cause
    truncated: bool = False      # len(chapters) >= _SPINE_LIMIT

async def read_spine(book_id: UUID, bearer: str, *, book: BookClient) -> Spine: ...
```
   Give **both** compute fns an optional `spine: Spine | None = None`: when `None` they call `read_spine`
   themselves (so `plan_overlay.py:255` and `mcp/server.py:3811` keep working **byte-identically** — zero
   behaviour change); when passed, they use it. `build_diagnostics` calls `read_spine` **ONCE** and hands the
   same `Spine` to sources (4) and (5).
   ⚠ **Their DIVERGENT degradation semantics stay exactly as written — do NOT unify them:** coverage treats
   `truncated` as `spine_truncated` (**a floor — it still renders**, `:149-153`) while prose_deleted treats it
   as `degraded=True` with its own warning (`:200-208`).

**The payload widening — the exact per-source table.** Copy this EXACTLY:

| Source (line in `server.py`) | `node_ref` becomes | Sibling fields |
|---|---|---|
| conformance (`:3997`) | `{"kind": "arc", "id": str(arc["structure_node_id"]), "title": arc.get("title"), "ref_kind": "structure_node"}` | — |
| canon_contradiction (`:4033`) | `{"kind": "scene", "id": str(issue["scene_id"]), "title": issue.get("scene_title"), "ref_kind": "outline_node"}` | `chapter_id=str(issue["chapter_id"]) if issue.get("chapter_id") else None` |
| broken_canon_rule (`:4049`) | `{"kind": "scene", "id": str(item["scene_id"]), "title": item.get("scene_title"), "ref_kind": "outline_node"}` | `chapter_id=…str-coerced…`, **`rule_id=item.get("rule_id")`** |
| prose_deleted_spec_node (`:4099`) | `{"kind": n.get("kind") or "chapter", "id": str(n["id"]), "title": n.get("title"), "ref_kind": "outline_node"}` | 🔴 **NO `chapter_id` — see below** |
| unplanned_chapter (`:4125`) | `{"kind": "chapter", "id": str(ch["chapter_id"]), "title": ch.get("title"), "ref_kind": "chapter"}` | `chapter_id=str(ch["chapter_id"])` — the SAME id, ALSO as a sibling, so **every routable row exposes `chapter_id` uniformly** and the FE reads ONE field, not a per-kind special case |
| index_stale (`:4013`) | **no node_ref** (unchanged) | — |
| open_thread_debt (`:4066`) | **no node_ref** (unchanged) | — |

> 🔴 **`prose_deleted_spec_node` MUST NOT emit `chapter_id`, even though the source row carries one**
> (⚖ ADJ `Q-37-IF1-REFKIND-ID-SPACE-COLLISION` refinement A + `Q-37-BE1A-PAYLOAD-WIDENING` step 4).
> **By construction that chapter is GONE:** `compute_prose_deleted` selects *exactly* the nodes whose chapter
> is not active (`coverage.py:210-213`: `dangling = [n for n in linked if str(n["chapter_id"]) not in active]`).
> Emitting it hands the FE a **guaranteed-404 deep-link target** under the same field name every other row uses
> to mean *"a live chapter to focus"* — i.e. it re-creates IF-1's exact failure **through the sibling field**.
> **Put that sentence in the code as a comment.** If a future consumer genuinely needs it, name it
> `deleted_chapter_id` — **never** `chapter_id`. A test locks this (`test_prose_deleted_never_emits_chapter_id`).
>
> ⚠ **`kind` STAYS. It is the DISPLAY label; `ref_kind` is the ROUTING key. Both ride.** Two decision entries
> (`Q-37-IF3` (B) and `Q-37-BE1A-MCP-BACKPORT` step 2) proposed *replacing* `kind` with `ref_kind`. **They lose
> to the dominant, thrice-stated IF-1 ruling** (spec 37 §3, `Q-37-IF1-ENUM-MUST-STAY-3`,
> `Q-37-BE1A-PAYLOAD-WIDENING` step 3): *"`kind` REMAINS the DISPLAY label ('arc'/'scene'/'chapter');
> `ref_kind` is the ROUTING key."* **The FE routes on `ref_kind` ONLY — an FE that switches on `kind` is a
> review finding.** Recorded here so it is not re-litigated in either direction.
>
> ⚠ `rule_violations` returns `chapter_id` as a **str-or-None** (`outline.py:1361`); `canon_issues` returns it
> as a **UUID** off asyncpg. **`str()`-coerce both** — a UUID object is not JSON-serializable and a mixed-type
> field is the `cross-service-normalization-bug-class` again. **Omit the key when NULL — never emit `null`**
> (absence is the routing signal; a `chapter_id: null` reads as *routable* and produces the silent-wrong-target
> this spec exists to kill).
>
> ⚠ **DO NOT touch `entity_references.py:138-222`.** It builds a **different** `node_ref` (kinds
> `motif_application` / `canon_rule` / `narrative_thread`) for BE-1d — a different id-space set. The 3-member
> closed set is the **DIAGNOSTICS** contract only. Unifying them drags `canon_rule` back into the set IF-1
> deliberately excludes.

**THE CHANGE — `server.py`**

`composition_diagnostics` keeps its `@mcp_server.tool(...)` decorator and `meta` **verbatim**. Its **description
gains ONE routing sentence** (⚖ ADJ `Q-37-OQ1-AGENT-OPENS-ISSUES` EDIT A — this is a *composition-service*
MCP description; it does **NOT** touch `contracts/frontend-tools.contract.json`, so DoD-5 stays green). Append,
verbatim:

> *"Each row carries `panel_id` — the Studio panel that owns that finding. To SHOW the user a finding, call
> `ui_open_studio_panel` with that `panel_id`. A row with `panel_id: null` has no owning panel — state it, do
> NOT try to open one. The same ranked list is in the Studio bottom panel → Issues tab."*

⚠ While you are in the description: it currently names only **5 of the 8 kinds** — it omits `broken_canon_rule`
and `prose_deleted_spec_node`, **the two ERROR classes**. Fix that too (`Q-37-SOURCE-COUNT-INCONSISTENT` §6).

The body becomes:

```python
async def composition_diagnostics(ctx: MCPContext, book_id: str, limit: int = 25) -> dict:
    from app.clients.book_client import get_book_client
    from app.services.agent_native import build_diagnostics

    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)

    pool = get_pool()
    _work, pid = await resolve_scope(WorksRepo(pool), bid)

    diag = await build_diagnostics(
        pool=pool, book_client=get_book_client(), book_id=bid,
        bearer=mint_service_bearer(tc.user_id, settings.jwt_secret),
        project_id=pid, limit=limit,      # ← RAW. build_diagnostics clamps. No second clamp here.
    )
    return {"book_id": str(bid), **diag.ranked(cap=max(1, min(int(limit or 25), 100)))}
```

> ⚠ The `ranked(cap=…)` above re-applies the same idempotent clamp expression **because `ranked` takes a cap,
> not a limit**. If you prefer, have `build_diagnostics` expose its computed `cap` (e.g. `diag.cap`) and pass
> **that** — either way, **the arithmetic `max(1, min(int(x or 25), 100))` must appear in exactly ONE place.**
> Two clamp sites that drift is the exact bug `server.py:3966`'s comment was written about.
>
> **Keep `mint_service_bearer` on the MCP path — it is CORRECT there** (the MCP envelope carries no JWT;
> `service_bearer.py:1-30` documents exactly this) **and WRONG in the route.** Do not "clean it up".

**TESTS** — `services/composition-service/tests/unit/test_agent_native.py` (no DB; pure + fakes).
TDD order: write these RED first.

> 🔴 **FOUR EXISTING TESTS WILL GO RED — RE-POINT THEM, DO NOT LOOSEN THEM** (⚖ ADJ `Q-37-BE1A-MCP-BACKPORT`
> step 4). `test_agent_native.py` guards the diagnostics logic **by SOURCE TEXT** via
> `inspect.getsource(server.composition_diagnostics)`: lines **171-175** (`compute_conformance_status(`,
> `canon_issues(`, `list_open(`, `compute_coverage(`), **253-260** (every `SEVERITY` key appears in the
> source), **272-275** (the `# (1)`…`# (5)` markers + `rule_violations(`), **349-351** (the clamp expression,
> and no `[:limit]`). Moving the fanout takes that text **out of the tool fn** ⇒ all four break.
> **Re-point them at `inspect.getsource(agent_native.build_diagnostics)` with EVERY assertion intact** — they
> encode the silent-hole bug a previous `/review-impl` found. **Keep `test_diagnostics_NEVER_SPENDS`
> (`:178-190`) pointed at `server.composition_diagnostics`** (its `require_meta("R","book")` block still lives
> there) **and add the same `"conformance_run(" not in src` assertion to the extracted fn.**

| Test name | Asserts |
|---|---|
| `test_ref_kinds_is_exactly_three_members` | `REF_KINDS == frozenset({"chapter","outline_node","structure_node"})`; `"scene" not in REF_KINDS`; `"canon_rule" not in REF_KINDS`. *(The guard against re-adding the two dead members.)* |
| `test_a_fourth_ref_kind_raises` | `Diagnostic(node_ref={"ref_kind": "scene", …})` **raises `ValueError`**. *(The `__post_init__` guard — the enum is enforced by construction, not by convention.)* |
| `test_every_emitted_node_ref_carries_a_ref_kind_from_the_closed_set` | Drive `build_diagnostics` with fakes firing **all five** node_ref-bearing sources; assert `{i["node_ref"]["ref_kind"] for i in items} <= REF_KINDS` **and** that every item carrying a node_ref **HAS** a `ref_kind` (a missing key must **red**, not pass). |
| `test_unplanned_chapter_ref_kind_is_chapter_and_prose_deleted_is_outline_node` | The IF-1 bug, asserted directly — **both rows in ONE payload**: they both say `kind == "chapter"` yet carry **different** `ref_kind`s, and `unplanned_chapter.node_ref.id` is the **book-service** chapter id while `prose_deleted.node_ref.id` is the **outline_node** id (NOT its chapter_id). |
| `test_prose_deleted_never_emits_chapter_id` | 🔴 `"chapter_id" not in item` for that kind. *(Locks the tombstone decision so a later agent cannot "fix" it back.)* |
| `test_broken_canon_rule_carries_rule_id_and_chapter_id` | IF-2. Both non-empty. |
| `test_a_violation_with_no_rule_id_OMITS_the_key` | 🔴 `"rule_id" not in item` — **not `None`**. A `focusRuleId: null` on the FE would match `r.rule_id === focusRuleId` against **other unattributed rows** and hoist the wrong ones. |
| `test_canon_contradiction_carries_chapter_id` | IF-3's half. |
| `test_ranked_filters_AFTER_the_sort_and_BEFORE_the_cap` | 🔴 **THE D-2 REGRESSION.** Seed **30 `canon_contradiction` (error) + 12 `open_thread_debt` (info)**. `ranked(cap=25, severity="info")` ⇒ **12 rows, NOT 0**; `counts["canon_contradiction"] == 30` (the error kind **still present and non-zero**); `severity_counts == {"error":30,"warn":0,"info":12}`; `total == 42`; `matched == 12`; `refs_capped is False`. Then `ranked(cap=25)` unfiltered ⇒ 25 rows + `refs_capped True`. *(Filter-then-cap. A cap-then-filter impl returns 0 info rows while `counts` says 12 — that is the shipped bug.)* |
| `test_counts_are_never_filtered` | `?severity=info` ⇒ `counts` **still carries the error kinds at their true values**. *(Makes "Error 2 → Error 0" impossible.)* |
| `test_the_source_and_kind_maps_cannot_drift` | `set(KIND_SOURCE) == set(SEVERITY)`; `set(KIND_SOURCE.values()) == set(DIAGNOSTIC_SOURCES)`; `set(KIND_PANEL) == set(SEVERITY)`. *(A 7th source / a 9th kind becomes unwritable without updating both.)* |
| `test_every_panel_id_is_openable_or_explicitly_null` | 🔴 For every kind: `KIND_PANEL[kind]` is **either** a member of the `panel_id` enum loaded from `contracts/frontend-tools.contract.json` **or** exactly `None` **and** in the declared inert set. *(A `panel_id` the agent cannot open is `silent-success-is-a-bug` shipped again. ⚖ ADJ `Q-37-OQ1`.)* |
| `test_degraded_coverage_source_omits_the_key_and_warns` | Fake `list_chapters` **raises** ⇒ **no `unplanned_chapter` item**, **`"unplanned_chapter" not in counts`** (NOT `== 0`), `warnings` non-empty, `degraded_sources` non-empty. **DoD-2 — absent ≠ zero.** 🔴 **AND `"prose_deleted_spec_node" not in counts` too** — `list_chapters` feeds **TWO** sources (`compute_prose_deleted` **and** `compute_coverage`); one raising fake degrades **both**, so `len(warnings) == 2`. **A test asserting ONE warning will red — by design.** |
| `test_a_raw_transport_error_does_not_500` | Same, but the fake raises a **bare `RuntimeError("connect timeout")`** (not a `BookClientError`). `compute_coverage`/`compute_prose_deleted` catch **only** `BookClientError` (`coverage.py:138,190`) — the **only** thing between an unwrapped transport error and a 500 is the fanout's outer `except Exception`. **This test is what proves the try/except survived the lift.** |
| `test_a_book_with_NO_composition_work_DEGRADES_not_RAISES` | Stub `works.resolve_by_book → []`. `build_diagnostics` **RETURNS** (no exception); `has_work is False`; **`len(warnings) == 3`** (🔴 the anti-double-count guard — today's code produces **4** warnings for 3 unread sources); `"canon_contradiction" not in counts and "open_thread_debt" not in counts`; **a seeded unplanned chapter STILL appears** (proving the book-keyed sources ran). |
| `test_build_diagnostics_clamps_once` | `limit=-5` ⇒ **1** item and it is the **HIGHEST-severity** row (proves the negative sliced from the **FRONT** via `cap>=1`, not from the end via a raw `[:-5]` — the exact bug `server.py:3966`'s comment records). `limit=0` ⇒ **1** item (not `[]`). `limit=1000` ⇒ ≤100. `limit=None` ⇒ 25. |
| `test_ranked_counts_are_exact_when_rows_are_capped` | `cap=2` over 5 items ⇒ `len(items) == 2`, `total == 5`, `refs_capped is True`, `counts` sums to 5. *(Guards OUT-5.)* |

**`tests/unit/test_coverage.py`** — `test_the_spine_is_read_exactly_once_per_diagnostics_run`: a spy
`BookClient` whose `list_chapters` increments a counter ⇒ assert it is **exactly 1** across a full
`build_diagnostics` run (**today it would be 2** — this is the regression guard). Plus: an **unreadable**
`Spine` ⇒ coverage omits its key + warns **AND** prose_deleted omits + warns; a **truncated** `Spine` ⇒
coverage still renders with `spine_truncated=True` **while** prose_deleted goes `degraded=True`.

**DoD evidence:** `cd services/composition-service && python -m pytest tests/unit/test_agent_native.py tests/unit/test_coverage.py -q` → all pass;
**and** `grep -c "compute_coverage" services/composition-service/app/mcp/server.py` → **0**;
**and** the DoD-1 grep (⚖ ADJ `Q-37-BE1-EXTRACT-NOT-FORK`):
`grep -rn "SEVERITY\[" services/composition-service/app/ --include=*.py` returns hits **ONLY** in
`services/agent_native.py` — **zero** in `mcp/server.py`, **zero** in `routers/`. *(That is what proves the
fanout has exactly one home.)*

---

### ── W7-S2 · BE-1 — `GET /v1/composition/books/{book_id}/diagnostics`

**dependsOn:** `W7-S1`. **Kind:** BE / CONTRACT.

**FILES**

| Path | Action |
|---|---|
| `services/composition-service/app/routers/diagnostics.py` | **CREATE** |
| `services/composition-service/app/main.py` | **EDIT** — one `app.include_router(diagnostics.router)` line + the import |
| `services/composition-service/tests/unit/test_diagnostics_router.py` | **CREATE** |

**ROUTE CONTRACT**

```
GET /v1/composition/books/{book_id}/diagnostics
  query:
    limit     int   1..100, default 25   (Query(ge=1,le=100) VALIDATES → 422. It does NOT clamp.)
    severity  enum  error|warn|info      optional
    kind      enum  the 8 SEVERITY keys  optional   (a Literal — NEVER a free str)
    ⚠ NO `chapter_id` PARAM. The feed is BOOK-WIDE. (⚖ ADJ Q-37-OQ3 — see below.)
  200 → {
    book_id: str,
    items: [{
      kind, severity, title,
      detail?, at?,
      node_ref?: { kind, id, title, ref_kind },   // ref_kind ∈ chapter|outline_node|structure_node
      chapter_id?, rule_id?,                      // OMITTED when absent — never null
      source,                                     // ⚖ ADJ — one of the 6 DIAGNOSTIC_SOURCES
      panel_id                                    // ⚖ ADJ — the owning panel, or null ⇒ INERT
    }],
    counts: { <kind>: int },          // KIND-keyed. EXACT. NEVER filtered. NEVER capped. SPARSE.
    severity_counts: { error, warn, info },  // ⚖ ADJ — what the toolbar chips render. counts is
                                             //   KIND-keyed, so counts["error"] is undefined.
    total: int,                       // EXACT, book-wide. Never narrowed by a filter.
    matched: int,                     // ⚖ ADJ — rows the filter selected, BEFORE the cap
    refs_capped: bool,                // matched > cap  (relative to the FILTERED set)
    has_work: bool,                   // ⚖ ADJ — false ⇒ render the No-Work BANNER (not an empty state)
    sources: [str],                   // ⚖ ADJ — the 6. The FE's copy renders {{count}} from THIS.
    computed_at: str,                 // ⚖ ADJ — SERVER stamp. The footer binds to this, not to
                                      //   React-Query's dataUpdatedAt.
    warnings?: [str],                 // OMITTED when clean — NOT []. `res.warnings.length` CRASHES.
    degraded_sources?: [str]          // OMITTED when clean. 🔴 The ONLY honest "N sources failed" count —
                                      //   warnings[] also carries NON-failures (the cap notice).
  }
  403 → insufficient access        (InsufficientGrant)
  404 → NOT_ACCESSIBLE_MESSAGE     (OwnershipError — H13 uniform, no enumeration oracle)
  422 → unknown `severity` / `kind`, or limit out of 1..100 (FastAPI Literal / ge-le validation)
  NEVER 500 on a degraded source — that is a `warnings[]` + `degraded_sources[]` entry.
```

> ### ⚖ ADJ — **BOOK-WIDE ONLY. There is no `chapter_id` param, and there never will be.** (`Q-37-OQ3-BOOK-WIDE-VS-CHAPTER`)
> **The code forbids the alternative:** only **3 of the 8 kinds** carry a live chapter. `index_stale` and
> `open_thread_debt` are **book-level rollups** (`server.py:4002-08`, `:4064-70` — no `node_ref` at all); the
> conformance pair is **arc**-scoped; and `prose_deleted_spec_node`'s chapter is **DELETED by construction**
> (`coverage.py:175-178`) so it **can never match the open chapter**. Therefore:
> 1. **No `chapter_id` query param.** Do not add one.
> 2. `useDiagnostics`'s query key is `['composition','diagnostics',bookId,severity,kind]` — it **must not**
>    read `activeChapterId` from the studio bus.
> 3. **No "This chapter" toggle** in the toolbar.
> 4. **No chapter-proximity sort or boost.** `ranked` is severity→recency and `SEVERITY` is *fixed, not
>    computed, by design* (`agent_native.py:58-73`). If a "your open chapter" affordance is ever wanted it is
>    a **non-filtering visual marker only** (a dot when `row.chapter_id === activeChapterId`) that changes
>    **neither ordering nor counts**.
> 5. **BE-1a still lands in full** — `ref_kind` + `chapter_id` + `rule_id` are for the **DEEP-LINK**, not for
>    filtering. Do not skip them on the strength of this decision.
> 6. **REGRESSION GUARD (an M1 DoD test, literal):** a vitest asserting the diagnostics query key **contains
>    no chapter id** AND that **switching the editor's open chapter changes neither the row set nor the chip
>    counts**. *(This is the guard against a later agent "helpfully" adding the filter back.)*

**THE CHANGE — `routers/diagnostics.py`**

Mirror `routers/plan_overlay.py` exactly (same class of route: book-scoped, VIEW-gated, cheap, composes an
engine). Copy its `_gate_book` helper verbatim.

```python
"""28 AN-4 / 37 BE-1 — the REST mirror of `composition_diagnostics`.

The problems panel, for a HUMAN: everything wrong with this book, ranked error → warn → info, for $0
and with zero LLM calls. The MCP tool and this route call ONE `build_diagnostics()` — a second fanout
would be two truths for "what is wrong with this book" (the css-var-duplication class).

TENANCY (BPS-8 / H13): E0 VIEW grant on the path `book_id`, resolved BEFORE any repo call.
OwnershipError → 404 (the uniform not-accessible message — no existence oracle); InsufficientGrant → 403.

THE BEARER: this route passes the USER'S OWN JWT to the two cross-service reads (compute_coverage,
compute_prose_deleted), exactly as plan_overlay.py:255 does. It does NOT mint a service bearer — the MCP
tool does that because it has no user request to ride; a user-facing route that minted one would re-open
the `internal-route-driven-by-a-session-must-grant-check` hole. The E0 gate runs FIRST, so the user's own
token is both sufficient and correct.

FILTERS (D-2 — DECIDED, do not "simplify" this): `severity`/`kind` filter SERVER-side, INSIDE
`Diagnostics.ranked()`, in the order SORT → FILTER → CAP. `counts`/`total` stay UNFILTERED. A filtered
counts map turns "Error 2" into "Error 0" the moment the user clicks the Info chip — and the author reads
that as "my errors went away".

⚖ ADJ (Q-37-D2-SERVER-SIDE-FILTERS): the FILTER DOES NOT LIVE IN THIS FILE. A route-side
`[i for i in payload["items"] if …]` runs AFTER the cap — and `ranked` sorts error→warn→info THEN caps, so
on a book with 30 errors and cap=25 EVERY info row is already off the array. `?severity=info` would render
ZERO rows while `counts` says 12. It would also re-derive severity from the item rows and fork the SEVERITY
map. The route VALIDATES and DELEGATES. Nothing else.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.book_client import BookClient
from app.db.repositories.works import WorksRepo
from app.deps import get_book_client_dep, get_grant_client_dep, get_pool
from app.grant_client import GrantClient, GrantLevel, InsufficientGrant, OwnershipError
from app.grant_deps import authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.services.agent_native import build_diagnostics, resolve_scope

router = APIRouter(prefix="/v1/composition")

NOT_ACCESSIBLE_MESSAGE = "book not found"   # reuse the module-level constant plan_overlay.py imports

#: The 8 SEVERITY keys, as a Literal. A free `str` here is the closed-set-arg bug: an unknown value
#: would silently return an empty list, which the author reads as "no problems of that kind".
DiagKind = Literal[
    "canon_contradiction", "broken_canon_rule", "prose_deleted_spec_node",
    "conformance_never_run", "conformance_dirty", "index_stale",
    "unplanned_chapter", "open_thread_debt",
]


async def _gate_book(grant, book_id, caller, need) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


@router.get("/books/{book_id}/diagnostics")
async def read_diagnostics(
    book_id: UUID,
    limit: int = Query(25, ge=1, le=100),      # VALIDATES (422). Does NOT clamp. Do NOT re-clamp below.
    severity: Literal["error", "warn", "info"] | None = Query(None),
    kind: DiagKind | None = Query(None),
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    book: BookClient = Depends(get_book_client_dep),
) -> dict[str, Any]:
    # E0 VIEW gate FIRST — before ANY repo/pool call. Gating on the PATH book_id (never on a book_id
    # derived from a repo row) and never calling resolve_scope first is what keeps a bookless book
    # indistinguishable from an inaccessible one (H13 — no enumeration oracle).
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)

    pool = get_pool()
    _work, pid = await resolve_scope(WorksRepo(pool), book_id)

    diag = await build_diagnostics(
        pool=pool, book_client=book, book_id=book_id, bearer=bearer,
        project_id=pid, limit=limit,
    )
    # ONE cap value drives BOTH the per-source row slices (inside build_diagnostics) and the ranked cap.
    # The filter lives in ranked(), in the order sort → filter → cap.
    return {"book_id": str(book_id), **diag.ranked(cap=limit, severity=severity, kind=kind)}
```

> ⚠ **Import check before you write:** `get_pool` may live in `app.db.pool` rather than `app.deps` in this
> service — `grep -rn "from app.*import get_pool" services/composition-service/app/routers/ | head -1` and
> copy whatever the neighbouring routers do. Same for `NOT_ACCESSIBLE_MESSAGE` — reuse the constant
> `plan_overlay.py` imports, do not redefine the string.

**`main.py`:** add `diagnostics` to the routers import block and, after line 244
(`app.include_router(conformance.router)`), add:

```python
app.include_router(diagnostics.router)  # 37 BE-1 — the problems-panel REST mirror (read-only)
```

**TESTS** — `services/composition-service/tests/unit/test_diagnostics_router.py`. **No DB** — bare app +
`dependency_overrides`, mirroring `tests/unit/test_plan_overlay.py:291-311` verbatim (`_make_client`,
`_StubGrant`). **No `xdist_group("pg")` mark needed** (no real DB/port).

| Test name | Asserts |
|---|---|
| `test_viewer_gets_ranked_diagnostics` | 200; `items[0]["severity"] == "error"`; `counts` present; `book_id` echoed; `computed_at` present; `sources` has **6** members. |
| `test_no_grant_is_404_and_underlevel_is_403` | `_StubGrant` raising `OwnershipError` → **404**; raising `InsufficientGrant` → **403**. 🔴 **Assert the 404 body is BYTE-IDENTICAL to the no-such-book 404** — that identity IS the anti-oracle assertion; assert it, don't assume it. |
| `test_the_gate_runs_BEFORE_the_repo` | 🔴 On the 404 **and** the 403 path, the works/pool repo mock recorded **ZERO calls**. *(A `resolve_scope` before the gate makes a bookless book distinguishable from an inaccessible one.)* |
| `test_book_service_down_is_404_not_502` | `GrantClient` raising/timing out ⇒ **404** (fail-closed — `GrantClient.resolve_access` returns `(NONE,"")` on a book-service outage, `loreweave_grants/__init__.py:117-130`), and the body matches the no-such-book 404. |
| `test_severity_filter_does_not_shrink_counts` | 🔴 `?severity=info` ⇒ every item is info, **`counts["broken_canon_rule"]` is still its true value**, `total` unchanged, `severity_counts.error` still non-zero. *(D-2 asserted at the route. The test that stops a later agent "simplifying" the filter client-side.)* |
| `test_the_info_filter_is_not_starved_by_the_cap` | 🔴 **THE D-2 ROUTE BUG.** Seed 30 errors + 12 infos; `?severity=info&limit=25` ⇒ **12 items**, not 0. *(A route that filters after `ranked(cap)` returns 0. This is the assertion that catches it end-to-end.)* |
| `test_unknown_kind_is_422_not_an_empty_list` | `?kind=nonsense` → **422** (the `Literal`). An empty 200 would read as "no problems of that kind", which is a lie. |
| `test_limit_out_of_range_is_422_not_a_silent_default` | `?limit=0` → **422**; `?limit=-1` → **422**; `?limit=101` → **422**. 🔴 Assert `== 422` and **NOT `200`** — a 200 carrying a silently-substituted default is the `chapter-list-limit100-fallback-20-bug` class. |
| `test_default_limit_is_25_and_counts_stay_exact` | Omit `limit`, seed >25 ⇒ `len(items) == 25`, `refs_capped is True`, `total` == the true count. |
| `test_degraded_book_client_yields_warnings_and_omits_the_key` | 🔴 **DoD-2.** Fake `BookClient.list_chapters` raises `BookClientError(503)` ⇒ **200** (never 500); `"unplanned_chapter" not in body["counts"]` (**NOT `== 0`**); 🔴 **`"prose_deleted_spec_node" not in body["counts"]` TOO — `list_chapters` feeds TWO sources**; `len(body["warnings"]) == 2` (both substrings: *"unplanned chapters are unknown for this book (not zero)"* `coverage.py:143` and *"prose-deleted spec nodes are unknown for this book (not zero)"* `coverage.py:197`); `body["degraded_sources"] == ["prose_deleted","coverage"]` (order-insensitive); **and the OTHER sources still populate** (seed one open thread ⇒ its kind IS in `counts` — degrade is per-source, not a payload wipe); **and** `set(body["counts"]) <= set(SEVERITY)` with **no zero-seeded keys**. |
| `test_a_workless_book_is_200_with_has_work_false` | `resolve_scope → (None, None)` ⇒ **200** (never 404/500), `has_work is False`, `len(warnings) == 3`, and the book-keyed rows still render. |
| `test_clean_book_omits_warnings_entirely` | `"warnings" not in body and "degraded_sources" not in body`. *(The real wire shape — the FE must read `data.warnings ?? []`.)* |
| `test_route_passes_the_users_bearer_not_a_service_bearer` | Spy on the injected `BookClient`: it was called with `"test-bearer"` (the `get_bearer_token` override). 🔴 **AND `patch.object(module, "mint_service_bearer", side_effect=AssertionError)`** — it must be **unreachable** on the REST path. *(A later copy-paste from the MCP handler would re-open the `internal-route-driven-by-a-session-must-grant-check` hole; this makes that copy-paste RED.)* |
| `test_the_route_and_the_MCP_tool_return_the_same_payload` | 🔴 **The anti-fork parity test.** The same `Diagnostics` object through the route and through the tool yields identical `items/counts/total/refs_capped`. *(DoD-1's "one fanout, no fork" at test level.)* |

**DoD evidence:** `cd services/composition-service && python -m pytest tests/unit/test_diagnostics_router.py tests/unit/test_agent_native.py -q` → all pass; plus `curl` of the route on a stack-up returning a 200 with a non-empty `counts` map (folded into the wave live-smoke, §10).

---

### ── W7-S3 · BE-1d — `GET /v1/composition/books/{book_id}/entity-references`

**dependsOn:** none (parallel with S1/S2). **Kind:** BE / CONTRACT.

**DECISION, RECORDED SO IT IS NOT RE-LITIGATED: REST, not the `mcpBridge`.** Every sibling panel reaches
composition over REST. The bridge's `FE_BRIDGE_TOOL_ALLOWLIST` (`api-gateway-bff/src/tools/tools.controller.ts:24-30`)
is **exactly 5 names**, and every one is **spend-adjacent** (4 cost-gated PROPOSE flows + 1 poll). A **free
read** does not belong in a spend allowlist. Going REST also keeps this slice **single-service**.

> ⚠ **The path `/works/{pid}/references` is TAKEN.** `routers/references.py` is the author's **research
> reference shelf** (`reference_source` + embeddings, LOOM T3.6) — a different concept the repo already
> flags as a name collision (`entity_references.py:8-15`). The new route is **book-scoped** and named
> **`entity-references`**. One name, one concept.

**FILES**

| Path | Action |
|---|---|
| `services/composition-service/app/services/agent_native.py` | **EDIT** — ⚖ ADJ: **EXTRACT** `find_entity_references(...)` (the shared producer). |
| `services/composition-service/app/mcp/server.py` | **EDIT** — `composition_find_references` becomes a caller **+ the one-line `except ValueError: raise` fix-now (see 🔴 below)**. |
| `services/composition-service/app/routers/entity_references.py` | **CREATE** |
| `services/composition-service/app/main.py` | **EDIT** — one `include_router` line |
| `services/composition-service/tests/unit/test_entity_references_router.py` | **CREATE** |

**ROUTE CONTRACT**

```
GET /v1/composition/books/{book_id}/entity-references
  query:
    entity_id  UUID  REQUIRED
    sources    repeated enum, optional — members of REFERENCE_SOURCES (8). Omit ⇒ all eight.
    limit      int 1..100, default 20   (rows per source; COUNTS STAY EXACT)
  200 → {
    book_id, entity_id,
    sources: {
      "<source>": { count: int, refs: [{source, node_ref:{kind,id,title}, detail}], has_more: bool }
      | { error: "this source could not be read" }        // PER-SOURCE degrade — never a 0
    },
    _meta: { note: "Composition scope only. …" }
  }
  403 / 404 → same uniform H13 shape as BE-1
  422 → an unknown `sources` member (FastAPI Literal). NEVER (0, []).
```

**⚖ ADJ — THE CHANGE IS "EXTRACT", NOT "MIRROR".** (`Q-37-BE1D-ENTITY-REFS-ROUTE` §1) The first draft said
*"Mirror the MCP handler exactly"*. **That is a FORK** — the identical `css-var-duplicated-across-two-
consumers-drifts` class BE-1a exists to prevent, committed in the sibling surface. **Do it as ONE producer:**

**Step 1 — extract.** Move `mcp/server.py:3892-3931`'s loop into `app/services/agent_native.py` (where
`REFERENCE_SOURCES` already lives):

```python
async def find_entity_references(
    pool, *, book_id: UUID, entity_id: UUID,
    sources: tuple[str, ...] | None, limit: int,
) -> dict[str, Any]:
    """The 8-source entity-backlinks fanout, ONCE. The MCP tool and the REST route both call this."""
    want = tuple(sources) if sources else REFERENCE_SOURCES
    cap = max(1, min(int(limit or 20), 100))
    repo = EntityReferencesRepo(pool)
    out: dict[str, Any] = {}
    for src in want:
        try:
            count, refs = await repo.find(src, book_id=book_id, entity_id=entity_id, limit=cap)
        except ValueError:
            raise                       # 🔴 a closed-set violation is a BUG, not a degraded source.
        except Exception:               # noqa: BLE001 — a REAL read failure degrades exactly ONE source
            logger.warning("entity_references: source %s failed", src, exc_info=True)
            out[src] = {"error": "this source could not be read"}
            continue
        out[src] = {"count": count, "refs": refs, "has_more": count > len(refs)}
    return {"book_id": str(book_id), "entity_id": str(entity_id), "sources": out, "_meta": {"note": …}}
```
Then rewrite `mcp/server.py:3892-3931` to **call it**. One producer ⇒ tool and route return **one
byte-identical shape** and cannot drift.

> 🔴 **FIX-NOW BUG IN THE EXISTING MCP CONSUMER** (⚖ ADJ `Q-37-BE1D-SOURCES-ENUM-NO-ZERO` §3 — this is the
> live half). `server.py:3911` catches a **bare `Exception`**, so an unknown source becomes
> `{"error": "this source could not be read"}` — a **transient-looking** failure. It isn't a zero, so it
> doesn't break the letter of the rule, but it **hides a closed-set typo as a retryable read error**, and the
> M2 lens renders both identically. The `except ValueError: raise` line above fixes it. **One line, this
> wave.** A test asserts it (`test_mcp_find_references_propagates_a_bad_source`).

**Two differences from the MCP handler, in the ROUTE:**

1. `sources` is typed `list[ReferenceSource] | None = Query(None)` — **the `Literal` imported from
   `agent_native.py:43`, not a free `list[str]`. Do NOT re-declare the 8-set (one name, one concept).**
   `EntityReferencesRepo.find` **RAISES** on an unknown source *precisely so a typo cannot return `(0, [])`*,
   which would read as *"this entity is used nowhere"* — and, as its own docstring says, **"the agent's next
   move on that answer is to delete something."** The enum makes it a **422 before the repo is ever reached**.
   **Do NOT catch that `ValueError` into a zero. Do NOT normalize or drop unknown members.**
   ⚠ **Repeatable-param style** (`?sources=outline_pov&sources=canon_rule`), **not** a comma-joined string —
   that is what FastAPI gives you free with `list[Literal]` and what makes the 422 automatic. A CSV would need
   a hand-parser and **re-opens exactly this bug class**.
2. The gate is `_gate_book(grant, book_id, user_id, GrantLevel.VIEW)` — **import the helper from
   `routers/diagnostics.py`**; do **not** invent a third gate shape.

**No Work/project resolution.** All 8 sources are BOOK-scoped and the E0 gate is on the book
(`entity_references.py:42-48` states this — threading a project id through and never using it was how a
`book_id` once ended up in a project slot).

**TESTS** — `tests/unit/test_entity_references_router.py` (bare app + fake repo, no DB):

| Test name | Asserts |
|---|---|
| `test_all_eight_sources_are_returned_by_default` | Omit `sources` ⇒ the response's `sources` dict has **exactly the 8 `REFERENCE_SOURCES` keys**. *(The guard against a 6-source regression.)* |
| `test_a_failing_source_renders_error_not_zero` | The fake repo raises `asyncpg.PostgresError` for `motif_application` ⇒ `body["sources"]["motif_application"] == {"error": "this source could not be read"}`, the **other 7 still answer**, and 🔴 **the degraded key has NO `count` field at all**. |
| `test_unknown_source_is_422_and_the_repo_is_never_called` | `?sources=outline` (the classic typo the repo docstring names) → **422**, **and a spy on `EntityReferencesRepo.find` recorded ZERO calls**. It must not be a 200 with a zero. |
| `test_mcp_find_references_propagates_a_bad_source` | 🔴 The fix-now: `composition_find_references` with a bad source **raises** — it does **not** return `{"error": "could not be read"}`. *(Guards the narrowed `except ValueError: raise`.)* |
| `test_counts_are_exact_when_refs_are_capped` | fake returns `count=40, refs=[…20]` ⇒ `count == 40`, `len(refs) == 20`, `has_more is True`. |
| `test_gate_404_403` | Same H13 pair as BE-1. |
| `test_the_route_and_the_MCP_tool_return_the_identical_dict` | 🔴 **The anti-fork guard.** Same args ⇒ same dict. *(Proves step 1's extraction did not fork.)* |
| `test_meta_note_is_present` | `_meta.note` is non-empty **on the wire**. ⚠ **The FE does NOT render it verbatim** — see the 🔴 in W7-S8: the real string names MCP tool names (`glossary_list_chapter_links`, `kg_entity_edge_timeline`) and putting those in an author's popover is a defect. BE keeps it for the **agent**; FE renders an i18n string. |

**DoD evidence:** `python -m pytest tests/unit/test_entity_references_router.py -q` → all pass.

---

### ── W7-S3b · 🔴 CONTRACT — freeze the two new routes in the OpenAPI spec **BEFORE any FE consumes them**

**dependsOn:** `W7-S2`, `W7-S3`. **Kind:** CONTRACT. **BLOCKS:** `W7-S5`, `W7-S8`.

**WHY THIS SLICE EXISTS.** CLAUDE.md: **"Contract-first: API contract frozen before frontend flow."** This
wave adds **two new REST routes**. The first draft of this plan added them to **zero** contract files — an
across-the-board omission the completeness critic caught in **seven of ten waves**. A route the FE consumes
that no spec describes is a contract that lives only in a TypeScript interface, i.e. **no contract at all**.

**🔴 FIND THE FILE — DO NOT GUESS.** Verified on disk:

| Candidate | Verdict |
|---|---|
| **`contracts/api/composition/v1/openapi.yaml`** | ✅ **THIS ONE.** Live + maintained: `openapi: 3.0.3`, `servers: [{url: /v1/composition}]`, **17 paths** (it already carries `/canon-rules/{rule_id}`, `/jobs/{job_id}`, `/books/{book_id}/work`, …), a `components.parameters.BookId`, and `components.responses.NotFound`. **Both of this wave's routes go here.** |
| `contracts/api/composition-service/plan-forge.v1.yaml` | ❌ **A DIFFERENT FILE.** That is **Wave 5's** home (plan-forge). Do not put Wave 7's routes in it. |
| `contracts/api/book-service/…` | ❌ **DOES NOT EXIST.** (Wave 8's plan names it three times and is wrong; the real path is `contracts/api/books/v1/openapi.yaml`.) Wave 7 touches neither. |
| a jobs-service spec | ❌ **DOES NOT EXIST** — `contracts/api/` has **no** jobs directory. See the defer row below. |

**FILES**

| Path | Action |
|---|---|
| `contracts/api/composition/v1/openapi.yaml` | **EDIT** — 2 new paths + 4 new schemas + 1 new parameter + 1 new tag |

**THE CHANGE.** `servers.url` is already `/v1/composition`, so the **paths are written RELATIVE to it**
(`/books/{book_id}/diagnostics`, **not** `/v1/composition/books/...`). Match the file's existing terse
flow-style. Add `- name: diagnostics` to the top-level `tags:` list.

```yaml
  # ─────────────────────────────────────────────────────────────────────────────
  # 37 BE-1 / BE-1d — the Issues feed + the find-references lens (Wave 7).
  # Read-only. VIEW-gated on the PATH book_id. NEVER 500s on a degraded source.
  # ─────────────────────────────────────────────────────────────────────────────
  /books/{book_id}/diagnostics:
    get:
      tags: [diagnostics]
      summary: Everything wrong with this book, ranked error → warn → info ($0, no LLM)
      description: >
        The REST mirror of the `composition_diagnostics` MCP tool — ONE shared `build_diagnostics()`
        producer, so agent and human can never see two different truths.
        SIX independently-degradable sources emit EIGHT kinds. A source that could not be read is
        OMITTED from `counts` (absent ≠ zero) and named in `warnings[]` + `degraded_sources[]` — it is
        NEVER reported as 0 and it NEVER 500s. `counts`/`severity_counts`/`total` are EXACT and are
        NEVER narrowed by `severity`/`kind`; only `items` is filtered and capped.
      parameters:
        - { $ref: '#/components/parameters/BookId' }
        - name: limit
          in: query
          required: false
          description: rows per page. VALIDATED (422 out of range) — not clamped.
          schema: { type: integer, minimum: 1, maximum: 100, default: 25 }
        - name: severity
          in: query
          required: false
          schema: { type: string, enum: [error, warn, info] }
        - name: kind
          in: query
          required: false
          schema: { $ref: '#/components/schemas/DiagnosticKind' }
      responses:
        '200':
          description: The ranked findings (200 even when sources degraded)
          content:
            application/json:
              schema: { $ref: '#/components/schemas/DiagnosticsResponse' }
        '403': { description: insufficient access (InsufficientGrant) }
        '404': { $ref: '#/components/responses/NotFound' }
        '422': { description: unknown severity/kind, or limit outside 1..100 }

  /books/{book_id}/entity-references:
    get:
      tags: [diagnostics]
      summary: Everything in the SPEC layer that references this entity (8 sources)
      description: >
        The REST mirror of `composition_find_references`. Composition scope ONLY — prose mentions live in
        the glossary, graph edges in the KG. Degrades PER SOURCE: a source that could not be read carries
        `{error}` and the other seven still answer. An unknown `sources` member is a 422 — it is NEVER
        coerced into a zero count (a zero reads as "used nowhere", and the next move on that answer is to
        delete the entity).
      parameters:
        - { $ref: '#/components/parameters/BookId' }
        - { name: entity_id, in: query, required: true, schema: { type: string, format: uuid } }
        - name: sources
          in: query
          required: false
          description: repeat the param per source (?sources=a&sources=b). Omit ⇒ all eight.
          schema: { type: array, items: { $ref: '#/components/schemas/ReferenceSource' } }
        - name: limit
          in: query
          required: false
          description: caps `refs` per source. `count` stays EXACT.
          schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
      responses:
        '200':
          description: One entry per requested source — a count block or an error block
          content:
            application/json:
              schema: { $ref: '#/components/schemas/EntityReferencesResponse' }
        '403': { description: insufficient access (InsufficientGrant) }
        '404': { $ref: '#/components/responses/NotFound' }
        '422': { description: unknown `sources` member, or limit outside 1..100 }
```

…and under `components.schemas`:

```yaml
    DiagnosticKind:
      type: string
      description: The 8 SEVERITY keys (agent_native.py:60-73). A closed set.
      enum: [canon_contradiction, broken_canon_rule, prose_deleted_spec_node,
             conformance_never_run, conformance_dirty, index_stale,
             unplanned_chapter, open_thread_debt]
    RefKind:
      type: string
      description: >
        IF-1 — the ID SPACE `node_ref.id` lives in. THREE members, because three id spaces exist.
        `node_ref.kind` is the DISPLAY label ("scene"/"chapter"/"arc") and is NOT routable: two kinds
        emit kind:"chapter" over DISJOINT id spaces. A client routes on `ref_kind` ONLY.
        `scene` is NOT a member (a scene IS an outline_node) and `canon_rule` is NOT a member
        (no diagnostic emits one — `rule_id` is a sibling field).
      enum: [chapter, outline_node, structure_node]
    Diagnostic:
      type: object
      required: [kind, severity, title, source]
      properties:
        kind: { $ref: '#/components/schemas/DiagnosticKind' }
        severity: { type: string, enum: [error, warn, info] }
        title: { type: string }
        detail: { type: string }
        at: { type: string, format: date-time }
        source: { type: string, description: which of the 6 DIAGNOSTIC_SOURCES produced it }
        panel_id:
          type: string
          nullable: true
          description: >
            The Studio panel that owns this finding. NULL ⇒ no panel owns the fix ⇒ the row is INERT on
            every surface (an agent must STATE it, never try to open a panel for it).
        node_ref:
          type: object
          nullable: true
          required: [id, ref_kind]
          properties:
            kind: { type: string, description: DISPLAY label only — never route on this }
            id: { type: string, format: uuid }
            title: { type: string, nullable: true }
            ref_kind: { $ref: '#/components/schemas/RefKind' }
        chapter_id:
          type: string
          format: uuid
          description: >
            OMITTED (never null) when absent. A LIVE book-service chapter. `prose_deleted_spec_node`
            deliberately never carries it — its chapter is deleted by construction, so emitting it would
            hand the client a guaranteed-404 deep-link target.
        rule_id:
          type: string
          description: OMITTED (never null) when the violation carried no attributable rule.
    DiagnosticsResponse:
      type: object
      required: [book_id, items, counts, severity_counts, total, matched, refs_capped, has_work, sources, computed_at]
      properties:
        book_id: { type: string, format: uuid }
        items: { type: array, items: { $ref: '#/components/schemas/Diagnostic' } }
        counts:
          type: object
          additionalProperties: { type: integer }
          description: KIND-keyed. EXACT, SPARSE, never filtered, never capped. A kind absent here was NOT checked — it is NOT zero.
        severity_counts:
          type: object
          description: What the toolbar chips render. `counts` is kind-keyed, so counts["error"] does not exist.
          properties: { error: { type: integer }, warn: { type: integer }, info: { type: integer } }
        total: { type: integer, description: EXACT book-wide total. Never narrowed by a filter. }
        matched: { type: integer, description: rows the filter selected, BEFORE the cap }
        refs_capped: { type: boolean, description: matched > limit }
        has_work: { type: boolean, description: false ⇒ this book has no composition Work; the project-keyed sources were NOT checked (absent, not zero) }
        sources: { type: array, items: { type: string }, description: the 6 DIAGNOSTIC_SOURCES. Clients render "N sources" from THIS — never a literal. }
        computed_at: { type: string, format: date-time, description: SERVER stamp. Not the client's fetch time. }
        warnings:
          type: array
          items: { type: string }
          description: OMITTED when clean — NOT []. Present ⇒ degraded. Also carries NON-failures (a truncation notice), so it is NOT a count of failed sources.
        degraded_sources:
          type: array
          items: { type: string }
          description: OMITTED when clean. The ONLY honest "N sources could not be read" count.
    ReferenceSource:
      type: string
      description: >
        EIGHT sources over the seven F-A4 shapes — the outline pov/present pair SPLITS by node kind
        (there is no `scenes` table; `outline_node` holds both). Do NOT collapse to six.
      enum: [outline_pov, outline_present, scene_pov, scene_present,
             structure_roster, motif_application, canon_rule, narrative_thread]
    EntityReferenceBlock:
      oneOf:
        - type: object
          required: [count, refs, has_more]
          properties:
            count: { type: integer, description: EXACT. Only `refs` is capped. }
            refs:
              type: array
              items:
                type: object
                properties:
                  source: { type: string }
                  node_ref: { type: object, properties: { kind: { type: string }, id: { type: string }, title: { type: string, nullable: true } } }
                  detail: { type: string }
            has_more: { type: boolean }
        - type: object
          required: [error]
          description: This source could not be read. It is NOT zero. A client MUST NOT render it as 0.
          properties:
            error: { type: string }
    EntityReferencesResponse:
      type: object
      required: [book_id, entity_id, sources]
      properties:
        book_id: { type: string, format: uuid }
        entity_id: { type: string, format: uuid }
        sources:
          type: object
          description: One key per REQUESTED source. A key missing from a response the client asked for MUST be treated as an error, never as zero.
          additionalProperties: { $ref: '#/components/schemas/EntityReferenceBlock' }
        _meta:
          type: object
          properties:
            note: { type: string, description: AGENT-facing. It names MCP tools — a GUI must NOT render it verbatim. }
```

**TESTS / DoD evidence** (a spec with a syntax error is worse than no spec):

1. `npx @redocly/cli lint contracts/api/composition/v1/openapi.yaml` → **0 errors**
   *(or `python -c "import yaml,sys; yaml.safe_load(open('contracts/api/composition/v1/openapi.yaml'))"` if
   redocly is not installed — a parse check is the floor, not the ceiling).*
2. 🔴 **The spec must match the code, not the intention.** Assert it mechanically in
   `services/composition-service/tests/unit/test_diagnostics_router.py`:
   `test_the_openapi_contract_matches_the_live_route` — load
   `contracts/api/composition/v1/openapi.yaml`, and assert
   (a) `paths["/books/{book_id}/diagnostics"]` exists,
   (b) its `kind` enum **==** `set(SEVERITY)` (the 8 keys — imported, not retyped),
   (c) `components.schemas.RefKind.enum` **==** `sorted(REF_KINDS)`,
   (d) `components.schemas.ReferenceSource.enum` **==** `list(REFERENCE_SOURCES)` (all **8**),
   (e) `paths["/books/{book_id}/entity-references"]` exists.
   *(This is the `checklist⇒test-the-effect` rule: a contract nobody diffs against the code rots in one
   commit. It also makes the "re-collapse the lens to 6 rows" regression fail in **two** places.)*

> **Defer row (written, not silently dropped): `D-W7-JOBS-CONTRACT-ABSENT`.** `GET /v1/jobs` gains a
> `book_id` query param in **W7-S11**, but **`contracts/api/` has NO jobs-service spec at all** — there is no
> file to add it to, and authoring a full jobs-service OpenAPI (list/get/cancel/retry/stream/projection) is a
> **structural** effort with its own review surface, not a line in this wave. It is **not** a new route (it is
> a new param on an existing, already-undocumented one). Gate **#2 (large/structural)**. Target: the wave that
> next touches jobs-service, or a dedicated contract sweep. **Recorded in §12.**

---

## 6 · Frontend slices

### ── W7-S4 · The bottom panel: 3 always-mounted bodies + the honest stub + the resize grip

**dependsOn:** none. **Kind:** FE.

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/studio/components/StudioBottomPanel.tsx` | **EDIT** — the structural refactor (**Part 1**) |
| `frontend/src/features/studio/components/StudioFrame.tsx` | **EDIT** — 🔴 **Part 2 + Part 3.** ⚖ ADJ — **without this, Part 1 buys NOTHING.** |
| `frontend/src/features/jobs/context/JobsStreamProvider.tsx` | **EDIT** — 🔴 **Part 3** — make it **re-entrant** |
| `frontend/src/features/studio/types.ts` | **EDIT** — `StudioChromeState.bottomHeight` + the bounds consts |
| `frontend/src/features/studio/hooks/useStudioChrome.ts` | **EDIT** — `bottomHeight` + `setBottomHeight` + `clampBottomHeight` (⚖ ADJ — **the EXISTING persistence home**) |
| `frontend/src/features/studio/components/bottom/IssuesTab.tsx` | **CREATE** — placeholder body in this slice (real in S5) |
| `frontend/src/features/studio/components/bottom/JobsTab.tsx` | **CREATE** — honest stub body (real in S12) |
| `frontend/src/features/studio/components/bottom/GenerationTab.tsx` | **CREATE** — honest stub body (real in S12) |
| `frontend/src/features/studio/components/__tests__/StudioBottomPanel.test.tsx` | **EDIT** — **the guard inverts** |
| `frontend/src/features/studio/hooks/__tests__/useStudioChrome.test.ts` | **EDIT** — the clamp tests |
| `frontend/src/i18n/__tests__/studioBottomParity.test.ts` | **CREATE** — ⚖ ADJ, the i18n gate |
| `frontend/src/i18n/locales/en/studio.json` | **EDIT** — 🔴 **DELETE `bottomStub`**; add `bottom.*` / `bottom.pending.*` / `issues.*` |
| `frontend/src/i18n/locales/{17 others}/studio.json` | **GENERATED** — `python scripts/i18n_translate.py --ns studio` |

### THE CHANGE — it is THREE parts. **Part 1 alone is a no-op.** (⚖ ADJ `Q-37-ALWAYS-MOUNTED-3-BODIES`)

**Part 1 — `StudioBottomPanel.tsx`: three always-mounted bodies.**
Today (`:43-45`) it renders **ONE `<div>` for whichever tab is active**. **CLAUDE.md hard rule** — *"Never
conditionally unmount stateful components"*: the Jobs tab owns an SSE subscription and the Issues tab a
React-Query subscription; a ternary tears both down on every tab click.

> 🔴 **HIDE WITH THE HTML `hidden` ATTRIBUTE, NOT THE TAILWIND `hidden` CLASS.** (⚖ ADJ
> `Q-37-BOTTOM-PANEL-TEST-INVERSION`.) vitest runs `environment: 'jsdom'` (`vite.config.ts:66`) **with NO CSS
> loaded**, so `className="hidden"` computes to `display:block` in jsdom and jest-dom's `toBeVisible()` would
> call a hidden body **VISIBLE** — making `not.toBeVisible()` **falsely RED**. jest-dom honours
> `hasAttribute('hidden')` and jsdom's UA stylesheet applies `[hidden]{display:none}`. The repo's shipped
> precedent for keep-mounted tab bodies is `knowledge/components/EntityDetailPanel.tsx:332`
> (`<div hidden={panelTab !== 'current'}>`). **Mirror it.** Keep the class too — it is for prod CSS.
> ⚠ And **never** write `cn('flex …', tab !== tb && 'hidden')`: `flex` and `hidden` are **both `display`
> utilities** and precedence is decided by Tailwind's **source order**, not class order. Apply `block`/`flex`
> **OR** `hidden`, never both.

```tsx
// Bottom panel — the VS Code "panel" analogue: Jobs / Generation / Issues.
// THREE ALWAYS-MOUNTED BODIES. Never a ternary (CLAUDE.md), and never CSS-only hiding in a jsdom-tested
// component (the `hidden` ATTRIBUTE is what jest-dom's toBeVisible() actually reads).
export function StudioBottomPanel({ open, height, onHeightChange, onClose }: Props) {
  const { t } = useTranslation('studio');
  const [tab, setTab] = useState<BottomTab>('issues');   // ← Issues is now the useful default

  return (
    <div
      data-testid="studio-bottom"
      style={open ? { height } : undefined}
      className={cn('flex-shrink-0 flex-col border-t bg-card', open ? 'flex' : 'hidden')}
    >
      <div data-testid="studio-bottom-grip" role="separator" aria-orientation="horizontal"
           tabIndex={0} onPointerDown={onGripPointerDown} onKeyDown={onGripKeyDown}
           className="h-1 w-full flex-shrink-0 cursor-row-resize hover:bg-primary/40" />
      {/* … the existing tab strip; each button gains data-testid={`bottom-tab-${tb}`} … */}

      <div className="min-h-0 flex-1">
        {TABS.map((tb) => {
          const Body = BODIES[tb];                       // { jobs: JobsTab, generation: …, issues: … }
          return (
            <div key={tb} role="tabpanel" data-testid={`bottom-body-${tb}`}
                 hidden={tab !== tb}                                        // ← THE ATTRIBUTE. Load-bearing.
                 className={cn('h-full min-h-0 overflow-y-auto', tab !== tb && 'hidden')}>
              <Body />
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**🔴 Part 2 — `StudioFrame.tsx:160`. THE ONE THE FIRST DRAFT MISSED.**
Today: `{chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}`. **That unmounts ALL
THREE bodies every time the user collapses the panel** — so Part 1 buys nothing and the SSE/query
subscriptions die anyway. Change to an **unconditional mount**, collapsing via CSS **inside** the panel:

```tsx
<StudioBottomPanel
  open={chrome.bottomOpen}
  height={chrome.bottomHeight}
  onHeightChange={chrome.setBottomHeight}
  onClose={chrome.toggleBottom}
/>
```
This is **the file's own established precedent**: `ManuscriptUnitProvider` is hoisted *"above every chrome
conditional, so a sidebar/bottom toggle never remounts it"* (`StudioFrame.tsx:133-137`) and the palettes are
*"always mounted … visibility via `open`"* (`:173`). The `&&` at `:160` **contradicts the same file's own D4
no-remount comment at `:157-158`.**

**🔴 Part 3 — hoist ONE `JobsStreamProvider` and make it RE-ENTRANT.**
The Jobs subscription lives in `JobsStreamProvider` (`:38`) → `useJobsStream` (`:20`), which opens **one
long-lived `fetch()` stream per mount** and **aborts it on unmount** (`useJobsStream.ts:111-116`).
`JobsListPanel.tsx:26` and `JobDetailPanel.tsx:46` **already each mount their own** — a third inside the Jobs
tab would make **three concurrent `/v1/jobs/stream` connections per user.**

(a) Mount **exactly one** `<JobsStreamProvider>` in `StudioFrame` **directly inside `<ManuscriptUnitProvider>`**
    (`StudioFrame.tsx:137`) so it sits **above every chrome conditional**.
(b) `JobsTab` consumes `useJobLive`/`useJobsConnection` **from context** and mounts **NO provider**.
(c) Make the provider **re-entrant** so the dock panels **inherit** instead of opening a second stream — split
    it into two components (**do not early-return inside the existing body** — that changes hook counts):
```tsx
export function JobsStreamProvider({ children }) {
  const existing = useContext(StoreCtx);
  if (existing) return <>{children}</>;          // already provided upstream → inherit, don't re-stream
  return <JobsStreamRoot>{children}</JobsStreamRoot>;   // ← the CURRENT body, moved VERBATIM
}
```
    Standalone `/jobs` + `/jobs/:id` pages have **no ancestor provider**, so they keep working unchanged.

> **Default (PO may veto):** the Jobs SSE stays connected for the whole studio session, **including while the
> bottom panel is collapsed.** It is one fetch stream, it is what `/jobs` already does, and
> disconnect-on-collapse would re-introduce the reconnect-backoff storm `useJobsStream.ts:43-48` exists to
> survive. If the PO wants it to drop on collapse, that is a `JobsStreamProvider` **prop** (`enabled`), **never
> a remount**.

### ⚖ ADJ — the resize grip uses the **EXISTING** chrome store. **NO new localStorage key.** (`Q-37-RESIZE-GRIP-UNASSIGNED`)

The first draft invented `bottom/useBottomPanelHeight.ts` + a new `studio.bottomPanel.height` key. **Both are
wrong — the home already exists.** `useStudioChrome.ts:11` owns `lw_studio_chrome_${bookId}` with
write-through at `:43/:51/:59` and a defensive `load()` at `:16-31`. **Add `bottomHeight` to that state.**
*(The `168px` literal lives at `StudioBottomPanel.tsx:16` — `h-[168px]` — **not** in `StudioFrame.tsx:160`,
which is only the mount site. `StudioDock.tsx:32` is already `min-h-0 flex-1`, so a `flex-shrink-0` sibling
of ANY height needs **zero** frame layout change.)*

- `types.ts` — `StudioChromeState.bottomHeight: number`; `DEFAULT_CHROME.bottomHeight = 168`; export
  `BOTTOM_MIN_PX = 120` and `BOTTOM_MAX_VH = 0.6`.
- `useStudioChrome.ts` — `clampBottomHeight(px) => Math.min(Math.max(px, 120), Math.round(window.innerHeight * 0.6))`.
  In `load()` (mirroring the existing defensive `ACTIVITY_VIEWS.includes` guard at `:22`):
  `bottomHeight: Number.isFinite(parsed.bottomHeight) ? clampBottomHeight(parsed.bottomHeight!) : 168`.
  Add `setBottomHeight(px)` — clamps + write-throughs to the **SAME key** (copy `toggleBottom`'s body at `:56-62`).
  **Clamp on LOAD and on DRAG.** Bounds: **min 120px · max 60vh · default 168px.**
- `StudioBottomPanel.tsx` — `onGripPointerDown` captures `startY`/`startH`, attaches `pointermove`/`pointerup`
  to `window` **inside the handler**, calls `onHeightChange(startH - (e.clientY - startY))` (drag **up** grows),
  detaches on `pointerup`. 🔴 **NO `useEffect`** (CLAUDE.md: *no useEffect for event handling*).
  **Keyboard: `ArrowUp`/`ArrowDown` on the focused `role="separator"` = ±16px** — the grip must not be
  mouse-only.
- **SET-1..8 does not apply:** this is per-device UI state, explicitly carved out by CLAUDE.md
  (*"sidebar collapsed, editor panel widths"*). **Not a user setting. Not an env flag. No server round-trip.**

**`bottom/JobsTab.tsx` and `bottom/GenerationTab.tsx` (CREATE — the HONEST stub, until S12).**
They are **REAL components** rendering honest copy — not the `bottomStub.*` *"once wired"* lie.

### 🔴 ⚖ ADJ — i18n: **DELETE `bottomStub`. Do NOT repurpose it.** (`Q-37-I18N-KEYS-18-LOCALES`)

The first draft **changed the meaning of the existing `bottomStub.*` keys**. **That ships a silent lie in 17
languages.** `scripts/i18n_translate.py:339-357`'s resume path carries an existing translation forward on
**key-presence + placeholder-parity alone** — it **never compares the English source VALUE**. So a repurposed
key keeps its **OLD sentence forever in all 17 target locales**, and `--check` reports **0 hard / 0 soft
(green)**. Silent-stale, no signal.

**THE RULE (bake it into every wave's DoD): _never change the meaning of an existing i18n key — a changed
meaning is a NEW key + a DELETE of the old one._**

1. Hand-edit **ONLY** `frontend/src/i18n/locales/en/studio.json`. **Never** hand-edit the other 17.
   - 🔴 **DELETE the whole `"bottomStub"` object** (`en/studio.json:721-725`). All three keys.
   - **ADD** the new keys under **`bottom.*`** (labels + the honest pending copy), **`issues.*`** (S5),
     **`refs.*`** (S8):
```json
"bottom": {
  "jobs": "Jobs", "generation": "Generation", "issues": "Issues",
  "pending": {
    "jobs": "Book-scoped job feed — pending book_id on the jobs projection (BE-1b).",
    "generation": "Live composition generation — pending book_id on the jobs projection (BE-1b)."
  }
}
```
   *(Keeping the literal ticket id `BE-1b` in the visible string is deliberate — it is what makes the stub
   greppable and un-rottable. PO may veto the id; nothing else changes if so.)*
2. **Do NOT hand-delete `bottomStub` from the 17 target files.** Because the wave adds new `en` keys,
   `plan_namespace` returns `status:"work"` for `studio.json` in every language and `assemble_and_write`
   (`i18n_translate.py:366-380`) rebuilds each file from `passthrough + carry + chunks` — all keyed off the
   **EN key set** — so **orphan keys are pruned automatically**.
3. **GENERATE** (bring LM Studio up on `:1234` with `google/gemma-4-26b-a4b-qat`), from repo root:
```bash
python scripts/i18n_translate.py --ns studio     # gap-fill: translates ONLY the new keys, carries the ~700 others
```
   🔴 **Do NOT pass `--force`** (it re-translates the whole namespace × 17 langs for nothing).
   If LM Studio genuinely cannot run: `ENDPOINT`/`MODEL` are module constants at `i18n_translate.py:50-51`
   (plain OpenAI-compatible chat) — temporarily repoint them; **do not commit that edit**. **This is NOT a defer.**
4. **VERIFY — paste the output into the evidence string:**
```bash
for l in vi ja ko zh-CN zh-TW es pt-BR fr de ru id ms tr ar hi bn th; do \
  python scripts/i18n_translate.py --check $l/studio.json; done   # every line must read `0 hard`
ls frontend/src/i18n/locales/*/_FAILED.json                        # must be EMPTY
grep -rl bottomStub frontend/src/                                  # must return NOTHING (incl. the test)
```
   ⚠ **Eyeball the 8 Latin-script targets' new keys** (vi/es/pt-BR/fr/de/id/ms/tr): `isolate_retry_soft`
   (`i18n_translate.py:270-308`) **early-returns when `script_re is None`**, so an English echo in those 8
   has **no detector**. ~10 keys × 8 files — cheap.
5. 🔴 **ADD THE MECHANICAL GUARD** (`checklist⇒test-the-effect`): **`frontend/src/i18n/__tests__/studioBottomParity.test.ts`**,
   modelled on the existing `onboardingParity.test.ts` (same `flatten()` + key-set-equality shape), importing
   all 17 target `studio.json`. Per locale assert: (a) key set **===** en's; (b) no empty values;
   (c) the `{{placeholder}}` set per key **===** en's; (d) **NO key begins with `bottomStub.`**; (e) every
   `BottomTab` id has a `bottom.<id>` key. **This test reds if the generator was skipped — which is exactly
   the desired signal.**

**TESTS — `StudioBottomPanel.test.tsx`. THE GUARD INVERTS, and there is a trap in doing it.**

Today's `:9` asserts `expect(panel.textContent).toContain('bottomStub.jobs')` — **it currently guards the
bug.** And `:12`'s `not.toContain(...)` **WILL RED** after this refactor, because **hidden elements still
contribute to `textContent`**. 🔴 **DELETE both assertions. Do NOT "fix" the component to satisfy them.**

| Test name | Asserts |
|---|---|
| `test_every_bottom_tab_has_a_label_key_and_a_body_component` | `it.each(TABS)`: `screen.getByText('bottom.<id>')` exists **and** `screen.getByTestId('bottom-body-<id>')` **is in the document — even when inactive**. *(i18n is mocked to return the KEY — `vitest.setup.ts:24-40`.)* |
| `test_switching_tabs_hides_but_does_not_unmount` | Default ⇒ `bottom-body-issues` **`toBeVisible()`**, `bottom-body-jobs` **`not.toBeVisible()`**. Click `bottom.jobs` ⇒ they swap, **and `bottom-body-issues` is STILL `toBeInTheDocument()`** — hidden, not destroyed. |
| `test_the_bodies_mount_exactly_once_across_three_tab_switches` | 🔴 A mount-counter body (increments a ref in `useEffect(…, [])`) ⇒ **1**, not 3. *(The always-mounted invariant, asserted by EFFECT.)* |
| `test_no_tab_renders_the_word_once_wired` | `expect(panel.textContent).not.toMatch(/once wired|soon/i)` — the copy-honesty guard. |
| `test_the_en_locale_has_no_bottomStub_key` | `import en from '@/i18n/locales/en/studio.json'` ⇒ `expect('bottomStub' in en).toBe(false)`. *(Anti-rot: stops the copy silently regressing while M3 sits deferred.)* |
| `test_the_grip_resizes` | `pointerDown(grip,{clientY:500})` → `pointerMove(window,{clientY:400})` → `pointerUp` ⇒ `onHeightChange(268)`. Plus: `ArrowUp` on the focused separator ⇒ `onHeightChange(height + 16)`. |
| `test_fires_onClose_from_the_collapse_control` | unchanged. |

**`useStudioChrome.test.ts`:** `setBottomHeight(9999)` persists the **60vh** clamp; `setBottomHeight(10)`
persists **120**; a corrupt/absent stored `bottomHeight` loads **168**.

**🔴 `StudioFrame.test.tsx` (the Part-2 regression gate — WITHOUT IT A FUTURE `&&` CREEPS BACK IN SILENTLY):**
`test_collapsing_and_reopening_the_bottom_panel_opens_the_jobs_stream_exactly_ONCE` — spy `global.fetch` (or
mock `jobsApi.streamUrl`), toggle the bottom panel closed → open, assert the stream fetch was called **exactly
1** time.

**DoD evidence:** `cd frontend && npx vitest run src/features/studio/components/__tests__ src/features/studio/hooks/__tests__ src/i18n/__tests__` → green;
`git diff --stat frontend/src/i18n/locales` shows **18** locale files touched;
`grep -rl bottomStub frontend/src/` → **empty**.

---

### ── W7-S5 · The Issues tab — the feed, the routing table, the warnings strip

**dependsOn:** `W7-S2`, `W7-S4`. **Kind:** FS. **This is the wave's centre of gravity.**

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/studio/components/bottom/api.ts` | **CREATE** — `diagnosticsApi.get(bookId, {severity, kind, limit}, token)` over `apiJson` |
| `frontend/src/features/studio/components/bottom/types.ts` | **CREATE** — `Diagnostic`, `DiagnosticsResponse`, `RefKind` |
| `frontend/src/features/studio/components/bottom/useDiagnostics.ts` | **CREATE** — the controller (hook) |
| 🔴 `frontend/src/features/studio/host/issueRouting.ts` | **CREATE** — ⚖ ADJ: the row→panel router. **A PURE MODULE in `host/`, not a hook in `bottom/`.** See below. |
| `frontend/src/features/studio/components/bottom/IssuesTab.tsx` | **EDIT** — the real body |
| `frontend/src/features/studio/components/bottom/IssueRow.tsx` | **CREATE** — one row (view) |
| `frontend/src/features/studio/components/bottom/IssuesWarningsStrip.tsx` | **CREATE** — the amber strip (view) |
| `frontend/src/features/studio/host/__tests__/issueRouting.test.ts` | **CREATE** |
| `frontend/src/features/studio/components/bottom/__tests__/IssuesTab.test.tsx` | **CREATE** |

**MVC split (CLAUDE.md):** `useDiagnostics` owns state; `issueRouting.ts` is a **pure resolver** (no React, no
hooks — the host is injected by the caller); `IssuesTab` / `IssueRow` / `IssuesWarningsStrip` **render only**.
≤~100 lines per component, ≤~200 per hook.

> ### 🔴 ⚖ ADJ — the router is `host/issueRouting.ts`, a **pure module**, and **M2 SHARES IT**. (`Q-37-M1-M2-DISJOINT-CLAIM`, `Q-37-LENS-EXPANDED-ROWS-INERT`)
>
> The first draft put it in `components/bottom/useIssueRouting.ts` **as a hook**, and claimed M2 touches
> disjoint files. **Both are wrong.** Spec 37:385 requires the **lens** to deep-link *"exactly like an Issues
> row (§4.1.1 routing) — **including the FE-1 inert rule**"*. Two surfaces + one table ⇒ **ONE module, or the
> table forks and M1b's flip lights up only half the app.**
>
> **Home:** `frontend/src/features/studio/host/issueRouting.ts` — mirroring the shipped
> `host/studioLinks.ts` **exactly** (pure, React-free, `{kind, effect: (host: StudioHost) => void}`, host
> injected, tested standalone in `host/__tests__/`). **There is no `studio/lib/` dir** — do not create one.
>
> ```ts
> export type IssueRefKind = 'chapter' | 'outline_node' | 'structure_node';   // IF-1. Do NOT add scene/canon_rule.
>
> export type IssueRoute =
>   | { kind: 'inert'; reason: 'no-owner' | 'param-blind'; panelId?: string }
>   | { kind: 'open'; panelId: string; params: Record<string, unknown>;
>       effect: (host: StudioHost) => void };
>
> /** FE-1 (§4.1.1): panels that do NOT yet read their focus param. THE SINGLE KILL-SWITCH — W7-S9 empties
>  *  this set and EVERY row in BOTH surfaces lights up at once. NEVER inline this test anywhere else. */
> export const PARAM_BLIND_PANELS: ReadonlySet<string> = new Set(['plan-hub', 'chapter-browser']);
>
> export function routeDiagnostic(item: Diagnostic, bookId: string): IssueRoute;
> export function routeReference(source: ReferenceSource, ref: RefTarget, bookId: string): IssueRoute;
> ```
> Both public fns normalize to one internal target and delegate to ONE private
> `route(panelId, params, effect)` applying, in order: (1) `panelId == null` ⇒ `{inert, reason:'no-owner'}`;
> (2) `PARAM_BLIND_PANELS.has(panelId)` ⇒ `{inert, reason:'param-blind', panelId}`; (3) otherwise
> `{kind:'open', …, effect}`. **The `canon_contradiction` row's `publish` + `openPanel` pair lives INSIDE that
> effect closure** — `StudioHost` exposes **both** (`StudioHostProvider.tsx:43,52`), so one closure covers
> every row in §4.1.1.
>
> 🔴 **THE TARGET PANEL COMES OFF THE ROW, NOT OFF A SECOND FE MAP.** BE-1a emits `panel_id` per item
> (`KIND_PANEL`, W7-S1). `issueRouting.ts` reads `item.panel_id`; it does **NOT** re-declare a kind→panel
> table (`css-var-duplicated-across-two-consumers-drifts`). The FE owns only (a) the **params builder** per
> `ref_kind` and (b) the **inert predicate**.
>
> 🔴 **CONSUMER RULE (a DoD grep):** neither `IssuesTab.tsx` nor `EntityReferencesLens.tsx` may contain a
> **literal panel id string**.
> `grep -nE "openPanel\(['\"](quality-canon|quality-promises|plan-hub|chapter-browser|editor|job-detail)" frontend/src/features/studio/components/bottom/ frontend/src/features/studio/panels/EntityReferencesLens.tsx`
> **must return ZERO hits.**

**`types.ts` — the payload contract, mirroring BE-1 exactly:**

```ts
export type RefKind = 'chapter' | 'outline_node' | 'structure_node';
export type Severity = 'error' | 'warn' | 'info';
export type DiagnosticKind =
  | 'canon_contradiction' | 'broken_canon_rule' | 'prose_deleted_spec_node'
  | 'conformance_never_run' | 'conformance_dirty' | 'index_stale'
  | 'unplanned_chapter' | 'open_thread_debt';

export interface NodeRef { kind: string; id: string; title?: string | null; ref_kind: RefKind }
export interface Diagnostic {
  kind: DiagnosticKind; severity: Severity; title: string;
  detail?: string; at?: string; node_ref?: NodeRef;
  chapter_id?: string; rule_id?: string;   // OMITTED when absent — NEVER null. Absence is the signal.
  source: string;                          // one of the 6 DIAGNOSTIC_SOURCES
  panel_id: string | null;                 // ⚖ ADJ — the owning panel. null ⇒ INERT (no-owner).
}
export interface DiagnosticsResponse {
  book_id: string; items: Diagnostic[];
  counts: Partial<Record<DiagnosticKind, number>>;        // KIND-keyed, SPARSE, EXACT
  severity_counts: Record<Severity, number>;              // ⚖ ADJ — what the chips render
  total: number;                                          // EXACT, book-wide
  matched: number;                                        // ⚖ ADJ — selected by the filter, pre-cap
  refs_capped: boolean;
  has_work: boolean;                                      // ⚖ ADJ — false ⇒ the No-Work BANNER
  sources: string[];                                      // ⚖ ADJ — the 6. Copy renders {{count}} from THIS.
  computed_at: string;                                    // ⚖ ADJ — SERVER stamp
  warnings?: string[];        // 🔴 OMITTED when clean — NOT []. `data.warnings.length` CRASHES on a clean book.
  degraded_sources?: string[];// 🔴 The ONLY honest "N sources failed" count. NEVER derive it from warnings.length.
}
```

> 🔴 **`warnings.length` IS NOT "N SOURCES COULD NOT BE READ".** (⚖ ADJ `Q-37-WARNINGS-STRIP-MANDATORY` C /
> `Q-37-SOURCE-COUNT-INCONSISTENT` §3.) `warnings[]` also carries **non-failures** — the OUT-5 truncation
> notice (*"showing 25 of 38 broken canon rules"*, `server.py:4053`). Deriving N from it **re-commits the
> exact dishonesty the strip exists to kill.** Use `degraded_sources.length`. Use `sources.length` for the
> denominator. **No literal `6` or `7` anywhere in the copy.**

**`useDiagnostics.ts` — the controller.**

> 🔴 **It MUST own its data through React-Query.** The Lane-B handler (S6) reaches it via
> `invalidateQueries`, and `invalidateQueries` **cannot reach hand-rolled state**
> (`invalidatequeries-cannot-reach-hand-rolled-state`). This is a design constraint, not a preference.

```ts
export function useDiagnostics(bookId: string) {
  const { accessToken } = useAuth();
  const [severity, setSeverity] = useState<Severity | null>(null);
  const [kind, setKind] = useState<DiagnosticKind | null>(null);   // EPHEMERAL UI state. NOT a setting.

  const q = useQuery({
    // ⚖ ADJ (Q-37-OQ3): the key carries NO chapter id, and this hook NEVER reads activeChapterId.
    // The feed is BOOK-WIDE. A regression test asserts exactly this.
    queryKey: ['composition', 'diagnostics', bookId, severity, kind],
    queryFn: () => diagnosticsApi.get(bookId, { severity, kind, limit: 25 }, accessToken!),
    enabled: !!accessToken && !!bookId,
    staleTime: 60_000,          // §4.1.4 — PULL, not push. No polling. No SSE. No websocket.
    refetchInterval: false,
    refetchOnWindowFocus: false, // 🔴 ⚖ ADJ — MUST be explicit. App.tsx:11 sets the GLOBAL default to TRUE,
                                 //    so an inheriting Issues tab re-fans-out to book-service on EVERY
                                 //    alt-tab return — a 4th refresh trigger the spec never sanctioned.
  });

  const data = q.data;
  const warnings = data?.warnings ?? [];          // 🔴 the key is OMITTED when clean — `?? []` is mandatory
  const degradedSources = data?.degraded_sources ?? [];
  return {
    loading: q.isLoading,
    error: q.isError ? (q.error as Error) : null,
    items: data?.items ?? [],
    counts: data?.counts ?? {},
    severityCounts: data?.severity_counts ?? { error: 0, warn: 0, info: 0 },  // ⚖ chips read THIS
    total: data?.total ?? 0,
    matched: data?.matched ?? 0,
    refsCapped: data?.refs_capped ?? false,
    hasWork: data?.has_work ?? true,               // ⚖ ADJ — false ⇒ the No-Work BANNER above the rows
    sourceCount: data?.sources?.length ?? 0,       // ⚖ ADJ — the copy's {{count}}. NEVER a literal.
    computedAt: data?.computed_at ?? null,         // 🔴 the SERVER's stamp — NOT q.dataUpdatedAt
    warnings,
    degradedCount: degradedSources.length,         // 🔴 NEVER warnings.length
    degraded: warnings.length > 0,                 // §4.1.3 — load-bearing
    // 🔴 EMPTY IS ONLY "CLEAN" WHEN NOTHING DEGRADED. Never conflate them.
    emptyClean:    !q.isLoading && !q.isError && (data?.total ?? 0) === 0 && warnings.length === 0,
    emptyDegraded: !q.isLoading && !q.isError && (data?.total ?? 0) === 0 && warnings.length > 0,
    severity, setSeverity, kind, setKind,
    refresh: q.refetch,
  };
}
```

**The THREE — and only three — sanctioned refresh triggers** (⚖ ADJ `Q-37-FRESHNESS-PULL-ONLY` §3):
(a) the query going active (the tab opening) · (b) the **Refresh** button (`refetch()`) · (c)
`diagnosticsEffects.ts`'s `invalidateQueries` (W7-S6). **Nothing else.** A vitest asserts the `useQuery`
options object carries `staleTime: 60_000`, `refetchInterval: false`, `refetchOnWindowFocus: false` — *a
checklist item is DONE only when a test asserts its effect.*

**`host/issueRouting.ts` — THE ROUTING TABLE. This is the whole point of the feed.**

**FE-1 IS OPEN AT HEAD (re-verified at HEAD: `grep -rn "focusNodeId\|focusArcId" frontend/src` → ZERO hits).**
`PlanHubPanel.tsx:39` and `ChapterBrowserPanel.tsx:23` call `useStudioPanel(id, props.api)` and **never read
`props.params`**. (⚠ `useStudioPanel(panelId, api, extras?) -> string` returns the **localized label** — it
does NOT "expose params". Params arrive **only** as the dockview prop `props.params`. Do not re-introduce
the opposite claim.) So `openPanel('plan-hub', {params:{focusNodeId}})` **mounts the Hub and focuses
NOTHING** — `silent-success-is-a-bug`.

### 🔴 ⚖ ADJ — **IT IS 5 INERT KINDS AND 3 CLICKABLE. NOT "the 3 FE-1 rows".** (`Q-37-IF4-INERT-ROW-RULE`)

Spec 37 §4.1.1's routing table has **7 rows** because `conformance_never_run` and `conformance_dirty` are
**TWO distinct kinds collapsed into ONE table row**. `SEVERITY` has **8 kinds**. **A builder implementing
per-`kind` from a 7-row table leaves the 4th kind CLICKABLE, opening `plan-hub` onto nothing** — the exact
`silent-success-is-a-bug` class IF-4 exists to kill, **smuggled in through the test that was supposed to
guard it.**

**True M1 tally: 3 CLICKABLE · 5 INERT.**

| kind | severity | `panel_id` (from the row) | M1 state | Effect when clickable |
|---|---|---|---|---|
| `broken_canon_rule` | error | `quality-canon` | ✅ **CLICKABLE** | `openPanel('quality-canon', { focus: true, params: { bookId, focusRuleId: d.rule_id, focusChapterId: d.chapter_id ?? null } })` — **the PH18 seam, already shipped: `PlanHubPanel.tsx:72-76` emits it and `useQualityCanon.ts:74,107` hoists on it. REUSE IT. DO NOT REBUILD IT.** |
| `canon_contradiction` | error | `quality-canon` | ✅ **CLICKABLE** | 🔴 **TWO calls, in this order** — see the publish rule below. |
| `open_thread_debt` | info | `quality-promises` | ✅ **CLICKABLE** | `openPanel('quality-promises', { focus: true, params: { bookId } })` — `QualityPromisesPanel.tsx:23` reads `props.params`. It is a rollup, so it passes no focus id. |
| `prose_deleted_spec_node` | error | `plan-hub` | ⛔ **INERT** (case 2) | Would be `openPanel('plan-hub', { params: { bookId, focusNodeId: d.node_ref.id } })`. |
| `conformance_never_run` | warn | `plan-hub` | ⛔ **INERT** (case 2) | Would be `openPanel('plan-hub', { params: { bookId, focusNodeId: d.node_ref.id } })`. ⚠ The **Run button on this row is NOT a deep-link and is NOT inert** — see S7. **An inert ROW with a live BUTTON is the honest shape.** |
| `conformance_dirty` | warn | `plan-hub` | ⛔ **INERT** (case 2) | 🔴 **THE 4th KIND. The one a 7-row table drops.** Same as above. |
| `unplanned_chapter` | warn | `chapter-browser` | ⛔ **INERT** (case 2) | Would be `openPanel('chapter-browser', { params: { bookId, focusChapterId: d.node_ref.id } })`. |
| `index_stale` | warn | **`null`** | ⛔ **INERT FOREVER** (case 1) | **No panel owns the fix; the sweeper heals it.** |

**IF-4 (a recorded DECISION — do not "fix" it back):** a row is **inert** when **either** (1) **no panel owns
the fix** (`panel_id === null`), **or** (2) its target panel is **param-blind**. *"The panel exists" is NOT
the test — "the panel will actually focus what I clicked" is.*

🔴 **The two inert cases get DIFFERENT copy — they are not the same promise to the user:**
- case 1 (`no-owner`): *"the sweeper heals this automatically — nothing to open"*
- case 2 (`param-blind`): *"the Plan Hub can't focus this yet"*
**Do NOT give an unfixable row a "coming soon" title.**

**Make it DATA-DRIVEN so M1b's flip is one line and the test cannot drift:**
`isClickable(item) = item.panel_id !== null && !PARAM_BLIND_PANELS.has(item.panel_id)`.
`IssueRow` emits a chevron + `onClick` **iff** `isClickable`; otherwise **no chevron, no handler**, and a
`title` from `inertReason(item)`. **W7-S9 deletes the two entries from `PARAM_BLIND_PANELS` and all 4 rows
light up with ZERO edits to the row renderer — on BOTH surfaces.**

### 🔴 ⚖ ADJ — `canon_contradiction` **PUBLISHES to the bus, then opens.** (`Q-37-BUS-PUBLISH-SIDE-EFFECT`, `Q-37-IF3-SCENE-INSPECTOR-BUS-NOT-PARAMS`)

The first draft's table had **only** the `openPanel`. The publish is **intended and load-bearing**:

```ts
// INSIDE the route's effect closure. Order matters: publish moves the CONTEXT, openPanel moves the FOCUS.
if (row.chapter_id) {                                  // 🔴 THE GUARD IS MANDATORY — see below
  host.publish({ type: 'scene', sceneId: row.node_ref!.id, chapterId: row.chapter_id });
}
host.openPanel('quality-canon', { focus: true, params: { bookId, focusChapterId: row.chapter_id } });
```
- **Why publish:** a `scene` event sets **both** `activeSceneId` **and** `activeChapterId` (`host/types.ts:97-98`),
  which retargets the **editor** (`ManuscriptUnitProvider.tsx:321-326`), the **SceneRail** (`:197-200`) and the
  **scene-inspector** (`useSceneInspector.ts:49-53`). That is *exactly* what the user wants when they click
  *"this scene contradicts canon"*: the canon panel comes forward **and the editor behind it is already sitting
  on the offending scene, ready to fix.** It is **dirty-SAFE** — `openUnit` **flushes (saves) before
  switching** (`ManuscriptUnitProvider.tsx:184-190`), so no unsaved work is ever lost. And it is the
  **established precedent**: all three existing scene publishers (`StudioFrame.tsx:115`, `:125`,
  `SceneBrowserPanel.tsx:229`) do this same whole-studio retarget.
- 🔴 **DO NOT call `host.focusManuscriptUnit()` here** (unlike `StudioFrame.tsx:115/125`). It calls
  `openPanel('editor')`, which would **steal dock focus back from quality-canon**. Use the **bare**
  `host.publish(...)`.
- 🔴 **THE `if (row.chapter_id)` GUARD IS MANDATORY.** `host/types.ts:97` reduces `case 'scene'` as
  `activeChapterId: e.chapterId` **UNCONDITIONALLY** — publishing `chapterId: ''` **silently clobbers the
  editor's active chapter.** `SceneBrowserPanel.tsx:229` has that latent hole (`r.chapterId ?? ''`) —
  **DO NOT COPY IT.** A row with no `chapter_id` publishes **nothing** and still opens the panel.
- ✅ Safe by construction: `canon_issues` hard-filters `n2.kind = 'scene'` (`outline.py:1229`) **and**
  `migrate.py:212`'s `CHECK (kind NOT IN ('chapter','scene') OR chapter_id IS NOT NULL)` guarantees
  `chapter_id` on every canon row. `prose_deleted_spec_node` is **NOT** safe to publish (its node_ref may be a
  chapter-kind outline node) — it keeps plan-hub-only routing.
- **No `scene-inspector` code changes in M1 at all.** The routing table sends this row to **`quality-canon`**;
  the publish exists so an **already-open** scene-inspector re-targets. `scene-inspector` selects from the
  **BUS by design** (`useSceneInspector.ts:1-2`, SC10) — **do NOT make it param-aware**; that would give one
  concept two selection sources.

### 🔴 ⚖ ADJ — `index_stale` is a FIRST-CLASS ROW. Do not drop it, do not downgrade it. (`Q-37-OQ4-INDEX-STALE-IN-FEED`)

It renders with the **`warn`** chip (severity comes **from the payload** — the FE never recomputes it), title
and detail **from the BE strings** (the detail already reads *"the sweeper heals these; re-indexing refreshes
the canon windows"*). **No chevron, not clickable, no `node_ref`, no target.** An **absent entry in the router
is what makes it inert** — do **not** give it a fallback target.
🔴 **The FE must NOT filter ANY kind out of the payload.** A client-side suppression filter for a kind the BE
deliberately ships recreates the *"two truths for what is wrong with this book"* divergence
(`agent_native.py:47-52`) — agent says 3, human says 2. **Unlike the 4 param-blind rows, `index_stale` is inert
FOREVER**: do **not** add it to W7-S9's light-up list, and do **not** invent a "re-index" button for it
(that would be a new paid/queued action with no spec and no cost gate).

> 🔴 **Route on `ref_kind`, NEVER on `node_ref.kind`.** `node_ref.kind` is a **display label**
> (`"scene"`/`"chapter"`/`"arc"`); two rows carry `kind:"chapter"` over **disjoint id spaces** (IF-1).
> Add a defensive assertion in `issueRouting.ts`: if a `conformance_*` row's `ref_kind !== 'structure_node'`,
> or an `unplanned_chapter` row's `ref_kind !== 'chapter'`, treat the row as **inert** and log — a payload
> that lost `ref_kind` must degrade to **honest**, never to a **wrong target**. **An FE that switches on
> `kind` is a review finding.**

**`IssuesTab.tsx` — every state RENDERED (the mock IS the acceptance criterion; none may be hand-waved):**

| State | Render | Test |
|---|---|---|
| **Loading** | 4 skeleton rows (`data-testid="issues-skeleton"`). **Never a spinner in a void** — the tab is 168px by default. | ✔ |
| **Empty (genuinely clean)** | `issues.emptyClean` = *"No issues found across {{count}} sources."* with **`count = data.sources.length`** (renders **6**) **plus the source list rendered from `data.sources`**. 🔴 **NO literal number in the copy.** | ✔ |
| **Empty (DEGRADED)** | 🔴 **NEVER the clean state.** `issues.emptyDegraded` = *"No issues found in the sources that answered — **{{count}} of {{total}} sources could not be read.**"* with `count = degraded_sources.length` (🔴 **NOT `warnings.length`**) and `total = sources.length`. `data-testid="issues-empty-degraded"`. **`emptyClean` is UNREACHABLE whenever `warnings` is non-empty — assert that, don't just intend it.** | 🔴 **DoD-3** |
| **Error (4xx/5xx)** | ONE inline row with the status + a **Retry**. The tab never blanks. | ✔ |
| **No Work** (`has_work === false`) | 🔴 The route still **200**s (the spec tree is book-keyed). Render the **No-Work BANNER** (`issues.noWork`) **ABOVE the normal body** — rows render as normal. **It is a BANNER, not an empty state.** 🔴 **Branch on the `has_work` BOOLEAN — never substring-match the English warning** (i18n-fragile, and it is a closed-set state, not prose). | ✔ |
| **Capped** | Footer: **`Showing {items.length} of {matched} · {total} findings in this book · computed {relative(computed_at)}`**. ⚖ ADJ: the `matched` middle number is what stops a filtered view reading as *"my errors went away"*; `refs_capped` means *"there are more MATCHING rows than shown"*. **`computed_at` is the SERVER's stamp.** | ✔ |

**Toolbar row 1** (from the mock): severity chips `All <total> · Error N · Warn N · Info N` — 🔴 **the chip
numbers come from `data.severity_counts`, NEVER from `counts` (which is KIND-keyed — `counts["error"]` is
`undefined`) and NEVER from `items.length`.** Chips **stay lit and keep their real numbers while a filter is
active**; the active chip gets `aria-pressed`, **not a zeroed label**. Plus a `kind` `<select>` of the 8 kinds
and a **Refresh** button. **Toolbar row 2 (conditional):** the warnings strip.

**`IssuesWarningsStrip.tsx` — NOT optional chrome.** `agent_native.py`'s entire design is **absent ≠ zero**.
If the FE renders a degraded response as *"No issues found"*, it converts the engine's careful honesty into
the exact lie the engine was written to prevent — **on the one screen the user trusts to tell them their book
is fine.** Contract: `warnings.length > 0` ⇒ an amber strip renders **ABOVE the rows, in BOTH the empty AND
the populated state**. `data-testid="issues-warnings-strip"`, `role="status"`, amber
(`border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400`), an i18n heading + a `<ul>` with
**one `<li>` per warning rendering the BE string VERBATIM** — **no truncation, no re-wording, no i18n of the
body. The string IS the message.**

**TESTS**

`host/__tests__/issueRouting.test.ts` (mirror `host/__tests__/studioLinks.test.ts`):

| Test name | Asserts |
|---|---|
| `test_broken_canon_rule_opens_quality_canon_with_the_rule_id` | `openPanel` spy called with `('quality-canon', {focus:true, params:{bookId, focusRuleId:'r1', focusChapterId:'c1'}})`. |
| `test_canon_contradiction_PUBLISHES_then_opens` | 🔴 `publish` called with **exactly one** `{type:'scene', sceneId, chapterId}` **BEFORE** `openPanel`; **`focusManuscriptUnit` / `openPanel('editor')` NOT called** (quality-canon stays the active dock panel). |
| `test_a_canon_row_with_no_chapter_id_publishes_NOTHING` | 🔴 `publish` **not called**; `openPanel('quality-canon')` **still called**. *(The activeChapterId-clobber guard.)* |
| `test_open_thread_debt_opens_quality_promises` | ✔ |
| `test_ALL_FIVE_inert_kinds_are_inert_and_carry_a_reason` | 🔴 **THE GUARD.** Table-driven over **all 8 kinds**: `prose_deleted_spec_node`, `conformance_never_run`, **`conformance_dirty`**, `unplanned_chapter` ⇒ `{kind:'inert', reason:'param-blind'}`; `index_stale` ⇒ `{kind:'inert', reason:'no-owner'}`. Each `reason` maps to **non-empty, DISTINCT** copy. |
| `test_the_arithmetic_guard` | 🔴 `expect(ALL_8_KINDS.filter(isClickable)).toHaveLength(3)` **and** `expect(inert).toHaveLength(5)`, with a comment naming the 4 param-blind kinds. *(This test passes unchanged through W7-S9's flip **only if the counts are updated deliberately** — 3→7 clickable, 5→1 inert. So M1b cannot silently leave a row dark, and M1 cannot silently let one through.)* |
| `test_a_row_with_a_wrong_ref_kind_degrades_to_inert` | An `unplanned_chapter` with `ref_kind:'outline_node'` ⇒ **inert**, `openPanel` **never called**. *(The IF-1 defence.)* |
| `test_a_prose_deleted_outline_node_id_is_NEVER_emitted_as_focusChapterId` | 🔴 IF-1, asserted at the router. |
| `test_no_consumer_holds_a_literal_panel_id` | The DoD grep, as a test: read `IssuesTab.tsx` + `EntityReferencesLens.tsx` source and assert **no `openPanel('<literal>')`**. |

`__tests__/IssuesTab.test.tsx`:

| Test name | Asserts |
|---|---|
| `test_warnings_and_no_items_never_renders_no_issues_found` | 🔴 **DoD-3.** Mock `{items: [], total: 0, warnings: ['a','b'], degraded_sources: ['coverage','prose_deleted'], sources: [...6]}` ⇒ the strip renders with **both strings verbatim**; `issues-empty-degraded` matches `/2 of 6 sources could not be read/`; `queryByText(/No issues found across 6 sources/)` is **null**. |
| `test_a_clean_book_has_NO_warnings_KEY_AT_ALL_and_does_not_crash` | 🔴 `{items: [], counts: {}, total: 0, refs_capped: false, sources:[...6]}` — **no `warnings` key on the object** (the real wire shape) ⇒ no strip, clean copy, **no crash**. *(`data.warnings.length` would throw.)* |
| `test_the_strip_precedes_the_rows_in_DOM_order` | `{items:[row], warnings:['showing 25 of 38 broken canon rules']}` ⇒ the strip renders **and precedes `issues-row-0`**. |
| `test_the_degraded_count_is_NOT_warnings_length` | 🔴 `{warnings: ['a','b','c'], degraded_sources: ['coverage']}` ⇒ the copy says **1**, not 3. *(A cap notice is not a failed source.)* |
| `test_chips_read_severity_counts_not_the_visible_rows` | Mock `{items: [1 row], severity_counts: {error:3, warn:5, info:14}, total: 38}` ⇒ the **Error** chip reads **3**, the **All** chip **38** — while only 1 row is on screen. |
| `test_a_filtered_view_keeps_the_other_chips_lit` | `counts={canon_contradiction:2}`, active filter `info`, `items=[]` ⇒ the **Error chip renders "2"**, not "0", and is **not hidden**. |
| `test_ALL_FIVE_inert_rows_render_with_no_chevron_and_are_not_clickable` | 🔴 `for (const kind of ALL_8_KINDS)`: `queryByTestId('issue-chevron')` is null **exactly when** `!isClickable(kind)`; `fireEvent.click(row)` ⇒ `openPanel` **not called**. |
| `test_index_stale_renders_and_is_NOT_suppressed` | 🔴 Feed a payload with one `index_stale` + one clickable kind ⇒ **BOTH rows render** (`count === 2` — no kind is filtered out); the `index_stale` row has **no chevron**, `onClick` does not fire; its detail contains *"the sweeper heals"*. |
| `test_has_work_false_renders_the_banner_AND_the_rows` | `has_work:false` ⇒ the no-work banner **plus** the book-keyed rows. |
| `test_the_query_key_carries_no_chapter_id` | 🔴 ⚖ ADJ (OQ-3). Assert the key is `['composition','diagnostics',bookId,severity,kind]`, **and** that switching the editor's open chapter (publish a `scene` bus event) changes **neither the row set nor the chip counts**. *(The guard against a later agent adding chapter-scoping back.)* |
| `test_the_query_opts_pin_the_three_triggers` | `staleTime === 60_000`, `refetchInterval === false`, `refetchOnWindowFocus === false`. |
| `test_the_footer_uses_the_SERVER_computed_at` | Mock `computed_at` 5 minutes old with `dataUpdatedAt` = now ⇒ the footer says **5 minutes**, not "just now". |
| `test_loading_renders_skeleton_rows_not_a_spinner` | ✔ |
| `test_route_error_renders_an_inline_retry_row_not_a_blank_tab` | ✔ |

**DoD evidence:** `cd frontend && npx vitest run src/features/studio/components/bottom src/features/studio/host` → all green, and the
live browser smoke (§10) clicks a real `broken_canon_rule` row and lands on a **hoisted rule**.

---

### ── W7-S6 · Lane-B effect handler — `diagnosticsEffects.ts`

**dependsOn:** `W7-S5`. **Kind:** FE. **MANDATORY for this batch (X-4).**

Today `useStudioEffectReconciler.ts` registers handlers for `book_*`, `composition_*(prose|draft)`,
`composition_(outline_node|scene_link)_`, glossary, knowledge, `translation_job_control`. **Nothing
invalidates the Issues feed.** So: the agent fixes a canon rule, and the human's problems panel keeps
showing the problem.

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/studio/agent/handlers/diagnosticsEffects.ts` | **CREATE** — plan 30 §8.0b: **`diagnosticsEffects.ts` is spec 37's file. ONE FILE PER DOMAIN.** |
| `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` | **EDIT** — one import + one call in the register-once effect; **delete the now-FALSE comment at `:7-9`** |
| `frontend/src/features/studio/agent/handlers/__tests__/diagnosticsEffects.test.ts` | **CREATE** |

**THE CHANGE.** Mirror `glossaryEffects.ts` exactly (exported pattern + exported handler + a module-level
idempotency guard + a `_reset*` test hook).

### 🔴 ⚖ ADJ — THE FIRST DRAFT'S REGEX IS WRONG IN **THREE** WAYS. Use this one. (`Q-37-LANEB-REGEX-COVERAGE`, `Q-37-LANEB-HANDLER`, `Q-37-PAID-ACTION-IN-FLIGHT`)

```ts
// 37 §7.1 (X-4) — Lane-B effect handler for the Issues feed + the find-references lens.
//
// ⚠ RegExp, NOT a string. `registerEffectHandler`'s string branch is `tool === p || tool.startsWith(p)` —
// NOT a pattern match — so a string with alternation matches NOTHING and ships a silent no-op handler that
// no unit test (which registers and calls its own fake) could ever catch. Plan 30 §8.0b.
//
// DERIVED FROM THE EMITTED TOOL NAMES, not asserted. Every branch stales at least one of the 8 SEVERITY
// kinds (agent_native.py:60-72) or one of the 8 REFERENCE_SOURCES (agent_native.py:53).
//   book-service  mcp_server.go / mcp_actions.go  → book_chapter_* , book_index_chapter
//   composition   mcp/server.py                   → composition_*
const DIAGNOSTICS_STALING =
  /^(book_(chapter_|index_chapter)|composition_(canon_rule_|outline_node_|scene_link_|write_prose|publish|generate|arc_(create|update|delete|move|apply|assign_chapters|restore)|motif_(bind|unbind|adopt|archive|mine|link_create|link_delete)|authoring_run_(start|resume|close|gate|accept_unit|reject_unit|revert_all)))/;

export function diagnosticsEffect(ctx: EffectContext): void {
  const { bookId, queryClient } = ctx;
  queryClient.invalidateQueries({ queryKey: ['composition', 'diagnostics', bookId] });
  queryClient.invalidateQueries({ queryKey: ['composition', 'entity-references', bookId] });
}

let registered = false;
export function registerDiagnosticsEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(DIAGNOSTICS_STALING, diagnosticsEffect);
  // ⚖ ADJ (Q-37-PAID-ACTION-IN-FLIGHT §4) — the ONLY place an agent-driven RUN COMPLETION ever surfaces
  // as a chat tool_call. `composition_conformance_run` is a PROPOSE (it mints a token and writes NOTHING),
  // so matching it above would fire a refresh BEFORE any work happened AND still miss the completion.
  registerEffectHandler('composition_get_mine_job', (ctx) => {
    if ((ctx.result as any)?.status === 'completed') diagnosticsEffect(ctx);
  });
}
export function _resetDiagnosticsEffectHandlers(): void { registered = false; }
```

**WHY IT CHANGED — three independent defects in the drafted pattern:**

1. 🔴 **`arc_` is a BARE PREFIX and matches five READ tools** that exist today: `composition_arc_list`,
   `_get`, `_suggest`, `_template_drift`, `_import_analyze`. **Every agent read of the arc roster would
   invalidate diagnostics → refetch → invalidate.** Use the **write-verb allowlist** above. Allowlist (not
   negative-lookahead) is deliberate: a read tool added later then **fails CLOSED** (a stale panel = the
   status quo) rather than joining a refetch storm.
2. 🔴 **`conformance_run` is DROPPED.** It is a **PROPOSE**, not a write (`server.py:3121` mints a confirm
   token; `actions.py:714` is what enqueues). Matching it invalidates **before any work happened**. Completion
   arrives via the **separate `composition_get_mine_job` handler** above (agent path) and via **polling**
   (human path — see W7-S7). ⚠ Do **not** add `conformance_status` to the pattern either — it is a read.
3. 🔴 **FOUR WHOLE WRITER FAMILIES WERE MISSING** — a `^composition_`-only regex can never see them:
   - **`book_chapter_*` + `book_index_chapter`** — `unplanned_chapter` is a **set-difference over the BOOK
     chapter spine** (`compute_coverage`) and `prose_deleted_spec_node` is its inverse. Both move on chapter
     create/bulk_create/delete/purge/restore_revision; `index_stale` moves on save_draft/publish/index_chapter.
   - **`composition_write_prose|publish|generate` + `authoring_run_*`** — `DIRTY_REASONS` includes
     `prose_drift` (`arc_conformance_orchestrate.py:304`): **prose writes dirty every arc.** These are also
     the **ONLY** writers of `narrative_thread` (there is **no `composition_thread_*` MCP tool**), so
     `open_thread_debt` + the `narrative_thread` lens source stale **here or nowhere**. They also produce
     `canon_contradiction` (the critic lane).
   - **`composition_scene_link_*`** — scenes **ARE** `outline_node` rows; scene links move the chapter↔spec
     linkage coverage/prose-deleted read.
   - **motif `adopt|archive|mine|link_create|link_delete`** — `motif_application` (a lens source) is
     FK-SET-NULLed by **archive** (`motif_repo.py:444`) and written by adopt/mine, **not only by bind/unbind**.

**`outline_node_` DOUBLE-MATCHING IS CORRECT — do not "fix" it.** `bookEffects.ts:62` already registers
`/^composition_(outline_node|scene_link)_/` → `outlineEffect`. `effectRegistry.ts:46-51` runs **ALL** matching
handlers and the reconciler dedupes **per tool-CALL, not per handler**. An outline write correctly runs both.

🔴 **DELETE the FALSE comment at `useStudioEffectReconciler.ts:7-9.`** It asserts *"authoring_run has no MCP
tools at all, REST-only, no Studio consumer to go stale"* — **provably false** (`server.py:1616`
`composition_authoring_run_create`, `:1723` `_start`). Replace it with a one-liner naming the five registered
handler families (book / glossary / knowledge / translation / diagnostics).

> ⚠ The query keys must be a **PREFIX** of `useDiagnostics`'s key
> (`['composition','diagnostics',bookId,severity,kind]`) — React-Query invalidates by prefix, so the
> filter-suffixed keys are reached. **Assert this in the test**, do not assume it.
>
> 🔴 **HARD CONSTRAINT (or this whole file is a silent no-op):** the Issues tab and the lens **must** hold
> their data in **React-Query** — `invalidateQueries` **cannot reach hand-rolled `useState` loader state**
> (`invalidatequeries-cannot-reach-hand-rolled-state`). `EffectContext` (`effectRegistry.ts:9-24`) exposes
> **only** `queryClient` as a generic refresh channel; its two other escape hatches (`reloadChapter` /
> `reloadScenes`) are hard-bound to the Tier-4 manuscript hoist and have **no bottom-panel analogue.**

**TESTS** — `__tests__/diagnosticsEffects.test.ts` (this dir holds only `resultEnvelope.test.ts` today — write
it fresh; `clearEffectHandlers()` + `_resetDiagnosticsEffectHandlers()` in `beforeEach`).
⚠ **Do NOT return a mock from `beforeEach`** — Vitest treats a returned fn as **teardown** and will call it
after the test (`vitest-beforeeach-returning-a-mock-is-treated-as-teardown`).

| Test name | Asserts |
|---|---|
| `test_the_pattern_is_a_regexp` | `DIAGNOSTICS_STALING instanceof RegExp`. *(The silent-no-op guard — a string with alternation matches nothing.)* |
| `test_it_matches_every_staling_writer` | 🔴 Table-driven, **all of**: `book_chapter_create/bulk_create/delete/purge/save_draft/publish/unpublish/update_meta/restore_revision`, `book_index_chapter`, `composition_canon_rule_create/update/delete`, `composition_outline_node_create/update/delete/move/restore`, `composition_scene_link_create/delete`, `composition_write_prose`, `composition_publish`, `composition_generate`, `composition_arc_create/update/delete/move/apply/assign_chapters/restore`, `composition_motif_bind/unbind/adopt/archive/mine/link_create/link_delete`, `composition_authoring_run_accept_unit/close/start/revert_all`. |
| `test_the_anti_thrash_guard` | 🔴 **THE POINT OF THE CORRECTED REGEX.** `composition_arc_list`, `composition_arc_get`, `composition_arc_suggest`, `composition_diagnostics`, `composition_find_references`, `composition_conformance_status`, `composition_get_prose`, `book_get_chapter`, `book_list_chapters` each invalidate **NOTHING**. *(The panel's OWN read tools matching would be a **self-invalidating refetch storm**.)* |
| `test_conformance_run_does_NOT_invalidate_but_get_mine_job_completed_DOES` | 🔴 `composition_conformance_run` ⇒ **no** invalidation. `composition_get_mine_job` with `result.status === 'completed'` ⇒ **both** keys invalidated. With `status: 'running'` ⇒ **nothing**. |
| `test_it_invalidates_the_diagnostics_key_including_a_filtered_variant` | Seed a real `QueryClient` with data at `['composition','diagnostics','b1','error',null]`, run the handler, assert that entry is **invalidated** (prefix match). |
| `test_it_refreshes_BY_EFFECT_not_by_spy` | 🔴 Render `<IssuesTab bookId="b1"/>` inside a **REAL `QueryClientProvider`** with a stubbed `diagnosticsApi.get`; await first render (fetched **once**); call `diagnosticsEffect({tool:'composition_canon_rule_update', bookId:'b1', queryClient, …})`; assert `get` was called a **SECOND** time **and the new row text appears in the DOM.** *(A spy on `invalidateQueries` passes even if the tab hand-rolls `useState`. Prove it by EFFECT.)* Repeat for `book_chapter_save_draft` to lock the widened pattern. |
| `test_registered_via_the_reconciler` | `matchEffectHandlers('composition_canon_rule_create')` returns a handler after `registerDiagnosticsEffectHandlers()`. |

**DoD evidence:** vitest green, **and** `grep -n "registerDiagnosticsEffectHandlers" frontend/src/features/studio/agent/useStudioEffectReconciler.ts` is non-empty (the wiring, proven — a handler file nobody registers is a silent no-op).

---

### ── W7-S7 · The Run-conformance button (cost-gated)

**dependsOn:** `W7-S5`, **`W7-S0`** (X-1). **Kind:** FS.
⚖ ADJ — **NOT conditional any more.** X-1 is `W7-S0`, a ~15-line slice in this wave. **Build both.**

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/studio/components/bottom/useRunConformance.ts` | **CREATE** |
| `frontend/src/features/studio/components/bottom/IssueRow.tsx` | **EDIT** — the Run affordance on `conformance_*` rows |
| `frontend/src/features/studio/components/bottom/__tests__/useRunConformance.test.ts` | **CREATE** |

**THE CHANGE — the flow, and the THREE traps in it.**

The propose→confirm spine is **generic and already shipped**:
`mcpExecute('composition_conformance_run', {args:{…}})` → returns `{confirm_token, estimate}` →
`POST /v1/composition/actions/confirm?token=<t>` (identity is the Bearer JWT; the token rides the QUERY) →
202 + `job_id` → poll `compositionApi.getJob(job_id)`. Descriptor `composition.conformance_run` is already
dispatched (`actions.py:75, 343 → _execute_conformance_run:714`), and `_execute_conformance_run` passes a
**real `project_id`** — so it is **NOT** affected by the 4th-live-404 bug.

> 🔴 **TRAP 1 — DO NOT reuse `motifApi.conformanceRunEstimate` / `.conformanceRunConfirm`
> (`features/composition/motif/api.ts:224,230`). They POST to `/actions/conformance_run/estimate` and
> `/actions/conformance_run/confirm`, which DO NOT EXIST and 404 in production today** (plan 30 §3.3).
> That is Wave 3's bug to fix. **Do not "align" with the broken one.**
>
> 🔴 **TRAP 2 — DO NOT reuse `motifApi.arcConformanceRunPropose` either.** It sends
> `arc_template_id` (`motif/api.ts:257`), and `_ConformanceRunArgs` is a **`ForbidExtra`** model whose
> arc-scope key is **`arc_id` — a `structure_node` id, NOT a template id** (`server.py:3105-3117`, and the
> comment there says so in as many words). Write a **fresh** propose in `useRunConformance.ts`.
>
> 🔴 **TRAP 3 — arc scope REQUIRES a BYOK `model_ref`** (the deep overlay tags prose with a classify model).
> ⇒ a `ModelPicker` ⇒ its empty state is `AddModelCta` ⇒ **X-1 is the hard prereq.** Never hardcode a model
> name (CLAUDE.md, ENFORCED): the `model_ref` is a `user_model_id` UUID the picker returns.

```ts
const res = await mcpExecute<{ confirm_token: string; estimate?: { estimated_usd?: number } }>(
  'composition_conformance_run',
  { args: {                              // FastMCP nests under `args` (a flat body fails validation)
      project_id: projectId,             // from useQualityWork(bookId) — the SAME work gate the siblings use
      scope: 'arc',
      arc_id: structureNodeId,           // ← node_ref.id where ref_kind === 'structure_node'
      model_ref: modelRef,               // BYOK user_model_id from the ModelPicker
      model_source: 'user_model',
  } },
  token,
);
// then: POST `${BASE}/actions/confirm?token=${res.confirm_token}` (JWT-authed) → 202 {job_id} → poll.
```

> 🔴 **TRAP 4 (⚖ ADJ `Q-37-COSTGATE-GENERIC-SPINE` §4) — the run MUST be `scope:'arc'`.**
> `engine/motif_conformance_run.py:74-79` raises a **terminal `ValueError` for `scope != 'arc'`** — so a
> chapter-scope run **through the correct spine still mints a token, runs the usage-billing precheck
> (`actions.py:721`), enqueues, and the job FAILS.** That is a **paid action that charges the user for
> nothing**. Chapter conformance is served by the **free synchronous GET**
> `/v1/composition/works/{pid}/conformance?scope=chapter&chapter_id=` (`motifApi.conformance`,
> `api.ts:204`) — if a chapter row ever needs a "refresh", **refetch that GET. It is not a paid action.**

### 🔴 ⚖ ADJ — **COMPLETION IS A POLL, NOT LANE-B.** The drafted claim ships a spinner that never resolves. (`Q-37-PAID-ACTION-IN-FLIGHT`)

The first draft said: *"On completion the Lane-B handler (S6) fires (`composition_conformance_run` matches
`DIAGNOSTICS_STALING`) → the query re-fetches."* **FALSE, and it is exactly the paid-action defect the PO
named as a CRITICAL blocker.** `useStudioEffectReconciler.ts:38-63` runs handlers **only for tool-call records
inside `useChatStream().messages`.** The human's Run click is
`mcpExecute(propose)` → `POST /v1/composition/actions/confirm` → **202** `{job_id}`. **None of that is a chat
tool_call. Lane-B can NEVER fire for it.** The user would sit on a spinner forever.

**BUILD THIS INSTEAD:**

1. **In-flight state is EPHEMERAL COMPONENT STATE** — never spliced into the React-Query data:
   `const [runs, setRuns] = useState<Map<string, {jobId: string; error?: string}>>()` keyed by the row's
   stable key. 🔴 **The diagnostics query object is READ-ONLY. Never `setQueryData` on it. NEVER optimistically
   mutate a diagnostics row — it is a *derived* read.**
2. **COMPLETION = POLL.** New `useConformanceRun.ts`: after `/actions/confirm` returns `job_id`, drive a
   React-Query query `['composition','job',jobId]` calling the **SHIPPED** `compositionApi.getJob(jobId, token)`
   (`composition/api.ts:420` → `GET /v1/composition/jobs/{job_id}`, VIEW-gated) with
   `enabled: !!jobId` and
   `refetchInterval: (q) => ['pending','running'].includes(q.state.data?.status) ? 2000 : false`.
   Mirror the shipped budget (`JOB_POLL_INTERVAL_MS = 2000`, `JOB_POLL_MAX = 300` ≈ 10 min,
   `composition/api.ts:47-51`). 🔴 **Do NOT hand-roll a `while` loop in the component** — it leaks past
   unmount; React-Query's `refetchInterval` stops on unmount. Precedent to copy:
   `motif/api.ts:274-296` already polls `getJob` **for this exact descriptor**.
3. **TERMINAL HANDLING — three branches, ALL MANDATORY:**
   - **`completed`** ⇒ `invalidateQueries({queryKey:['composition','diagnostics',bookId]})`, delete the `runs`
     entry, toast success. **The row DISAPPEARS because the source re-ranks.** That is correct and is the whole
     point of the derived-read rule.
   - **`failed`** ⇒ 🔴 **DO NOT clear silently and DO NOT let the row revert to its un-run state. THE USER
     PAID.** Pin the row's action area to an inline error (`job.result.error`) **+ a Retry**, until the user
     dismisses it. A silent revert here is `silent-success-is-a-bug` **on a spend path**.
   - **poll budget exhausted while still `running`** ⇒ keep *"running"* + the job id + a link
     `openPanel('job-detail', {params:{service:'composition', jobId}})`. 🔴 **NEVER claim done.**
4. **RELOAD (a default the PO may veto):** a full page reload loses `jobId` and the spinner. **ACCEPT that in
   M1** — the job still runs and the row re-ranks away on the next fetch. 🔴 **Do NOT persist `jobId` to
   localStorage** (it is per-book **server** state, not a per-device UI preference). Rehydrating the in-flight
   chip from the jobs list is an **M3** follow-up (it needs BE-1b/BE-1c's `book_id` stamp), not M1 work.

**TESTS:**

| Test name | Asserts |
|---|---|
| `test_propose_sends_arc_id_not_arc_template_id` | The `mcpExecute` spy's args contain `arc_id` and **do NOT** contain `arc_template_id`. *(TRAP 2, asserted.)* |
| `test_the_scope_is_always_arc` | 🔴 `args.scope === 'arc'`. *(TRAP 4 — a chapter-scope run is a paid job that terminally fails.)* |
| `test_confirm_hits_the_generic_actions_confirm_not_a_per_action_path` | The fetch spy's URL matches `/v1/composition/actions/confirm\?token=` and **NO** request URL ever matches `/conformance_run\/(estimate\|confirm)/`. *(TRAP 1 — the negative assertion is the mechanical guard that stops a future builder "aligning" with the broken helper.)* |
| `test_the_button_is_absent_when_the_user_has_no_chat_model` | The row renders the `AddModelCta` path (which, post-W7-S0, **opens the settings panel — it does not navigate**), not a Run that would 422. |
| `test_no_optimistic_row_removal` | 🔴 After confirm resolves, `queryClient.getQueryData(['composition','diagnostics',bookId])` is **BYTE-IDENTICAL** to the pre-click value, and the row is **still rendered**. *(Asserted, not assumed.)* |
| `test_the_poll_completing_invalidates_the_feed` | Poll returns `completed` ⇒ `invalidateQueries` called with the **diagnostics** key. |
| `test_a_FAILED_run_keeps_the_row_and_shows_the_error` | 🔴 Poll returns `failed` ⇒ the row is **still rendered** and shows `job.result.error` + Retry. *(The paid-for-nothing guard.)* |
| `test_an_exhausted_poll_budget_never_claims_done` | Still `running` at the budget ⇒ the chip says *running*, shows the job id, and offers the `job-detail` link. |

**DoD evidence:** vitest green + `grep -rn "conformance_run/estimate\|conformance_run/confirm\|arc_template_id" frontend/src/features/studio/` → **EMPTY**.

> **SPEC EDIT, same wave:** rewrite spec 37 §8.4's last bullet (the false Lane-B sentence) and §7.1's regex to
> match the above. **Leaving the false sentence on disk is how the next agent rebuilds the bug.**

---

### ── W7-S8 · M2 — the find-references LENS (a popover, **not a panel** — PO-1 verbatim)

**dependsOn:** `W7-S3`, **`W7-S5`** (⚖ ADJ — it **consumes `host/issueRouting.ts`**; it is **NOT** disjoint
from S5 and must **NOT** be built in parallel with it). **Kind:** FS.

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/studio/panels/EntityReferencesLens.tsx` | **CREATE** — the popover (view) |
| `frontend/src/features/studio/panels/useEntityReferences.ts` | **CREATE** — the controller |
| `frontend/src/features/studio/panels/entityReferencesApi.ts` | **CREATE** — `apiJson` over BE-1d |
| `frontend/src/features/studio/lens/referenceSources.ts` | **CREATE** — the 8-tuple + the label map (⚖ ADJ — **one source of ORDER**) |
| `frontend/src/features/studio/panels/EntityRefField.tsx` | **EDIT** — the lens affordance (studio-owned) |
| `frontend/src/features/plan-hub/components/NodeBadges.tsx` | **EDIT** — `CastBadge` (see the a11y ruling). ✅ ⚖ ADJ — **the Book-Package handoff HAS happened; this file is FREE. Edit it.** |
| `frontend/src/features/plan-hub/components/nodePresentation.ts` · `PlanCanvas.tsx` · `ChapterNode.tsx` · `SceneNode.tsx` · `ArcRollupNode.tsx` · `PlanHubPanel.tsx` | **EDIT** — thread the new `onOpenEntityLens` callback (additive + degrade-safe: **absent prop ⇒ the chip renders byte-identical to today**) |
| `frontend/src/features/plan-hub/components/__tests__/NodeBadges.test.tsx` | **EDIT** |
| `frontend/src/features/studio/panels/__tests__/EntityReferencesLens.test.tsx` | **CREATE** |

**THE CHANGE.** A ~320px popover over the badge. **Right-click AND a keyboard-accessible affordance** —
a right-click-only feature is an **a11y defect**. Close on `Escape` and on outside-click.

### 🔴 ⚖ ADJ — THE A11Y FIX IS **"make the chip itself the button"**, NOT "add a `⋯` glyph". (`Q-37-LENS-A11Y-AFFORDANCE`)

`NodeBadges.tsx`'s `case 'cast'` (`:88-121`) is a **bare, non-focusable `<span>`** — so right-click-only would
be **keyboard-unreachable**. But the same file **already has the right pattern**: `CanonBadge` (`:26-57`) is
`<button>` when its callback is wired and `<span>` when it is not. **Mirror it.**

- **SLICE A — plan-hub** (additive + degrade-safe):
  1. `nodePresentation.ts:45` — beside `onOpenRef`, add
     `onOpenEntityLens?: (entityId: string, nodeId: string) => void;` to `PlanNodeData`.
  2. `PlanCanvas.tsx:148, 201, 223` — accept it, spread it onto every node's `data`, **add it to the useMemo
     dep array**. Mirror `onOpenRef` at **all three** sites.
  3. Forward it in `ChapterNode.tsx:13/63`, `SceneNode.tsx:14/41`, `ArcRollupNode.tsx:15/69` → `<NodeBadges …>`.
  4. `NodeBadges.tsx` — extract `case 'cast'` into a **`CastBadge`** built like `CanonBadge`. When
     `onOpenEntityLens` is wired **AND `r.state !== 'unknown'`** (unknown = not-paged-in, nothing to look up):
     render a **`<button type="button">`** **keeping the existing `data-testid={`plan-badge-cast-${nodeId}-${entityId}`}`
     and `data-cast-state`** (tests depend on them), plus `aria-label={`Find references to ${label}`}`,
     `onClick={e => { e.stopPropagation(); onOpenEntityLens(b.entityId, nodeId); }}`,
     `onContextMenu={e => { e.preventDefault(); e.stopPropagation(); onOpenEntityLens(b.entityId, nodeId); }}`,
     `className={cn(cls, 'pointer-events-auto')}`.
     **`state === 'missing'` GETS the button too** — a broken ref is *exactly* what you want to find references
     for. **Not wired ⇒ today's exact `<span>`.** Enter/Space come free with `<button>` — **write no key handler.**
  5. `PlanHubPanel.tsx:228` and `:288` — pass `onOpenEntityLens={openEntityLens}` **right beside the existing
     `onOpenRef={openRef}`**.
  🔴 **NO `⋯` glyph on the plan-hub cast chip.** It is `max-w-[5rem] truncate` inside a dense ReactFlow node;
  a second glyph **doubles chip width and steals truncation budget from the entity name.** Right-click stays a
  power-user shortcut; **the button IS the accessible path.**
- **SLICE B — `EntityRefField.tsx`** (studio-owned): add `onOpenLens?: (entityId: string) => void` to
  `BaseProps` (`:12-17`). In **MultiRef** (`:55+`) the chip's label text becomes a `<button>` when `onOpenLens`
  is wired (`data-testid={`${testid}-lens-${id}`}`, `aria-label`), with `onContextMenu` on the wrapping
  `<span>`; **not wired ⇒ plain text, never a dead button.** **SINGLE mode has no chip** (the value lives in a
  `<select>`, `:36-51`) — render a `⋯` `<button data-testid={`${testid}-lens`}>` **immediately after the
  select**, mounted only when `props.value && onOpenLens`. 🔴 **This is the ONE legitimate `⋯` in the wave.**
  Wire `onOpenLens` at the SceneInspector call sites.
- **SLICE C — the popover:** 🔴 **Do NOT add a radix dep** (there is no `components/ui/` dir; `package.json`
  has only `@radix-ui/react-dialog` + `react-slot`). Hand-roll from `motif/components/SwapMotifPopover.tsx:16-30`:
  `role="dialog" aria-modal="true" aria-label={entityName} tabIndex={-1}`, autofocus on open, `Escape` → close.
  🔴 **ADD THE ONE THING `SwapMotifPopover` LACKS: RETURN FOCUS TO THE TRIGGER on close** (capture
  `document.activeElement` at open; `.focus()` it in **every** close path). **Mandatory now that the trigger is
  keyboard-reachable** — without it, Escape strands focus on `<body>`.

> 🔴 **EIGHT ROWS, ONE PER `REFERENCE_SOURCES` MEMBER. NOT SIX.** The set is exactly:
> `outline_pov · outline_present · scene_pov · scene_present · structure_roster · motif_application ·
> canon_rule · narrative_thread` (`agent_native.py:53-56`).
>
> An earlier cut of the design drew **six**, collapsing the pov/present pairs and thereby **silently
> dropping `outline_present` and `scene_pov`**. That is a bug for two independent reasons:
> 1. **It under-reports.** A character present-cast on 7 **chapter** nodes but zero scene nodes reads as
>    "Present in — 0". The author concludes she is unused. She is not.
> 2. 🔴 **A source with no row cannot render its own degrade.** The repo degrades **per source**
>    (`{"error": "this source could not be read"}`). A source the lens never draws is a source whose
>    **failure is invisible** — the same absent≠zero violation, committed in the sibling surface.
>
> **The split by node kind is the repo's own design** (`entity_references.py:17-21`: *"there is no `scenes`
> table … `outline_node` holds BOTH chapters and scenes (`kind`), so the pov/present pair splits by kind"*).
> **Render the split. Do not re-collapse it.**

**Rows:** `POV · chapters` · `Present · chapters` · `POV · scenes` · `Present · scenes` · `Arc roster` ·
`Motifs` · `Canon rules` · `Threads opened` — **in the exact order of `agent_native.py:53-56`.**

🔴 **RENDER THE CONSTANT, NEVER THE RESPONSE KEYS.** New `frontend/src/features/studio/lens/referenceSources.ts`
exports the 8-tuple + a `LABEL: Record<ReferenceSource, string>` map. The row list is
**`REFERENCE_SOURCES.map(...)`** — **NOT `Object.keys(payload.sources)`.** A row exists **before the response is
consulted**; you **cannot draw six because you cannot skip a `.map` member**. Iterating the payload is the same
bug class as the 6-row collapse: **a source the server omitted would silently not draw, and its failure would be
invisible.**

**Row state is a 3-WAY BRANCH, never a number-with-a-default** (⚖ ADJ `Q-37-LENS-PER-SOURCE-DEGRADE`):
1. `payload.sources[src] === undefined` (**key absent**) ⇒ **"could not be read"** — treat a missing key as an
   **error**, never as zero.
2. `'error' in payload.sources[src]` ⇒ **"could not be read"** (muted/warn styling, **no count glyph**, not
   expandable, not clickable).
3. else ⇒ the **exact `count`** + a `▸` expander revealing the capped `refs`, with a **"+N more"** when `has_more`.

🔴 **FORBIDDEN: `count ?? 0`, `count || 0`, `Number(count)`.** A lint-visible `?? 0` on a count **is** the
defect: `Block.into` OMITS a degraded key **by design**, so `?? 0` converts an *unknown* into a confident
**"0 references"** — and **the author's next move on "0" is to delete the entity.**

**Loading** ⇒ exactly **8 skeleton rows keyed by `REFERENCE_SOURCES`** — **not** a magic `[...Array(6)]`.
**All-zero copy** — *"Not referenced anywhere in the spec layer — all 8 sources answered, all 8 returned 0."* —
is gated on a **predicate, not on emptiness**:
`REFERENCE_SOURCES.every(s => payload.sources[s] && !('error' in payload.sources[s]) && payload.sources[s].count === 0)`.
**If ANY source is absent or errored, that copy is FORBIDDEN** — render the rows with their degrade markers.

### 🔴 ⚖ ADJ — the footnote is **an i18n string, NOT `_meta.note`**. (`Q-37-LENS-PER-SOURCE-DEGRADE` §6)

The first draft said *"render `_meta.note` verbatim"*. **The actual string** (`server.py:3926-3930`) is
**agent-facing and names MCP tools**: *"Composition scope only. The prose side is
`glossary_list_chapter_links` + `glossary_get_entity_evidence`; the graph side is
`kg_entity_edge_timeline`."* **Putting that in an author's popover is a defect.** BE-1d keeps returning
`_meta.note` unchanged (**the agent path needs it**); the FE renders an i18n key
**`refs.scopeNote`** = *"Composition scope only — prose mentions live in the glossary; graph edges in the KG."*
(generated across 18 locales — **never hand-written**). Render it **UNCONDITIONALLY in all three states**
(loaded / all-zero / degraded) — it is the guard against reading *"23 scenes"* as *"23 prose mentions"*.

### 🔴 ⚖ ADJ — **SIX of the eight expanded-row kinds are INERT in M2, not one.** (`Q-37-LENS-EXPANDED-ROWS-INERT`)

The first draft said only `structure_roster` is inert. **The code says FIVE of the eight sources emit refs into
plan-hub's id space** — `outline_pov`, `outline_present`, `scene_pov`, `scene_present` (all →
`node_ref={kind:"chapter"|"scene", id: outline_node.id}` via `_ref()`, `entity_references.py:207-213`) **plus**
`structure_roster` (→ `{kind: structure_node.kind, id: structure_node.id}`, `:135-141`) — **and `plan-hub` is
param-blind.** Only **TWO** sources have a target that provably focuses today: `canon_rule` → quality-canon
(`focusRuleId`) and `narrative_thread` → quality-promises (`focusThreadId`). **`motif_application` has NO
consuming panel at all.** ⇒ **6 inert · 2 live** in M2.

> 🔴 **ID-SPACE TRAP — do NOT route the `chapter`-kind rows to `chapter-browser`.** `node_ref.kind === "chapter"`
> here is an **`outline_node` of kind chapter**, **NOT** a book-service `chapter_id`. Passing
> `focusChapterId = node_ref.id` puts an outline_node id in a chapter_id slot: it **focuses nothing FOREVER,
> even after W7-S9 lands** (`cross-service-normalization-bug-class`). **All 5 go to `plan-hub` as
> `focusNodeId`. Never `chapter-browser`.**

✅ **This is exactly why the lens calls `host/issueRouting.ts`'s `routeReference()` (S5) rather than
hand-rolling.** When W7-S9 empties `PARAM_BLIND_PANELS`, **the 5 plan-hub rows light up in BOTH surfaces from
ONE edit** — which **removes the "M2 shipped before M1b" ordering hazard entirely**, rather than relying on a
builder remembering a rule. `motif_application` stays inert until spec 33's motif panel lands with a focus param.

**TESTS:**

| Test name | Asserts |
|---|---|
| `test_all_eight_source_rows_render` | 🔴 **THE GUARD against re-collapsing pov/present.** Mock a payload containing **only 3 of the 8 keys**, one of them `{error}` ⇒ `screen.getAllByTestId(/^lens-source-/)` has length **8**, and the 8 testids equal `REFERENCE_SOURCES`. |
| `test_a_failed_source_renders_could_not_be_read_not_zero` | Mock `{scene_pov: {error: '…'}}` ⇒ that row's text contains *"could not be read"* and the string **"0" does NOT appear in that row**; the other 7 counts render. |
| `test_an_OMITTED_key_also_renders_could_not_be_read` | 🔴 A payload that omits `outline_present` **entirely** ⇒ its row still renders and reads *"could not be read"* — **not `0`**. |
| `test_all_zero_copy_only_claims_eight_sources_answered` | All 8 at `count: 0` ⇒ 8 rows **and** the all-zero copy. One errored ⇒ the copy is **absent**. |
| `test_the_scope_note_is_i18n_not_the_raw_meta_note` | 🔴 `refs.scopeNote` is in the DOM in **loaded, all-zero AND degraded** states; the raw substring **`glossary_list_chapter_links` is NOT in the DOM**. |
| `test_loading_renders_eight_skeleton_rows` | ✔ |
| `test_opens_on_context_menu_and_on_the_keyboard` | `fireEvent.contextMenu(badge)` opens it **and `defaultPrevented === true`** (no native browser menu over the canvas); `userEvent.tab()` **reaches** the cast chip and `Enter` opens it; `Escape` closes it **and focus RETURNS to the trigger**. |
| `test_the_cast_chip_is_a_button_when_wired_and_a_span_when_not` | 🔴 With `onOpenEntityLens`: `getByTestId('plan-badge-cast-…').tagName === 'BUTTON'` + a non-empty `aria-label`. **Without the prop: still a `<span>`, and clicking calls nothing** — the never-a-dead-button guard. |
| `test_the_five_plan_hub_row_kinds_are_inert` | 🔴 FE-1 **in the lens**, driven off `routeReference()` — `outline_pov`, `outline_present`, `scene_pov`, `scene_present`, `structure_roster` ⇒ `inert`. `motif_application` ⇒ `inert` (no owner). `canon_rule` / `narrative_thread` ⇒ **live**. |
| `test_an_outline_node_id_is_never_passed_as_focusChapterId` | 🔴 The ID-SPACE TRAP, asserted. |

**DoD evidence:** vitest green + the live browser smoke (§10) **right-clicks a cast badge and counts 8 source
rows** and opens the lens **KEYBOARD-ONLY** (Tab to the chip → Enter). *A mouse-only smoke does not prove the
a11y fix.*

---

### ── W7-S9 · M1b — FE-1: the param-blind targets learn to focus

**dependsOn:** `W7-S5`. **Kind:** FE.
✅ ⚖ ADJ — **UNBLOCKED.** The Book-Package handoff has happened (see §2). **Edit both files directly.**
`D-W7-FE1-BOOKPKG` is **retired**. This slice **ships in this wave.**

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/plan-hub/components/PlanCanvas.tsx` | **EDIT** — 🔴 **SLICE 1: the camera cannot resolve an EXPANDED arc.** Do this FIRST. |
| `frontend/src/features/plan-hub/hooks/usePlanHub.ts` | **EDIT** — 🔴 **`revealNode()`.** `expandAncestorsOf` **cannot see an outline_node id.** |
| `frontend/src/features/studio/panels/PlanHubPanel.tsx` | **EDIT** — read `props.params.focusNodeId`; drive the EXISTING `focusNode()` |
| `frontend/src/features/studio/panels/ChapterBrowserPanel.tsx` | **EDIT** — read `props.params.focusChapterId`; **PIN** the target (the list is **server-paged**) |
| `frontend/src/features/plan-hub/components/{ChapterNode,ArcRollupNode,SceneNode}.tsx` | **EDIT** — `data-selected` (focus is **unassertable** today) |
| `frontend/src/features/studio/panels/ChapterBrowserTitleView.tsx` | **EDIT** — `data-chapter-id` + `data-focused` |
| `frontend/src/features/studio/host/issueRouting.ts` | **EDIT** — `PARAM_BLIND_PANELS` becomes an **empty set**; **all 4 rows** (and the lens's 5) become clickable |
| `frontend/src/features/plan-hub/components/__tests__/PlanCanvas.test.tsx` | **CREATE/EDIT** |
| `frontend/src/features/plan-hub/hooks/__tests__/usePlanHubReveal.test.tsx` | **CREATE** |
| `frontend/src/features/studio/panels/__tests__/planHubDeepLink.test.tsx` | **EDIT** (the file exists) |
| `frontend/src/features/studio/panels/__tests__/issuesFeedFocusContract.test.tsx` | **CREATE** — the emitter→consumer JOIN |

### 🔴 ⚖ ADJ — "mirror `focusNode` / mirror `hoist()`" AS WRITTEN SHIPS **TWO SILENT NO-OPS**. (`Q-37-FE1-PARAM-BLIND-TARGETS`, `Q-37-PLANHUB-CAN-IT-REVEAL-AN-OUTLINE-NODE`, `Q-37-USESTUDIOPANEL-DOES-NOT-EXPOSE-PARAMS`, `Q-37-OQ2-CLOSED-DO-NOT-RELITIGATE`)

**ONE PARAM NAME.** `grep -rn "focusNodeId|focusArcId" services/ frontend/` = **ZERO hits** — both names exist
only in docs, so there is **no compat cost**. **The router emits `focusNodeId` ONLY**, accepting **any**
plan-hub node id (saga | arc | chapter | scene): the plan-hub canvas holds **BOTH id spaces in ONE keyspace**
(`usePlanHub.ts:106`: *"the window content wins on id collision — it never collides, arcs vs outline nodes"*;
`select(id)` is one id space at `:145`; the camera keys on a plain node id). *(Two names for one concept
violates one-name-one-concept. `PlanHubPanel` still coalesces `focusNodeId ?? focusArcId` defensively.)*

**SLICE 1 — `PlanCanvas.tsx` camera. DO THIS FIRST; plan-hub's deep-link is inert without it.**
`CameraController` (`:69-91`) resolves `nodes.find(p => p.id === focusTarget.nodeId)` and **returns silently
when absent** (`:86`). 🔴 **An EXPANDED arc is a `LaneBand` (`laneLayout.ts:105-119`), NOT a member of
`layout.nodes`** — only a **COLLAPSED** arc is a rollup node (`:139`). And `focusNode` calls
`expandAncestorsOf` (**ancestors only**), so an expanded arc **never becomes a rollup** ⇒ **an arc pan NEVER
FIRES.**
**Fix:** pass `lanes: LaneBand[]` into `PlanCanvas` → `CameraController`; resolve the target as
`nodes.find(n => n.id === id)` **?? the first node drawn inside that band**, where the band's descendants are
the lanes with `l.y >= band.y && l.y < band.y + band.height` (**`LaneBand` has no `parent_id` — nesting is
geometric**) and the node is `nodes.find(n => n.laneId && bandLaneIds.has(n.laneId))` (`NodePosition.laneId`,
`laneLayout.ts:128`). **Add `lanes` to the effect deps** — the existing per-`seq` `pannedFor` latch (`:82-87`)
then makes this **WAIT FOR LAYOUT**, which is what makes a **COLD-OPEN** deep-link work (params land on the
**first** render, when `layout.nodes` is still **empty** — resolving eagerly in the panel would return null
forever). *This also fixes the identical latent no-op on the PH25 rail path.*
**TEST:** focus an **expanded** arc's id ⇒ `setCenter` called with the coords of the **first node in its band**;
focus a **collapsed** arc's id ⇒ centers the rollup; focus an id **absent at mount, then land the layout** ⇒
centers **exactly ONCE**.

**SLICE 2 — `usePlanHub.revealNode()`. The REAL gap.**
🔴 Outline nodes are **LAZILY WINDOWED** — a chapter card exists only once its **arc** is expanded; a scene card
only once its parent **chapter** is expanded (`usePlanHub.ts:71-72`). And **`expandAncestorsOf` (`:152-167`)
builds `byId` from the ARC SHELL ONLY**, so handing it an `outline_node.id` **finds nothing → `ancestors=[]` →
early return → nothing expands → the camera pans to nothing.** `PlanHubPanel.focusNode()` therefore **works for
arcs and SILENTLY NO-OPS for outline nodes** — which is **most of the rows this slice exists to light up.**
Add to `PlanHubView` (**logic in the hook, not the panel — MVC**):
```ts
async revealNode(nodeId: string): Promise<void>
```
- `shell.some(s => s.id === nodeId)` ⇒ arc/saga: `expandAncestorsOf(nodeId)`. Done.
- else it is an **outline node** ⇒ resolve its ancestors via `compositionApi.getNode(nodeId, token)`
  (`queryClient.fetchQuery`, key `['plan-hub','node',nodeId]` — **the SAME key `usePlanNode.ts` already uses**,
  so it is cache-shared, **no extra request**). `OutlineNode` carries `parent_id` and `structure_node_id`
  (`composition/types.ts:189,216`).
  - kind `chapter` ⇒ `arcId = node.structure_node_id`.
  - kind `scene` ⇒ `chapterNodeId = node.parent_id`; a **second** `getNode(chapterNodeId)` ⇒ `arcId = chapter.structure_node_id`.
- then: if `arcId` → `expandAncestorsOf(arcId)` **AND add `arcId` ITSELF to `expandedArcs`** (🔴
  `expandAncestorsOf` deliberately expands only **ANCESTORS** — **the arc itself must also be open or its
  chapter window never loads**); if `chapterNodeId` → add it to `expandedChapters`. **Both setters idempotent**
  (return `prev` when already present, keeping identity).
- `arcId === null` ⇒ the chapter lives in the **always-loaded UNASSIGNED window** (`usePlanWindows.UNASSIGNED_KEY`)
  ⇒ **no expand needed**, just select + pan.

**SLICE 3 — `PlanHubPanel.tsx` consumes the param.**
`const target = (props.params as {focusNodeId?: string; focusArcId?: string} | undefined)?.focusNodeId
  ?? (props.params as any)?.focusArcId ?? null` → `await view.revealNode(target); focusNode(target);`
**Reuse the EXISTING `focusNode()` (`:104-114` = expandAncestorsOf + camera seq bump + select). Do NOT write a
second focus path.**
🔴 **TWO TRAPS, both of which a naive impl hits:**
- **`props.params` alone is NOT sufficient here.** `PlanHubPanel` holds focus in **`useState`** (`focusTarget`
  at `:102`), and **useState ignores a changed prop on re-render** — so the **SECOND** issue-row click into an
  **already-open** Hub focuses **nothing**. The host's re-open path is
  `existing.api.updateParameters(opts.params)` (`StudioHostProvider.tsx:83`); only a **CLOSED** panel gets
  params via `addPanel` (`:92`). ⇒ **You MUST also subscribe `props.api.onDidParametersChange`.**
  Mirror `JobDetailPanel.tsx:28-34`'s dispose shape and its `str()` guard (`:16`).
- **Do NOT fire on a bare mount effect.** `shell` is **EMPTY at mount**, so `expandAncestorsOf` early-returns
  and `select()` selects a node that is **not drawn** — reproducing the exact *"opens the panel onto nothing"*
  bug this slice exists to kill, **while a unit test over a mocked `usePlanHub` still passes.**
  **Guard on the params OBJECT IDENTITY via a `useRef`** (dockview only swaps that object on
  `addPanel`/`updateParameters`, so identity-guarding **re-pans on a REPEAT deep-link to the same node**, which
  a value-guard would swallow, while unrelated re-renders are inert), **and** gate on the layout having landed.
- **NO SILENT NO-OP (the pagination edge):** an arc's chapter window is keyset-paged at `CHILD_PAGE = 100`
  (`usePlanWindows.ts:14`), so a chapter past page 1 will not be in `layout.nodes` even after its arc expands.
  After reveal, if the id is **still absent** from `view.nodeContent` and the slice `hasMore`, call
  `loadMoreArc` (and, for scenes, `loadMoreChapter` — `usePlanWindows` exports it but **`usePlanHub` does NOT
  currently return it: add it to `PlanHubView`**) up to a bound of **5 pages**; if still not found, render
  `data-testid="plan-hub-focus-miss"` (*"that plan node isn't on this canvas — it may have been archived"*),
  mirroring `ThreadsPanel`'s `composition-threads-focus-missing`.

**SLICE 4 — `ChapterBrowserPanel.tsx`. 🔴 THE LIST IS SERVER-PAGED — a hoist of the loaded rows is a LIE.**
Read `props.params.focusChapterId`, pass it into `ChapterBrowserTitleView` (**and force `mode='title'`** —
content-mode cannot show it). 🔴 **DO NOT just hoist the loaded rows:** `ChapterBrowserTitleView.tsx:9-13` uses
`useServerPagedList`, so **a focused chapter on page 3 would be silently ABSENT** — the exact
`paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` bug class.
**Instead:** fetch the target directly with the **EXISTING** `booksApi.getChapter(token, bookId, chapterId)`
(`books/api.ts:345` — **no new route**) via a `useQuery`, and render it as a **PINNED, highlighted focus row
ABOVE the list** (reuse the row component + the `HIT` ring from `QualityCanonPanel.tsx:26`), **de-duped against
the in-page rows** (if it IS on the current page, highlight it **in place AND keep the pin** — never hide
either). Mirror `useQualityCanon`'s honesty clause (`:15-18`): **`getChapter` 404 ⇒ an explicit
`data-testid="chapter-browser-focus-miss"` banner** (*"that chapter no longer exists"*) — **never an unchanged
list that pretends the link did something.** 🔴 **Do not touch the filters/pagination — a focus HOISTS, never
filters.** *(`ChapterBrowserPanel` is derive-only ⇒ `props.params` alone IS sufficient; do **not** add an
`onDidParametersChange` subscription there.)*

**SLICE 5 — MAKE FOCUS ASSERTABLE** (⚖ ADJ `Q-37-M1B-DOD-FOCUS-NOT-MOUNT` — *this is why the "obvious test" is
a mount test*). Today `selected` renders **ONLY as a Tailwind class** (`ChapterNode.tsx:27` `ring-2
ring-primary`) — **unassertable.**
- `ChapterNode.tsx:21`, `ArcRollupNode.tsx:23`, `SceneNode.tsx:23`: add
  `data-selected={selected ? 'true' : undefined}` beside the existing `data-testid`.
- `ChapterBrowserTitleView.tsx:463` (the row div): add `data-chapter-id={c.chapter_id}` and
  `data-focused={c.chapter_id === focusChapterId ? 'true' : undefined}`.
Both **mirror `QualityCanonPanel.tsx:168`** — **one idiom, one name.**

**TESTS:**

| Test name | Asserts |
|---|---|
| `PlanCanvas.test.tsx :: test_the_camera_resolves_an_EXPANDED_arc_via_its_lane_band` | 🔴 SLICE 1. Expanded arc ⇒ `setCenter` on the first node in its band. Collapsed ⇒ the rollup. Absent-then-landing ⇒ centers **exactly once**. |
| `usePlanHubReveal.test.tsx :: test_revealing_a_SCENE_under_a_collapsed_arc` | 🔴 SLICE 2. `getNode` called **twice** (scene→chapter); the **arc AND the parent chapter** end up expanded; the scene appears in `layout.nodes`. |
| `usePlanHubReveal.test.tsx :: test_an_unassigned_chapter_needs_no_expand` | `structure_node_id: null` ⇒ **no expand**, still selectable. |
| `planHubDeepLink.test.tsx :: test_it_focuses_an_OUTLINE_NODE_id_not_just_an_arc` | 🔴 Render with `params.focusNodeId` = an **outline_node** id ⇒ `select` fired with **that** id and the camera target equals it. |
| `planHubDeepLink.test.tsx :: test_it_survives_an_ASYNC_shell` | 🔴 `usePlanHub` whose `shell` is **empty on first render, populated on the second** ⇒ the focus still lands. **This test REDS against the naive mount-effect and GREENS only with the layout-gated latch.** |
| `planHubDeepLink.test.tsx :: test_a_SECOND_deep_link_into_an_already_open_hub_lands` | 🔴 Fire `onDidParametersChange` with a **different** id ⇒ the selection **MOVES**. *(The assertion a `props.params`-only impl fails.)* |
| `planHubDeepLink.test.tsx :: test_an_unresolvable_id_renders_the_miss_banner` | `plan-hub-focus-miss`, and **zero** `[data-selected]`. |
| `test_plan_hub_focus_does_not_filter_the_tree` | The other nodes are **still rendered**. (PH14 forbids re-laying out under the user.) |
| `ChapterBrowserPanel :: test_an_OFF_PAGE_focus_is_PINNED_from_getChapter` | 🔴 `focusChapterId` **not on the loaded page** ⇒ a pinned row rendered from `getChapter`; the page rows and the total are **unchanged**. On-page ⇒ highlighted **in place**, **no duplicate row**. `getChapter` 404 ⇒ the miss banner. **No params ⇒ `getChapter` is NOT called at all.** |
| 🔴 `issuesFeedFocusContract.test.tsx` | **THE EMITTER→CONSUMER JOIN — the one that closes DoD-0.** For each of the 4 param-blind kinds: **IMPORT `host/issueRouting.ts` and use the `openPanel` args it ACTUALLY emits** (**never a hand-written params object** — a hand-written one only encodes the author's assumption and **cannot catch a `focusNodeId` vs `nodeId` key drift**), render the target panel with `props.params = args.params`, and assert **exactly ONE** `[data-focused="true"]` / `[data-selected="true"]` element **AND that its `data-testid`/`data-chapter-id` carries the id the ROW sent.** |
| `test_negative_control` | Panel rendered with **NO params** ⇒ **zero** `[data-focused]`/`[data-selected]`. *(Proves the assertion can fail.)* |
| `issueRouting.test.ts :: test_the_four_rows_are_no_longer_inert` | `PARAM_BLIND_PANELS.size === 0`; the **arithmetic guard flips to 7 clickable / 1 inert** (`index_stale` stays inert **forever**). |

🔴 **WRITE THE BAN INTO THE DoD:** *"Asserting a panel/tab MOUNTED, or asserting any `studio-*-panel` testid is
visible, is **NOT** an M1b assertion and does not close the slice. The assertion must name the entity id the
clicked row sent."*

**DoD evidence:** vitest green + **a Playwright click that lands on the FOCUSED node** — not merely on the
mounted panel (§10 / W7-S12c).

---

### ── W7-S10 · M3 / BE-1b — stamp `book_id` onto the jobs projection (producer)

**dependsOn:** none. **Kind:** BE. **Cross-service ⇒ live-smoke MANDATORY.**

**THE BLOCKER, NAMED.** `GET /v1/jobs` accepts `status · kind · parent · q · bucket · cursor · offset ·
limit` (`jobs-service/app/routers/jobs.py:42-51`) — **no `book_id`**. And composition's `_job_params`
(`generation_jobs.py:127-144`) emits `model · model_ref · operation · mode · reasoning · reasoning_effort ·
retryable` and **not `book_id`**. So a *book-scoped* Jobs feed is unbuildable today — and a bottom panel
inside a per-book Studio showing the user's jobs **from every book they own** is not a feature, it is noise.

This is **buildable, not blocked** (CLAUDE.md's anti-laziness rule).

**FILES**

| Path | Action |
|---|---|
| `services/composition-service/app/db/repositories/generation_jobs.py` | **EDIT** — `create()` and the guarded sibling at `:490-560` |
| `services/composition-service/tests/unit/test_worker_jobs.py` (or the nearest generation-jobs test) | **EDIT** |

**THE CHANGE.** `book_id` is **derived inside the INSERT** (`SELECT $1, $2, w.book_id, … FROM
composition_work w`) — the caller does not know it. So stamp it **from the returned row**, right before the
emit, in **both** insert paths:

```python
if row is not None:
    job = _row_to_job(row)
    # BE-1b — the jobs projection has no book column, and a per-BOOK Studio feed cannot filter without
    # one. Taken from the ROW (book_id is derived from composition_work inside the INSERT), never from a
    # caller-passed value — a caller-supplied book_id would be an unvalidated scope key.
    # Additive + safe under redelivery: the projection's params column is a jsonb MERGE (new keys win,
    # an event that omits params keeps the accumulated object), so a later status event without book_id
    # can never wipe it (`jobs-projection-usage-fields-coalesce-merge`).
    _job_params["book_id"] = str(job.book_id) if job.book_id else None
    await emit_job_event(c, service=_JOB_SERVICE, job_id=str(job.id), …, params=_job_params)
```

⚠ **Both call sites.** `grep -n "emit_job_event" services/composition-service/app/db/repositories/generation_jobs.py`
and patch **every** one. (`replace_all` misses the deep one — `stream-service-has-three-terminal-usage-yields`.)

**MIGRATION (additive, jobs-service):** add to the `DDL` string in `services/jobs-service/app/migrate.py`,
below the existing `CREATE INDEX IF NOT EXISTS idx_job_projection_parent` (line ~74):

```sql
-- 37 BE-1c — the per-book Studio Jobs feed filters on params->>'book_id'. Expression index so the
-- filter is not a seq scan on a projection that mirrors EVERY service's jobs.
CREATE INDEX IF NOT EXISTS idx_job_projection_owner_book
  ON job_projection (owner_user_id, (params->>'book_id'), job_updated_at DESC);
```

**Additive. No backfill.** Historical rows have no `book_id` in `params` and will simply not match a
book filter — **which is correct**: we genuinely do not know which book they belonged to, and inventing one
would be fabricating data. *(This is why the tab's empty state must say "no jobs for this book **yet**",
not "no jobs".)* ⚠ `ADD COLUMN IF NOT EXISTS` never revisits a bad default on an already-migrated DB — this
migration adds **no column and no default**, so that trap does not apply. There is **no CHECK constraint**
and **no partial unique index** here, so those two traps do not apply either.

**TESTS:**

| Test name | Asserts |
|---|---|
| `test_create_emits_book_id_in_params` | Spy on `emit_job_event`; assert `params["book_id"] == str(<the work's book>)`. |
| `test_the_guarded_create_path_also_emits_book_id` | 🔴 The **second** call site (`generation_jobs.py:~563`, promoted-scene-prose — it passes **NO `params` at all** today). A test on only one path is how the deep one stays unpatched. |
| `test_book_id_comes_from_the_row_not_from_a_caller_arg` | `create()` has **no `book_id` parameter** — assert via `inspect.signature`. *(A caller-passed scope key is a tenancy smell.)* |
| `test_status_transition_emits_do_NOT_wipe_book_id` | The later status events pass `params=None`; the projection's jsonb `||` merge (`store.py:61`) **preserves** the create-time key. *(Additive + safe under redelivery.)* |

> ⚖ ADJ (`Q-37-M3-CROSS-SERVICE-SMOKE` §1) — **the translation half.** `services/translation-service/app/routers/jobs.py:229`'s
> `_job_params` also omits `book_id`, and `book_id` is **already a parameter of the enclosing
> `_resolve_and_create_job(db, book_id, …)` (`:106`)** — so it is the **same one-liner**. Without it, a tab
> labelled **"Jobs"** shows composition jobs only while **the book's translation jobs run invisibly** — this
> repo's own silent-omission class. **Do it.** 🔴 If the builder judges translation genuinely out of scope,
> that is the **ONE** thing here that may become a defer row **+ an honest tab label** — **the composition half
> may NOT.**

**DoD evidence:** `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup` green.

---

### ── W7-S11 · M3 / BE-1c — `GET /v1/jobs?book_id=…`

**dependsOn:** `W7-S10`. **Kind:** BE / CONTRACT.

**FILES**

| Path | Action |
|---|---|
| `services/jobs-service/app/projection/store.py` | **EDIT** — `_build_filters` (+2 lines), `list_jobs` (+1 kwarg), `list_jobs_paged` (+1 kwarg) |
| `services/jobs-service/app/routers/jobs.py` | **EDIT** — `list_jobs` gains `book_id: Optional[str] = Query(None)` and threads it through |
| `services/jobs-service/tests/test_store.py` + `tests/test_api.py` | **EDIT** |

**THE CHANGE — `_build_filters` (`store.py:257-282`)**, one new clause, placed with the others:

```python
if book_id:
    args.append(book_id)
    where.append(f"j.params->>'book_id' = ${len(args)}")
```

Thread `book_id: Optional[str] = None` through `list_jobs` and `list_jobs_paged` (both already forward every
filter into `_build_filters`, so it is one kwarg each).

> ⚠ **Text compare — no `::uuid` cast.** `params` is jsonb and the producer stamps a **string**; a cast would
> blow up on a legacy row carrying a junk value. Note `_build_filters` **already forces
> `j.parent_job_id IS NULL`** on the default view — composition jobs are top-level so the smoke is unaffected,
> but **do not remove that clause**.

**Router (`routers/jobs.py:42-52`):** add
`book_id: Optional[str] = Query(default=None, description="scope to one book (composition jobs stamp it into params — BE-1b)")`,
**validate it parses as a UUID** (`uuid.UUID(book_id)` → `HTTPException(400)` on failure), and pass it to
**both** store calls. **Owner-scoping is unchanged and unconditional** (`j.owner_user_id = $1` stays the
**first** predicate) — `book_id` is an **additional narrowing filter, never a substitute for the owner gate,
never an auth key**.

**⚖ ADJ — MCP PARITY (`Q-37-M3-JOBS-BOOKID-BLOCKER` §4), do not skip it:** add the **same optional `book_id`
arg to the `jobs_list` MCP tool** (`services/jobs-service/app/mcp/server.py`) and pass it through — otherwise
the agent and the human get **two different job lists for the same book**. 🔴 **And fix the now-false docstring
at `mcp/server.py:12`** (*"a job is owned by exactly one user (owner_user_id) with **no book_id**"*) →
*"…with an optional `params.book_id` scope stamp (**filter only — never an auth key**)."*

**TESTS:**

| Test name | Asserts |
|---|---|
| `test_book_id_filter_narrows_to_that_books_jobs` | Seed 2 jobs, one with `params.book_id = b1`; `?book_id=b1` returns **1** — in **BOTH keyset and offset modes** (`list_jobs` **and** `list_jobs_paged`). |
| `test_book_id_does_not_widen_past_the_owner_gate` | 🔴 Seed a job owned by **user B** with `params.book_id = b1`; user A's `?book_id=b1` returns **0**. *(A filter that leaked across owners would be a tenancy breach.)* |
| `test_no_book_id_is_unchanged_behaviour` | The existing list is byte-identical. |
| `test_a_job_without_a_book_id_in_params_never_matches` | Historical rows do not silently match. |
| `test_a_malformed_book_id_is_400_not_a_silent_full_list` | 🔴 `?book_id=not-a-uuid` ⇒ **400**. *(A param the query ignores returns EVERYTHING and still passes a presence-only test — `silent-success-is-a-bug`.)* |
| `test_the_jobs_list_MCP_tool_takes_the_same_filter` | Agent and human see the **same** book-scoped list. |

⚠ Any NEW test here touching the real dev Postgres **must** carry `pytestmark = pytest.mark.xdist_group("pg")`
(`test_store_pg.py` is the precedent) — parallel workers otherwise interleave and the counts lie.

**DoD evidence:** `cd services/jobs-service && python -m pytest tests -q -n auto --dist loadgroup` green.

---

### ── W7-S12 · M3 — the Jobs + Generation tabs

**dependsOn:** `W7-S11`, `W7-S4`. **Kind:** FE.

**FILES**

| Path | Action |
|---|---|
| `frontend/src/features/jobs/types.ts` | **EDIT** — `JobListParams` gains `book_id?: string` |
| `frontend/src/features/jobs/api.ts` | **EDIT** — `list()` forwards it |
| `frontend/src/features/studio/components/bottom/JobsTab.tsx` | **EDIT** — the real body |
| `frontend/src/features/studio/components/bottom/GenerationTab.tsx` | **EDIT** — the real body |
| `frontend/src/features/studio/components/bottom/useBookJobs.ts` | **CREATE** — the controller |
| `frontend/src/features/studio/components/bottom/__tests__/JobsTab.test.tsx` | **CREATE** |
| `frontend/src/i18n/locales/en/studio.json` (+ 17 generated) | **EDIT** — remove the now-dead **`bottom.pending.*`** keys (⚖ ADJ: `bottomStub.*` was already **deleted** in W7-S4 — do not resurrect it) **and the `test_the_en_locale_has_no_bottomStub_key` guard's sibling**, in the SAME commit as BE-1b/BE-1c |

**THE CHANGE.**

- **JobsTab** = the book's background work (translation, extraction, import, composition generation),
  **book-scoped**: 4 compact rows, `title · kind · status · progress`, click →
  `host.openPanel('job-detail', { params: { service, jobId } })` (the shipped `JobsListPanel.tsx:20-22`
  seam — **reuse it, do not fork**). Wrap in the existing `JobsStreamProvider` (DOCK-2: no fork of the
  jobs feature).
- **GenerationTab** = the same store filtered to `service === 'composition'`, plus a deep-link to `editor`
  (`host.focusManuscriptUnit(chapterId)`).
- **Empty state copy:** *"No jobs for this book yet."* — **not** "No jobs". Historical jobs (pre-BE-1b) carry
  no `book_id` and are genuinely unknown, not absent.

**TESTS:** `test_jobs_tab_requests_the_book_scoped_list` (the api spy sees `book_id`), `test_row_click_opens_job_detail`,
`test_generation_tab_shows_only_composition_jobs`, `test_empty_state_says_yet_not_none`.

**DoD evidence:** vitest green + **live smoke: a real composition generate job appears in the Jobs tab,
book-scoped, on a stack-up** (this is the cross-service pair BE-1b/BE-1c — a green unit suite is
insufficient).

---

### ── W7-S12b · X-10 — the agent's discovery scent (⚖ ADJ — **the no-go zone is LIFTED**)

**dependsOn:** everything above (it is the **LAST code slice** — so the sentence is written **once, and
correctly, after the human surfaces exist**). **Kind:** BE. **RUN ONLY IF PRE-FLIGHT G8 IS EMPTY.**

**⚖ ADJ (`Q-37-X10-DO-NOT-TOUCH-STREAM-SERVICE`) — THE PREMISE OF THE "DO NOT TOUCH" ROW IS FALSE AT HEAD.**
`git status --porcelain services/chat-service/ frontend/src/features/chat/` is **EMPTY**: Track C's D8 files
(`stream_service.py`, `tool_permissions.py`, `ToolApprovalCard.tsx`, `useChatMessages.ts`) are **committed and
clean** (`stream_service.py` last touched by `a23c3f15e`). **Plan 30 §9:715's *"uncommitted, mid-edit RIGHT
NOW"* row is STALE.** Spec 37 §7.3's *"out of scope / do not touch it"* is **superseded**: *"Track C has landed;
X-10 runs as the last slice of this wave."* **(Still: re-run G8 at build time. Verify, don't assume.)**

**THE CHANGE.** `services/chat-service/app/services/stream_service.py` — replace the inline block at
**`:3751-3765`** with a call to a new **module-level pure helper** (put it next to `_inject_context_ids`, which
is already unit-tested):

```python
def _build_book_context_note(book_id, chapter_id, project_id, tools_enabled: bool) -> str | None:
    if not book_id:
        return None
    note = f"You are working inside book_id={book_id}."
    if chapter_id:
        note += f" The active chapter is chapter_id={chapter_id}."
    if project_id:
        note += (f" This book's composition/knowledge project is project_id={project_id}"
                 " — pass it verbatim to any tool that requires a project_id"
                 " (a book_id is NOT a project_id).")
    note += (" Use these exact ids for any tool that requires a book_id or chapter_id."
             " Never ask the user for the book_id and never pass a placeholder.")
    if tools_enabled:      # ← the X-10 / AN-C2 discovery scent — ONE sentence, ~45 tokens
        note += (" To see what is wrong with this book call composition_diagnostics;"
                 " to see everything that references an entity call composition_find_references;"
                 " for the book's structure at a glance call composition_package_tree.")
    return note
```
**Call site:** `book_context_note = _build_book_context_note(_ctx_book_id, _ctx_chapter_id, _ctx_project_id,
tools_enabled=(stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled))` — **reuse the
EXACT guard expression already used at `:3635`** for the workflows fetch. The scent is gated on `tools_enabled`
so a **no-tools turn never names tools it cannot call** (no-silent-no-op discipline).

🔴 **Use the tool names EXACTLY as registered** — `composition_package_tree` (`mcp/server.py:3712`),
`composition_find_references` (`:3867`), `composition_diagnostics` (`:3935`). **Do NOT invent a
namespaced/prefixed variant.**

**Why all THREE tools, including the one with no GUI** (a default the PO may veto): AN-11's own risk row calls
*"shipped but never called"* a **FAIL**, and `package_tree` is precisely the tool with **no human path to it**.
Naming it in the **AGENT's** scent is **not a human GUI surface**, so **IF-5 / AN-12 still stand for it.**

**Cost note (Context Budget Law):** +1 sentence (~45 tokens) **on book-scoped, tool-enabled turns only**. If a
budget test reds on the constant, **update the baseline — do not drop the scent.**

**TESTS** — `services/chat-service/tests/test_stream_service_book_context_note.py` (new), 4 cases:
(a) `book_id=None` ⇒ the note is `None`; (b) `tools_enabled=True` ⇒ **all three literals** appear;
(c) `tools_enabled=False` ⇒ **none of the three** appear; (d) `project_id` present ⇒ the
*"a book_id is NOT a project_id"* clause **survives** (the CTX-1 regression guard).

**DoD evidence:** `cd services/chat-service && python -m pytest tests/test_stream_service_book_context_note.py -q` → 4 passed.

---

### ── W7-S12c · The live-smoke SEED + the two Playwright specs (DoD-7's actual recipe)

**dependsOn:** `W7-S5`, `W7-S8`, `W7-S9`. **Kind:** TEST.
**⚖ ADJ (`Q-37-SEED-CANON-VIOLATION-FIXTURE`, `Q-37-DOD6-LIVE-BROWSER-SMOKE`) — DoD-7 said *"a book with a
known-seeded canon-rule violation"* and gave no recipe. Here it is. It is $0, deterministic, and needs NO LLM.**

🔴 **NO BOOK QUALIFIES TODAY, AND NONE CAN.** Live query against `loreweave_composition`: the full
`rule_violations` predicate returns **0 rows**; `canon_rule` holds **0 active rules across 0 projects**;
`generation_job` holds **0 rows with a non-null `critic`**; `outline_node` holds **0 rows of `kind='scene'`**.
**Do not spend time hunting for a fixture book — there isn't one.**

**THE UNLOCK:** a `broken_canon_rule` row is **NOT computed by an engine at read time.** It is read straight out
of `generation_job.critic` JSONB (`outline.py:1257`), joined to the rule **by plain text**:
`LEFT JOIN canon_rule cr ON cr.id::text = v.violation ->> 'rule_id'` (`:1350`). **So the fixture is PURE SQL.**
🔴 **Do NOT run the critic** to seed it — that is non-deterministic **and paid**, and that flakiness is exactly
what DoD-7's word *"KNOWN-SEEDED"* exists to exclude.

**FILES**

| Path | Action |
|---|---|
| `frontend/tests/e2e/helpers/db.ts` | **EDIT** — add `seedCanonViolation()` beside the existing `seedPriorExtractionJob()` (`:30` — the identical `docker exec … psql` precedent). Gate on the existing `dbAvailable()` (`:45`). |
| `frontend/tests/e2e/specs/issues-feed.spec.ts` | **CREATE** (M1 — DoD-7 bullets 1-4) |
| `frontend/tests/e2e/specs/entity-references-lens.spec.ts` | **CREATE** (M2 — DoD-7 bullet 5) |

**THE SEED — a FRESH book per run** (title e.g. `LW-E2E-ISSUES-FEED`), **not a named permanent fixture**
(`shared-dev-db-not-clean-fixture-e2e`: a shared book accumulates unrelated rows, and DoD-7 requires **clicking
the `broken_canon_rule` row specifically**; a fresh book yields **exactly one error row** ⇒ an unambiguous click
target). Rows, in order:

1. **Book + project** via the existing `tests/e2e/helpers/api.ts` (owned by `claude-test@loreweave.dev`).
2. **Cast entity** via the existing `tests/e2e/helpers/glossary.ts` — 🔴 **MINT IT, do not invent a UUID.**
   `entity_id` is a **glossary** entity id; a fabricated UUID renders a **nameless cast chip** the right-click
   lens smoke **cannot target**.
3. `outline_node` **chapter**: `kind='chapter'`, `book_id`, `project_id`, `NOT is_archived`.
4. `outline_node` **scene**: `kind='scene'`, `chapter_id` → the chapter, `NOT is_archived`, **AND
   `pov_entity_id = <entityId>`, `present_entity_ids = ARRAY[<entityId>::uuid]`**.
5. `canon_rule`: a **FIXED** uuid, `project_id`, `book_id`, `created_by`, a real sentence, `active = true`,
   `is_archived = false`, `entity_id = <entityId>`.
6. `generation_job`: `status='completed'`, 🔴 **`operation='scene_prose'` — ANY value EXCEPT
   `'promoted_scene_prose'`** (that value is **explicitly excluded** by the query at `outline.py:1324` and would
   silently yield **zero rows**), `outline_node_id = <the scene>`,
   `critic = '{"violations":[{"rule_id":"<canon_rule uuid AS TEXT>","violated":true,"why":"…","span":"…"}]}'::jsonb`.

🔴 **CRITICAL:** `rule_id` **must be the canon_rule UUID rendered as a STRING** (the join is `cr.id::text = …`).
Get it wrong and `rule_text` comes back **NULL** — **the row still appears** (the repo never drops unattributable
findings, by design), **so the smoke goes GREEN while the "focused rule is hoisted" assertion is vacuous.**
**Assert `rule_text` is non-null inside the seed helper itself.** Make the helper **idempotent** (fixed UUIDs +
`ON CONFLICT DO NOTHING`, or delete-then-insert scoped to the seeded book).

✅ **The cast entity with non-zero references is NOT a second fixture — it falls out of the above for free.**
Step 4 makes `outline_present` / `scene_pov` / `scene_present` non-zero and step 5 makes `canon_rule` non-zero
⇒ **3 of the 8 REFERENCE_SOURCES carry a non-zero exact count**, which is precisely what DoD-7 asks. The other 5
correctly render **0** — and **0 ≠ absent** is the very distinction §4.2 protects.

**THE SPECS.**
- **New testids the M1 build must ADD:** `bottom-tab-<id>`, `bottom-body-<id>`, `issues-row-<kind>-<idx>`
  carrying `data-severity="error|warn|info"`, and **`issues-row-chevron-<idx>` rendered ONLY when the row is
  live — the chevron's ABSENCE is the machine-readable inert contract.** `refs-lens-source-<source>` +
  `refs-lens-count-<source>` for the lens. (`StudioPage` already exposes `bottom` + `toggleBottom` at
  `pages/StudioPage.ts:23-24` — **reuse, don't re-add.**)
- **The IF-2 proof is ONE line** and needs **no new testid**: `QualityCanonPanel.tsx:168` already renders
  `<li data-testid="quality-canon-rule-item" data-focused={…}>`:
  `await expect(page.getByTestId('quality-canon-rule-item').first()).toHaveAttribute('data-focused','true')`
  🔴 **If `rule_id` is still dropped from the payload, `focusRuleId` is null, `hoist()` is inert, and `.first()`
  has no `data-focused` → RED. That is exactly the assertion the unit test cannot make.**
- 🔴 **THE INERT PROOF MUST DIFF THE DOCK-TAB SET, not just look for one tab.** For each of the **4** param-blind
  kinds: assert `issues-row-chevron-<idx>` has **count 0**; snapshot
  `page.locator('.dv-default-tab').allTextContents()` **BEFORE**, `.click()` the row, assert the array is
  **UNCHANGED after**. *(Asserting merely "no plan-hub tab" would **pass** if the row opened some **other**
  panel.)*
- **The FOCUS assertion is written against the SEEDED id** — the id comes from the test's own fixture and is
  **NEVER read back out of the panel** (reading it back lets a panel that focuses *anything at all* pass):
```ts
// BANNED — certifies nothing:  expect(page.getByTestId('studio-plan-hub-panel')).toBeVisible()
await clickIssuesRow('unplanned_chapter');
const f = page.locator('[data-testid="studio-chapter-browser-panel"] [data-focused="true"]');
await expect(f).toHaveCount(1);
await expect(f).toHaveAttribute('data-chapter-id', seededChapterId);
```
- **Drive dockview via `evaluate` + `data-testid`** (refs go stale); use **`page.mouse`** for the resize-grip drag.

**THE RUN RECIPE — use `:5199`, NOT `:5174`.** `:5174` is the **BAKED nginx image**; FE changes need an image
rebuild and a host `vite dev` would **SHADOW** it.
```bash
cd frontend && npx vite --port 5199        # proxies /v1 → gateway :3123
PLAYWRIGHT_BASE_URL=http://localhost:5199 npx playwright test tests/e2e/specs/issues-feed.spec.ts --project=chromium
```
(`playwright.config.ts:3` already reads `PLAYWRIGHT_BASE_URL`.) Docker stack must be up (gateway + composition +
book + postgres), and 🔴 **rebuild the images first** (`live-smoke-rebuild-stale-images-first` — stale images =
false-green). **Screenshots → `docs/specs/2026-07-01-writing-studio/evidence/37-issues-feed.png` and
`-lens.png`, and COMMIT them** (playwright's `outputDir` is throwaway).

🔴 **SKIP-GATE POLICY.** Guard both specs with `test.skip(!dbAvailable())` so a stack-less CI **SKIPS rather than
REDS** — **BUT A SKIP DOES NOT SATISFY DoD-7.** The wave closes only when the transcript contains the **pasted
runner output showing the specs PASSED** (`N passed`, **not** `N skipped`) **+ the two committed screenshots.**
*(`env-gated-integration-tests-skip-and-the-green-suite-lies` — a skipped smoke is an **unmet** DoD, not a green one.)*

---

### ── W7-S13 · Wave close-out — `/review-impl`, the doc edits, SESSION, COMMIT

**dependsOn:** all. **Kind:** DOC/TEST. See §10.

**⚖ ADJ — THE DOC EDITS THIS WAVE OWES (all cheap, all fix-now; do them in the wave's docs commit):**

| # | Edit | Why (decision) |
|---|---|---|
| 1 | `37_issues_feed.md` — **"seven sources" → "six sources"** (§1); §1.1's *"~2.5 of 5 sources have a human surface"* → *"2 of the 8 kinds (`index_stale`, `prose_deleted_spec_node`) have NO human surface at all"*; §2's *"Each of the 7 sources"* → **6** (its engine list is **already** correct at six); retitle the §1.1 table header *"Diagnostic kind (8 of them, across 6 sources)"*. ⚠ **Do NOT edit plan 30 §0 PO-1's "~2.5 of 5" rationale — §0 is SEALED**, and the corrected count does not disturb the decision. | `Q-37-SOURCE-COUNT-INCONSISTENT` |
| 2 | `37_issues_feed.md` §4.1.1 — the M1 line *"4 live rows (…, index_stale-inert)"* **double-counts `index_stale` as live while calling it inert**. Correct to **3 clickable / 5 inert**. | `Q-37-IF4-INERT-ROW-RULE` |
| 3 | `37_issues_feed.md` §9 — replace *"M1 and M2 are independently shippable and touch disjoint files"* with *"M2 depends on M1: it consumes `host/issueRouting.ts` and the same `studio.json` locale family. Ship M1 → M2 → (M1b \| M3). Do not parallelize."* Add `host/issueRouting.ts` + its test to M1's Contents, and add the zero-literal-panel-id grep to M1's DoD. | `Q-37-M1-M2-DISJOINT-CLAIM` |
| 4 | `37_issues_feed.md` §8.4 + §7.1 — rewrite the **false Lane-B completion sentence** and the regex. **Leaving them on disk is how the next agent rebuilds the bug.** | `Q-37-PAID-ACTION-IN-FLIGHT` |
| 5 | `37_issues_feed.md` §7.3 — strike *"out of scope / do not touch stream_service"*; replace with *"Track C has landed; X-10 runs as the last slice of this wave."* Also `:509` and `:666`: **de-hardcode the `57`** → *"py enum == contract enum == openable, zero drift (N=57 at time of writing — **N is NOT load-bearing**; concurrent tracks may move it and that is correct, not drift)."* | `Q-37-X10-…`, `Q-37-PANEL-ENUM-57-CLAIM` |
| 6 | `37_issues_feed.md` §11 — mark **OQ-1, OQ-3, OQ-4, OQ-5 CLOSED** with pointers to the decisions file. Mark **D-1** with the PH21 dependency note (below). | several |
| 7 | 🔴 **`24_plan_hub_v2.md` PH21 + `37_issues_feed.md` D-1** — record that **PH21's "Unplanned chapters" tray is LOAD-BEARING for the `composition_package_tree` won't-fix and IS NOT BUILT** (grepping the FE for it returns only `ArcConformancePanel.tsx:225`, unrelated). It is the **sole carrier** of the coverage-gap human surface, so GG-1 is satisfied for that leg **only by a spec promise**. **It is a must-ship, not polish.** If spec 24 ever drops PH21, the remedy is to **restore the tray inside plan-hub — never to build a package-tree panel.** | `Q-37-D1-PACKAGE-TREE-WONTFIX` |
| 8 | 🔴 **RENAME the OTHER "AN-12" to `AN-14`** in **5 places** — `28_agent_native_studio.md:615`, `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:337/:339/:346`, `00C_POST_ARCHITECTURE_QUEUE.md:46`, `32_arc_inspector.md:405`. **The label now names TWO artifacts** — the **AMENDMENT** (which exists, `28:217`, and IS what DoD-7 means) and an **UNWRITTEN `resource_ref` section** (spec 24 Phase 4, gates nothing here). A close-out grep for "AN-12" surfaces both **and will make a builder conclude DoD-7 is unmet when it is met.** AN-13 is taken; **AN-14 is free.** Change **only the row label**, not the content. 🔴 **Do NOT touch the `AN-12 AMENDED` section itself, and do NOT delete AN-12's original row at `28:196`** — the amendment says *"read them together; do not reconcile one against the other by deleting either."* | `Q-37-AN12-AMENDMENT-LOCATION` |
| 9 | `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §8.2's X-13 bullet (~`:662`) — replace *"→ Wave 0 stretch, or Wave 7 at the latest"* with *"→ **Wave 0**, folded into the X-5/X-12 contract slice (same file, same contract regen, same two resolvers). **NOT Wave 7** — spec 37 adds zero frontend tools / panel ids / contributeContext consumers."* Mark spec 37 §11 **OQ-5 CLOSED** with a pointer, and update `00_OVERVIEW.md:93/:99`'s 🔴 dead-field notes to point at the Wave-0 slice. | `Q-37-OQ5-X13-REHOME` |
| 10 | **DoD-7 tick** — one command, **paste the output**: `git show HEAD:docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md \| grep -n "AN-12 AMENDED"` → expect `217:## AN-12 AMENDED (PO-1, 2026-07-12)`. **Do not re-author anything** — the amendment is already committed (`d0f17555e`). | `Q-37-AN12-AMENDMENT-LOCATION` |

---

## 7 · Migrations

| Slice | File | DDL | Additive? | Backfill |
|---|---|---|---|---|
| **W7-S10** | `services/jobs-service/app/migrate.py` (the idempotent `DDL` string, applied on startup) | `CREATE INDEX IF NOT EXISTS idx_job_projection_owner_book ON job_projection (owner_user_id, (params->>'book_id'), job_updated_at DESC);` | **Yes** — an index only. No column, no default, no constraint. | **NONE, deliberately.** Historical rows have no `book_id` and must not match a book filter — we do not know which book they belonged to, and inventing one would be fabricating data. The FE's empty-state copy says *"yet"* because of this. |

**No other migration in this wave.** BE-1 and BE-1d are **read-only routes over existing tables**; the
payload widening adds no column. The trap-list is checked and **none apply**: no `ADD COLUMN IF NOT EXISTS`
(so the never-revisits-a-bad-default trap is moot), no new enum value (so no historical CHECK block to
backfill), no partial unique index (so no soft-delete-tombstone exemption and no `ON CONFLICT` predicate to
repeat).

---

## 8 · The registration checklist (GG-8) — **how the drift-locks stay green with ZERO new panel ids**

**This wave adds NO panel. That is the design, and it is also what keeps the two machine guards green.**

| GG-8 step | This wave |
|---|---|
| 1. `panels/<New>.tsx` | ❌ **NONE.** The new files are `components/bottom/{IssuesTab,JobsTab,GenerationTab,IssueRow,IssuesWarningsStrip}.tsx`, `components/bottom/{useDiagnostics,useRunConformance,useBookJobs}.ts`, **`host/issueRouting.ts`**, `lens/referenceSources.ts`, `panels/EntityReferencesLens.tsx` — **not one of them is a dock panel.** *(The grip's state lives in the EXISTING `useStudioChrome`, not a new hook.)* |
| 2. `catalog.ts` | ❌ **NO ROW.** |
| 3–4. i18n `panels.<id>.*` × 18 locales | ❌ none. **BUT** 🔴 ⚖ ADJ — the `bottomStub.*` object is **DELETED** (**never repurposed** — the generator carries a stale translation forward on key-presence alone, so a changed meaning ships the OLD sentence in 17 locales with a green `--check`) and **NEW** `bottom.*` / `bottom.pending.*` / `issues.*` / `refs.*` keys land ⇒ **`python scripts/i18n_translate.py --ns studio` (NOT `--force`), NEVER hand-written**, + the new `studioBottomParity.test.ts` gate. |
| 5. `frontend_tools.py` `panel_id` enum | 🔴 **DO NOT ADD `"issues"`.** The enum is machine-locked to `OPENABLE_STUDIO_PANELS`; a pseudo-id with no catalog row **REDS `panelCatalogContract.test.ts` immediately** — and rightly: `ui_open_studio_panel` resolves through **dockview**, which **cannot mount the bottom panel**. |
| 6. `contracts/frontend-tools.contract.json` | ❌ **no regen.** 🔴 ⚖ ADJ — **ASSERT IT WITH A *SCOPED* DIFF:** `git diff --exit-code <wave-base-sha>..HEAD -- contracts/frontend-tools.contract.json` (the sha from pre-flight **G7**). **A bare `git diff` is wrong**: it would **false-RED** if a concurrent track (Book-Package, Track C) legitimately lands a panel and regenerates. **The assertion this wave owes is "THIS WAVE did not touch the contract file", not "the file never changed."** If the scoped diff is non-empty, that is a **REAL failure** — the wave added a panel it was not supposed to. **Stop and fix the wave; do NOT regenerate the contract to make it green.** **That is DoD-5.** |
| 6b. **the OpenAPI contract** | ✅ **YES — `W7-S3b`.** Two new REST routes ⇒ `contracts/api/composition/v1/openapi.yaml`, **frozen BEFORE the FE slices that consume them** (CLAUDE.md: *contract-first*). ⚠ **Not** `composition-service/plan-forge.v1.yaml` (that is Wave 5's). |
| 7. `studioLinks.ts` | ❌ none (no new URL shape). |
| 8. **Lane-B effect handlers** | ✅ **YES — MANDATORY (X-4).** `handlers/diagnosticsEffects.ts`, slice W7-S6. Plan 30 §8.0b: **this file is spec 37's, one file per domain** — two waves writing two handler files for one domain **DOUBLE-FIRE** (`matchEffectHandlers` returns EVERY match and `runEffectHandlers` awaits ALL of them). |
| 9. tours | ❌ none. |

**THE PANEL-ID BASELINE (plan 30 §8.0 — the count is CUMULATIVE across waves; six of eight specs got this
wrong by each computing from 57).** The running ledger: HEAD `9262ed53e` = **57** → w1 **61** → w2 **62** →
w3 **64** → w4 **65** → w5 **66** → w6 **69** → **w7 adds 0 ⇒ 69** → w8 **71**.

> 🔴 **ASSERT THE DELTA, NEVER A LITERAL.** Waves may be re-ordered or dropped, and a literal *"sends a
> builder hunting a phantom regression"* (spec 36's rule, adopted batch-wide). **Wave 7's assertion is:
> `N_after == N_before` (delta **0**) AND the three-way equality `OPENABLE == py enum == contract enum`
> still holds.** Record `N_before` from pre-flight G6.

**The ONE guard this wave ADDS:** the rewritten `StudioBottomPanel.test.tsx` (§6.1 W7-S4) — *every `BottomTab`
id has a `bottom.<id>` label key **and** a rendered body component*. Today's test asserts the **stub string is
present** — i.e. **it currently guards the bug**. That assertion inverts.

---

## 9 · Compliance — tenancy · settings · OCC · cost-gates · the four invariants

**Tenancy (User Boundaries).** **No new table, no new row, no new scope key.** Every read is **Per-book**,
gated at the E0 grant on `book_id` (`authorize_book(grant, book_id, user_id, VIEW)`) **BEFORE any repo call**.
Denial and missing-row return the **same** response (H13: `OwnershipError` → 404, `InsufficientGrant` → 403 —
**no enumeration oracle**). The project-keyed sources resolve the canonical Work via `resolve_scope` (PM-3/PM-4),
so a derivative's rows never merge into the source's feed. **A collaborator with VIEW sees the book's issues —
that is correct; they are the book's, not the owner's.** BE-1c's `book_id` is a **narrowing** filter layered
**on top of** the unconditional owner gate, never a substitute for it (its test asserts exactly this).

**Settings (SET-1..8).** **This wave adds ZERO settings and ZERO env flags.** The severity/kind filters are
**ephemeral component state** (a lens on a list, not a preference). The panel **height** is `localStorage` —
explicitly sanctioned by CLAUDE.md (*"UI state that is per-device — OK in localStorage (e.g. sidebar
collapsed, editor panel widths)"*). **No new global `*_ENABLED` / `*_MODE` env flag.** Nothing here is a user
setting, so SET-1..8 is satisfied by having nothing to satisfy.

**OCC.** **This wave performs ZERO writes.** Every surface is Tier-R. No `If-Match`, no `expected_version`, no
412 state to design. The feed **routes to** the panels that own the OCC writes (`quality-canon`, `plan-hub`),
and each already handles its own 412. **A feed that could edit would be the DOCK-2 fork AN-12 forbids. It
cannot.**

**Provider-gateway invariant.** **Zero provider SDK imports, zero model names.** The one paid action (W7-S7)
resolves its model as a **BYOK `user_model_id` UUID** from the `ModelPicker` and hands it to the existing
Tier-W spine, which resolves it through provider-registry. **Never hardcode a model name.**

**MCP-first.** This wave adds **no agentic logic**. BE-1/BE-1d are **non-agentic read mirrors** of engines that
already exist, exposed as REST because *every sibling panel reaches composition over REST*. The agentic Tier-W
propose (`composition_conformance_run`) stays an **MCP tool-call** through the existing bridge — S7 does not
invent an HTTP endpoint for it.

**Gateway invariant.** All traffic goes through `api-gateway-bff`. **Zero gateway work needed**:
`gateway-setup.ts:354` is `pathFilter: (p) => p.startsWith('/v1/composition')` with **no rewrite**, so both new
routes are auto-proxied.

**Frontend-Tool Contract.** **Untouched.** No new frontend tool, no new `panel_id` enum member, no
`CLOSED_SET_ARGS` change. `contracts/frontend-tools.contract.json` must be **byte-identical** at wave close
(DoD-5).

**Cost gates (§8.4).** The one paid action goes through the **generic** spine —
`GET /v1/composition/actions/preview` → `POST /v1/composition/actions/confirm`, descriptor
`composition.conformance_run`. 🔴 **NEVER** the two invented per-action paths
`/actions/conformance_run/{estimate,confirm}` — **they 404 in production today** (plan 30 §3.3). This wave does
**not** fix that live bug (Wave 3 owns it) and **must not copy it**.

---

## 10 · Wave Definition of Done — the literal checklist

- [ ] **DoD-0 🔴 NO ROW OPENS A PANEL ONTO NOTHING.** Every **clickable** row's target panel **provably reads
      the focus param that row sends** — asserted by `issuesFeedFocusContract.test.tsx`, which **imports the
      router and uses the args it ACTUALLY emits** (never a hand-written params object). ⚖ ADJ: it is **5 INERT
      kinds and 3 clickable** in M1 (`conformance_never_run` and `conformance_dirty` are **TWO kinds**), and the
      **arithmetic guard** asserts `3 clickable / 5 inert` → `7 / 1` after W7-S9. 🔴 **Asserting a panel MOUNTED
      is NOT an M1b assertion and does not close the slice — the assertion must name the entity id the clicked
      row sent.** *This is item zero because a feed that false-focuses is worse than the stub it replaces: the
      stub is honest.*
- [ ] **DoD-0b 🔴 CONTRACT-FIRST.** `W7-S3b` landed **before** W7-S5/W7-S8: both new routes are in
      `contracts/api/composition/v1/openapi.yaml` with path, method, request schema, response schema and error
      codes — **and `test_the_openapi_contract_matches_the_live_route` asserts the spec's enums equal the code's
      (`SEVERITY`, `REF_KINDS`, `REFERENCE_SOURCES`).** A contract nobody diffs against the code rots in one commit.
- [ ] **DoD-1** BE-1 returns `Diagnostics.ranked()`'s shape + the IF-1/IF-2/IF-3 fields, and the MCP tool and
      the route call **ONE** `build_diagnostics()`. **`grep -c "compute_coverage" services/composition-service/app/mcp/server.py` → 0** and **`grep -rn "SEVERITY\[" services/composition-service/app/ --include=*.py` hits ONLY `services/agent_native.py`** (there is no second fanout). `ref_kind` is the **3-member** closed set — `__post_init__` **raises** on a 4th, and a test asserts it.
- [ ] **DoD-1b 🔴 FILTER-THEN-CAP.** `ranked()` does **sort → filter → cap**, and a test seeds **30 errors + 12
      infos** and asserts `?severity=info&limit=25` returns **12 rows, not 0**, while `counts` still carries the
      error kinds at full value. *(Cap-then-filter is the shipped D-2 bug.)*
- [ ] **DoD-2** The **degraded path is TESTED, not assumed**: a test that makes `book_client.list_chapters`
      raise asserts the response omits **BOTH** `unplanned_chapter` **and `prose_deleted_spec_node`** from
      `counts` (`list_chapters` feeds **two** sources), carries **2** warnings + `degraded_sources`, is **200**,
      and the other sources **still populate** — **never `unplanned: 0`, never a 500.** Plus a **bare
      `RuntimeError`** variant (the engines catch only `BookClientError` — this is what proves the outer
      `try/except` survived the lift).
- [ ] **DoD-3** The **warnings strip is TESTED**: a response with `warnings[]` and `items: []` renders the
      *"N of 6 sources could not be read"* copy, **NEVER** *"No issues found"* — and 🔴 **N comes from
      `degraded_sources.length`, NOT `warnings.length`** (warnings also carry a truncation notice), and the
      **6** comes from `sources.length`, **never a literal**. A **clean** response with **no `warnings` key at
      all** (the real wire shape) must not crash.
- [ ] **DoD-4** **Guard inversion:** `StudioBottomPanel.test.tsx` no longer asserts `bottomStub.jobs` is
      present for a wired tab; it asserts every `BottomTab` has a label key + a **mounted** body component, and
      it asserts on **visibility**, not `textContent` (hidden bodies still contribute to `textContent` —
      asserting on it after the always-mounted refactor is how a green test certifies the wrong thing).
      🔴 ⚖ ADJ — **and the bodies are hidden by the HTML `hidden` ATTRIBUTE, not the Tailwind class** (jsdom
      loads no CSS, so `toBeVisible()` would call a class-hidden body VISIBLE). **Plus `StudioFrame.tsx:160`'s
      `&&` is GONE** — a `StudioFrame` test asserts the jobs stream `fetch` fires **exactly ONCE** across a
      collapse→reopen. **Plus `grep -rl bottomStub frontend/src/` returns NOTHING** and
      `studioBottomParity.test.ts` is green across all 18 locales.
- [ ] **DoD-5** **Drift-lock proof:** 🔴 ⚖ ADJ — the **SCOPED** diff
      `git diff --exit-code <wave-base-sha>..HEAD -- contracts/frontend-tools.contract.json` exits **0** (a bare
      diff false-REDs on a concurrent track's legitimate regen); `panelCatalogContract.test.ts` → **4 passed**;
      **and** `cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py -q` → green
      (**the py→contract leg — the FE test alone does NOT cover it**). 🔴 **Assert the three-way EQUALITY, never
      the literal `57`** — concurrent tracks may legitimately move N, and that is **correct, not drift**.
- [ ] **DoD-6** **Full suites green** (name them, paste the counts):
      - `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup`
      - `cd services/jobs-service && python -m pytest tests -q -n auto --dist loadgroup`
      - `cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py tests/test_stream_service_book_context_note.py -q`
      - `cd frontend && npx vitest run`
      *(Paste the ACTUAL "N passed" line. A claim that a check passed, without its output, is not evidence.)*
- [ ] **DoD-7 🔴 LIVE BROWSER SMOKE (mandatory — `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`).**
      **The seed and the two specs are `W7-S12c` — read it; the recipe is exact and it is $0 (pure SQL, no LLM).**
      A green unit suite has repeatedly hidden *"the FE could not actually execute it."* **Playwright**, against
      `vite dev` **:5199** (⚠ a host `vite dev` **SHADOWS** the baked :5174 image —
      `frontend-5174-is-baked-prod-nginx-not-vite`), with `claude-test@loreweave.dev` / `Claude@Test2026`.
      **Rebuild the images first** (`live-smoke-rebuild-stale-images-first` — stale images = false-green):
      - seed a **fresh** book with a **known-seeded** canon-rule violation (`seedCanonViolation()`, W7-S12c);
      - toggle the bottom panel → **Issues** → assert ≥1 row with severity `error`;
      - 🔴 **click the `broken_canon_rule` row** → assert the `quality-canon` dock tab mounts **AND the focused
        rule is hoisted to the top** (`quality-canon-rule-item`.first() has `data-focused="true"`). *This is the
        assertion that proves IF-2 is actually fixed — the unit test cannot see it, because the unit test does
        not know the payload dropped `rule_id`.*
      - 🔴 **assert the 4 param-blind rows + `index_stale` are INERT** — **no chevron**, and 🔴 **the
        `.dv-default-tab` text array is UNCHANGED before/after `click()`.** *(Asserting merely "no plan-hub tab"
        would PASS if the row opened some OTHER panel. Asserting the good row works does NOT prove the bad rows
        are safe.)*
      - after W7-S9: 🔴 **the click LANDS ON THE FOCUSED NODE** — `[data-focused="true"]` has count **1** and its
        `data-chapter-id` **equals the SEEDED id** (never an id read back out of the panel).
      - **right-click a cast badge on `plan-hub`** → assert the lens opens with **all 8 source rows present** and
        a **non-zero exact count** *(a 6-row lens is the W7-S8 regression)* — **and open it KEYBOARD-ONLY once**
        (Tab → Enter). *A mouse-only smoke does not prove the a11y fix.*
      - if M3 shipped: 🔴 assert a real composition job appears in the **Jobs** tab under `?book_id=<BOOK>`
        **AND is ABSENT under `?book_id=<a different uuid>`.** *(The **negative half** is the whole test — a
        filter that is a silent no-op passes the positive and fails only this.)*
      - **screenshot both, and COMMIT them** to `docs/specs/2026-07-01-writing-studio/evidence/`.
      🔴 **A SKIP DOES NOT SATISFY THIS.** The transcript must contain the pasted `N passed` (not `N skipped`).
      Drive dockview via **`evaluate` + `data-testid`** — refs go stale (`playwright-live-dockview-automation-recipe`); use `page.mouse` for any drag (the resize grip).
- [ ] **DoD-7b 🔴 M3's cross-service live-smoke is a HARD GATE, not advisory.** If M3 (S10-S12) ships, a real
      composition job minted **through the real producer** (propose→confirm — **do NOT `INSERT` a row by hand**;
      the point is to exercise producer→outbox→projection) must be visible under `GET /v1/jobs?book_id=<BOOK>`
      **and absent under another book's id**. **ESCAPE HATCH (the only one): if the stack genuinely cannot boot,
      M3 DOES NOT SHIP** — unit-green alone may **never** close M3. In that case M1's honest stub copy stays and
      `D-W7-M3-JOBS-LIVE-SMOKE` (gate 4) is written. **Shipping the Jobs/Generation tabs on mock-green is forbidden.**
- [ ] **DoD-8 🔴 `/review-impl` runs on the wave's diff, and EVERY bug it finds is FIXED before the wave
      closes.** Not deferred. Not noted. Fixed.
- [ ] **DoD-9** `docs/sessions/SESSION_HANDOFF.md` updated: the ▶ NEXT SESSION block, the Deferred rows from
      §12 added, any `D-QUALITY-*` rows this wave touches reconciled. The AN-12 amendment stays committed **in
      spec 28**, not here.
- [ ] **DoD-10** Committed. **Stage files by NAME** — `git add -A` is forbidden (three tracks share this
      checkout: `shared-file-collision-safe-staging-multi-agent-checkout`). ⚠ `git commit -- <path>` commits the
      **WORKING TREE**, not the index — and the index may already carry another agent's pre-staged changes
      (`git diff --cached --name-only` before you commit).

---

## 11 · Collisions & sequencing (plan 30 §9) — **all three tracks are on THIS branch, in THIS checkout**

> 🔴 ⚖ ADJ — **TWO OF THE FIRST DRAFT'S FOUR "DO NOT TOUCH" ROWS WERE FALSE AT HEAD.** Both were taken from a
> **stale doc note** rather than from `git`. Both are **now cleared on verified evidence** (see §2). **Verify
> with pre-flight G8/G9 at build time and proceed** — a builder who parks on either is parking on nothing.

| File / area | Owner | Rule |
|---|---|---|
| `frontend/src/features/studio/panels/PlanHubPanel.tsx` · `ChapterBrowserPanel.tsx` (W7-S9) | ✅ **FREE** — Book-Package track **DECLARED COMPLETE 2026-07-12** (plan 30 §9:716, 🟡 = *verify-then-go*, **not** 🔴) | ✅ ⚖ ADJ — **EDIT DIRECTLY.** Clean in the worktree; last commits (`d662bd97d`, `09f2d29b1`) are merged ancestors of HEAD; the 7 `lane/*` worktrees are stale (0-ahead / 0-dirty). **`D-W7-FE1-BOOKPKG` is RETIRED.** *This adjudication IS the handoff record.* |
| `frontend/src/features/plan-hub/components/NodeBadges.tsx` · `PlanCanvas.tsx` · `nodePresentation.ts` (W7-S8/S9) | ✅ **FREE** — same owner, same evidence (`58e89720f` is an ancestor) | ✅ **EDIT DIRECTLY.** The changes are **additive + degrade-safe** (an absent prop ⇒ byte-identical render), which is the minimal conflict surface anyway. |
| `frontend/src/features/plan-hub/components/PlanDrawer.tsx` | ✅ **FREE** — **bonus clearance, same owner, same evidence** | ⚖ ADJ — cleared **pre-emptively** so the next slice does not stall on the identical phantom. |
| `services/chat-service/app/services/stream_service.py` (W7-S12b / X-10) | ✅ **FREE** — 🔴 **Track C HAS LANDED** | ✅ ⚖ ADJ — `git status --porcelain services/chat-service/ frontend/src/features/chat/` is **EMPTY**; `stream_service.py` last touched by `a23c3f15e` (committed). **Plan 30 §9:715's *"uncommitted, mid-edit RIGHT NOW"* is STALE.** X-10 runs as **W7-S12b**, the last code slice. ⚠ **Re-run G8 at build time** — if it comes back non-empty, someone genuinely is mid-edit: **skip S12b and defer it.** |
| `features/composition/motif/api.ts` | Wave 3 | Its **4** live breaks are Wave 3's *(the 2 404ing per-action paths, `arc_template_id`→422, **and `regenerate-to-beat`, which has ZERO backend at all**)*. **Read it to know what NOT to copy** (W7-S7 traps 1+2). **Do not "fix" it here** — that is scope creep into another wave's diff and invites a merge collision. |
| `QualityCanonPanel.tsx` / `useQualityCanon.ts` | 🟡 touched `d662bd97d` (D-04) | **READ ONLY.** Its `focusRuleId` seam is **already there — use it, don't rebuild it.** |
| `SceneBrowserPanel.tsx:229` | studio | Its `chapterId ?? ''` is a **latent activeChapterId-clobber**. 🔴 **DO NOT COPY IT** into the Issues row handler (W7-S5 guards against it). Fixing it there is a one-liner: **fix-now if the wave touches that file, else leave it.** |

---

## 12 · Defer register — the starting rows

### ⚖ ADJ — RETIRED ROWS (do NOT carry these; they were overruled against source)

| ~~ID~~ | Why it is gone |
|---|---|
| ~~**D-W7-RUN-BUTTON-X1**~~ | **RETIRED → it is now slice `W7-S0`.** X-1 is ~15 lines in ONE shared component. *"X-1 is a prerequisite to BUILD, not a reason to CUT scope."* **Fixing it is cheaper than writing and carrying its defer row.** (`Q-37-X1-DOCK7-HARD-PREREQ`) |
| ~~**D-W7-FE1-BOOKPKG**~~ | **RETIRED → the handoff HAS happened.** Book-Package is `DECLARED COMPLETE`; all three files are clean, their commits are merged ancestors of HEAD, the `lane/*` worktrees are stale. **W7-S9 ships in this wave.** (`Q-37-TRACK-OWNERSHIP-HANDOFF`, `Q-37-OQ2-CLOSED`, `Q-37-IF4`) |

### The live rows

| ID | Origin | What | Gate (CLAUDE.md 1–5) | Target |
|---|---|---|---|---|
| **D-W7-JOBS-CONTRACT-ABSENT** | W7-S3b / S11 | 🔴 **NEW (⚖ ADJ, contract-first).** `GET /v1/jobs` gains a `book_id` query param — but **`contracts/api/` has NO jobs-service spec at all**, so there is **no file to add it to**. It is **not a new route** (it is a new param on an existing, already-undocumented one), and authoring a full jobs-service OpenAPI (list/get/cancel/retry/stream/projection) is a **structural** effort with its own review surface. **The two NEW routes this wave adds ARE contracted** (`contracts/api/composition/v1/openapi.yaml`, W7-S3b). | **#2 large/structural** | The wave that next touches jobs-service, or a dedicated contract sweep. |
| **D-W7-M3-JOBS** | W7-S10..S12 | The Jobs + Generation tabs are **independently deferrable**. If deferred, **M1 still ships the honest stub copy** — the lie *"once wired"* is deleted either way. 🔴 ⚖ ADJ: **if M3 ships, its cross-service live-smoke (with the NEGATIVE half) is a HARD GATE — unit-green may never close it.** | **#3 naturally-next-phase** (cross-service, its own live-smoke). | A follow-up session. |
| **D-W7-M3-JOBS-LIVE-SMOKE** | W7-S12 | 🔴 **NEW (⚖ ADJ).** Written **only if** M3 code lands but the stack genuinely cannot boot at build time. **In that case M3 DOES NOT SHIP** — the honest stub copy stays. | **#4 blocked** — external (no bootable stack). | The next stack-up. |
| **D-W7-TRANSLATION-BOOKID** | W7-S10 | 🔴 **NEW (⚖ ADJ), and ONLY if the builder judges it out of scope:** `translation-service`'s `_job_params` (`routers/jobs.py:229`) also omits `book_id` (which is **already in scope** at `:106`). Without it the "Jobs" tab shows composition jobs only while the book's **translation jobs run invisibly**. 🔴 **The composition half may NOT be deferred; only this one, and only with an honest tab label.** | **#1 out of scope** (a different service) — *if* invoked at all. Otherwise **fix-now, one line**. | Same wave, preferably. |
| **D-W7-PACKAGE-TREE-NO-GUI** | §7.2 of spec 37 (IF-5) | `composition_package_tree` gets **NO human surface** — **zero** catalog rows, **zero** `panel_id` enum entries, **zero** contract churn. Verified against code, not rubber-stamped: the tool is **self-declaredly** *"summary-shaped and hard-capped — ORIENTATION, not content"* (`server.py:3713-3721`) and routes callers to other tools for real reads, so a panel would be a **read-only mirror of organs the GUI already owns** = exactly the DOCK-2 fork AN-12 exists to prevent. Two of three human equivalents **ship today** (`plan-hub` = the spec tree, `chapter-browser` = the manuscript spine). ⚠ **PO-1 is PERMISSIVE, not mandatory** — its consequence column mandates a surface only for diagnostics + find_references, and the amendment PO-1 itself ordered written into spec 28 (`28:266-269`) **explicitly keeps the clause for package_tree.** WON'T-FIX is consistent with §0. | **#5 conscious won't-fix** | 🔴 **Never — do NOT re-open as a gap.** **RE-OPEN ONLY IF spec 24 drops PH21's unplanned-chapters tray** — which is **UNBUILT** and is the **sole carrier** of the coverage-gap human surface, hence **LOAD-BEARING for this won't-fix and must not be trimmed as polish**. In that event the remedy is to **restore the tray inside plan-hub, NEVER to build a package-tree panel.** **ACTION THIS WAVE: add that note to `24_plan_hub_v2.md` PH21 + `37_issues_feed.md` D-1 (W7-S13 doc edit #7).** |
| **D-W7-UI-TOGGLE-BOTTOM-PANEL** | OQ-1 | 🔴 ⚖ ADJ — **RE-GATED: this is a CONSCIOUS WON'T-FIX (gate #5), NOT a defer-to-Wave-0.** The agent is **not blind to this data**: it already has `composition_diagnostics`, **and** it already has a deterministic *"show me"* — every Issues row's owning panel (`quality-canon`, `quality-promises`, `quality-coverage`, `quality-critic`, `plan-hub`) is **already in the `ui_open_studio_panel` enum**. A 13th, overlapping nav tool would **red DoD-5** and **contradict sealed PO-3** (which retires `ui_show_panel` *precisely because* two overlapping nav tools make the model pick the wrong one). **Building the thing we are simultaneously retiring is wrong by construction.** ✅ **Instead this wave makes the existing path REAL** (both edits are OUTSIDE the frontend-tools contract, so DoD-5 stays green): the MCP description gains the routing sentence, and the payload gains **`panel_id`** so that sentence is not a lie (**W7-S1**). | **#5 conscious won't-fix** | **Never as a *gap*.** If the PO later wants a literal *"open the Issues tab for me"*, it is **ONE tool inside Wave 0's already-happening contract regen** — not a new mechanism, and **not a reason to hold Wave 7**. |
| **D-W7-X13-REHOME** | OQ-5 | 🔴 ⚖ ADJ — **DECIDED, not "raise to the PO": X-13 IS RE-HOMED TO WAVE 0**, folded into the **X-5/X-12** frontend-tool-contract slice (same file, same regen, same two resolvers). **Wave 0 is EARLIER than Wave 7, so nothing lapses — the deadline TIGHTENS.** Spec 37 adds **zero** frontend tools / panel ids / `contributeContext` consumers, so it has no consumer for X-13; X-5+X-12 already reopen `frontend_tools.py` + the contract + both resolvers. It does not contradict PO-1..4 (**PO-3 in fact creates the slice it rides on**). ⚠ **The premise was understated:** `ConsumerCapabilities` is not merely *unread* — it is an **EMPTY model (`pass`, zero fields)** that `messages.py` **never forwards**, so it could not carry a value even if the FE sent one. **No consumer AND no producer** ⇒ moving it costs nothing. *(Also dead: `StudioContext.active_panel_ids` — genuinely **sent** and read by nothing.)* **FALLBACK the PO may veto:** if Wave 0 slips X-13 for scope, the ONLY acceptable alternative is to **DELETE the four dead symbols** — a declared-and-unread field is the class CLAUDE.md bans. **Do not defer them a third time.** | **#1 out of scope of spec 37** (re-homed, not dropped) | 🔴 **Wave 0, X-5/X-12.** **ACTION THIS WAVE: amend plan 30 §8.2's X-13 bullet + mark spec 37 OQ-5 CLOSED (W7-S13 doc edit #9)** — do not let it lapse silently. |
| **D-W7-OQ3-CHAPTER-SCOPE** | OQ-3 | **BOOK-WIDE, CLOSED.** ⚖ ADJ — **this is not a taste call; the code forbids the alternative:** only **3 of the 8 kinds** carry a live chapter (2 are book-level rollups, 2 are arc-scoped, and `prose_deleted_spec_node`'s chapter is **deleted by construction** so it can *never* match the open chapter). **No `chapter_id` param, no "This chapter" toggle, no proximity sort.** Every row shows its chapter, so nothing is lost. **A regression vitest guards it.** | **#5 conscious won't-fix** | If the PO ever wants chapter scoping, the correct shape is **NOT a filter** but a **second, separate read** ("issues in this chapter"). |

---

## 13 · Risks — and the TELL that each has fired

| Risk | The tell |
|---|---|
| ✅ **RESOLVED — the adjudication register EXISTS.** The first draft said *"the register named in the wave brief DOES NOT EXIST ON DISK"* and fell back to plan 30 §0 + spec 37's own recorded decisions. **The rulings were recovered** and live at [`docs/plans/studio-adjudication/wave-7-decisions.md`](studio-adjudication/wave-7-decisions.md) (**61 items · 55 decided · 5 not-a-question · 1 deferred**). **They are folded in above and marked ⚖ ADJ.** | If a future edit contradicts a ⚖ ADJ block, **the decisions file WINS** — every ruling carries an `*Evidence:*` line naming the file:line it was settled from. The four SEALED PO decisions (PO-1..4, plan 30 §0) are **not re-openable from memory** either way. |
| 🔴 **A builder reads a STALE "do not touch" note and parks on nothing.** Two of the first draft's four collision rows were **false at HEAD** — both taken from a doc note rather than from `git`. | The builder writes `D-W7-FE1-BOOKPKG` or skips X-10 **without running G8/G9**. **Run the greps.** A 🟡 in plan 30 §9 means *verify-then-go*; only 🔴 means *do not touch* — **and even the 🔴 rows go stale.** |
| 🔴 **The filter runs AFTER the cap** (the drafted route did exactly this). On a book with 30 errors and `limit=25`, **every info row is already sliced off** before the filter sees it ⇒ `?severity=info` renders **0 rows while `counts` says 12**. | `routers/diagnostics.py` contains a list-comprehension over `payload["items"]`. **The filter belongs in `ranked()`, in the order sort → filter → cap.** `test_the_info_filter_is_not_starved_by_the_cap` is the guard. |
| 🔴 **The severity chips render "Error 0" on a book with 2 canon contradictions.** `counts` is **KIND-keyed** — `counts["error"]` is `undefined`. Spec 37 §4.1 says to render the chips from `counts`. **Following the spec literally ships the false-clean lie the module exists to prevent.** | The chips read `counts`, not `severity_counts`. Or the FE re-derives a kind→severity map (the duplication class). |
| 🔴 **The 4th conformance kind stays clickable and opens `plan-hub` onto nothing.** Spec 37 §4.1.1's table has **7 rows for 8 kinds** — `conformance_never_run` and `conformance_dirty` share a line. A builder implementing per-`kind` from a 7-row table **leaves one clickable.** | `ALL_KINDS.filter(isClickable).length !== 3` in M1. The arithmetic guard test exists **solely** for this. |
| 🔴 **The always-mounted refactor is a NO-OP** because `StudioFrame.tsx:160`'s `{chrome.bottomOpen && …}` unmounts all three bodies on every collapse. | The `&&` is still there. `test_..._opens_the_jobs_stream_exactly_ONCE` is the regression gate. |
| 🔴 **`toBeVisible()` LIES in jsdom.** vitest loads no CSS, so a Tailwind-`hidden` body computes to `display:block` and jest-dom calls it **VISIBLE**. | The bodies are hidden by `className`, not by the **`hidden` attribute**. `not.toBeVisible()` then falsely REDs — and "fixing" the component to satisfy it is how the real bug ships. |
| 🔴 **The i18n keys are REPURPOSED and 17 locales silently keep the OLD sentence** — with a **green `--check`**. `i18n_translate.py` carries a translation forward on **key-presence alone**; it never compares the English **value**. | `bottomStub` still exists in `en/studio.json`. **A changed meaning is a NEW key + a DELETE**, never an edit. `studioBottomParity.test.ts` (assertion **d**) is the gate. |
| 🔴 **The Run button's spinner NEVER RESOLVES.** The drafted "Lane-B lands the completion" is **false** — Lane-B fires only on **chat tool_calls**, and a REST `/actions/confirm` 202 is not one. **The user paid and watches a spinner forever.** | `useRunConformance.ts` has no `getJob` poll. And a `failed` job that **silently reverts the row** is the same class **on a spend path**. |
| 🔴 **A chapter-scope conformance run is a PAID JOB THAT ALWAYS FAILS.** `motif_conformance_run.py:74-79` raises a terminal `ValueError` for `scope != 'arc'` — **after** the token is minted, the billing precheck runs, and the job is enqueued. | `args.scope !== 'arc'`. Chapter conformance is the **free synchronous GET**, not a paid action. |
| 🔴 **The lens under-reports and its failures are invisible.** Collapsing pov/present to 6 rows drops `outline_present` and `scene_pov` — **and a source with no row cannot render its own degrade.** | `getAllByTestId(/^lens-source-/)` length **≠ 8**. Or a `?? 0` on a count — which turns an *unknown* into a confident **"0 references"**, and the author's next move on "0" is to **delete the entity**. |
| 🔴 **The lens ships MCP tool names into the author's UI.** `_meta.note` is **agent-facing** and literally reads *"the prose side is `glossary_list_chapter_links` …"*. | `EntityReferencesLens.tsx` renders `_meta.note`. It must render the i18n `refs.scopeNote`. |
| 🔴 **FE-1 lands and STILL focuses nothing.** Two independent silent no-ops: (a) the camera cannot resolve an **expanded arc** (it is a `LaneBand`, not a node); (b) `expandAncestorsOf` builds its map from the **arc shell only**, so an `outline_node` id expands **nothing**. **And a unit test over a mocked `usePlanHub` still passes.** | The M1b test asserts the panel **mounted**. That assertion is **banned** — it must name **the entity id the row sent**. `test_it_survives_an_ASYNC_shell` is the one that reds against the naive impl. |
| 🔴 **The chapter-browser focus silently misses an OFF-PAGE chapter.** The list is **server-paged**; a hoist of the loaded rows renders nothing and looks fine. | `ChapterBrowserPanel` hoists instead of **pinning** the row fetched via `booksApi.getChapter`. |
| 🔴 **The `?book_id=` jobs filter is a SILENT NO-OP** — `job_projection` has **no `book_id` column**, so a param with no carrier parses fine, filters nothing, and **returns EVERY job while the test looks green.** | The smoke asserts only the **positive** half. **The NEGATIVE half (`?book_id=<other uuid>` must NOT contain the job) is the whole test.** |
| **A "false-focus" row ships.** The single worst outcome: a row opens `plan-hub` onto an unfocused tree and reads as success. | Any row whose panel is in `PARAM_BLIND_PANELS` renders a **chevron**. `test_ALL_FIVE_inert_rows_render_with_no_chevron_and_are_not_clickable`, the **arithmetic guard** (3 clickable / 5 inert), and the **live smoke's dock-tab-set diff** all exist solely to catch this. If any is weakened, the row is lying. |
| **The lens re-collapses to 6 rows.** "POV" and "Present" *look* like two rows, not four. | `screen.getAllByTestId(/^lens-source-/)` has length **≠ 8**. A source with no row **cannot render its own degrade** — its failure becomes invisible. |
| **A degraded response renders as "No issues found."** The engine's careful honesty inverted into the exact lie it was written to prevent, on the one screen the user trusts. | `emptyClean` is true while `warnings.length > 0`. The `useDiagnostics` hook computes `emptyClean` and `emptyDegraded` as **separate** flags precisely so they cannot be conflated by a later edit. |
| **The `textContent` guard silently certifies the wrong thing.** After the always-mounted refactor, all three hidden bodies still contribute to `textContent`. | `StudioBottomPanel.test.tsx` still asserts on `textContent` instead of visibility. It will *pass*. That is the danger. |
| **A second diagnostics fanout drifts into existence.** Someone "helpfully" writes the route's own source loop instead of calling `build_diagnostics()`. | `grep -c "compute_coverage" services/composition-service/app/mcp/server.py` ≠ 0, or `compute_conformance_status` appears in `routers/diagnostics.py`. **DoD-1 greps for this.** |
| **The Run button copies its broken neighbour.** `motif/api.ts` has BOTH a 404ing per-action path AND a `arc_template_id` arg the `ForbidExtra` model rejects. | `grep -rn "conformance_run/estimate\|arc_template_id" frontend/src/features/studio/` is non-empty. |
| **The Lane-B handler ships as a silent no-op.** `registerEffectHandler`'s string branch is `startsWith`, **not** a pattern match — a string with alternation matches **nothing**, and a unit test that registers and calls its own fake **cannot catch it**. | `DIAGNOSTICS_STALING` is a **string**, not a `RegExp`. The test `test_the_pattern_is_a_regexp` exists for exactly this. |
| **The second `emit_job_event` call site stays unpatched** (BE-1b). `generation_jobs.py` has two insert paths (`:183` and `:543`). | Only the first path's test exists. `stream-service-has-three-terminal-usage-yields`: `replace_all` misses the deep one. |
| **The `book_id` jobs filter leaks across owners.** | A filter clause added *instead of* — rather than *in addition to* — `j.owner_user_id = $1`. `test_book_id_does_not_widen_past_the_owner_gate` is the guard. |
| **A stale image false-greens the live smoke.** | The smoke passes but the code under test never shipped into the container. **Rebuild first** (`live-smoke-rebuild-stale-images-first`), and remember a host `vite dev` **shadows** the baked :5174. |
