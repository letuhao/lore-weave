import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
// M2 — self-contained model picker + the take-generation orchestration. Mock the
// models API (so the picker has a model) and useWhatIfTakes (so Generate is a spy — the
// hook itself is unit-tested in useWhatIfTakes.test).
// W5 — spread the real module: the shared ModelPicker also imports getUserModelMeta.
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: vi.fn().mockResolvedValue({
        items: [{
          user_model_id: 'm1', provider_credential_id: 'c1', is_active: true, is_favorite: false,
          alias: 'M1', provider_kind: 'openai', provider_model_name: 'gpt',
          capability_flags: {}, tags: [], created_at: '2026-01-01T00:00:00Z',
        }],
      }),
      patchFavorite: vi.fn(),
    },
  };
});
// W5 — the shared useUserModels/ModelPicker read the token from useAuth.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { invalidateUserModelsCache } from '@/components/model-picker';

// W5 — the picker is the shared combobox; "the sole model resolved" shows as its
// display name on the trigger (the old assert read the <select>'s value).
const whatIfModelReady = async () =>
  waitFor(() => {
    const trigger = within(screen.getByTestId('scenegraph-whatif-model')).getByRole('combobox');
    expect(trigger).toHaveTextContent('M1');
  });
const { generateTakeSpy } = vi.hoisted(() => ({ generateTakeSpy: vi.fn() }));
vi.mock('../../hooks/useWhatIfTakes', () => ({
  // generateTake also flips the alt to 'ready' (the real hook does this async) so the
  // Promote button can enable in tests.
  useWhatIfTakes: (opts: { updateAlt: (id: string, p: unknown) => void }) => ({
    generateTake: (altId: string, anchor: string, model: unknown) => {
      generateTakeSpy(altId, anchor, model);
      opts.updateAlt(altId, { status: 'ready', take: { ghost: 'g', jobId: 'j', judge: null } });
    },
    generating: false,
  }),
}));
// M3 — mock the promote bridge (fires its onPromoted with a fake derivative) + the
// node-seeding api so the canvas promote flow is testable without the real cross-service path.
const { promoteSpy, onPromotedSpy, createNodeSpy, persistProseSpy } = vi.hoisted(() => ({
  promoteSpy: vi.fn(), onPromotedSpy: vi.fn(),
  createNodeSpy: vi.fn().mockResolvedValue({ id: 'newnode' }),
  persistProseSpy: vi.fn().mockResolvedValue({ node_id: 'newnode', persisted: true, version: 1 }),
}));
vi.mock('../../hooks/useWhatIfPromotion', () => ({
  useWhatIfPromotion: (args: { onPromoted: (d: unknown) => void }) => ({
    promote: () => { promoteSpy(); args.onPromoted({ project_id: 'deriv-p', book_id: 'b' }); },
    isPromoting: false, canPromote: true, buildDeriveBody: vi.fn(), error: null,
  }),
}));
vi.mock('../../api', () => ({ compositionApi: {
  createNode: (...a: unknown[]) => createNodeSpy(...a),
  persistScenePromoteProse: (...a: unknown[]) => persistProseSpy(...a),
} }));
// M3 — the chapters lookup (branch_point = the anchor scene's CHAPTER sort_order).
vi.mock('../../../books/api', () => ({
  booksApi: {
    listChapters: vi.fn().mockResolvedValue({
      items: [{ chapter_id: 'C1', sort_order: 0, title: 'Ch1' }, { chapter_id: 'C2', sort_order: 1, title: 'Ch2' }],
    }),
  },
}));

