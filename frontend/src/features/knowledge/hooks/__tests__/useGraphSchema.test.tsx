import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const getSchemaMock = vi.fn();
const addEdgeTypeMock = vi.fn();
const deprecateEdgeTypeMock = vi.fn();
const addVocabValueMock = vi.fn();
vi.mock('../../api/ontology', () => ({
  ontologyApi: {
    getSchema: (...a: unknown[]) => getSchemaMock(...a),
    addEdgeType: (...a: unknown[]) => addEdgeTypeMock(...a),
    deprecateEdgeType: (...a: unknown[]) => deprecateEdgeTypeMock(...a),
    addVocabValue: (...a: unknown[]) => addVocabValueMock(...a),
  },
}));

import { useGraphSchema } from '../useGraphSchema';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  getSchemaMock.mockReset().mockResolvedValue({
    schema_id: 's1',
    scope: 'project',
    code: 'xianxia',
    name: 'Xianxia',
    schema_version: 3,
    allow_free_edges: true,
    edge_types: [{ code: 'PURSUES', label: 'Pursues', directed: true, temporal: true, cardinality: 'single_active' }],
  });
  addEdgeTypeMock.mockReset().mockResolvedValue({ code: 'NEW', label: 'New' });
  deprecateEdgeTypeMock.mockReset().mockResolvedValue(undefined);
  addVocabValueMock.mockReset().mockResolvedValue({ code: 'obsession', label: 'Obsession' });
});

describe('useGraphSchema — tree + child mutations', () => {
  it('loads the schema tree', async () => {
    const { result } = renderHook(() => useGraphSchema('s1'), { wrapper });
    await waitFor(() => expect(result.current.schema?.code).toBe('xianxia'));
    expect(getSchemaMock).toHaveBeenCalledWith('s1', 'tok');
  });

  it('does not fetch when schemaId is null', async () => {
    const { result } = renderHook(() => useGraphSchema(null), { wrapper });
    expect(result.current.schema).toBeNull();
    expect(getSchemaMock).not.toHaveBeenCalled();
  });

  it('adds an edge type via the additive create', async () => {
    const { result } = renderHook(() => useGraphSchema('s1'), { wrapper });
    await waitFor(() => expect(result.current.schema).not.toBeNull());
    await act(async () => {
      await result.current.addEdgeType({ code: 'MASTER_OF', label: 'Master of' });
    });
    expect(addEdgeTypeMock).toHaveBeenCalledWith('s1', { code: 'MASTER_OF', label: 'Master of' }, 'tok');
  });

  it('deprecates an edge type (deprecate-only)', async () => {
    const { result } = renderHook(() => useGraphSchema('s1'), { wrapper });
    await waitFor(() => expect(result.current.schema).not.toBeNull());
    await act(async () => {
      await result.current.deprecateEdgeType('PURSUES');
    });
    expect(deprecateEdgeTypeMock).toHaveBeenCalledWith('s1', 'PURSUES', 'tok');
  });

  it('adds a vocab value under its set', async () => {
    const { result } = renderHook(() => useGraphSchema('s1'), { wrapper });
    await waitFor(() => expect(result.current.schema).not.toBeNull());
    await act(async () => {
      await result.current.addVocabValue({ setCode: 'drive', body: { code: 'obsession', label: 'Obsession' } });
    });
    expect(addVocabValueMock).toHaveBeenCalledWith('s1', 'drive', { code: 'obsession', label: 'Obsession' }, 'tok');
  });
});
