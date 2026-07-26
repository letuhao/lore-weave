import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReferences } from '../useReferences';

const api = vi.hoisted(() => ({
  listReferences: vi.fn(),
  searchReferences: vi.fn(),
  addReference: vi.fn(),
  deleteReference: vi.fn(),
  setGroundingPin: vi.fn(),
}));
vi.mock('../../api', () => ({ compositionApi: api }));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  api.listReferences.mockReset(); api.searchReferences.mockReset();
  api.addReference.mockReset(); api.deleteReference.mockReset(); api.setGroundingPin.mockReset();
  api.listReferences.mockResolvedValue({ references: [{ id: 'r1', title: 'A', content: 'x' }], embed_model_set: true });
  api.searchReferences.mockResolvedValue({ hits: [{ id: 'r1', title: 'A', content: 'x', score: 0.7, pinned: false, excluded: false }], embed_model_set: true, query: 'duel' });
  api.addReference.mockResolvedValue({ id: 'r2' });
  api.deleteReference.mockResolvedValue({ id: 'r1', deleted: true });
  api.setGroundingPin.mockResolvedValue({ item_type: 'reference', item_id: 'r1', action: 'pin' });
});

describe('useReferences (T3.6)', () => {
  it('loads the library and exposes embedModelSet', async () => {
    const { result } = renderHook(() => useReferences('p1', 's1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.references.length).toBe(1));
    expect(result.current.embedModelSet).toBe(true);
  });

  it('runs the per-scene search only once the embed model is set', async () => {
    const { result } = renderHook(() => useReferences('p1', 's1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.hits.length).toBe(1));
    expect(api.searchReferences).toHaveBeenCalledWith('p1', 's1', 't', undefined);
  });

  it('does NOT search when the work has no embed model', async () => {
    api.listReferences.mockResolvedValue({ references: [], embed_model_set: false });
    const { result } = renderHook(() => useReferences('p1', 's1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.embedModelSet).toBe(false));
    expect(api.searchReferences).not.toHaveBeenCalled();
  });

  it('passes a manual query through to the search call', async () => {
    renderHook(() => useReferences('p1', 's1', 't', 'echo'), { wrapper: makeWrapper() });
    await waitFor(() => expect(api.searchReferences).toHaveBeenCalledWith('p1', 's1', 't', 'echo'));
  });

  it('adds a reference', async () => {
    const { result } = renderHook(() => useReferences('p1', 's1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.embedModelSet).toBe(true));
    await act(async () => { result.current.add.mutate({ content: 'new', model_ref: 'm1' }); });
    await waitFor(() => expect(api.addReference).toHaveBeenCalledWith('p1', { content: 'new', model_ref: 'm1' }, 't'));
  });

  it('deletes a reference', async () => {
    const { result } = renderHook(() => useReferences('p1', 's1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.embedModelSet).toBe(true));
    await act(async () => { result.current.remove.mutate('r1'); });
    await waitFor(() => expect(api.deleteReference).toHaveBeenCalledWith('r1', 't'));
  });

  it('setPin pins a hit via the reference item_type', async () => {
    const { result } = renderHook(() => useReferences('p1', 's1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.hits.length).toBe(1));
    await act(async () => { result.current.setPin(result.current.hits[0], 'pin'); });
    await waitFor(() => expect(api.setGroundingPin).toHaveBeenCalledWith(
      'p1', 's1', { item_type: 'reference', item_id: 'r1', action: 'pin' }, 't'));
  });
});
