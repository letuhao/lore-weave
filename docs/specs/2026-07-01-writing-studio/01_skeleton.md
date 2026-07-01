# 01 · Frame Skeleton

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: ✅ built 2026-07-01 (browser-verified).

## Scope

Build the **fixed frame** (khung) — every chrome region as a real component with working
mechanics — around the dockview centre. Navigator / dock / bottom **content is stubbed**;
real tools are separate later components. This is the shell everything else plugs into.

## Regions & responsibilities

| Region | File | Fixed? | This phase |
|---|---|---|---|
| Top bar | `StudioTopBar` | fixed | Back-to-book · brand + book title · command-palette affordance (disabled placeholder) · settings. Generate/Save/model come with the panels that need them. |
| Activity bar | `StudioActivityBar` | fixed | Icon rail: Manuscript / Bible / Search / Quality (+ Settings). Click switches the active navigator. Active styling. **Real.** |
| Side bar | `StudioSideBar` | fixed, collapsible | Header = active navigator name; body = a per-view **stub** ("built next"). Collapse hides it. **Frame real, content stub.** |
| Dock area | `StudioDock` | dockview | `DockviewReact` + Welcome panel + per-book layout persistence. **Real.** |
| Bottom panel | `StudioBottomPanel` | toggle | Tabs Jobs/Generation/Issues, stub bodies. Toggle from status bar; default collapsed. **Frame real, content stub.** |
| Status bar | `StudioStatusBar` | fixed | Save state · book language · a bottom-panel toggle · ⌘P hint. Informational placeholders where no data yet. |

## State (hooks)

- **`useStudioChrome(bookId)`** — the frame's UI state, persisted per-book
  (`lw_studio_chrome_<bookId>`, per-device):
  `{ activeView, setActiveView, sidebarCollapsed, toggleSidebar, bottomOpen, toggleBottom }`.
  `activeView: ActivityView = 'manuscript' | 'bible' | 'search' | 'quality'`.
- **`useStudioLayout(bookId)`** — owns the dockview `onReady`: register persist listener →
  restore `lw_studio_layout_<bookId>` (guarded) → else seed the Welcome panel. Returns the
  `onReady` handler + a ref to the `DockviewApi` (for future add-panel actions).

## MVC / structure rules (per CLAUDE.md)

- Components **render**; hooks own state. No conditional unmount of the dock (dockview stays
  mounted; the welcome panel persists). Side-bar collapse + bottom toggle use CSS/branching,
  never unmount the dock.
- Feature-folder layout: `features/studio/{components,hooks}`, `types.ts`. Page composes.

## Done-criteria (this phase)

1. `/books/:bookId/studio` renders the full frame; regions visually match the draft.
2. Activity bar switches the side-bar navigator (state persists across reload).
3. Side bar collapses/expands; bottom panel toggles; both persist.
4. dockview renders with the Welcome panel; layout persists per-book (existing behaviour kept).
5. tsc + eslint clean; production build OK; browser-smoke confirms the four mechanics above
   with 0 console errors.

## Explicitly deferred to later components

Real navigator content (Manuscript tree → #02), any real dock tool (→ #03+), command-palette
behaviour (→ #06), Generate/Save/model wiring (with the panels that need them), the
navigator→dock "open in group" interaction (with #02/#03).
