import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManuscriptNode, ManuscriptRow } from '../types';
import { PART_UNASSIGNED_ID } from '../partsTree';

// S-02 — the manuscript navigator's act (parts) affordances, tested against a mocked grouped
// tree (the data layer is covered by useManuscriptTree/partsTree tests). Kept in its OWN file so
// it doesn't touch the concurrently-edited ManuscriptNavigator.test.tsx.

vi.mock('@tanstack/react-virtual', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useVirtualizer: (opts: any) => ({
    getTotalSize: () => opts.count * 26,
    getVirtualItems: () => Array.from({ length: opts.count }, (_, index) => ({ index, start: index * 26, key: index })),
  }),
}));
const hook = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../useManuscriptTree', () => ({ useManuscriptTree: () => hook.value }));
const jump = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../useManuscriptJump', () => ({ useManuscriptJump: () => jump.value }));
// Capture sonner toasts (the undo-toast on trash).
const toastFn = vi.hoisted(() => vi.fn());
vi.mock('sonner', () => ({ toast: (...a: unknown[]) => toastFn(...a) }));

import { ManuscriptNavigator } from '../ManuscriptNavigator';

const partNode = (id: string, title: string, unassigned = false): ManuscriptNode => ({
  id, kind: 'part', title, number: null, status: unassigned ? 'unassigned' : null,
  chapterId: null, hasChildren: true, childCount: 1,
});
const chapNode = (id: string): ManuscriptNode => ({
  id, kind: 'chapter', title: `Ch ${id}`, number: 1, status: null, chapterId: id, hasChildren: false, childCount: null,
});
const row = (node: ManuscriptNode, depth: number): ManuscriptRow => ({ type: 'node', node, depth, expanded: true, loading: false });

const mutators = () => ({
  createAct: vi.fn(() => Promise.resolve()),
  renameAct: vi.fn(() => Promise.resolve()),
  trashAct: vi.fn(() => Promise.resolve()),
  moveChapterToAct: vi.fn(() => Promise.resolve()),
  moveAct: vi.fn(() => Promise.resolve()),
  restoreAct: vi.fn(() => Promise.resolve()),
});

const partRow2 = (id: string, sort: number, state: 'active' | 'trashed' = 'active') => ({ part_id: id, book_id: 'b', title: id, path: id, sort_order: sort, lifecycle_state: state });

const base = (m: ReturnType<typeof mutators>, rows: ManuscriptRow[], parts: ReturnType<typeof partRow2>[] = [], trashedActs: ReturnType<typeof partRow2>[] = []) => ({
  // Mirror the real hook: in a chapters-source (parts) book, counts.arcs is null — acts are
  // surfaced via `parts.length`, never counted as arcs.
  source: 'chapters', rows, total: 1, error: null, partsMode: true, parts, trashedActs,
  counts: { arcs: null, chapters: 1, scenes: null },
  toggleExpand: vi.fn(), loadMore: vi.fn(), collapseAll: vi.fn(), reload: vi.fn(), ...m,
});

beforeEach(() => {
  jump.value = { query: '', setQuery: vi.fn(), results: [], searching: false, active: false };
  toastFn.mockReset();
  vi.restoreAllMocks();
});

