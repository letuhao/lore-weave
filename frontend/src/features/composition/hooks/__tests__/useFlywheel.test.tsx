import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useFlywheel } from '../useFlywheel';

const { getFlywheel } = vi.hoisted(() => ({ getFlywheel: vi.fn() }));
vi.mock('@/features/knowledge/api', () => ({ knowledgeApi: { getFlywheel } }));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => getFlywheel.mockReset());

describe('useFlywheel (T4.1)', () => {
  it('fetches the flywheel delta for the project', async () => {
    getFlywheel.mockResolvedValue({ has_delta: true, entities_added: 3, relations_added: 1, events_added: 0, new_items: [] });
    const { result } = renderHook(() => useFlywheel('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getFlywheel).toHaveBeenCalledWith('p1', 't');
    expect(result.current.data!.entities_added).toBe(3);
  });

  it('is disabled without a projectId', () => {
    renderHook(() => useFlywheel(undefined, 't'), { wrapper: makeWrapper() });
    expect(getFlywheel).not.toHaveBeenCalled();
  });

  it('is disabled without a token', () => {
    renderHook(() => useFlywheel('p1', null), { wrapper: makeWrapper() });
    expect(getFlywheel).not.toHaveBeenCalled();
  });
});
