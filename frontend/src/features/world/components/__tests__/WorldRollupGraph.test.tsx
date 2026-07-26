import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { WorldRollupGraph } from '../WorldRollupGraph';

// W5 (G4) — world rollup canvas. Mocks the data hook (fetch lives there) + the
// reused detail panel's hooks, then proves: renders the union nodes+edges, the
// per-book source legend, node_cap_hit → banner, click node → detail panel,
// empty/error states, and that there is NO ⊞ expand affordance (flat union).

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 't', user: { user_id: 'u1' } }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
const renderView = (props: Parameters<typeof WorldRollupGraph>[0]) =>
  render(<WorldRollupGraph {...props} />, { wrapper: Wrapper });

const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useWorldSubgraph', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useWorldSubgraph')>()),
  useWorldSubgraph: () => hook(),
}));

// Detail panel fetches on open; stub its hooks so it renders without network.
vi.mock('@/features/knowledge/hooks/useEntityDetail', () => ({
  useEntityDetail: (id: string | null) => ({
    detail: id ? { entity: { id, name: `Entity ${id}`, kind: 'character', aliases: [], status: 'discovered', confidence: 0.9, mention_count: 3, anchor_score: 0, glossary_entity_id: null, project_id: 'p', user_edited: false }, relations: [], relations_truncated: false, total_relations: 0 } : null,
    isLoading: false,
    error: null,
  }),
}));
// The reused EntityDetailPanel pulls the S-05/S-05b fact mutations on mount — stub
// all of them so opening the panel from a rollup node doesn't crash on a missing export.
vi.mock('@/features/knowledge/hooks/useEntityFacts', () => ({
  useEntityFacts: () => ({ facts: [], windowAvailable: true, isLoading: false, error: null }),
  useCreateEntityFact: () => ({ create: vi.fn(), isPending: false }),
  useInvalidateFact: () => ({ invalidate: vi.fn(), isPending: false }),
  useRevalidateFact: () => ({ revalidate: vi.fn(), isPending: false }),
}));
vi.mock('@/features/knowledge/hooks/useEntityMutations', () => ({
  useUnlockEntity: () => ({ unlock: vi.fn(), isPending: false }),
  usePromoteEntity: () => ({ promote: vi.fn(), isPending: false }),
  useToggleGlossaryPin: () => ({ toggle: vi.fn(), isPending: false }),
  useUpdateEntity: () => ({ update: vi.fn(), isPending: false }),
  useMergeEntity: () => ({ merge: vi.fn(), isPending: false }),
  useArchiveEntity: () => ({ archive: vi.fn(), isPending: false }),
  useRestoreEntity: () => ({ restore: vi.fn(), isPending: false, error: null }),
  useCreateRelation: () => ({ createRelation: vi.fn(), isPending: false }),
}));

// Two nodes from TWO distinct member projects (per-book islands) + one node
// from the world-level project → 2 sources after counting (p-a, p-b... here 2).
const base = {
  nodes: [
    { id: 'kael', name: 'Kael', kind: 'character', anchor_score: 0, mention_count: 5, glossary_entity_id: null, source_project_id: 'proj-a' },
    { id: 'mira', name: 'Mira', kind: 'character', anchor_score: 0, mention_count: 3, glossary_entity_id: null, source_project_id: 'proj-b' },
  ],
  edges: [{ id: 'e1', source: 'kael', target: 'mira', predicate: 'ally', confidence: 0.9 }],
  sources: [
    { projectId: 'proj-a', nodeCount: 1 },
    { projectId: 'proj-b', nodeCount: 1 },
  ],
  truncated: false,
  isLoading: false,
  isFetching: false,
  error: null as Error | null,
  refetch: vi.fn(),
};

beforeEach(() => hook.mockReturnValue(base));

const nodeBody = (id: string) =>
  within(document.querySelector(`[data-entity="${id}"]`) as HTMLElement).getByTestId('relmap-node-body');

describe('WorldRollupGraph (W5/G4)', () => {
  it('renders the union nodes + edges and the per-book source legend', () => {
    renderView({ worldId: 'w1' });
    expect(screen.getAllByTestId('relmap-node')).toHaveLength(2);
    expect(screen.getAllByTestId('relmap-edge')).toHaveLength(1);
    expect(screen.getByTestId('world-graph-counts')).toBeInTheDocument();
    // The per-book island legend renders (the distinct-count interpolation is
    // covered in useWorldSubgraph.test; the i18n stub here doesn't interpolate).
    expect(screen.getByTestId('world-graph-sources')).toBeInTheDocument();
  });

  it('has NO ⊞ expand affordance — the rollup is a flat union', () => {
    renderView({ worldId: 'w1' });
    expect(screen.queryByTestId('relmap-expand')).toBeNull();
  });

  it('shows the node-cap banner when the union is truncated', () => {
    hook.mockReturnValue({ ...base, truncated: true });
    renderView({ worldId: 'w1' });
    expect(screen.getByTestId('world-graph-truncated')).toBeInTheDocument();
  });

  it('clicking a node opens the reused entity detail panel', () => {
    renderView({ worldId: 'w1' });
    fireEvent.pointerDown(nodeBody('kael'), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('world-graph-svg'));
    expect(screen.getByTestId('entity-detail-panel')).toBeInTheDocument();
  });

  it('renders the empty state when the rollup is empty', () => {
    hook.mockReturnValue({ ...base, nodes: [], edges: [], sources: [] });
    renderView({ worldId: 'w1' });
    expect(screen.getByTestId('world-graph-hint')).toBeInTheDocument();
  });

  it('renders the error state on a failed rollup', () => {
    hook.mockReturnValue({ ...base, nodes: [], edges: [], sources: [], error: new Error('boom') });
    renderView({ worldId: 'w1' });
    expect(screen.getByTestId('world-graph-error')).toBeInTheDocument();
  });
});
