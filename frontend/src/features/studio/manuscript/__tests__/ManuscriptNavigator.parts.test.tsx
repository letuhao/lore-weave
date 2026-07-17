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
});

const base = (m: ReturnType<typeof mutators>, rows: ManuscriptRow[]) => ({
  source: 'chapters', rows, total: 1, error: null, partsMode: true,
  counts: { arcs: 1, chapters: 1, scenes: null },
  toggleExpand: vi.fn(), loadMore: vi.fn(), collapseAll: vi.fn(), reload: vi.fn(), ...m,
});

beforeEach(() => {
  jump.value = { query: '', setQuery: vi.fn(), results: [], searching: false, active: false };
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

  it('New act → prompts + calls createAct with the entered title', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    vi.spyOn(window, 'prompt').mockReturnValue('  Rising Action  ');
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    fireEvent.click(screen.getByTestId('manuscript-part-new'));
    expect(m.createAct).toHaveBeenCalledWith('Rising Action'); // trimmed
  });

  it('rename → calls renameAct; trash (confirmed) → calls trashAct', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    vi.spyOn(window, 'prompt').mockReturnValue('Act One');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ManuscriptNavigator bookId="b1" token="t" />);

    fireEvent.click(screen.getByTestId('manuscript-part-rename-p1'));
    expect(m.renameAct).toHaveBeenCalledWith('p1', 'Act One');
    fireEvent.click(screen.getByTestId('manuscript-part-trash-p1'));
    expect(m.trashAct).toHaveBeenCalledWith('p1');
  });

  it('trash CANCELLED → does not call trashAct', () => {
    const m = mutators();
    hook.value = base(m, [row(partNode('p1', 'Act I'), 0)]);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<ManuscriptNavigator bookId="b1" token="t" />);
    fireEvent.click(screen.getByTestId('manuscript-part-trash-p1'));
    expect(m.trashAct).not.toHaveBeenCalled();
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
