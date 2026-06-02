import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const listSourcesMock = vi.fn();
const registerSourceMock = vi.fn();
const ingestSourceMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    enrichmentApi: {
      listSources: (...a: unknown[]) => listSourcesMock(...a),
      registerSource: (...a: unknown[]) => registerSourceMock(...a),
      ingestSource: (...a: unknown[]) => ingestSourceMock(...a),
    },
  };
});

import { useEnrichmentSources } from '../useEnrichmentSources';
import type { Source, IngestResult } from '../../types';

const BOOK = 'book-1';

const S = (over: Partial<Source> = {}): Source =>
  ({
    corpus_id: 'c-1',
    project_id: BOOK,
    name: '封神演義',
    kind: 'fengshen',
    license: 'public_domain',
    chunk_count: 0,
    provenance_json: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  } as Source);

const ING = (over: Partial<IngestResult> = {}): IngestResult =>
  ({
    corpus_id: 'c-1',
    chunks_total: 12,
    chunks_inserted: 12,
    chunks_embedded: 12,
    ...over,
  } as IngestResult);

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => {
  [listSourcesMock, registerSourceMock, ingestSourceMock].forEach((m) => m.mockReset());
  Object.values(toastMocks).forEach((m) => m.mockReset());
  // Default: the list query resolves to an empty page so the hook mounts cleanly.
  listSourcesMock.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
});

describe('useEnrichmentSources', () => {
  it('register calls registerSource(bookId, body, token), toasts, invalidates, returns the source', async () => {
    const created = S();
    registerSourceMock.mockResolvedValue(created);
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentSources(BOOK), { wrapper: Wrapper });

    const body = { name: '封神演義', kind: 'fengshen', license: 'public_domain' };
    let out: unknown;
    await act(async () => {
      out = await result.current.register(body);
    });

    expect(registerSourceMock).toHaveBeenCalledWith(BOOK, body, 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('sources.registered');
    expect(invalidateSpy.mock.calls.map((c) => c[0]?.queryKey)).toContainEqual([
      'enrichment-sources',
      BOOK,
    ]);
    expect(out).toBe(created);
  });

  it('register on API error: toasts the error message, returns null, does NOT invalidate', async () => {
    registerSourceMock.mockRejectedValue(new Error('register boom'));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentSources(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.register({ name: 'x', kind: 'other' });
    });

    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('register boom');
    expect(toastMocks.success).not.toHaveBeenCalled();
    expect(invalidateSpy.mock.calls.map((c) => c[0]?.queryKey)).not.toContainEqual([
      'enrichment-sources',
      BOOK,
    ]);
  });

  it('ingest calls ingestSource(corpusId, bookId, body, token), toasts, invalidates, returns the result', async () => {
    const res = ING({ chunks_embedded: 7 });
    ingestSourceMock.mockResolvedValue(res);
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentSources(BOOK), { wrapper: Wrapper });

    const body = { text: '...', embedding_model_ref: 'm1', target_chars: 800 };
    let out: unknown;
    await act(async () => {
      out = await result.current.ingest('c-1', body);
    });

    expect(ingestSourceMock).toHaveBeenCalledWith('c-1', BOOK, body, 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('sources.ingested');
    expect(invalidateSpy.mock.calls.map((c) => c[0]?.queryKey)).toContainEqual([
      'enrichment-sources',
      BOOK,
    ]);
    expect(out).toBe(res);
  });

  it('ingest on API error: toasts the error message, returns null, does NOT invalidate', async () => {
    ingestSourceMock.mockRejectedValue(new Error('ingest boom'));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentSources(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.ingest('c-1', { text: 't', embedding_model_ref: 'm1' });
    });

    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('ingest boom');
    expect(invalidateSpy.mock.calls.map((c) => c[0]?.queryKey)).not.toContainEqual([
      'enrichment-sources',
      BOOK,
    ]);
  });

  it('items defaults to [] and total to 0 before the list query resolves (data undefined)', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentSources(BOOK), { wrapper: Wrapper });
    // Synchronously after mount the query is still pending → data is undefined.
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('items/total reflect the list query once it resolves', async () => {
    listSourcesMock.mockResolvedValue({ items: [S(), S({ corpus_id: 'c-2' })], total: 2, limit: 100, offset: 0 });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentSources(BOOK), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.total).toBe(2));
    expect(result.current.items).toHaveLength(2);
    expect(listSourcesMock).toHaveBeenCalledWith(BOOK, 'tok');
  });
});
