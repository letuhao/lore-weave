# Writing Studio Completeness — 8-Session Orchestration

> **Status:** framework proposed 2026-07-16. PO has approved: the 8-way split, same-folder execution,
> self-driven sessions (stop only at critical), and charters kept at "30+" (high/medium) altitude.
> **This doc is the DELEGATION FRAMEWORK, not a detailed spec.** Each session derives its own detail by
> role-playing a real user and reading the actual source. Spec drift is expected and normal.

---

## 0 · What "completeness" MEANS — the sealed finish line

The earlier plan (30–38) targeted only **① tool-GUI parity**. The PO has widened the goal to **all four**:

| | Dimension | Falsifiable "done" |
|---|---|---|
| **①** | **Tool-GUI parity** | Every backend capability a user owns has a registered Studio panel. 0 agent-only tools, 0 legacy-only tables. |
| **②** | **Legacy retirement** | `ChapterEditorPage` deleted after the parity gate flips green + a mechanical guard replaces the prose banner. |
| **③** | **The authoring loop closes** | A live-browser smoke drives ONE book **import → plan → draft → revise → translate → publish** entirely in the Studio, never touching the legacy page. |
| **⑤** | **Production-ready** | Every tool meets the bar in §2 — the user can actually **operate** it, not just click cards. |

**The bug this widening fixes:** what we built before was *"cho có và rất rời rạc"* — panels that exist but
don't work. The canonical example: **What-If is a skeleton** — the user clicks cards and can do nothing
else: no detail view, no audit, no operation. **A skeleton that renders is NOT done.** Done = the user
can do the job.

**The whole-run finish line (the `/goal` condition):**
> All 8 sessions closed to their production-ready bar (§2); the parity gate is green; the loop-③
> live-browser smoke passes (pasted); `ChapterEditorPage` is deleted behind a mechanical guard.

---

## 1 · The model — 8 functional sessions, same folder, self-driven

**Unit = a functional group a real user operates** (not a "wave", not a file). Each session OWNS one
tool-family end to end.

