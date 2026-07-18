import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { ProjectGraphView } from '../ProjectGraphView';

// The reused EntityDetailPanel (+ its merge dialog) reach for auth + a
// QueryClient on mount; stub auth and wrap renders so a node click can open
// the panel without a real provider tree.
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 't', user: { user_id: 'u1' } }),
}));

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
const renderView = (props: Parameters<typeof ProjectGraphView>[0]) =>
  render(<ProjectGraphView {...props} />, { wrapper: Wrapper });

// C19 — Project graph canvas component test. Mocks the data hook (fetch/merge
// lives there) + the detail panel's hook, then proves: renders nodes+edges
// from a subgraph fixture, node_cap_hit → banner, click node → detail panel,
// ⊞ → expand-hop fired from the click handler (not a useEffect).

const { hook, sliceHook, viewsHook } = vi.hoisted(() => ({
  hook: vi.fn(),
  sliceHook: vi.fn(),
  viewsHook: vi.fn(),
}));
vi.mock('../../hooks/useProjectSubgraph', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useProjectSubgraph')>()),
  useProjectSubgraph: (_pid: string | undefined, enabled?: boolean) => hook(enabled),
}));
// S-09 W3 — the panel now also drives the view-aware slice reader + the saved
// views list. Mock both so lens mode is deterministic (no network in jsdom).
vi.mock('../../hooks/useProjectGraphSlice', () => ({
  useProjectGraphSlice: (pid: string | undefined, view: string | null, asOf: number | null, enabled: boolean) =>
    sliceHook(pid, view, asOf, enabled),
}));
vi.mock('../../hooks/useGraphViews', () => ({
  useGraphViews: () => viewsHook(),
}));

// The detail panel fetches on open; stub its hooks so it renders without a
// QueryClient / network.
vi.mock('../../hooks/useEntityDetail', () => ({
  useEntityDetail: (id: string | null) => ({
    detail: id ? { entity: { id, name: `Entity ${id}`, kind: 'character', aliases: [], status: 'discovered', confidence: 0.9, mention_count: 3, anchor_score: 0, glossary_entity_id: null, project_id: 'p', user_edited: false }, relations: [], relations_truncated: false, total_relations: 0 } : null,
    isLoading: false,
    error: null,
  }),
}));
// The reused EntityDetailPanel now also pulls the S-05/S-05b fact mutations
// (author/invalidate/revalidate) on mount — stub them so this graph-view suite
// renders the panel without a real query client / network.
vi.mock('../../hooks/useEntityFacts', () => ({
  useEntityFacts: () => ({ facts: [], windowAvailable: true, isLoading: false, error: null }),
  useCreateEntityFact: () => ({ create: vi.fn(), isPending: false }),
  useInvalidateFact: () => ({ invalidate: vi.fn(), isPending: false }),
  useRevalidateFact: () => ({ revalidate: vi.fn(), isPending: false }),
}));
vi.mock('../../hooks/useEntityMutations', () => ({
  useUnlockEntity: () => ({ unlock: vi.fn(), isPending: false }),
  usePromoteEntity: () => ({ promote: vi.fn(), isPending: false }),
  useToggleGlossaryPin: () => ({ toggle: vi.fn(), isPending: false }),
  useUpdateEntity: () => ({ update: vi.fn(), isPending: false }),
  useMergeEntity: () => ({ merge: vi.fn(), isPending: false }),
  useArchiveEntity: () => ({ archive: vi.fn(), isPending: false, error: null }),
  useRestoreEntity: () => ({ restore: vi.fn(), isPending: false, error: null }),
  useCreateRelation: () => ({ create: vi.fn(), isPending: false, error: null }),
  useCreateEntity: () => ({ create: vi.fn(), isPending: false, error: null }),
}));

const expand = vi.fn();
// The hook returns nodes/edges in the C18 SubgraphNode/SubgraphEdge shape
// (edges keyed source/target); ProjectGraphView maps them onto the shared
// GraphNode/GraphEdge view shapes.
const base = {
  nodes: [
    { id: 'kael', name: 'Kael', kind: 'character', anchor_score: 0, mention_count: 5, glossary_entity_id: null },
    { id: 'mira', name: 'Mira', kind: 'character', anchor_score: 0, mention_count: 3, glossary_entity_id: null },
  ],
  edges: [{ id: 'e1', source: 'kael', target: 'mira', predicate: 'ally', confidence: 0.9 }],
  truncated: false,
  expandedIds: [] as string[],
  expandingId: null as string | null,
  expand,
  isLoading: false,
  isFetching: false,
  error: null as Error | null,
  refetch: vi.fn(),
};

// Lens-mode fixture: the slice reader returns a DIFFERENT single node so a test
// can tell which data source is live. Its shape mirrors useProjectSubgraph's.
const sliceBase = {
  nodes: [{ id: 'lyra', name: 'Lyra', kind: 'character', glossary_entity_id: null }],
  edges: [] as { id: string; source: string; target: string; predicate: string; confidence: number }[],
  warnings: [] as string[],
  truncated: false,
  isLoading: false,
  isFetching: false,
  error: null as Error | null,
  refetch: vi.fn(),
  expandedIds: [] as string[],
  expandingId: null as string | null,
  expand: vi.fn(),
};

beforeEach(() => {
  expand.mockReset();
  hook.mockReturnValue(base);
  sliceHook.mockReturnValue(sliceBase);
  viewsHook.mockReturnValue({
    views: [
      { view_id: 'v1', project_id: 'p1', code: 'allies', name: 'Alliances', edge_type_codes: [], node_kind_codes: [] },
    ],
    isLoading: false, isError: false, error: null, refetch: vi.fn(),
    createView: vi.fn(), upsertView: vi.fn(), deleteView: vi.fn(), isMutating: false,
  });
});

