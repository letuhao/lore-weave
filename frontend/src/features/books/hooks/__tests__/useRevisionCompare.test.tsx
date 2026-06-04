import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const listRevisionsMock = vi.fn();
const compareMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listRevisions: (...a: unknown[]) => listRevisionsMock(...a),
    compareRevisions: (...a: unknown[]) => compareMock(...a),
  },
}));

import { useRevisionCompare } from '../useRevisionCompare';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const render = () =>
  renderHook(() => useRevisionCompare('tok', 'b1', 'c1'), { wrapper: Wrapper });

beforeEach(() => {
  listRevisionsMock.mockReset();
  compareMock.mockReset();
  compareMock.mockResolvedValue({ left: {}, right: {}, diff: [], truncated: false });
});

describe('useRevisionCompare', () => {
  it('defaults to the two newest revisions (right=newest, left=second) and compares them', async () => {
    listRevisionsMock.mockResolvedValue({
      items: [
        { revision_id: 'r3', created_at: '2026-01-03' },
        { revision_id: 'r2', created_at: '2026-01-02' },
        { revision_id: 'r1', created_at: '2026-01-01' },
      ],
      total: 3,
    });
    const { result } = render();
    await waitFor(() => expect(result.current.items.length).toBe(3));
    await waitFor(() => expect(compareMock).toHaveBeenCalledWith('tok', 'b1', 'c1', 'r2', 'r3'));
    expect(result.current.leftId).toBe('r2');
    expect(result.current.rightId).toBe('r3');
  });

  it('does not call compare when there is only one revision', async () => {
    listRevisionsMock.mockResolvedValue({ items: [{ revision_id: 'r1', created_at: '2026-01-01' }], total: 1 });
    const { result } = render();
    await waitFor(() => expect(result.current.items.length).toBe(1));
    expect(compareMock).not.toHaveBeenCalled();
  });

  it('paginates: hasMore when loaded < total, loadMore accumulates pages', async () => {
    // page of 2 with total 3 → one more page (the older revision).
    listRevisionsMock.mockImplementation((_t: string, _b: string, _c: string, params: { offset?: number }) => {
      const all = [
        { revision_id: 'r3', created_at: '2026-01-03' },
        { revision_id: 'r2', created_at: '2026-01-02' },
        { revision_id: 'r1', created_at: '2026-01-01' },
      ];
      const offset = params?.offset ?? 0;
      return Promise.resolve({ items: all.slice(offset, offset + 2), total: 3 });
    });
    const { result } = render();
    await waitFor(() => expect(result.current.items.length).toBe(2));
    expect(result.current.hasMore).toBe(true);
    expect(result.current.total).toBe(3);
    // r1 (the oldest) is NOT yet selectable
    expect(result.current.items.map((i) => i.revision_id)).not.toContain('r1');

    await act(async () => {
      await result.current.loadMore();
    });
    await waitFor(() => expect(result.current.items.length).toBe(3));
    expect(result.current.hasMore).toBe(false);
    expect(result.current.items.map((i) => i.revision_id)).toContain('r1');
  });

  it('an explicit pick overrides the default side', async () => {
    listRevisionsMock.mockResolvedValue({
      items: [
        { revision_id: 'r3', created_at: '2026-01-03' },
        { revision_id: 'r2', created_at: '2026-01-02' },
        { revision_id: 'r1', created_at: '2026-01-01' },
      ],
      total: 3,
    });
    const { result } = render();
    await waitFor(() => expect(compareMock).toHaveBeenCalled());
    act(() => result.current.setLeftId('r1'));
    await waitFor(() => expect(compareMock).toHaveBeenLastCalledWith('tok', 'b1', 'c1', 'r1', 'r3'));
  });
});
