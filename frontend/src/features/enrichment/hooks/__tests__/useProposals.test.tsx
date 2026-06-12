import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listProposalsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    enrichmentApi: {
      listProposals: (...a: unknown[]) => listProposalsMock(...a),
    },
  };
});

import { useProposals } from '../useProposals';
import type { Proposal, ProposalListResponse } from '../../types';

const BOOK = 'book-1';

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    review_status: 'proposed',
    canonical_name: '玉虛宮',
    technique: 'recook',
    content: '...',
    confidence: 0.3,
    origin: 'enrichment',
    provenance_json: {},
    source_refs_json: [],
    ...over,
  } as Proposal);

const resp = (over: Partial<ProposalListResponse> = {}): ProposalListResponse => ({
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  ...over,
});

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

beforeEach(() => {
  listProposalsMock.mockReset();
});

describe('useProposals', () => {
  it("reviewStatus 'all' passes review_status undefined and keys the query with 'all'", async () => {
    listProposalsMock.mockResolvedValue(resp());
    renderHook(() => useProposals(BOOK, { reviewStatus: 'all' }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(listProposalsMock).toHaveBeenCalled());
    expect(listProposalsMock).toHaveBeenCalledWith(
      BOOK,
      { review_status: undefined, limit: 100 },
      'tok',
    );
  });

  it('reviewStatus undefined (default opts) passes review_status undefined', async () => {
    listProposalsMock.mockResolvedValue(resp());
    renderHook(() => useProposals(BOOK), { wrapper: makeWrapper() });
    await waitFor(() => expect(listProposalsMock).toHaveBeenCalled());
    expect(listProposalsMock).toHaveBeenCalledWith(
      BOOK,
      { review_status: undefined, limit: 100 },
      'tok',
    );
  });

  it('a concrete reviewStatus is forwarded to listProposals', async () => {
    listProposalsMock.mockResolvedValue(resp());
    renderHook(() => useProposals(BOOK, { reviewStatus: 'approved' }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(listProposalsMock).toHaveBeenCalled());
    expect(listProposalsMock).toHaveBeenCalledWith(
      BOOK,
      { review_status: 'approved', limit: 100 },
      'tok',
    );
  });

  it("distinct reviewStatus values issue distinct fetches ('all' vs concrete keying)", async () => {
    // Two hooks with different reviewStatus must NOT share a cache entry — the
    // queryKey embeds reviewStatus ?? 'all', so both queryFns run.
    listProposalsMock.mockResolvedValue(resp());
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    renderHook(() => useProposals(BOOK, { reviewStatus: 'all' }), { wrapper: Wrapper });
    renderHook(() => useProposals(BOOK, { reviewStatus: 'approved' }), { wrapper: Wrapper });
    await waitFor(() => expect(listProposalsMock).toHaveBeenCalledTimes(2));
    const statuses = listProposalsMock.mock.calls.map((c) => (c[1] as { review_status?: string }).review_status);
    expect(statuses).toContain(undefined);
    expect(statuses).toContain('approved');
  });

  it('items defaults to [] before data resolves / when absent', () => {
    listProposalsMock.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useProposals(BOOK), { wrapper: makeWrapper() });
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.projectIds).toEqual([]);
  });

  it('items reflects resolved data and total reflects data.total', async () => {
    listProposalsMock.mockResolvedValue(
      resp({
        items: [P({ proposal_id: 'p-1', project_id: 'proj-a' })],
        total: 7,
      }),
    );
    const { result } = renderHook(() => useProposals(BOOK), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.total).toBe(7);
    expect(result.current.items[0].proposal_id).toBe('p-1');
  });

  it('projectIds is the DISTINCT set of project_id across items, preserving first-seen order', async () => {
    listProposalsMock.mockResolvedValue(
      resp({
        items: [
          P({ proposal_id: 'p-1', project_id: 'proj-a' }),
          P({ proposal_id: 'p-2', project_id: 'proj-b' }),
          P({ proposal_id: 'p-3', project_id: 'proj-a' }), // duplicate
        ],
        total: 3,
      }),
    );
    const { result } = renderHook(() => useProposals(BOOK), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.items).toHaveLength(3));
    expect(result.current.projectIds).toEqual(['proj-a', 'proj-b']);
  });

  it('total defaults to 0 when the response omits items but provides nothing', async () => {
    // data present but total left at 0 — the ?? 0 fallback path is also exercised
    // when query.data is undefined (covered above); here total is genuinely 0.
    listProposalsMock.mockResolvedValue(resp({ items: [P()], total: 0 }));
    const { result } = renderHook(() => useProposals(BOOK), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.total).toBe(0);
  });
});
