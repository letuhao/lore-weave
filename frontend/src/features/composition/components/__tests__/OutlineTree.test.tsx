import { render, screen, fireEvent, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OutlineTree, flattenOutline, computeReorder } from '../OutlineTree';
import type { OutlineNode } from '../../types';

// Mock the work-resolution + outline read/mutation hooks and the toast. The
// component resolves the Work from bookId, reads GET /outline, and (T1.1b) drives
// node CRUD via useOutlineMutations. Tests assert tree-build, nav, current
// marker, empty, collapse, and the CRUD wiring (rename/add-child/archive/status)
// + the 412-conflict path, via test-ids/attributes (real i18n → defaultValues).
const { workHook, outlineHook, mutations, toastWarn, toastError } = vi.hoisted(() => ({
  workHook: vi.fn(),
  outlineHook: vi.fn(),
  mutations: {
    rename: { mutate: vi.fn() },
    setStatus: { mutate: vi.fn() },
    editCard: { mutate: vi.fn() },
    addChild: { mutate: vi.fn() },
    archive: { mutate: vi.fn() },
    restore: { mutate: vi.fn() },
    reorder: { mutate: vi.fn() },
    invalidate: vi.fn(),
  },
  toastWarn: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('../../hooks/useWork', () => ({ useWorkResolution: () => workHook() }));
vi.mock('../../hooks/useOutline', () => ({
  useOutline: (...a: unknown[]) => outlineHook(...a),
  useOutlineMutations: () => mutations,
}));
vi.mock('sonner', () => ({ toast: { warning: (...a: unknown[]) => toastWarn(...a), error: (...a: unknown[]) => toastError(...a) } }));

function node(over: Partial<OutlineNode>): OutlineNode {
  return {
    id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'T',
    chapter_id: null, story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, ...over,
  };
}

function mountWith(nodes: OutlineNode[]) {
  workHook.mockReturnValue({ data: { status: 'found', work: { project_id: 'proj' } }, isLoading: false });
  outlineHook.mockReturnValue({ data: nodes, isLoading: false });
}

beforeEach(() => {
  workHook.mockReset();
  outlineHook.mockReset();
  mutations.rename.mutate.mockReset();
  mutations.setStatus.mutate.mockReset();
  mutations.addChild.mutate.mockReset();
  mutations.archive.mutate.mockReset();
  mutations.restore.mutate.mockReset();
  mutations.reorder.mutate.mockReset();
  mutations.editCard.mutate.mockReset();
  mutations.invalidate.mockReset();
  toastWarn.mockReset();
  toastError.mockReset();
});

describe('flattenOutline (T1.1a)', () => {
  it('builds a depth-annotated pre-order tree ordered by story_order', () => {
    const nodes = [
      node({ id: 'arc', kind: 'arc', parent_id: null, story_order: 0 }),
      node({ id: 'ch1', kind: 'chapter', parent_id: 'arc', story_order: 0 }),
      node({ id: 's2', kind: 'scene', parent_id: 'ch1', story_order: 1, title: 'S2' }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', story_order: 0, title: 'S1' }),
    ];
    const rows = flattenOutline(nodes, new Set());
    expect(rows.map((r) => r.node.id)).toEqual(['arc', 'ch1', 's1', 's2']); // s1 before s2 by story_order
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 2, 2]);
    expect(rows.find((r) => r.node.id === 'arc')!.hasChildren).toBe(true);
    expect(rows.find((r) => r.node.id === 's1')!.hasChildren).toBe(false);
  });

  it('collapsing a parent skips its children', () => {
    const nodes = [
      node({ id: 'ch1', kind: 'chapter', parent_id: null, story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', story_order: 0 }),
    ];
    expect(flattenOutline(nodes, new Set(['ch1'])).map((r) => r.node.id)).toEqual(['ch1']);
  });

  it('orders siblings without story_order by rank (chapters), nulls last (REVIEW-IMPL MED-3)', () => {
    const nodes = [
      node({ id: 'arc', kind: 'arc', parent_id: null, story_order: null, rank: 'a' }),
      node({ id: 'chB', kind: 'chapter', parent_id: 'arc', story_order: null, rank: 'b' }),
      node({ id: 'chA', kind: 'chapter', parent_id: 'arc', story_order: null, rank: 'a' }),
      // a legacy scene with a story_order sorts before its null-story_order sibling
      node({ id: 'sNull', kind: 'scene', parent_id: 'chA', story_order: null, rank: 'a' }),
      node({ id: 'sOrd', kind: 'scene', parent_id: 'chA', story_order: 5, rank: 'z' }),
    ];
    const rows = flattenOutline(nodes, new Set());
    expect(rows.map((r) => r.node.id)).toEqual(['arc', 'chA', 'sOrd', 'sNull', 'chB']);
  });

  it('renders a duplicate id only once (defensive seen-guard)', () => {
    const dup = node({ id: 'x', parent_id: null });
    expect(flattenOutline([dup, dup], new Set()).filter((r) => r.node.id === 'x')).toHaveLength(1);
  });
});

describe('OutlineTree (T1.1a)', () => {
  it('renders rows + navigates to a node\'s chapter on click', () => {
    mountWith([node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', title: 'Ch One', story_order: 0 })]);
    const onNav = vi.fn();
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={onNav} />);
    const rows = screen.getAllByTestId('outline-node');
    expect(rows.length).toBeGreaterThan(0);
    fireEvent.click(rows[0]);
    expect(onNav).toHaveBeenCalledWith('C1');
  });

  it('marks the current chapter', () => {
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 'ch2', kind: 'chapter', parent_id: null, chapter_id: 'C2', story_order: 1 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C2" onNavigateChapter={vi.fn()} />);
    const current = screen.getAllByTestId('outline-node').find((r) => r.className.includes('border-l-primary'));
    expect(current).toBeTruthy();
  });

  it('shows the empty state with no outline', () => {
    mountWith([]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getByTestId('outline-empty')).toBeInTheDocument();
  });

  it('collapses children when the chevron is clicked', () => {
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 0 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getAllByTestId('outline-node')).toHaveLength(2);
    fireEvent.click(screen.getByTestId('outline-toggle'));
    expect(screen.getAllByTestId('outline-node')).toHaveLength(1); // scene hidden
  });
});

describe('OutlineTree node CRUD (T1.1b)', () => {
  it('inline-renames a node: edit → Enter sends title + version as If-Match', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, title: 'Old', version: 3 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getByTestId('outline-action-rename'));
    const input = screen.getByTestId('outline-rename-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'New title' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mutations.rename.mutate).toHaveBeenCalledTimes(1); // fire-once latch (no unmount double-commit)
    expect(mutations.rename.mutate).toHaveBeenCalledWith(
      { nodeId: 's1', title: 'New title', version: 3 },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('commits an unchanged/blank title as a cancel (no mutation)', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, title: 'Same', version: 1 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getByTestId('outline-action-rename'));
    fireEvent.keyDown(screen.getByTestId('outline-rename-input'), { key: 'Enter' }); // unchanged defaultValue
    expect(mutations.rename.mutate).not.toHaveBeenCalled();
    expect(screen.queryByTestId('outline-rename-input')).not.toBeInTheDocument();
  });

  it('Escape cancels the rename without mutating', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, title: 'Old', version: 1 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getByTestId('outline-action-rename'));
    fireEvent.keyDown(screen.getByTestId('outline-rename-input'), { key: 'Escape' });
    expect(mutations.rename.mutate).not.toHaveBeenCalled();
    expect(screen.queryByTestId('outline-rename-input')).not.toBeInTheDocument();
  });

  it('add-child on a chapter creates a scene carrying chapter_id', () => {
    mountWith([node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getByTestId('outline-action-addchild'));
    expect(mutations.addChild.mutate).toHaveBeenCalledWith(
      { kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', title: '' },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('add-child on a scene creates a beat (no chapter_id) and is absent on arcs', () => {
    mountWith([
      node({ id: 'arc', kind: 'arc', parent_id: null, story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'arc', chapter_id: 'C1', story_order: 0 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    // arc row has no add-child affordance; only the scene does
    expect(screen.getAllByTestId('outline-action-addchild')).toHaveLength(1);
    fireEvent.click(screen.getByTestId('outline-action-addchild'));
    expect(mutations.addChild.mutate).toHaveBeenCalledWith(
      { kind: 'beat', parent_id: 's1', chapter_id: null, title: '' },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('archives a leaf node directly (no confirm prompt)', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, story_order: 0 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getByTestId('outline-action-archive'));
    expect(confirmSpy).not.toHaveBeenCalled(); // leaf → no cascade → no prompt
    expect(mutations.archive.mutate).toHaveBeenCalledWith('s1', expect.objectContaining({ onError: expect.any(Function) }));
    confirmSpy.mockRestore();
  });

  it('confirms before archiving a parent (cascade); cancel aborts the mutation', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 0 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    // first archive button belongs to the parent chapter (has children)
    fireEvent.click(screen.getAllByTestId('outline-action-archive')[0]);
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(mutations.archive.mutate).not.toHaveBeenCalled(); // cancelled
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getAllByTestId('outline-action-archive')[0]);
    expect(mutations.archive.mutate).toHaveBeenCalledWith('ch1', expect.objectContaining({ onError: expect.any(Function) }));
    confirmSpy.mockRestore();
  });

  it('status-cycle advances a scene status and sends version (scenes only)', () => {
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', status: 'outline', story_order: 0, version: 2 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    // only the scene exposes the status-cycle affordance, not the chapter
    expect(screen.getAllByTestId('outline-action-status')).toHaveLength(1);
    fireEvent.click(screen.getByTestId('outline-action-status'));
    expect(mutations.setStatus.mutate).toHaveBeenCalledWith(
      { nodeId: 's1', status: 'drafting', version: 2 }, // outline → drafting
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('a 412 conflict warns + refetches; a non-412 error toasts the message', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, story_order: 0 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getByTestId('outline-action-archive'));
    const { onError } = mutations.archive.mutate.mock.calls[0][1];
    onError({ status: 412 });
    expect(toastWarn).toHaveBeenCalledTimes(1);
    expect(mutations.invalidate).toHaveBeenCalledTimes(1);
    onError(new Error('boom'));
    expect(toastError).toHaveBeenCalledWith('boom');
  });

  it('add-child opens the new node for rename on success (L-2)', () => {
    // mount the "created" node already in the tree so the editing input can render
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 0 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    fireEvent.click(screen.getAllByTestId('outline-action-addchild')[0]); // chapter → add scene (scene also has add-beat)
    const { onSuccess } = mutations.addChild.mutate.mock.calls[0][1];
    expect(screen.queryByTestId('outline-rename-input')).not.toBeInTheDocument();
    act(() => onSuccess(node({ id: 's1' }))); // BE returns the created node → opens it for rename
    expect(screen.getByTestId('outline-rename-input')).toBeInTheDocument();
  });
});

describe('OutlineTree archived view + restore (T1.1b / L-1)', () => {
  it('toggling "show archived" re-reads the outline with include_archived', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, story_order: 0 })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(outlineHook).toHaveBeenLastCalledWith('proj', 't', false); // default view
    fireEvent.click(screen.getByTestId('outline-toggle-archived'));
    expect(outlineHook).toHaveBeenLastCalledWith('proj', 't', true); // archived view
  });

  it('the archived toggle stays reachable when the (default) tree is empty', () => {
    mountWith([]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getByTestId('outline-empty')).toBeInTheDocument();
    expect(screen.getByTestId('outline-toggle-archived')).toBeInTheDocument(); // not buried behind the empty early-return
  });

  it('an archived node shows a restore action (not the edit cluster) and restores by id', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, story_order: 0, is_archived: true })]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.queryByTestId('outline-action-archive')).not.toBeInTheDocument(); // archived → no edit cluster
    expect(screen.queryByTestId('outline-action-rename')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('outline-action-restore'));
    expect(mutations.restore.mutate).toHaveBeenCalledWith('s1', expect.objectContaining({ onError: expect.any(Function) }));
  });
});

describe('computeReorder (T1.1c projection)', () => {
  // a fixed-depth tree: arc1 > {ch1 > [s1,s2,s3], ch2 > [s4]}
  const rows = [
    { node: node({ id: 'arc1', kind: 'arc', parent_id: null }) },
    { node: node({ id: 'ch1', kind: 'chapter', parent_id: 'arc1' }) },
    { node: node({ id: 's1', kind: 'scene', parent_id: 'ch1' }) },
    { node: node({ id: 's2', kind: 'scene', parent_id: 'ch1' }) },
    { node: node({ id: 's3', kind: 'scene', parent_id: 'ch1' }) },
    { node: node({ id: 'ch2', kind: 'chapter', parent_id: 'arc1' }) },
    { node: node({ id: 's4', kind: 'scene', parent_id: 'ch2' }) },
  ];

  it('reorders a scene within its chapter (drop s1 onto s3 → after s3)', () => {
    expect(computeReorder(rows, 's1', 's3')).toEqual({ nodeId: 's1', new_parent_id: 'ch1', after_id: 's3' });
  });

  it('reparents a scene to another chapter (drop s1 onto s4 → under ch2 after s4)', () => {
    expect(computeReorder(rows, 's1', 's4')).toEqual({ nodeId: 's1', new_parent_id: 'ch2', after_id: 's4' });
  });

  it('reparents a scene to the head of another chapter (drop onto its first child)', () => {
    // drop s4 onto s1 (ch1's first scene) → s4 becomes ch1's first child
    expect(computeReorder(rows, 's4', 's1')).toEqual({ nodeId: 's4', new_parent_id: 'ch1', after_id: null });
  });

  it('reorders a chapter within its arc (drop ch2 onto ch1 → first chapter)', () => {
    expect(computeReorder(rows, 'ch2', 'ch1')).toEqual({ nodeId: 'ch2', new_parent_id: 'arc1', after_id: null });
  });

  it('returns null for a no-op (same node) and an out-of-list id', () => {
    expect(computeReorder(rows, 's1', 's1')).toBeNull();
    expect(computeReorder(rows, 's1', 'ghost')).toBeNull();
  });

  it('returns null when a scene would land with no preceding chapter (invalid kind nesting)', () => {
    // dropping s1 onto arc1 → it lands right after arc1 with no chapter ancestor → invalid
    expect(computeReorder(rows, 's1', 'arc1')).toBeNull();
  });

  it('reorders a beat within its scene (parent-kind = scene)', () => {
    const r = [
      { node: node({ id: 'ch', kind: 'chapter', parent_id: 'a' }) },
      { node: node({ id: 'sc', kind: 'scene', parent_id: 'ch' }) },
      { node: node({ id: 'b1', kind: 'beat', parent_id: 'sc' }) },
      { node: node({ id: 'b2', kind: 'beat', parent_id: 'sc' }) },
    ];
    expect(computeReorder(r, 'b1', 'b2')).toEqual({ nodeId: 'b1', new_parent_id: 'sc', after_id: 'b2' });
  });

  it('coerces a cross-kind drop to the nearest valid parent (chapter dropped amid scenes → stays under its arc)', () => {
    // drop ch2 onto s2 (a scene inside ch1) → ch2 can only parent under an arc → lands after ch1
    expect(computeReorder(rows, 'ch2', 's2')).toEqual({ nodeId: 'ch2', new_parent_id: 'arc1', after_id: 'ch1' });
  });
});

describe('OutlineTree drag wiring (T1.1c)', () => {
  it('shows a drag handle per row in the default view, but not in the archived view', () => {
    mountWith([node({ id: 's1', kind: 'scene', parent_id: null, story_order: 0 })]);
    const { rerender } = render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getByTestId('outline-drag-handle')).toBeInTheDocument();
    // archived view → reorder disabled → no drag handle
    fireEvent.click(screen.getByTestId('outline-toggle-archived'));
    rerender(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.queryByTestId('outline-drag-handle')).not.toBeInTheDocument();
  });
});

describe('OutlineTree cards⇄tree toggle (T1.1d)', () => {
  it('switches to the Corkboard and hides the archived toggle in cards mode', () => {
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', title: 'Ch One', story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 0, title: 'Sc' }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getByTestId('composition-outline')).toBeInTheDocument();
    expect(screen.getByTestId('outline-toggle-archived')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('outline-toggle-view'));
    expect(screen.getByTestId('composition-corkboard')).toBeInTheDocument();
    expect(screen.getByTestId('corkboard-card')).toBeInTheDocument(); // the scene as a card
    expect(screen.queryByTestId('outline-toggle-archived')).not.toBeInTheDocument(); // tree-only
  });
});
