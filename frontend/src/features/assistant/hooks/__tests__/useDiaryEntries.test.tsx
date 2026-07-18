import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// M1 — the journal-timeline controller: fetch the diary book's PRIMARY entries, newest-first,
// and surface an error rather than a blank list on failure.

const listDiaryEntries = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({
  assistantApi: { listDiaryEntries: (...a: unknown[]) => listDiaryEntries(...a) },
}));

import { useDiaryEntries } from '../useDiaryEntries';

beforeEach(() => {
  listDiaryEntries.mockReset();
});

describe('useDiaryEntries', () => {
  it('loads PRIMARY entries newest-first and drops non-primary kinds', async () => {
    listDiaryEntries.mockResolvedValue({
      entries: [
        { chapter_id: 'a', entry_date: '2026-07-12', journal_kind: 'primary', body: 'x', title: 'A', word_count: 1, entry_zone: 'UTC', kept: false },
        { chapter_id: 'b', entry_date: '2026-07-14', journal_kind: 'primary', body: 'y', title: 'B', word_count: 1, entry_zone: 'UTC', kept: false },
        { chapter_id: 'r', entry_date: '2026-07-13', journal_kind: 'reflection', body: 'z', title: 'R', word_count: 1, entry_zone: 'UTC', kept: false },
      ],
      count: 3,
    });
    const { result } = renderHook(() => useDiaryEntries('book-1'));
    await waitFor(() => expect(result.current.entries.length).toBe(2));
    // reflection dropped; newest-first
    expect(result.current.entries.map((e) => e.chapter_id)).toEqual(['b', 'a']);
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error instead of a blank list on failure', async () => {
    listDiaryEntries.mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useDiaryEntries('book-1'));
    await waitFor(() => expect(result.current.error).toBe('nope'));
    expect(result.current.entries).toEqual([]);
  });

  it('does nothing without a bookId', async () => {
    const { result } = renderHook(() => useDiaryEntries(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listDiaryEntries).not.toHaveBeenCalled();
  });
});
