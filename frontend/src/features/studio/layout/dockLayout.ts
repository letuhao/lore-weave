// Programmatic dock layouts for the Studio — arrange the OPEN dockview panels into an N-column
// or C×R grid, the way VS Code's "Editor Layout" menu arranges editor groups. dockview supports
// unlimited splits natively; this just gives users a one-click way to reach a wide grid on an
// ultrawide screen instead of hand-dragging to ~2×2. Pure over the dockview API so it is unit-
// testable with a fake api (no real DOM).
import type { DockviewApi, DockviewGroupPanel, IDockviewPanel } from 'dockview-react';

/** A layout preset = a target grid. `rows: 1` is a pure column layout. `id` is stable for i18n +
 * test selection; `glyph` is the cols×rows the picker draws. */
export interface LayoutPreset {
  id: string;
  cols: number;
  rows: number;
}

/** The presets the picker offers, ordered narrow → wide. Columns cover the ultrawide ask (up to
 * 8); the 2-row grids cover the classic "2 rows" arrangement. */
export const LAYOUT_PRESETS: readonly LayoutPreset[] = [
  { id: 'single', cols: 1, rows: 1 },
  { id: 'cols2', cols: 2, rows: 1 },
  { id: 'cols3', cols: 3, rows: 1 },
  { id: 'cols4', cols: 4, rows: 1 },
  { id: 'grid2x2', cols: 2, rows: 2 },
  { id: 'grid3x2', cols: 3, rows: 2 },
  { id: 'grid4x2', cols: 4, rows: 2 },
  { id: 'cols6', cols: 6, rows: 1 },
  { id: 'cols8', cols: 8, rows: 1 },
];

/** The minimum comfortable width (px) for one dock column. A preset whose columns would be
 * narrower than this on the current dock is offered but flagged (soft ultrawide guard). */
export const MIN_COLUMN_PX = 200;

/** Balanced distribution of `n` items across `buckets` cells: each cell gets floor(n/buckets),
 * and the first `n % buckets` cells get one extra. Pure — the core of the reflow, unit-tested. */
export function distribute(n: number, buckets: number): number[] {
  if (buckets <= 0 || n <= 0) return [];
  const base = Math.floor(n / buckets);
  const extra = n % buckets;
  return Array.from({ length: buckets }, (_, i) => base + (i < extra ? 1 : 0));
}

/**
 * Plan the (col, row) cell layout for `n` panels into a `cols`×`rows` grid, column-major, never
 * creating an empty cell (so 3 panels into a 4-col preset yields 3 columns, not 4). Returns the
 * per-cell panel counts plus the shape, so `reflowDockGrid` can drive the imperative moves and a
 * test can assert the shape without a dockview instance.
 */
export function planGrid(n: number, cols: number, rows: number): { cells: number[]; colCount: number; rowsPerCol: number[] } {
  const c = Math.max(1, Math.floor(cols));
  const r = Math.max(1, Math.floor(rows));
  if (n <= 0) return { cells: [], colCount: 0, rowsPerCol: [] };
  const cellTarget = Math.min(c * r, n);            // never more cells than panels
  const counts = distribute(n, cellTarget);         // panels per cell, balanced
  const colCount = Math.ceil(cellTarget / r);       // columns actually used
  // Cells are numbered column-major: column k owns cells [k*r, k*r + rowsPerCol[k]).
  const rowsPerCol = Array.from({ length: colCount }, (_, k) => Math.min(r, cellTarget - k * r));
  return { cells: counts, colCount, rowsPerCol };
}

/**
 * Rearrange the open dock panels into a `cols`×`rows` grid. No-op for <2 panels (nothing to
 * arrange). Reuses the first panel's group as the top-left cell; every other cell is a fresh
 * group created to the right (new column) or below (new row within a column). dockview auto-
 * removes the groups we empty out, so no manual cleanup. The previously-active panel stays active.
 */
export function reflowDockGrid(api: DockviewApi, cols: number, rows: number): void {
  const panels: IDockviewPanel[] = [...api.panels];
  const n = panels.length;
  if (n < 2) return; // one panel (or none) is already "arranged"

  const active = api.activePanel ?? null;
  const { cells, colCount, rowsPerCol } = planGrid(n, cols, rows);
  if (colCount === 0) return;

  const anchor: DockviewGroupPanel = panels[0].group; // top-left cell reuses this group
  let panelIdx = 0;
  let cellIdx = 0;
  let prevColTop: DockviewGroupPanel = anchor;

  for (let col = 0; col < colCount; col++) {
    // The top cell of each column: column 0 reuses the anchor; later columns open to the right.
    const colTop: DockviewGroupPanel = col === 0
      ? anchor
      : api.addGroup({ referenceGroup: prevColTop, direction: 'right' });
    prevColTop = colTop;

    let prevCellInCol: DockviewGroupPanel = colTop;
    for (let row = 0; row < rowsPerCol[col]; row++) {
      const cellGroup: DockviewGroupPanel = row === 0
        ? colTop
        : api.addGroup({ referenceGroup: prevCellInCol, direction: 'below' });
      prevCellInCol = cellGroup;

      const count = cells[cellIdx] ?? 0;
      for (let k = 0; k < count; k++) {
        // Skip a panel already in its target cell. Moving a panel into its OWN group when it is the
        // sole occupant makes dockview empty→auto-remove that group mid-move, orphaning the panel
        // (and cascading to an empty dock — caught in live smoke on the merge-to-single path).
        if (panels[panelIdx].group !== cellGroup) {
          panels[panelIdx].api.moveTo({ group: cellGroup, index: k });
        }
        panelIdx++;
      }
      cellIdx++;
    }
  }

  active?.api.setActive();
}

/** Would this preset squeeze columns below the comfortable minimum on a dock of `dockWidth` px?
 * Used to flag (not block) presets that only make sense on a wider screen. */
export function isPresetTooNarrow(preset: LayoutPreset, dockWidth: number): boolean {
  if (!Number.isFinite(dockWidth) || dockWidth <= 0) return false; // unknown width → don't flag
  return dockWidth / preset.cols < MIN_COLUMN_PX;
}