function node(over: Partial<OutlineNode>): OutlineNode {
  return {
    id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'T',
    chapter_id: 'C1', story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, beat_role: null, ...over,
  };
}
const work = { project_id: 'p', book_id: 'b', settings: {} } as unknown as Work;
// M2 needs a QueryClient (the self-contained model picker query). One wrapper for all.
const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const Graph = () => (
  <QueryClientProvider client={qc}>
    <SceneGraphCanvas
      work={work}
      bookId="b"
      token="t"
      onPromoted={onPromotedSpy}
    />
  </QueryClientProvider>
);

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
    localStorage.clear();
    invalidateUserModelsCache();  // W5 — shared fetch cache must not leak across tests
    createSceneLink.mutate.mockReset(); deleteSceneLink.mutate.mockReset();
    setSettings.mutate.mockReset(); navigateFn.mockReset(); generateTakeSpy.mockReset();
    promoteSpy.mockReset(); onPromotedSpy.mockReset(); createNodeSpy.mockClear(); persistProseSpy.mockClear(); (toast.error as ReturnType<typeof vi.fn>).mockReset();
    outlineHook.mockReturnValue({ data: scenes });
    linksHook.mockReturnValue({ data: links });
  });

  it('renders scenes as nodes and a typed edge (setup_payoff = solid)', () => {
    render(<Graph />);
    expect(screen.getAllByTestId('scene-node')).toHaveLength(2);
    const edge = screen.getByTestId('scene-edge');
    expect(edge.getAttribute('data-kind')).toBe('setup_payoff');
  });

  it('empty state when there are no scenes', () => {
    outlineHook.mockReturnValue({ data: [] });
    render(<Graph />);
    expect(screen.getByTestId('scenegraph-empty')).toBeInTheDocument();
  });

  it('pick-two-nodes + button creates a link (from, to, kind, label)', () => {
    render(<Graph />);
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
    render(<Graph />);
    fireEvent.keyDown(body('s1'), { key: 'Enter' });
    fireEvent.keyDown(body('s2'), { key: 'Enter' });
    expect(screen.getByTestId('scenegraph-linkbar')).toBeInTheDocument();
    expect(body('s1').getAttribute('aria-pressed')).toBe('true');
  });

  it('a duplicate link (409) toasts and adds no edge', () => {
    createSceneLink.mutate.mockImplementation((_v: unknown, opts: { onError?: (e: unknown) => void }) => opts.onError?.({ status: 409 }));
    render(<Graph />);
    clickNode('s1'); clickNode('s2');
    fireEvent.click(screen.getByTestId('scenegraph-add'));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(screen.getAllByTestId('scene-edge')).toHaveLength(1); // still just l1, no optimistic dup
  });

  it('selecting an edge reveals ✕ and deletes it', () => {
    render(<Graph />);
    const hitLine = screen.getByTestId('scene-edge').querySelector('line')!;
    fireEvent.pointerDown(hitLine);
    fireEvent.click(screen.getByTestId('scene-edge-delete'));
    expect(deleteSceneLink.mutate).toHaveBeenCalledWith('l1', expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it('the open (↗) button jumps to the scene’s chapter', () => {
    render(<Graph />);
    fireEvent.click(within(document.querySelector('[data-node="s2"]')!).getByTestId('scene-node-open'));
    expect(navigateFn).toHaveBeenCalledWith('/books/b/chapters/C2/edit');
  });

  // ── WS-B3 M1 — on-canvas what-if (ephemeral, zero residue) ──
  it('selecting ONE scene reveals "What-if from here"; starting it draws a dashed alt node + edge', () => {
    render(<Graph />);
    clickNode('s1');                                   // exactly one scene selected
    fireEvent.click(screen.getByTestId('scenegraph-whatif-start'));
    // a dashed alternate + branch edge appear; canon nodes are unchanged
    expect(screen.getByTestId('whatif-alt-node')).toBeInTheDocument();
    expect(document.querySelector('[data-testid^="whatif-edge-"]')).toBeTruthy();
    expect(screen.getAllByTestId('scene-node')).toHaveLength(2);
    expect(createSceneLink.mutate).not.toHaveBeenCalled(); // ephemeral — nothing persisted
  });

  it('"+ alternate" adds another alt; "Discard" removes the whole branch (zero residue)', () => {
    render(<Graph />);
    clickNode('s1');
    fireEvent.click(screen.getByTestId('scenegraph-whatif-start'));
    fireEvent.click(screen.getByTestId('scenegraph-whatif-add'));
    expect(screen.getAllByTestId('whatif-alt-node')).toHaveLength(2);
    fireEvent.click(screen.getByTestId('scenegraph-whatif-discard'));
    expect(screen.queryByTestId('whatif-alt-node')).toBeNull();   // branch gone
    expect(screen.getAllByTestId('scene-node')).toHaveLength(2);  // canon intact
    expect(setSettings.mutate).not.toHaveBeenCalled();            // no persistence on discard
  });

  it('the ✕ on an alt node removes it (last alt → branch closes)', () => {
    render(<Graph />);
    clickNode('s1');
    fireEvent.click(screen.getByTestId('scenegraph-whatif-start'));
    const altId = (screen.getByTestId('whatif-alt-node').getAttribute('data-alt'))!;
    fireEvent.click(screen.getByTestId(`whatif-alt-remove-${altId}`));
    // it was the only alt → the whole branch closes (zero residue)
    expect(screen.queryByTestId('whatif-alt-node')).toBeNull();
    expect(screen.queryByTestId('scenegraph-whatif-bar')).toBeNull();
  });

  it('Generate on an alt calls generateTake with the anchor scene + the picked model (M2)', async () => {
    render(<Graph />);
    clickNode('s1');
    fireEvent.click(screen.getByTestId('scenegraph-whatif-start'));
    // the self-contained model picker populates from the (mocked) models API
    await whatIfModelReady();
    const altId = screen.getByTestId('whatif-alt-node').getAttribute('data-alt')!;
    fireEvent.click(screen.getByTestId(`whatif-alt-generate-${altId}`));
    expect(generateTakeSpy).toHaveBeenCalledWith(altId, 's1', expect.objectContaining({ modelRef: 'm1' }));
  });

  it('Promote: disabled until a take is ready; then derives + seeds the take as a node + switches (M3)', async () => {
    render(<Graph />);
    clickNode('s1');
    fireEvent.click(screen.getByTestId('scenegraph-whatif-start'));
    await whatIfModelReady();
    // before any take is ready, Promote is disabled
    expect((screen.getByTestId('scenegraph-whatif-promote') as HTMLButtonElement).disabled).toBe(true);
    const altId = screen.getByTestId('whatif-alt-node').getAttribute('data-alt')!;
    fireEvent.click(screen.getByTestId(`whatif-alt-generate-${altId}`)); // mock flips alt → ready
    // Promote enables only once a take is ready AND the chapters query has loaded
    // (branch_point = the anchor's chapter sort_order).
    const promoteBtn = () => screen.getByTestId('scenegraph-whatif-promote') as HTMLButtonElement;
    await waitFor(() => expect(promoteBtn().disabled).toBe(false));
    fireEvent.click(promoteBtn());
    expect(promoteSpy).toHaveBeenCalled();
    // seeded the ready take as a scene node in the DERIVATIVE project...
    // seeded with the anchor scene's chapter_id (a scene REQUIRES a chapter — live-smoke fix)
    // seeded WITH a story_order (review-impl HIGH: the read-back queries filter
    // `story_order IS NOT NULL`, so a NULL-order seed makes the promoted prose invisible).
    await waitFor(() => expect(createNodeSpy).toHaveBeenCalledWith('deriv-p', expect.objectContaining({ kind: 'scene', chapter_id: 'C1', story_order: 0 }), 't'));
    // M3 — and persisted the take's ghost prose into the NEW derivative scene node
    // (scene-scoped synthetic-job store; never the shared book draft).
    // D-S5-BRANCHDIFF-CORRESPONDENCE — the promote now records the canon anchor scene
    // (s1) so the branch-diff can pair reliably; assert the anchorNodeId opt is passed.
    await waitFor(() => expect(persistProseSpy).toHaveBeenCalledWith('deriv-p', 'newnode', 'g', 't', { anchorNodeId: 's1' }));
    // ...then switched the studio (AFTER seeding settles) + discarded the branch
    await waitFor(() => expect(onPromotedSpy).toHaveBeenCalledWith(expect.objectContaining({ project_id: 'deriv-p' })));
    expect(screen.queryByTestId('whatif-alt-node')).toBeNull();
  });

  it('auto-discards the branch if its anchor scene is deleted (no orphan + no stale branch_point)', () => {
    const { rerender } = render(<Graph />);
    clickNode('s1');
    fireEvent.click(screen.getByTestId('scenegraph-whatif-start'));
    expect(screen.getByTestId('whatif-alt-node')).toBeInTheDocument();
    // s1 (the anchor) is deleted out from under the open what-if
    outlineHook.mockReturnValue({ data: [node({ id: 's2', story_order: 1, title: 'Payoff', chapter_id: 'C2' })] });
    rerender(<Graph />);
    expect(screen.queryByTestId('whatif-alt-node')).toBeNull();   // branch auto-discarded
  });

  it('dragging a node past the threshold persists positions to work.settings', () => {
    render(<Graph />);
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
