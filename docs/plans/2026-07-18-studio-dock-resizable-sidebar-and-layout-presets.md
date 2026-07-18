# Plan — Studio dock: resizable manuscript sidebar + panel-layout presets (ultrawide)

> **Size L · FE-only** (book-service untouched). No API/DB/auth/contract change — only per-device
> UI state in localStorage (CLAUDE.md: per-device UI state = localStorage, not server). Goal: the
> manuscript left sidebar becomes width-resizable like a real dock panel, and a toolbar palette
> icon opens a layout-preset picker that arranges the open dock panels into N columns / grids
> (well beyond the 2×2 users can reach by hand today) for ultrawide screens.

## Prior art (web-searched)
- **VS Code "Editor Layout" menu** — the canonical model: Two/Three Columns, Grid (2×2), and a
  grid system that scales to up to 9 editor groups, adjustable by dragging the sash. A menu of
  visual preset glyphs that programmatically arrange editor *groups*. We mirror this exactly.
  (https://code.visualstudio.com/docs/configure/custom-layout)
- **Layout-type control popover** — a small non-blocking panel of visual layout options anchored
  to a toolbar trigger, dismiss-on-outside-click. That's our picker shell.

## Why "2×2 only" today
The studio dock is **dockview** (`dockview-react` ^7), which supports *unlimited* drag-split grids
already — there is no 2×2 code cap. The ceiling is purely **discoverability**: there's no UI to
build a wide grid, so users hand-drag to ~2×2 and stop. We add the missing UI; the engine already
supports it.

## Current architecture (verified)
- `StudioFrame` → `[ StudioActivityBar | StudioSideBar (w-[250px] FIXED, outside dockview) | StudioDock (dockview) ]`.
- `StudioSideBar` — plain flex child, hardcoded `w-[250px] flex-shrink-0` → **not resizable** (complaint #1).
- `useStudioChrome(bookId)` — per-book localStorage `lw_studio_chrome_<bookId>`: `{activeView, sidebarCollapsed, bottomOpen}`.
- `useStudioLayout(bookId)` — dockview `api.toJSON()` persisted per-book `lw_studio_layout_<bookId>`; auto-restores.
- `StudioHostProvider` — exposes `_dockApiRef: MutableRefObject<DockviewApi>` + `openPanel`. The seam for a new `applyDockLayout`.
- `StudioTopBar` — right side has room for one more icon (next to Settings).
- dockview v7 API confirmed: `api.panels`, `api.groups`, `api.addGroup({referenceGroup, direction:'right'|'below'})`,
  `panel.api.moveTo({group, index})`, `api.activePanel`. **Emptied groups auto-remove** (default) — so a reflow that
  moves every panel into new cells lets the old groups vanish; no manual cleanup.

## SEALED DECISIONS

### Sidebar resize (A)
- **A1** Add `sidebarWidth: number` to chrome state (default **260**), persisted per-book in the SAME
  `lw_studio_chrome_<bookId>` blob. Per-device UI state ⇒ localStorage (matches the existing chrome pattern).
- **A2** A **6px drag handle** on the sidebar's right edge (`cursor-col-resize`, hover-highlight). Pointer-drag
  (pointerdown→setPointerCapture→pointermove) updates width **live**; **persist on pointerup only** (avoid a
  localStorage write per mouse-move). Delta model: `newW = startW + (e.clientX - startX)`, clamp **[200, 640]**.
- **A3** During drag: `user-select:none` + a transparent full-window overlay so the pointer can't get eaten by
  an iframe/panel; released on pointerup. Double-click the handle → reset to default 260.
- **A4** Collapsed sidebar (existing `sidebarCollapsed`) is unaffected — the handle only renders when the sidebar does.

### Layout presets (B)
- **B1** A **palette/grid icon** (`LayoutGrid`) in `StudioTopBar` (left of Settings) → a **popover** of preset glyphs.
- **B2** Presets = `(cols, rows)`: **1-col, 2-col, 3-col, 4-col** (row=1), **2×2, 3×2, 4×2** (row=2), **6-col, 8-col** (row=1).
  Each renders a mini SVG glyph + label. A "columns" preset is just `rows=1`.
- **B3** `applyDockLayout(cols, rows)` (host seam) → pure `reflowDockGrid(api, cols, rows)` in `dockLayout.ts`:
  - Snapshot `panels = [...api.panels]` (order) + `active = api.activePanel`.
  - `cells = min(cols*rows, n)`; column-major fill. `colCount = ceil(cells/rows)`.
  - Column 0's top cell REUSES `panels[0].group` (the anchor). New columns via `addGroup({referenceGroup: prevColTop, direction:'right'})`;
    extra rows within a column via `addGroup({referenceGroup: prevCellInCol, direction:'below'})`.
  - Panels distributed **balanced** across cells (earlier cells get the remainder). `moveTo({group, index})` in order.
  - Restore `active?.api.setActive()`. Old emptied groups auto-remove.
  - Guards: `n===0` → no-op; `n===1` → single-cell no-op; `cols<1` → clamp 1.
- **B4** **Soft ultrawide guard:** a preset whose per-column width (`api.width / cols`) would be **< 200px** renders
  **disabled** with a tooltip ("needs a wider window"). Never blocks — just guides. `api.width` read at open.
- **B5** The picker also shows a live line: "Arranges your **N** open panels." If `N<2`, all multi-cell presets
  disabled with "Open more panels first." The dock layout persists via the existing `onDidLayoutChange` writer — no new persistence.

### Out of scope / by-design
- No new server state, no cross-book sync of width/layout (per-device by design).
- No free-form grid editor (drag cells to arbitrary spans) — presets + the existing native drag-split cover it.
- Reflow does NOT touch the manuscript sidebar or bottom panel — only dockview panels.

## SLICES (build + QC each: tsc + vitest + commit)
- **S1 · sidebar resize** — chrome `sidebarWidth`+`setSidebarWidth`; `useSidebarResize` hook; StudioSideBar handle; StudioFrame wiring. Tests: clamp math, persist-on-commit, default+reset.
- **S2 · reflow util** — `dockLayout.ts` `reflowDockGrid` + `LAYOUT_PRESETS`. Tests (mocked DockviewApi): column count, balanced distribution, grid cells, n<2 guard, active restored.
- **S3 · picker + icon + seam** — `host.applyDockLayout`; `LayoutPicker` popover; `StudioLayoutButton` in TopBar. Tests: preset click → applyDockLayout(cols,rows); disabled state for n<2 / narrow width.
- **S4 · i18n + QC + live smoke** — 18-locale keys via i18n_translate.py; full studio vitest + tsc; live smoke on :5199 (resize the sidebar; apply a 4-col preset with ≥4 panels open).

## Evidence log
- (pending)
