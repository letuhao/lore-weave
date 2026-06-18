import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { SceneGraphCanvas } from '../SceneGraphCanvas';
import { autoLayout, COL_W, PAD, ROW_H } from '../sceneGraphLayout';
import type { OutlineNode, SceneLink, Work } from '../../types';

const { outlineHook, linksHook, createSceneLink, deleteSceneLink, setSettings, navigateFn } = vi.hoisted(() => ({
  outlineHook: vi.fn(), linksHook: vi.fn(),
  createSceneLink: { mutate: vi.fn(), isPending: false },
  deleteSceneLink: { mutate: vi.fn(), isPending: false },
  setSettings: { mutate: vi.fn() },
  navigateFn: vi.fn(),
}));
vi.mock('../../hooks/useOutline', () => ({
  useOutline: () => outlineHook(),
  useSceneLinks: () => linksHook(),
  useOutlineMutations: () => ({ createSceneLink, deleteSceneLink }),
}));
vi.mock('../../hooks/useWork', () => ({ useSetWorkSettings: () => setSettings }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateFn }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

function node(over: Partial<OutlineNode>): OutlineNode {
  return {
    id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'T',
    chapter_id: 'C1', story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, beat_role: null, ...over,
  };
}
const work = { project_id: 'p', book_id: 'b', settings: {} } as unknown as Work;

describe('autoLayout (T1.3 pure)', () => {
  it('lays scenes in columns by story_order, rows within a column, nulls trailing', () => {
    const pos = autoLayout([
      node({ id: 'a', story_order: 1 }),
      node({ id: 'b', story_order: 0 }),
      node({ id: 'c', story_order: null }),
      node({ id: 'd', story_order: 0 }),
    ]);
    expect(pos.b).toEqual({ x: PAD, y: PAD });             // col 0 (order 0), row 0
    expect(pos.d).toEqual({ x: PAD, y: PAD + ROW_H });     // col 0, row 1
    expect(pos.a).toEqual({ x: PAD + COL_W, y: PAD });     // col 1 (order 1)
    expect(pos.c).toEqual({ x: PAD + 2 * COL_W, y: PAD }); // col 2 (null → trailing)
  });

  it('is deterministic regardless of input order', () => {
    const a = autoLayout([node({ id: 'x', story_order: 0 }), node({ id: 'y', story_order: 0 })]);
    const b = autoLayout([node({ id: 'y', story_order: 0 }), node({ id: 'x', story_order: 0 })]);
    expect(a).toEqual(b); // sorted by id within a column
  });
});

describe('SceneGraphCanvas (T1.3)', () => {
  const scenes = [
    node({ id: 's1', story_order: 0, title: 'Setup', chapter_id: 'C1' }),
    node({ id: 's2', story_order: 1, title: 'Payoff', chapter_id: 'C2' }),
  ];
  const links: SceneLink[] = [
    { id: 'l1', project_id: 'p', from_node_id: 's1', to_node_id: 's2', kind: 'setup_payoff', label: 'gun' },
  ];
  const body = (id: string) =>
    within(document.querySelector(`[data-node="${id}"]`) as HTMLElement).getByTestId('scene-node-body');
  const clickNode = (id: string) => {
    fireEvent.pointerDown(body(id), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('scenegraph-svg'));
  };

  beforeEach(() => {
    createSceneLink.mutate.mockReset(); deleteSceneLink.mutate.mockReset();
    setSettings.mutate.mockReset(); navigateFn.mockReset(); (toast.error as ReturnType<typeof vi.fn>).mockReset();
    outlineHook.mockReturnValue({ data: scenes });
    linksHook.mockReturnValue({ data: links });
  });

  it('renders scenes as nodes and a typed edge (setup_payoff = solid)', () => {
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    expect(screen.getAllByTestId('scene-node')).toHaveLength(2);
    const edge = screen.getByTestId('scene-edge');
    expect(edge.getAttribute('data-kind')).toBe('setup_payoff');
  });

  it('empty state when there are no scenes', () => {
    outlineHook.mockReturnValue({ data: [] });
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    expect(screen.getByTestId('scenegraph-empty')).toBeInTheDocument();
  });

  it('pick-two-nodes + button creates a link (from, to, kind, label)', () => {
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    clickNode('s1');
    clickNode('s2');
    expect(screen.getByTestId('scenegraph-linkbar')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('scenegraph-kind'), { target: { value: 'custom' } });
    fireEvent.change(screen.getByTestId('scenegraph-label'), { target: { value: 'echo' } });
    fireEvent.click(screen.getByTestId('scenegraph-add'));
    expect(createSceneLink.mutate).toHaveBeenCalledWith(
      { from_node_id: 's1', to_node_id: 's2', kind: 'custom', label: 'echo' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it('nodes are keyboard-selectable (Enter) so pick-two works without a pointer', () => {
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    fireEvent.keyDown(body('s1'), { key: 'Enter' });
    fireEvent.keyDown(body('s2'), { key: 'Enter' });
    expect(screen.getByTestId('scenegraph-linkbar')).toBeInTheDocument();
    expect(body('s1').getAttribute('aria-pressed')).toBe('true');
  });

  it('a duplicate link (409) toasts and adds no edge', () => {
    createSceneLink.mutate.mockImplementation((_v: unknown, opts: { onError?: (e: unknown) => void }) => opts.onError?.({ status: 409 }));
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    clickNode('s1'); clickNode('s2');
    fireEvent.click(screen.getByTestId('scenegraph-add'));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(screen.getAllByTestId('scene-edge')).toHaveLength(1); // still just l1, no optimistic dup
  });

  it('selecting an edge reveals ✕ and deletes it', () => {
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    const hitLine = screen.getByTestId('scene-edge').querySelector('line')!;
    fireEvent.pointerDown(hitLine);
    fireEvent.click(screen.getByTestId('scene-edge-delete'));
    expect(deleteSceneLink.mutate).toHaveBeenCalledWith('l1', expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it('the open (↗) button jumps to the scene’s chapter', () => {
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    fireEvent.click(within(document.querySelector('[data-node="s2"]')!).getByTestId('scene-node-open'));
    expect(navigateFn).toHaveBeenCalledWith('/books/b/chapters/C2/edit');
  });

  it('dragging a node past the threshold persists positions to work.settings', () => {
    render(<SceneGraphCanvas work={work} bookId="b" token="t" />);
    fireEvent.pointerDown(body('s1'), { clientX: 0, clientY: 0 });
    fireEvent.pointerMove(screen.getByTestId('scenegraph-svg'), { clientX: 60, clientY: 10 });
    fireEvent.pointerUp(screen.getByTestId('scenegraph-svg'));
    expect(setSettings.mutate).toHaveBeenCalledTimes(1);
    const arg = setSettings.mutate.mock.calls[0][0];
    // the persisted x reflects the +60 drag delta off s1's seed (auto col-0 = PAD),
    // not just "some truthy position" — proves the moved coordinate was written.
    expect(arg.patch.scene_graph.positions.s1.x).toBe(PAD + 60);
    expect(createSceneLink.mutate).not.toHaveBeenCalled(); // a drag is not a select
  });
});