**Each session's mandate (this is the "brainstorm as a real user" directive):**
1. **Role-play a real web-novel author** using this tool family. What do they actually need to DO?
2. **Audit the current surface** against that — what works, what's a skeleton, what's a dead button.
3. **Decide per capability:** **PORT** (legacy has it, bring it 100%) · **ENHANCE** (legacy is thin, the
   user needs more) · **BUILD** (doesn't exist). Record the call; don't silently drop a legacy feature.
4. **Write your own detailed design** (the 30+ specs are *reference*, the source is *truth*), then build
   to the §2 bar.
5. **Self-drive.** A blocker → a tracked defer row + keep going. Stop and ask ONLY for the 4 critical
   classes (§5). Run `/review-impl` at each panel/wave close and fix what it finds.

**Same-folder execution (PO's call).** No worktrees. Safe because: the 8 file-trees are disjoint, S0
pre-reserves every shared-registry slot (§3), and each session commits small + often and runs scoped
tests during BUILD (§5).

---

## 2 · The production-ready bar — every session drives every panel to ALL of these

1. **Operable** — the user can complete the job. Every read has its write; every list row opens a
   detail; every action runs to a visible result. *(the What-If lesson: a card must open something)*
2. **CRUD complete** — no dead buttons. *(the kg-overview 3-noop-buttons lesson)*
3. **Reachable** — registered in `catalog.ts` + the agent `panel_id` enum + the command palette + the
   User Guide (`guideBodyKey`). *(GG-8; the "built-but-unreachable" lesson)*
4. **No silent failure** — every action surfaces success/error. *(the global `MutationCache.onError` /
   "a resolver never silently no-ops" law)*
5. **Agent parity** — a Lane-B effect handler so an agent write refreshes the panel; the agent can drive
   the tool the same way the human can.
6. **Loop-connected** — deep-links in/out to the adjacent tools in the authoring loop ③. A tool that
   can't hand off is an island.
7. **Proven** — a **live-browser smoke** drives the real panel end-to-end (not just unit tests). *(the
   `agent-gui-loop-needs-live-browser-smoke` law)*
8. **i18n + responsive** — 18 locales; usable on the target viewports (desktop + mobile — see the D-5
   mobile-shell decision, which the retirement node ② depends on).
9. **Scale** — degrades gracefully at 10k chapters where the tool lists book-scale data.

A panel that renders but misses 1, 4, 6, or 7 is the *"cho có"* failure. It is **not** done.

---

## 3 · S0 — the foundation (runs FIRST, single session, before the 8 fan out)

Nothing below is a feature; all of it is what makes the 8 parallel sessions safe and unblocked.

- **Verify the committed Wave-0 code** (`gather_motif`, `create_unbound`, `AddModelCta followStudioLink`
  are in HEAD) actually passes: `tsc --noEmit` + composition pytest + frontend vitest. Don't assume — it
  was written by parallel agents, stopped mid-flight, then committed by another track. If it's broken,
  **fixing it is S0's first real work.**
- **Finish the unbuilt Wave-0 slices — VERIFY each against HEAD first, several are already done:**
  - ✅ **X-2 already done** (`CATEGORY_ORDER` has `'quality'` after `knowledge` — `useStudioCommands.ts:27`).
  - ❌ **W0-S16** (global `MutationCache.onError`) — 0 hits in `App.tsx`. **Build it.**
  - ❓ **W0-S15** (Translate `preselectedChapterIds`), **X-4** (Lane-B effect registry + coverage ledger),
    **X-3** (`guideBodyKey` guard) — grep HEAD; build only what's missing.
- **D-4:** create `contracts/languages.contract.json` (the content-language SSOT).
- 🔴 **PRE-RESERVE all 19 panel slots — the mechanism that makes same-folder 8-session safe.**
  `catalog.ts`'s convention is `id === component id` and **every row references a real component** — so a
  bare enum row won't compile. Therefore:
  1. Add ONE shared `StubPanel.tsx` (renders "⏳ &lt;title&gt; — coming soon", takes the id as a prop).
  2. Add all 19 `catalog.ts` rows now, each `component: StubPanel`, tagged `/* owner: S<n> */`, plus a
     `guideBodyKey` (X-3 guard) — with matching `en` i18n stub keys and `panel_id` enum + `CLOSED_SET_ARGS`
     entries **in sync** (the contract test asserts enum == openable == contract; all three move together).
  3. Each session then **swaps its stub → its real component** (same file path) and edits **only its own
     pre-tagged row** — no two sessions ever touch the same line of `catalog.ts`.
- **Write the 8 per-session RUN-STATE stubs** (§7 template) so each session has its anchor from turn 1.

**S0 launch-gate (what the 8 wait on):** the 19 stubs are present, the registry compiles, the contract +
guideBody + category-order guard tests pass, and `tsc --noEmit` is clean. That is ALL the 8 need.

**D-1 is DECOUPLED from the launch-gate.** The `Vietnamese`→`vi` rekey (destructive, PO-gated) only
affects **S8**'s historical data, not the scaffold. S0 produces its migration + rollback + row-count
assertion + **dry-run and STOPS for PO review** — but the 8 launch on the scaffold regardless, and S8
proceeds on the enum write-path (deferring the historical rekey behind the PO decision). D-1 blocks
neither S0's gate nor the fan-out.

---

## 4 · The 8 session charters

Each charter is deliberately light (per PO #3). The session does the deep audit itself. "Resolved by
21-28" tells the session what NOT to rebuild.

### S1 · Manuscript & Compose
- **User:** *"I write a chapter — draft, get AI candidates, accept, revise, and my edits teach the model."*
- **Files:** `features/studio/panels/Editor*`, `ComposePanel`, `features/composition/{compose,assemble}`,
  the manuscript navigator.
- **Homeless sub-tabs it must home:** `compose` (the scene draft loop + the *only* adapt-from-source
  path), `assemble` (chapter stitch + the **second** correction producer).
- **Resolved by 21-28:** the compose-generate route is **gated, not a bug** (B4) — do not re-gate it.
- **Watch:** owns the **correction-capture seam** (accept/reject → `generation_correction`). S6 renders
  the stats; **S1 owns the seam.**

### S2 · Plan & Structure
- **User:** *"I structure my book — arcs, sub-arcs, the outline, decompose an imported book."*
- **Files:** `features/plan-hub`, `features/composition/arc*`.
- **Panels:** `arc-inspector`, arc-templates + 拆文 (Import & Deconstruct).
- **Resolved by 21-28:** the arc-decompiler (O-2), BA11's 5 arc-template MCP tools (O-3), plan-hub
  keyset perf + live drag (H8.1/H8.2). So the **backend is largely done — this is FE.**
- **Watch:** **owns `PlanDrawer.tsx`** (S4 sends motif-chip patches through S2).

### S3 · PlanForge compiler
- **User:** *"I compile a plan from a premise and review each of the 7 passes, approving the checkpoints."*
- **Files:** `features/plan-forge`, `features/studio/panels/Plan*`.
- **Panels:** `plan-passes` (the Pass Rail), planner repair.
- **Resolved by 21-28:** the proposer is grounded (O-1/G2); rules-mode pre-flight + auto-compile drive
  (P-O1a, D-G5). The headline gap remains: **a GUI-only user cannot advance a run past pass 2.**

### S4 · Motif & craft (套路/爽点/打脸)
- **User:** *"I study tropes, bind them to scenes, and check whether my prose actually delivered them."*
- **Files:** `features/composition/motif`.
- **Panels:** `motif-library` (~40-file port), the binding lens, suggest, `quality-conformance`.
- **Resolved by 21-28:** conformance dirty-flip proven live (F2). The motif-mine 500 is fixed in
  committed Wave-0 (`create_unbound`).
- **Watch:** sends motif-chip edits to **S2's `PlanDrawer.tsx`** — patch, don't fork.

### S5 · What-If & Divergence ⭐ (the PO's skeleton example)
- **User:** *"I explore an alternate branch, see what's different, compare takes, audit it, promote one."*
- **Files:** `features/composition/{divergence,whatif}`, `WhatIfCanvasPanel`, `SceneGraphCanvas`.
- **Panels:** `divergence` wizard, the what-if canvas; homes `canonview` (canon-at-branch-point).
- **Resolved by 21-28:** the what-if **producer** is ported and survives the Wave-6 port (O-11) — so the
  branch generates. **But the PO says it's a skeleton:** cards render, nothing operates. **This session's
  whole job is to make it OPERABLE** — detail views, the diff/audit of a branch, the judge badges,
  `PromoteWhatIfButton` actually promoting. The audit-current step matters most here.

### S6 · Canon, Quality & Progress
- **User:** *"Is my book consistent? What's wrong with it? Fix it. Am I making progress?"*
- **Files:** `features/composition/{canon,quality,polish,corrections,progress}`.
- **Panels:** `quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`; homes `flywheel`.
- **Resolved by 21-28:** conformance is S4's; here it's canon-rules CRUD + quality-critic + self-heal +
  the corrections *display* + progress.
- **Watch:** renders corrections from **S1's** seam — display only; don't duplicate the writer.

### S7 · Knowledge, World & Cast
- **User:** *"Who is in my world, where, and how do they relate? The map, the character arcs, the cast."*
- **Files:** `features/knowledge`, `features/world`, `features/composition/components/WorldMap`.
- **Panels:** the KG write-holes (create entity/relation, the 3 dead buttons, forget), `world-map`
  (book-service maps), `place-graph` (the `work.settings.world_map` place graph — **NOT** the same as
  world-map; plan 30 §10). Homes `cast` (the codex), `character-arc`, `worldmap`.
- **Watch:** the largest lore surface — likely the heaviest session; may need to sequence its own panels.

### S8 · Translation
- **User:** *"I translate my book to several languages, track coverage, and fix drift."*
- **Files:** `features/translation`.
- **Panels:** translation repair (spec 29, 0 of T1–T10 built), coverage matrix, targets.
- **Resolved by 21-28:** none — fully disjoint, the cleanest lane. W0-S15 discharges the dropped-selection
  half; this session builds the rest (T5 wedge, T9 grant-level, the `target_language` enum via D-4's SSOT).

---

## 5 · Coordination rules (same-folder)

- **Disjoint file trees** — build only under your charter's `features/**` subtree.
- **Shared registry files** (`catalog.ts`, `frontend-tools.contract.json`, `CATEGORY_ORDER`, i18n, the
  Lane-B registry index): **edit ONLY your pre-reserved region** (S0 stubbed them). Never append; fill in.
- **Seam ownership — via component mounting, so ownership stays truly disjoint (no shared-file edits):**
  the file owner mounts a component the OTHER session owns.
  - `PlanDrawer.tsx` → **S2 owns the file.** S4 builds `MotifBindingLens.tsx` (S4's file); S2 mounts
    `<MotifBindingLens nodeId={…}/>` with a one-line import. S4 never edits `PlanDrawer.tsx`.
  - Correction seam → **S1 owns** the capture (accept/reject → `generation_correction`). S6 builds
    `CorrectionsPanel.tsx` (S6's file) that only READS the stats route. S6 never edits S1's compose path.
  - Rule: if you need behaviour inside a file you don't own, ship it as YOUR component and ask the owner
    to mount it. Never cross-edit a seam file.
- **Commit discipline:** never `git add -A` — stage only your own files. Commit **small + often** so your
  uncommitted work doesn't pollute another session's test run. `git pull --rebase` before you push.
- **Tests during BUILD:** run your feature's tests scoped (`-k` / your suite). The **full suite is the
  convergence gate**, not a per-session gate — it reflects everyone's committed state.
- **Your own RUN-STATE:** each session keeps `docs/plans/2026-07-16-studio-session-S<n>-RUN-STATE.md`
  with its slice board (done = an evidence string), decisions, parked, debt, drift registers.
- **The 4 critical-class stops** (everything else is defer-and-continue): a destructive/irreversible
  action · a sealed decision proven wrong · a tenancy/security breach · a paid action that charges the
  user for nothing.

---

## 6 · The convergence node (after all 8 close — NOT parallelizable)

1. **Reconcile the registry** — should be conflict-free (pre-reservation), but verify: enum == openable
   == contract, `CATEGORY_ORDER` complete, i18n parity across 18 locales.
2. **The loop-③ live-browser smoke** — drive ONE book **import → plan → draft → revise → translate →
   publish** entirely in the Studio, Studio-only, and paste the run. This is the ③ finish line, and it
   can only run once every tool exists and hands off.
3. **GG-4 retirement ②** — the parity gate goes green only when every legacy sub-tab is homed (all 8
   sessions done). Then delete `ChapterEditorPage` behind the mechanical guard (`legacyParityContract`),
   after the D-5 mobile-shell decision is resolved.
4. **Full gate** — full test suites green, `ai-provider-gate`, no silent-failure regressions.

---

## 7 · Reference material each session reads (don't rebuild what's written)

- **plan 30** (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`) — the law (GG-1) + the gap register + §10 REFUTED.
- **specs 31–38** — the per-domain designs (reference; the source is truth).
- **the adjudication decisions** (`docs/plans/studio-adjudication/`) — 586 questions settled from source.
- **the HTML drafts** (`design-drafts/screens/studio/`) — the UI acceptance target, house style.
- **close-21-28** (`2026-07-13-close-21-28-plan.md`) — what the concurrent track already resolved.

### Per-session RUN-STATE stub template
```
# Studio Session S<n> — <domain> — RUN-STATE
## COMMITMENT: <the production-ready finish line for THIS tool family>
## INVARIANTS: <the §2 bar + the §5 coordination rules + the repo laws>
## SLICE BOARD:  | slice | status TODO/DOING/DONE | EVIDENCE (test count / smoke line / sha) |
## REGISTERS: DECISIONS · PARKED · DEBT · DRIFT  (append as you go; an empty drift log is dishonest)
## RESUME: re-read THIS file first → git log --oneline -15 → continue at first non-DONE slice
```

---

## 8 · Honest caveats

- **Same-folder + 8 simultaneous sessions** is the PO's call and is workable with §5's rules. The one
  residual risk the rules can't fully erase: a session running the **full** suite mid-flight will see
  other sessions' committed-but-incomplete work. Mitigation: full suite is the *convergence* gate;
  during BUILD, sessions run scoped tests. If churn becomes painful, fall back to a branch-per-session +
  merge model — the charters don't change, only the isolation does.
- **S7 is the heaviest** (KG + World + Cast + place-graph). If effort is lopsided, S7 may run longest;
  consider letting it start first or splitting its panels across two passes.
- **The loop-③ smoke and GG-4 retirement are serial tail work** — budget for them; they are not
  "free at the end."
