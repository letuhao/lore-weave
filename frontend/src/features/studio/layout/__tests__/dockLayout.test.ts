import { describe, it, expect, vi } from 'vitest';
import { distribute, planGrid, reflowDockGrid, isPresetTooNarrow, LAYOUT_PRESETS, MIN_COLUMN_PX } from '../dockLayout';

describe('distribute', () => {
  it('splits balanced with the remainder on the earliest cells', () => {
    expect(distribute(4, 2)).toEqual([2, 2]);
    expect(distribute(5, 2)).toEqual([3, 2]);
    expect(distribute(7, 3)).toEqual([3, 2, 2]);
    expect(distribute(1, 3)).toEqual([1, 0, 0]);
  });
  it('degenerate inputs → empty', () => {
    expect(distribute(0, 3)).toEqual([]);
    expect(distribute(4, 0)).toEqual([]);
  });
});

describe('planGrid', () => {
  it('N columns, 1 row: one cell per column, balanced', () => {
    expect(planGrid(4, 2, 1)).toEqual({ cells: [2, 2], colCount: 2, rowsPerCol: [1, 1] });
  });
  it('2×2 grid of 4 → four single-panel cells in two columns', () => {
    expect(planGrid(4, 2, 2)).toEqual({ cells: [1, 1, 1, 1], colCount: 2, rowsPerCol: [2, 2] });
  });
  it('never makes an empty cell: 3 panels into an 8-col preset → 3 columns', () => {
    const p = planGrid(3, 8, 1);
    expect(p.colCount).toBe(3);
    expect(p.cells).toEqual([1, 1, 1]);
    expect(p.rowsPerCol).toEqual([1, 1, 1]);
  });
  it('uneven grid: 5 panels into 3×2 → last column has one row', () => {
    const p = planGrid(5, 3, 2);
    expect(p.colCount).toBe(3);
    expect(p.rowsPerCol).toEqual([2, 2, 1]); // column-major: 2 + 2 + 1 = 5 cells
    expect(p.cells).toEqual([1, 1, 1, 1, 1]);
  });
});

/** A fake DockviewApi recording moveTo + addGroup so the reflow can be asserted with no real DOM. */
function makeFakeApi(n: number) {
  let seq = 0;
  const mkGroup = () => ({ id: `g${seq++}` });
  const anchor = mkGroup();
  const moves: Array<{ panel: number; group: string; index: number }> = [];
  const addGroup = vi.fn((opts: { direction: string }) => {
    const g = mkGroup();
    (addGroup.calls ||= []).push({ id: g.id, direction: opts.direction });
    return g;
  }) as unknown as ReturnType<typeof vi.fn> & { calls?: Array<{ id: string; direction: string }> };

  const panels = Array.from({ length: n }, (_, i) => {
    const p: {
      idx: number;
      group: { id: string };
      api: { moveTo: (o: { group: { id: string }; index: number }) => void; setActive: () => void };
    } = {
      idx: i,
      group: anchor,
      api: {
        moveTo: ({ group, index }) => { p.group = group; moves.push({ panel: i, group: group.id, index }); },
        setActive: vi.fn(),
      },
    };
    return p;
  });

  const api = {
    get panels() { return panels; },
    activePanel: panels[0],
    addGroup,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
  return { api, panels, moves, addGroup, anchor };
}

/** Group-id → count of panels currently in it (reads each panel's live `.group`, so it counts
 * panels the guard left in place as well as moved ones). */
function finalGroups(panels: Array<{ group: { id: string } }>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const p of panels) counts[p.group.id] = (counts[p.group.id] ?? 0) + 1;
  return counts;
}

