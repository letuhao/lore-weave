import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { MergeCandidate } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({
  listMergeCandidates: vi.fn(),
  confirmMerge: vi.fn(),
  dismissMergeCandidate: vi.fn(),
  revertMerge: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

import { useMergeCandidates } from '../useMergeCandidates';

const BOOK = 'book-1';

function candidate(): MergeCandidate {
  return {
    candidate_id: 'c1',
    kind_code: 'character',
    score: 0.82,
    rationale: 'coref cluster',
    evidence: [],
    suggested_winner_entity_id: 'g-jiang',
    status: 'proposed',
    created_at: '2026-06-07T00:00:00Z',
    members: [
      { entity_id: 'g-jiang', name: '姜子牙', aliases: ['子牙'], chapter_link_count: 50 },
      { entity_id: 'g-taigong', name: '太公望', aliases: [], chapter_link_count: 20 },
    ],
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

async function mountHook(candidates: MergeCandidate[]) {
  apiMocks.listMergeCandidates.mockResolvedValue({ candidates });
  const { Wrapper, invalidateSpy } = makeWrapper();
  const { result } = renderHook(() => useMergeCandidates(BOOK), { wrapper: Wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  return { result, invalidateSpy };
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  apiMocks.confirmMerge.mockResolvedValue({
    winner_id: 'g-jiang',
    results: [{ loser_id: 'g-taigong', journal_id: 'j1', status: 'merged' }],
  });
  apiMocks.dismissMergeCandidate.mockResolvedValue({ candidate_id: 'c1', status: 'dismissed' });
  apiMocks.revertMerge.mockResolvedValue({ journal_id: 'j1', status: 'reverted' });
});

describe('useMergeCandidates', () => {
  it('loads the proposed clusters for the book', async () => {
    const { result } = await mountHook([candidate()]);
    expect(apiMocks.listMergeCandidates).toHaveBeenCalledWith(BOOK, 'tok');
    expect(result.current.candidates).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('confirm folds every member EXCEPT the winner and returns journal ids', async () => {
    const { result, invalidateSpy } = await mountHook([candidate()]);
    let journalIds: string[] = [];
    await act(async () => {
      journalIds = await result.current.confirm(result.current.candidates[0], 'g-jiang');
    });
    // losers = members − winner
    expect(apiMocks.confirmMerge).toHaveBeenCalledWith(BOOK, 'g-jiang', ['g-taigong'], 'tok');
    expect(journalIds).toEqual(['j1']);
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['glossary-merge-candidates', BOOK]);
    expect(keys).toContainEqual(['glossary-entities', BOOK]);
  });

  it('confirm respects a non-suggested winner choice', async () => {
    const { result } = await mountHook([candidate()]);
    await act(async () => {
      await result.current.confirm(result.current.candidates[0], 'g-taigong');
    });
    expect(apiMocks.confirmMerge).toHaveBeenCalledWith(BOOK, 'g-taigong', ['g-jiang'], 'tok');
  });

  it('confirm returns only merged journal ids (skips failed/skipped losers)', async () => {
    apiMocks.confirmMerge.mockResolvedValue({
      winner_id: 'g-jiang',
      results: [
        { loser_id: 'g-taigong', journal_id: 'j1', status: 'merged' },
        { loser_id: 'g-x', status: 'skipped', reason: 'different kind' },
      ],
    });
    const { result } = await mountHook([candidate()]);
    let journalIds: string[] = [];
    await act(async () => {
      journalIds = await result.current.confirm(result.current.candidates[0], 'g-jiang');
    });
    expect(journalIds).toEqual(['j1']);
  });

  it('dismiss calls the dismiss endpoint and invalidates', async () => {
    const { result, invalidateSpy } = await mountHook([candidate()]);
    await act(async () => { await result.current.dismiss(result.current.candidates[0]); });
    expect(apiMocks.dismissMergeCandidate).toHaveBeenCalledWith(BOOK, 'c1', 'tok');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['glossary-merge-candidates', BOOK]);
  });

  it('undo reverts a merge journal', async () => {
    const { result } = await mountHook([candidate()]);
    await act(async () => { await result.current.undo('j1'); });
    expect(apiMocks.revertMerge).toHaveBeenCalledWith(BOOK, 'j1', 'tok');
  });
});
