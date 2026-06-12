import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const patchWorkMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { patchWork: (...a: unknown[]) => patchWorkMock(...a) },
}));

import { useSetAssemblyMode } from '../useChapterAssembly';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => patchWorkMock.mockReset());

describe('useSetAssemblyMode (chapter-assembly settings merge)', () => {
  it('MERGES assembly_mode over the existing settings (never drops other keys)', async () => {
    patchWorkMock.mockResolvedValue({ project_id: 'p1' });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useSetAssemblyMode('book-1', 'tok'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        projectId: 'p1',
        currentSettings: { critic_model_ref: 'x', reasoning_engine: 'rule_based', voice: 'wry' },
        mode: 'chapter',
      });
    });

    // /review-impl MED-1: the server REPLACES the settings blob, so the patch MUST
    // carry the existing keys + the new assembly_mode — a plain {assembly_mode}
    // would silently wipe critic_model_*/reasoning_engine/etc.
    expect(patchWorkMock).toHaveBeenCalledWith(
      'p1',
      { settings: { critic_model_ref: 'x', reasoning_engine: 'rule_based', voice: 'wry', assembly_mode: 'chapter' } },
      'tok',
    );
  });

  it('invalidates the work query (keyed by bookId) so the toggle reflects the persisted value', async () => {
    patchWorkMock.mockResolvedValue({ project_id: 'p1' });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useSetAssemblyMode('book-1', 'tok'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync({ projectId: 'p1', currentSettings: {}, mode: 'per_scene' });
    });

    await waitFor(() => {
      const keys = invalidateSpy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown[] }).queryKey));
      expect(keys).toContain(JSON.stringify(['composition', 'work', 'book-1']));
    });
  });
});