const nodeBody = (id: string) =>
  within(document.querySelector(`[data-entity="${id}"]`) as HTMLElement).getByTestId('relmap-node-body');

describe('ProjectGraphView (C19)', () => {
  it('renders nodes + edges from the subgraph fixture', () => {
    renderView({ projectId: "p1", bookId: "b1" });
    expect(screen.getAllByTestId('relmap-node')).toHaveLength(2);
    expect(screen.getAllByTestId('relmap-edge')).toHaveLength(1);
    // counts label present (i18n returns the key in test env, not interpolated).
    expect(screen.getByTestId('project-graph-counts')).toBeInTheDocument();
  });

  it('shows the node-cap banner when truncated', () => {
    hook.mockReturnValue({ ...base, truncated: true });
    renderView({ projectId: "p1" });
    expect(screen.getByTestId('project-graph-truncated')).toBeInTheDocument();
  });

  it('clicking a node opens the reused entity detail panel', () => {
    renderView({ projectId: "p1", bookId: "b1" });
    fireEvent.pointerDown(nodeBody('kael'), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('project-graph-svg'));
    expect(screen.getByTestId('entity-detail-panel')).toBeInTheDocument();
  });

  it('⊞ fires expand-hop from the click handler (re-query, no full reload)', () => {
    renderView({ projectId: "p1" });
    fireEvent.click(within(document.querySelector('[data-entity="mira"]') as HTMLElement).getByTestId('relmap-expand'));
    expect(expand).toHaveBeenCalledWith('mira');
  });

  it('renders the loading state', () => {
    hook.mockReturnValue({ ...base, isLoading: true, nodes: [], edges: [] });
    renderView({ projectId: "p1" });
    expect(screen.getByTestId('project-graph-hint')).toBeInTheDocument();
  });

  it('renders the empty state when there are no nodes', () => {
    hook.mockReturnValue({ ...base, nodes: [], edges: [] });
    renderView({ projectId: "p1" });
    expect(screen.getByText('graph.empty')).toBeInTheDocument();
  });

  // ── S-09 W3 (F-12) — the view + as-of-chapter lens ──────────────────────────
  describe('lens (view + as-of-chapter)', () => {
    it('shows the lens toolbar with the saved views as options', () => {
      renderView({ projectId: "p1" });
      const select = screen.getByTestId('project-graph-view-select');
      expect(select).toBeInTheDocument();
      expect(within(select).getByRole('option', { name: 'Alliances' })).toBeInTheDocument();
    });

    it('starts in subgraph mode (slice reader idle, subgraph enabled)', () => {
      renderView({ projectId: "p1" });
      // subgraph enabled=true, slice enabled=false while no lens is set
      expect(hook).toHaveBeenCalledWith(true);
      expect(sliceHook).toHaveBeenLastCalledWith('p1', null, null, false);
      // the subgraph fixture is on screen (Kael/Mira), not the slice's Lyra
      expect(screen.getAllByTestId('relmap-node')).toHaveLength(2);
    });

    it('selecting a view switches the data source to the slice reader', () => {
      renderView({ projectId: "p1" });
      fireEvent.change(screen.getByTestId('project-graph-view-select'), { target: { value: 'allies' } });
      // now the slice reader is enabled with the chosen view code…
      expect(sliceHook).toHaveBeenLastCalledWith('p1', 'allies', null, true);
      // …and the subgraph query is disabled (enabled=false)
      expect(hook).toHaveBeenLastCalledWith(false);
      // the rendered graph is now the slice's single node (Lyra), not the subgraph's two
      expect(screen.getAllByTestId('relmap-node')).toHaveLength(1);
    });

    it('typing an as-of chapter activates the lens', () => {
      renderView({ projectId: "p1" });
      fireEvent.change(screen.getByTestId('project-graph-asof-input'), { target: { value: '5' } });
      expect(sliceHook).toHaveBeenLastCalledWith('p1', null, 5, true);
    });

    it('clearing the lens returns to subgraph mode', () => {
      renderView({ projectId: "p1" });
      fireEvent.change(screen.getByTestId('project-graph-view-select'), { target: { value: 'allies' } });
      fireEvent.click(screen.getByTestId('project-graph-lens-clear'));
      expect(sliceHook).toHaveBeenLastCalledWith('p1', null, null, false);
      expect(screen.getAllByTestId('relmap-node')).toHaveLength(2);
    });

    it('an empty lens shows an escapable hint, not a dead end', () => {
      sliceHook.mockReturnValue({ ...sliceBase, nodes: [], edges: [] });
      renderView({ projectId: "p1" });
      fireEvent.change(screen.getByTestId('project-graph-view-select'), { target: { value: 'allies' } });
      // the empty-lens hint (not the generic empty), and the toolbar is still there
      expect(screen.getByText('graph.emptyLens')).toBeInTheDocument();
      expect(screen.getByTestId('project-graph-lens-clear')).toBeInTheDocument();
    });

    it('renders deprecated-edge warnings from the slice', () => {
      sliceHook.mockReturnValue({ ...sliceBase, warnings: ['edge type "foe" is deprecated'] });
      renderView({ projectId: "p1" });
      fireEvent.change(screen.getByTestId('project-graph-view-select'), { target: { value: 'allies' } });
      expect(screen.getByTestId('project-graph-warnings')).toHaveTextContent('deprecated');
    });
  });
});
