# Cycle 28: Living-world view (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** **M6 / living world. dị bản M5.** The world container (C20/C21) surfaces its **canon Work + all dị bản branches** (Works whose `source_work_id` chains into books in the world) as a **navigable timeline tree** — canon as the trunk, derivatives branching off at their `branch_point`. **Reuses `GraphCanvas`** (the hand-rolled SVG layer / tree rendering — no new graph library). Click a branch → navigate into that Work. Verify: one world shows canon + ≥2 derivative branches.
- **Acceptance gate:** `scripts/raid/verify-cycle-28.sh` exits 0
- **Top 3 LOCKED decisions consumed:** Living-world lock (world surfaces canon + dị bản branches as a timeline tree, reuses GraphCanvas), G2 (each branch = its own derivative project/partition), C23's `source_work_id` join (the branch spine)
- **DPS count:** 2
- **Estimated wall time:** 3–4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C21, C27
- Files expected to exist (grep-able paths): the C21 world container FE (world entry + bible-chapter-anchored lore); `composition_work.source_work_id`/`branch_point` (C23, the branch join); the C27 delta flywheel (branches are live, promotable); `GraphCanvas.tsx` (the SVG/tree layer being reused).

## Scope (IN)
- **Living-world timeline tree:** in the world container, render the world's **canon Work as the trunk** and each **dị bản branch** (Works whose `source_work_id` chains into the world's books) as a branch off the trunk at its `branch_point` (chapter-level, G3). Reuse `GraphCanvas` tree/SVG rendering — **no new graph library**.
- **Navigation:** click a node/branch → navigate into that Work (the derivative studio for a dị bản, the canon writing surface for the trunk). Pan/zoom/expand consistent with the existing canvas.
- **Branch metadata surfacing:** each branch shows its divergence type + branch_point so the tree reads as a navigable "what-if map" of the world.
- `scripts/raid/verify-cycle-28.sh` (acceptance gate) + a **Playwright screenshot** of a world showing canon + ≥2 derivative branches.

## Scope (OUT — explicitly)
- **NO BE work** — the `source_work_id` join (C23), delta (C27), world model (C20) all exist; this is FE composition over them.
- **NO new graph library** (LOCKED G5 — reuse `GraphCanvas` / generalize the existing pattern).
- **NO editing in the tree view** — read-only navigation; editing happens in the destination Work's existing surfaces.
- **NO wizard/studio internals** (C24), **NO packer/critic/flywheel logic** (C25/C26/C27) — this view only READS branch existence + metadata.
- NO world-level sharing (deferred).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: living-world tree component/unit tests (`frontend/.../LivingWorldTree*.test.tsx`) — canon trunk + N branches render, click→navigate target resolves, branch metadata shown.
- Lints pass: frontend lint + typecheck; React-MVC rules (hooks own data fetch/logic, GraphCanvas reused render-only; no useEffect for click navigation — explicit handlers).
- Integration smoke: **Playwright MCP** (test account `claude-test@loreweave.dev`) — open a world that has a canon Work + **≥2 dị bản branches**, capture a **screenshot** of the timeline tree, click a branch → land in that Work. Evidence string carries `playwright: world timeline tree shows canon + ≥2 derivative branches + branch click navigates`.

## DPS parallelism plan
- DPS 1: **Tree data + layout** — query the world's canon + derivative Works via the `source_work_id` chain, build the trunk+branch tree model anchored at each `branch_point`, feed `GraphCanvas`. (return budget: 1500 tokens summary)
- DPS 2: **Navigation + branch metadata + Playwright** — click→navigate handlers (explicit, no useEffect), branch divergence-type/branch_point labels, the Playwright screenshot smoke. Converges with DPS 1 on the canvas render.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **New graph library smuggled in:** any added dependency (d3-force, cytoscape, reactflow, etc.) — LOCKED G5 is reuse `GraphCanvas`, no new library.
- **useEffect-for-navigation smell:** branch click handled via `useEffect` watching a selected-node state instead of an explicit click handler (CLAUDE.md FE rule).
- **Broken branch join:** branches not correctly resolved via the `source_work_id` chain (missing a 2nd-degree derivative, or a branch from another world bleeding in) — confirm branches chain into THIS world's books only.
- **Screenshot gap:** unit-only green with no Playwright shot proving canon + ≥2 branches actually render and a click navigates.
- **Edit surface leak:** the tree view exposing edit actions (read-only navigation only).
- **Branch_point mislocation:** a branch rendered at the wrong chapter (not its `branch_point`, chapter-level G3).

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only world-container FE + `scripts/raid/verify-cycle-28.sh` changed; tree reuses `GraphCanvas` (no new graph library); canon trunk + dị bản branches resolved via `source_work_id` chain into this world's books, anchored at branch_point; click→navigate via explicit handlers; read-only; Playwright screenshot of canon + ≥2 branches filed; NO BE change, NO packer/critic/flywheel/wizard logic. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C28** row (dị bản M5 / living world; reuses `GraphCanvas`; M6 milestone).
- OPEN_QUESTIONS_LOCKED.md — **World-container locks** (Living-world view = world surfaces canon Work + dị bản branches whose `source_work_id` chains into the world's books, as a timeline tree, reuses GraphCanvas/tree rendering), **§G5** (no new graph library; reuse GraphCanvas), **§G2/§G3** (each branch = own partition; chapter-level branch_point), **Architecture-review locks** (C28's `source_work_id` join provided by C23).
- `docs/specs/2026-06-13-derivative-works-living-world-plan.md` — dị bản M5 / living world.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Reuse GraphCanvas (LOCKED G5):** NO new graph library — generalize the existing hand-rolled SVG/tree layer.
- 🔴 **Branch join (C23):** branches = Works whose **`source_work_id` chains into this world's books**, anchored at their `branch_point` (chapter-level, G3). Don't let another world's branches bleed in.
- 🔴 **Read-only + explicit nav:** the tree is read-only; click→navigate via **explicit handlers**, NOT useEffect; editing happens in the destination Work.
- 🔴 **Acceptance MUST include:** a **Playwright screenshot** of a world showing canon + **≥2** derivative branches with a working branch-click — unit-green alone is a false pass.
- 🔴 **Do NOT touch:** any BE (C20/C23/C27 own the data); no packer/critic/flywheel/wizard logic; no world-level sharing.
- 🔴 **Fresh session reminder:** this is a new `/raid 28` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
