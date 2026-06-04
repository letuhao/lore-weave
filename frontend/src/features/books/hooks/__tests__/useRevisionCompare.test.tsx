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
