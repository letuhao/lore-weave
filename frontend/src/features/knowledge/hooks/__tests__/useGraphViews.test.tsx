import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const listMock = vi.fn();
const createMock = vi.fn();
const upsertMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../../api/ontology', () => ({
  ontologyApi: {
    listViews: (...a: unknown[]) => listMock(...a),
    createView: (...a: unknown[]) => createMock(...a),
    upsertView: (...a: unknown[]) => upsertMock(...a),
    deleteView: (...a: unknown[]) => deleteMock(...a),
  },
}));

import { useGraphViews } from '../useGraphViews';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  listMock.mockReset().mockResolvedValue({
    items: [
      { view_id: 'v1', project_id: 'p1', code: 'relationship', name: 'Relationship', edge_type_codes: ['LOVER_OF'], node_kind_codes: ['character'] },
    ],
  });
  createMock.mockReset().mockResolvedValue({ view_id: 'v2', code: 'power', name: 'Power' });
  upsertMock.mockReset().mockResolvedValue({ view_id: 'v1', code: 'relationship', name: 'Rel2' });
  deleteMock.mockReset().mockResolvedValue(undefined);
});

describe('useGraphViews — CRUD', () => {
  it('lists the caller-owned views', async () => {
    const { result } = renderHook(() => useGraphViews('p1'), { wrapper });
    await waitFor(() => expect(result.current.views).toHaveLength(1));
    expect(result.current.views[0].code).toBe('relationship');
    expect(listMock).toHaveBeenCalledWith('p1', 'tok');
  });

  it('creates a view', async () => {
    const { result } = renderHook(() => useGraphViews('p1'), { wrapper });
    await waitFor(() => expect(result.current.views).toHaveLength(1));
    await act(async () => {
      await result.current.createView({ name: 'Power', edge_type_codes: ['MASTER_OF'] });
    });
    expect(createMock).toHaveBeenCalledWith('p1', { name: 'Power', edge_type_codes: ['MASTER_OF'] }, 'tok');
  });

  it('upserts by code', async () => {
    const { result } = renderHook(() => useGraphViews('p1'), { wrapper });
    await waitFor(() => expect(result.current.views).toHaveLength(1));
    await act(async () => {
      await result.current.upsertView({ code: 'relationship', body: { name: 'Rel2' } });
    });
    expect(upsertMock).toHaveBeenCalledWith('p1', 'relationship', { name: 'Rel2' }, 'tok');
  });

  it('deletes by code', async () => {
    const { result } = renderHook(() => useGraphViews('p1'), { wrapper });
    await waitFor(() => expect(result.current.views).toHaveLength(1));
    await act(async () => {
      await result.current.deleteView('relationship');
    });
    expect(deleteMock).toHaveBeenCalledWith('p1', 'relationship', 'tok');
  });
});
