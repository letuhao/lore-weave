# Writing Studio (v2) — Master Spec

> **Status:** ACTIVE · branch `feat/writing-studio` · started 2026-07-01
> **Type:** FE, from-scratch. Does **not** touch the current `ChapterEditorPage`.

## What this is

A new, VS Code–style **docking workspace for a whole book** — the successor surface to the
chaotic 24-tab co-writer studio. dockview owns the centre (drag / split / stack / float /
pop-out); a fixed frame of chrome (activity bar, side-bar navigators, top/status bars, a
toggle bottom panel) wraps it. Panels (the real writing tools) are added **one at a time**.

Frame reference mockup: [`design-drafts/screens/studio/screen-writing-studio-frame.html`](../../../design-drafts/screens/studio/screen-writing-studio-frame.html).

## How we work here — build-while-plan (LOCKED)

This track deliberately **inverts** the usual plan-then-build. We build incrementally and
spec **just-in-time**:

- This **master file** holds the durable decisions, the frame architecture, and the
  **component index** (below) with per-component status.
- Each component gets its **own small spec file** (`NN_<component>.md`) written when we start
  it — scope, data, states, done-criteria — not a big upfront plan.
- A component is only as specced as it is built. Specs grow with the code, never ahead of it.

## Locked decisions

| # | Decision | Why |
|---|---|---|
| D1 | **dockview-react v7** owns the centre dock | Our in-house dock layer is a single linear rail — can't do splits/tab-groups/regions. dockview = VS Code-grade, zero-dep, MIT, React-18. |
| D2 | New route `/books/:bookId/studio`, book-level (no chapter needed) | It's a whole-book workspace; a book-level "Studio" CTA opens it. |
| D3 | From scratch — reuse shared components + the state-hoist blueprint, **not** the current editor | Easier to control a clean build than retrofit the editor. |
| D4 | **Live/in-flight state lives ABOVE dockview**; panels are thin views over hoisted state | dockview unmounts a closed panel; hoisting keeps co-writer streams / editor docs alive so closing/moving a panel never drops work. Wire when the first *stateful* panel lands. |
| D5 | Fixed chrome (top bar, activity bar, side bar, status bar) is **never** a dock tab; bottom panel is a toggle | Navigation is the spine — it must never be floated, buried, or accidentally closed. |
| D6 | Layout + chrome UI state persist **per-book** in localStorage (per-device) | `lw_studio_layout_<bookId>` (dockview `toJSON`) + `lw_studio_chrome_<bookId>` (active view / collapses). |

## Frame regions

```
┌ Top bar (fixed) ───────────────────────────────────────────────┐
│ Act │ Side bar (fixed) │ Dock area (dockview) ▸ split/float/pop │
│ bar │  active navigator │──────────────────────────────────────│
│     │                   │ Bottom panel (toggle)                 │
├ Status bar (fixed) ────────────────────────────────────────────┤
```

The Side-Bar navigator **drives the dock**: selecting a unit opens/focuses its panel in a
dock group (Explorer → editor-group analogue).

## Component index

| # | Component | Spec | Status |
|---|---|---|---|
| 01 | **Frame skeleton** — all fixed regions + dockview shell, mechanics working, content stubbed | [`01_skeleton.md`](01_skeleton.md) | ✅ built |
| 02 | Manuscript navigator (chapters→scenes, drives the dock) | — | ⏳ **next** |
| 03 | Compose panel (co-writer, first stateful dock panel → wires D4) | — | ⏳ |
| 04 | Manuscript editor panel | — | ⏳ |
| 05 | Story-Bible navigator + detail panel | — | ⏳ |
| 06 | Command palette (⌘P: jump to chapter/scene/tool) | — | ⏳ |
| … | Search nav · Quality nav · Jobs/Generation/Issues bottom panels · Planner/Cast/Timeline/… | — | ⏳ |

*(Rows are added/promoted as we go. Order is a guide, not a contract — the human directs which is next.)*

## Testing discipline (LOCKED — this track is stricter than the rest)

**Build-to-solid, no defer.** Every component ships with tests before we move on:

1. **Unit tests** for each component + hook (states, branches, persistence, guards).
2. **E2E** for each component's user-visible behaviour, via a Playwright spec + page object.
3. **Inter-component links:** build the **data link first** (the wiring in code + unit tests).
   **Defer only the E2E of that link** until the *other* component exists — then add it. Record
   the deferred E2E-link on the **Debt stack** below.
4. Each milestone ends with **`/review-impl`** (adversarial) → fix → re-run all tests.

**Debt is a STACK, not a queue — newest debt is paid FIRST (LIFO).** Every deferral is
recorded here the moment it's created; when we start the next component we clear the top of
the stack before adding new rows.

## Debt stack (LIFO — top = paid next)

| ▲ | From | Debt | Clears when |
|---|---|---|---|
| 1 | 01 skeleton | **navigator→dock "open in group" link** — data wiring + its E2E deferred | #02 Manuscript navigator + #03 a dock panel exist → build the link + E2E it |
| 2 | 01 skeleton | Top-bar **Generate / Save / model** controls not built | the first panel that needs them (#03 Compose) |

**Recently cleared:** ~~Studio inherited `EditorLayout`'s app rail → two left rails~~ → **fixed
2026-07-01**: studio moved to a standalone full-screen `RequireAuth` route (out of `EditorLayout`);
`StudioFrame` root is `h-screen`. The Activity Bar is now the only left rail.

*(Pop the top when starting the next component; push any new deferral on top. Nothing leaves
this table silently — it's cleared by building, not by forgetting.)*

## Out of scope (for now)

Mobile (the studio is desktop-first; small screens fall back to the existing editor); server
sync of layout (localStorage per-device is enough until multi-device studio is needed);
migrating the old co-writer studio (it stays until the new one reaches parity).
