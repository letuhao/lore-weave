import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useJobsDashboard } from '../useJobsDashboard';

// Debounce is identity in the test so `q` updates synchronously.
vi.mock('@/features/knowledge/hooks/useDebouncedValue', () => ({
  useDebouncedValue: (v: unknown) => v,
}));

const listSpy = vi.fn(() => ({
  data: undefined, isLoading: false, error: null,
  hasNextPage: false, fetchNextPage: vi.fn(), isFetchingNextPage: false,
}));
const historySpy = vi.fn(() => ({
  data: { items: [], total: 0, next_cursor: null }, isLoading: false, error: null,
}));
const summarySpy = vi.fn(() => ({ data: { active: 0, completed: 0, failed: 0, cancelled: 0 } }));

vi.mock('../useJobsList', () => ({ useJobsList: (...a: unknown[]) => listSpy(...a) }));
vi.mock('../useJobsHistory', () => ({ useJobsHistory: (...a: unknown[]) => historySpy(...a) }));
vi.mock('../useJobsSummary', () => ({ useJobsSummary: () => summarySpy() }));

const lastHistoryArgs = () => historySpy.mock.calls.at(-1) as unknown as [{ status?: string; kind?: string }, number, number];
const lastListArg = () => (listSpy.mock.calls.at(-1) as unknown as [{ bucket?: string; kind?: string }])[0];

beforeEach(() => {
  listSpy.mockClear();
  historySpy.mockClear();
  summarySpy.mockClear();
});

describe('useJobsDashboard', () => {
  it("default quick='active' → Active shown, History not status-filtered", () => {
    const { result } = renderHook(() => useJobsDashboard());
    expect(result.current.quick).toBe('active');
    expect(result.current.showActive).toBe(true);
    expect(lastListArg().bucket).toBe('active'); // Active list = bucket=active
    const [filters, page] = lastHistoryArgs();
    expect(filters.status).toBeUndefined(); // 'active' card ⇒ History shows ALL terminal
    expect(page).toBe(0);
  });

  it('a terminal card hides Active + filters History to that status', () => {
    const { result } = renderHook(() => useJobsDashboard());
    act(() => result.current.selectQuick('failed'));
    expect(result.current.showActive).toBe(false);
    expect(lastHistoryArgs()[0].status).toBe('failed');
  });

  it('resets History to page 0 on EVERY filter change (else an out-of-range offset)', () => {
    const { result } = renderHook(() => useJobsDashboard());

    act(() => result.current.setPage(3));
    expect(result.current.page).toBe(3);
    act(() => result.current.selectQuick('completed'));
    expect(result.current.page).toBe(0);

    act(() => result.current.setPage(3));
    act(() => result.current.changeKind('translation'));
    expect(result.current.page).toBe(0);

    act(() => result.current.setPage(3));
    act(() => result.current.changeQ('dracula'));
    expect(result.current.page).toBe(0);

    act(() => result.current.setPage(3));
    act(() => result.current.changePageSize(25));
    expect(result.current.page).toBe(0);
    expect(result.current.pageSize).toBe(25);
  });

  it('kind + search apply to BOTH tables', () => {
    const { result } = renderHook(() => useJobsDashboard());
    act(() => result.current.changeKind('translation'));
    act(() => result.current.changeQ('vi'));
    expect(lastListArg().kind).toBe('translation');
    expect(lastHistoryArgs()[0].kind).toBe('translation');
  });
});
