# Cycle 19: Graph canvas (FE) — ▶ M4

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Turn the project subgraph (C18) into an **explorable visual network**. Reuse the existing hand-rolled `GraphCanvas` SVG layer and **generalize the `RelationshipMap` ego-network pattern** to render a whole-project subgraph: **pan / zoom / click→entity-detail / expand-hop**, honouring the endpoint's node cap with an "expand"/"load-more" affordance. **NO new graph library** — force/radial layout stays hand-rolled. **Read-only** — editing reuses the existing entity/relation dialogs. **Milestone M4: the graph is an explorable visual network.** FE-only.
- **Acceptance gate:** `scripts/raid/verify-cycle-19.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G5, no-new-graph-library, read-only
- **DPS count:** 2
- **Estimated wall time:** 4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C18
- Files expected to exist (grep-able paths): `frontend/src/**/GraphCanvas.tsx` (generic SVG layer), `frontend/src/**/RelationshipMap.tsx` (ego-network pattern to generalize), and C18's `GET /v1/knowledge/projects/{id}/subgraph` endpoint (must be DONE).

## Scope (IN)
- A project graph view that fetches C18's subgraph and renders it on `GraphCanvas`: nodes + edges, hand-rolled force/radial layout.
- **Pan / zoom**, **click a node → entity detail** (reuse existing entity detail UI), **expand-hop / load-more** to grow the subgraph within the node cap (re-query C18 with `center`/`hops`/`limit`).
- Generalize `RelationshipMap` (single-entity ego-network) into a reusable project-subgraph renderer — share the layout/interaction code, don't fork it.
- `scripts/raid/verify-cycle-19.sh` (acceptance gate — the runner creates it) + Playwright screenshots (built graph renders as a navigable network; expand-hop grows it).

## Scope (OUT — explicitly)
- **No new graph library** (no d3-force pkg, vis-network, cytoscape, reactflow, etc.) — hand-rolled on `GraphCanvas` only.
- **Read-only** — no node/edge editing on the canvas; editing reuses the existing entity/relation dialogs (no new edit surface).
- No BE changes — C18 owns the subgraph endpoint.
- No server-side layout — layout is computed FE.
- No living-world / derivative tree (that is C28, also reuses GraphCanvas but is a different surface).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `scripts/raid/verify-cycle-19.sh` exits 0 — asserts (1) the canvas renders nodes+edges from a subgraph payload (component test with a fixture), (2) pan/zoom + click→detail handlers wired, (3) expand-hop re-queries C18 (no full reload), (4) the node cap is respected (no unbounded render), (5) **no new graph-library import** added to package.json (grep guard).
- Lints pass: frontend `eslint` + `tsc` on touched files.
- Integration smoke: **Playwright MCP** (`claude-test@loreweave.dev`) — open a built project's graph → it renders as a navigable network; pan/zoom; click a node → detail; expand a hop. Screenshots filed. **M4 milestone screenshot.**

## DPS parallelism plan
- DPS 1: generalize `RelationshipMap` → project-subgraph renderer on `GraphCanvas` + hand-rolled layout + node-cap handling (return budget: 1500 tokens summary).
- DPS 2: interaction layer — pan/zoom, click→entity-detail, expand-hop/load-more re-query of C18; data hook (fetch + cache + merge expanded nodes).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **New graph library smuggled in:** any added package (cytoscape/reactflow/vis/d3-force) — LOCKED "no new graph library" violation; must stay on `GraphCanvas`.
- **Editing leak:** any write/mutation from the canvas — this is read-only; edits must go through existing dialogs.
- **Stateful unmount:** ternary-rendering the canvas on tab/route switch, destroying pan/zoom/layout state — use CSS hidden or internal branching (CLAUDE.md FE rule).
- **useEffect-for-events:** expand-hop fired from a `useEffect` reacting to state instead of the click handler.
- **Unbounded render:** ignoring the C18 node cap and trying to render a runaway subgraph → DOM/SVG perf collapse.
- **MVC drift:** fetch/merge logic inside the component instead of a hook.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (canvas renders subgraph, pan/zoom, click→detail, expand-hop, node cap)
- No OUT items touched (no new graph lib, no edit surface, no BE, no C28 living-world tree)
- All acceptance criteria met; `verify-cycle-19.sh` exits 0 + M4 Playwright screenshots filed
- Cross-cycle invariants not violated (read-only; reuse GraphCanvas)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C19 (Graph canvas, BL-18/KN-4, ▶ M4).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — G5 (reuse `GraphCanvas` + generalize `RelationshipMap`; pan/zoom/click→detail/expand-hop; node cap; no new graph library; read-only).
- Spec: `docs/specs/2026-06-13-writer-core-flow-P0.md`, `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** G5 → reuse `GraphCanvas` + generalize `RelationshipMap`; NO new graph library.
- 🔴 **Top LOCKED 2:** Read-only canvas → editing reuses existing entity/relation dialogs; no new edit surface.
- 🔴 **Top LOCKED 3:** Honour C18's node cap with expand-hop / load-more; don't render an unbounded subgraph.
- 🔴 **Acceptance MUST include:** `verify-cycle-19.sh` exit 0 (incl. no-new-graph-lib grep guard) AND M4 Playwright screenshots.
- 🔴 **Do NOT touch:** the C18 subgraph endpoint (BE), package.json graph deps, C28 living-world tree.
- 🔴 **Fresh session reminder:** this is a new `/raid 19` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
