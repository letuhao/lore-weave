import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
const listRuns = vi.fn();
vi.mock('@/features/plan-forge/api', () => ({
  planForgeApi: { listRuns: (...a: unknown[]) => listRuns(...a) },
}));

import { useDraftHandoffCta } from '../useDraftHandoffCta';

const run = (status: string) => ({
  id: 'r', status, book_id: 'b1', mode: 'rules', model_ref: null, source_checksum: null,
  active_job_id: null, job_status: null, error_detail: null, checkpoint_state: null,
  artifacts: [], created_at: '', updated_at: '',
});

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => listRuns.mockReset());

describe('useDraftHandoffCta', () => {
  it('shows the CTA when a compiled plan exists (draftable)', async () => {
    listRuns.mockResolvedValue({ items: [run('compiled')] });
    const { result } = renderHook(() => useDraftHandoffCta('b1'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.showStartDrafting).toBe(true));
  });

  it('shows the CTA when a validated plan exists (also draftable, mirrors the New-run picker)', async () => {
    listRuns.mockResolvedValue({ items: [run('validated')] });
    const { result } = renderHook(() => useDraftHandoffCta('b1'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.showStartDrafting).toBe(true));
  });

  it('hides the CTA when only a proposed (not-yet-draftable) plan exists', async () => {
    listRuns.mockResolvedValue({ items: [run('proposed')] });
    const { result } = renderHook(() => useDraftHandoffCta('b1'), { wrapper: makeWrapper() });
    await waitFor(() => expect(listRuns).toHaveBeenCalled());
    expect(result.current.showStartDrafting).toBe(false);
  });

  it('hides the CTA when the book has no plans at all', async () => {
    listRuns.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useDraftHandoffCta('b1'), { wrapper: makeWrapper() });
    await waitFor(() => expect(listRuns).toHaveBeenCalled());
    expect(result.current.showStartDrafting).toBe(false);
  });
});