describe('ManuscriptNavigator — S-02 act affordances', () => {
  it('renders act group headers + a "New act" button; Unassigned bucket has no rename/trash', () => {
    const m = mutators();
    hook.value = base(m, [
      row(partNode('p1', 'Act I'), 0),
      row(chapNode('c1'), 1),
      row(partNode(PART_UNASSIGNED_ID, 'Unassigned', true), 0),
    ]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    expect(screen.getByTestId('manuscript-part-new')).toBeTruthy();
    expect(screen.getByTestId('manuscript-row-p1')).toBeTruthy();
    // real act → rename + trash affordances
    expect(screen.getByTestId('manuscript-part-rename-p1')).toBeTruthy();
    expect(screen.getByTestId('manuscript-part-trash-p1')).toBeTruthy();
    // Unassigned bucket → NOT editable
    expect(screen.queryByTestId(`manuscript-part-rename-${PART_UNASSIGNED_ID}`)).toBeNull();
    expect(screen.queryByTestId(`manuscript-part-trash-${PART_UNASSIGNED_ID}`)).toBeNull();
  });

  it('S-02c: New act → INLINE input (no prompt); Enter commits the trimmed title', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    const promptSpy = vi.spyOn(window, 'prompt');
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    fireEvent.click(screen.getByTestId('manuscript-part-new'));
    const input = screen.getByTestId('manuscript-part-new-input');
    fireEvent.change(input, { target: { value: '  Rising Action  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(m.createAct).toHaveBeenCalledWith('Rising Action'); // trimmed
    expect(promptSpy).not.toHaveBeenCalled();                  // no window.prompt
  });

  it('S-02c: New act → Esc cancels (no create, input gone)', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    fireEvent.click(screen.getByTestId('manuscript-part-new'));
    const input = screen.getByTestId('manuscript-part-new-input');
    fireEvent.change(input, { target: { value: 'Nope' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(m.createAct).not.toHaveBeenCalled();
    expect(screen.queryByTestId('manuscript-part-new-input')).toBeNull();
  });

  it('S-02c: rename → INLINE in-place edit (no prompt); Enter commits', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    const promptSpy = vi.spyOn(window, 'prompt');
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    fireEvent.click(screen.getByTestId('manuscript-part-rename-p1'));
    const input = screen.getByTestId('manuscript-part-rename-input-p1');
    fireEvent.change(input, { target: { value: 'Act One' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(m.renameAct).toHaveBeenCalledWith('p1', 'Act One');
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it('S-02c: footer counts acts as "act", never "arc"', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)], [partRow2('p1', 1)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    // test-i18n returns the raw key → the "act" stat renders via statActs, never statArcs.
    const totals = screen.getByTestId('manuscript-totals').textContent ?? '';
    expect(totals).toMatch(/statActs/);
    expect(totals).not.toMatch(/statArcs/);
  });

  it('S-02b: trash is INSTANT + UNDOABLE — no confirm, fires an undo toast whose action restores', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    const confirmSpy = vi.spyOn(window, 'confirm');
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    fireEvent.click(screen.getByTestId('manuscript-part-trash-p1'));
    expect(m.trashAct).toHaveBeenCalledWith('p1');
    expect(confirmSpy).not.toHaveBeenCalled();          // no blocking confirm
    expect(toastFn).toHaveBeenCalledTimes(1);           // undo toast shown
    // the toast carries an Undo action that restores the act
    const opts = toastFn.mock.calls[0][1] as { action?: { onClick?: () => void } };
    expect(opts.action).toBeTruthy();
    opts.action!.onClick!();
    expect(m.restoreAct).toHaveBeenCalledWith('p1');
  });

  it('S-02b: the Trashed-acts section lists trashed acts + Restore calls restoreAct', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)], [partRow2('p1', 1)], [partRow2('gone', 2, 'trashed')]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    expect(screen.getByTestId('manuscript-trashed-acts')).toBeTruthy();
    fireEvent.click(screen.getByTestId('manuscript-part-restore-gone'));
    expect(m.restoreAct).toHaveBeenCalledWith('gone');
  });

  it('no Trashed-acts section when there are none', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    expect(screen.queryByTestId('manuscript-trashed-acts')).toBeNull();
  });

  it('S-02b: ↑/↓ reorder buttons — only with ≥2 acts, disabled at the boundary, call moveAct', () => {
    const m = mutators();
    hook.value = base(m, [
      row(partNode('p1', 'Act I'), 0),
      row(partNode('p2', 'Act II'), 0),
    ], [partRow2('p1', 1), partRow2('p2', 2)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    // first act: up disabled, down enabled
    expect((screen.getByTestId('manuscript-part-up-p1') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('manuscript-part-down-p1') as HTMLButtonElement).disabled).toBe(false);
    // last act: down disabled
    expect((screen.getByTestId('manuscript-part-down-p2') as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByTestId('manuscript-part-down-p1'));
    expect(m.moveAct).toHaveBeenCalledWith('p1', 'down');
  });

  it('S-02b: a single act shows NO reorder buttons (nothing to reorder)', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)], [partRow2('p1', 1)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    expect(screen.queryByTestId('manuscript-part-up-p1')).toBeNull();
    expect(screen.queryByTestId('manuscript-part-down-p1')).toBeNull();
  });

  it('S-02c: an empty act shows a "drag chapters here" hint; a non-empty act does not', () => {
    const m = mutators();
    const emptyAct: ManuscriptNode = { id: 'pe', kind: 'part', title: 'Empty', number: null, status: null, chapterId: null, hasChildren: false, childCount: 0 };
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0), row(emptyAct, 0)], [partRow2('p1', 1), partRow2('pe', 2)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    expect(screen.getByTestId('manuscript-part-empty-hint-pe')).toBeTruthy();
    expect(screen.queryByTestId('manuscript-part-empty-hint-p1')).toBeNull(); // has a chapter → no hint
  });

  it('S-02c: dragging a chapter over an act highlights it (drop-target ring); leaving clears it', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0), row(chapNode('c1'), 1)], [partRow2('p1', 1)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    const actRow = screen.getByTestId('manuscript-row-p1');
    fireEvent.dragStart(screen.getByTestId('manuscript-row-c1'));
    fireEvent.dragEnter(actRow);
    expect(actRow.className).toMatch(/ring-primary/);
    fireEvent.dragLeave(actRow);
    expect(actRow.className).not.toMatch(/ring-primary/);
  });

  it('S-02c: the New-act button is labeled "Act" (not just an icon beside the Plan +)', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    // test-i18n returns the raw key → the button carries the actShort label (not icon-only).
    expect(screen.getByTestId('manuscript-part-new').textContent).toMatch(/actShort/);
  });

  it('drag a chapter onto an act → moveChapterToAct(chapterId, partId); onto Unassigned → null', () => {
    const m = mutators();
    hook.value = base(m, [
      row(partNode('p1', 'Act I'), 0),
      row(chapNode('c1'), 1),
      row(partNode(PART_UNASSIGNED_ID, 'Unassigned', true), 0),
    ]);
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    // drag c1 onto Act I
    fireEvent.dragStart(screen.getByTestId('manuscript-row-c1'));
    fireEvent.drop(screen.getByTestId('manuscript-row-p1'));
    expect(m.moveChapterToAct).toHaveBeenCalledWith('c1', 'p1');

    // drag c1 onto Unassigned → un-home (null)
    fireEvent.dragStart(screen.getByTestId('manuscript-row-c1'));
    fireEvent.drop(screen.getByTestId(`manuscript-row-${PART_UNASSIGNED_ID}`));
    expect(m.moveChapterToAct).toHaveBeenLastCalledWith('c1', null);
  });
});