describe('reflowDockGrid', () => {
  it('is a no-op for fewer than 2 panels', () => {
    const { api, moves, addGroup } = makeFakeApi(1);
    reflowDockGrid(api, 2, 1);
    expect(moves).toEqual([]);
    expect(addGroup).not.toHaveBeenCalled();
  });

  it('4 panels → 2 columns: one new group, two cells of two panels', () => {
    const { api, panels, addGroup } = makeFakeApi(4);
    reflowDockGrid(api, 2, 1);
    expect(addGroup).toHaveBeenCalledTimes(1);
    expect(addGroup.mock.calls[0][0]).toMatchObject({ direction: 'right' });
    const counts = Object.values(finalGroups(panels)).sort();
    expect(counts).toEqual([2, 2]); // two cells, two panels each
    expect(Object.keys(finalGroups(panels))).toHaveLength(2);
  });

  it('4 panels → 2×2 grid: three new groups, four single-panel cells', () => {
    const { api, panels, addGroup } = makeFakeApi(4);
    reflowDockGrid(api, 2, 2);
    expect(addGroup).toHaveBeenCalledTimes(3);
    // one column split (right) + two row splits (below)
    const dirs = addGroup.mock.calls.map((c) => (c[0] as { direction: string }).direction).sort();
    expect(dirs).toEqual(['below', 'below', 'right']);
    expect(Object.values(finalGroups(panels))).toEqual([1, 1, 1, 1]);
  });

  it('3 panels into an 8-column preset → 3 columns (no empty cells)', () => {
    const { api, panels, addGroup } = makeFakeApi(3);
    reflowDockGrid(api, 8, 1);
    expect(addGroup).toHaveBeenCalledTimes(2); // anchor + 2 = 3 columns
    expect(Object.keys(finalGroups(panels))).toHaveLength(3);
  });

  it('merge-to-single: a panel already in the target cell is NOT self-moved (dock-empty bug guard)', () => {
    // Simulate the post-cols2 state: two panels each ALONE in its own group. Reflowing to a single
    // cell must merge them without moving panel[0] into its own group (which dockview would empty→
    // remove mid-move, orphaning everything → empty dock, caught in live smoke).
    let seq = 0;
    const g = () => ({ id: `g${seq++}` });
    const gA = g(), gB = g();
    const moves: Array<{ panel: number; group: string }> = [];
    const p0 = { group: gA, api: { moveTo: vi.fn((o: { group: { id: string } }) => { p0.group = o.group; moves.push({ panel: 0, group: o.group.id }); }), setActive: vi.fn() } };
    const p1 = { group: gB, api: { moveTo: vi.fn((o: { group: { id: string } }) => { p1.group = o.group; moves.push({ panel: 1, group: o.group.id }); }), setActive: vi.fn() } };
    const panels = [p0, p1];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const api = { get panels() { return panels; }, activePanel: p0, addGroup: vi.fn(g) } as any;

    reflowDockGrid(api, 1, 1);
    expect(p0.api.moveTo).not.toHaveBeenCalled();   // already in the anchor (gA) → no self-move
    expect(p1.api.moveTo).toHaveBeenCalledTimes(1);  // relocated into gA
    expect(p1.group.id).toBe('g0');                  // gA
    expect(api.addGroup).not.toHaveBeenCalled();     // single = one column, no new groups
  });

  it('restores the previously-active panel', () => {
    const { api, panels } = makeFakeApi(4);
    api.activePanel = panels[2];
    reflowDockGrid(api, 2, 1);
    expect(panels[2].api.setActive).toHaveBeenCalledTimes(1);
    expect(panels[0].api.setActive).not.toHaveBeenCalled();
  });
});

describe('isPresetTooNarrow', () => {
  const cols4 = LAYOUT_PRESETS.find((p) => p.id === 'cols4')!;
  it('flags when columns would fall below the comfortable minimum', () => {
    expect(isPresetTooNarrow(cols4, MIN_COLUMN_PX * 4 - 1)).toBe(true);
    expect(isPresetTooNarrow(cols4, MIN_COLUMN_PX * 4 + 100)).toBe(false);
  });
  it('unknown/zero width never flags (avoid a false disable before measure)', () => {
    expect(isPresetTooNarrow(cols4, 0)).toBe(false);
    expect(isPresetTooNarrow(cols4, Number.NaN)).toBe(false);
  });
});
