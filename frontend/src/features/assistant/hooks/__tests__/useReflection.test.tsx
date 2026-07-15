import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// R1 (D-REFLECTION-PATTERNS-FEED) — the hook must FEED the structured patterns (previously hardcoded
// to []), so the card can render dismissable chips, and a dismiss must re-fetch (server is SoT).

const listDiaryEntries = vi.fn();
const getReflectionPatterns = vi.fn();
const dismissReflectionPattern = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({
  assistantApi: {
    listDiaryEntries: (...a: unknown[]) => listDiaryEntries(...a),
    getReflectionPatterns: (...a: unknown[]) => getReflectionPatterns(...a),
    dismissReflectionPattern: (...a: unknown[]) => dismissReflectionPattern(...a),
  },
}));

import { useReflection } from '../useReflection';

const reflectionEntry = { chapter_id: 'r1', entry_date: '2026-07-12', journal_kind: 'reflection', body: '## x' };

beforeEach(() => {
  listDiaryEntries.mockReset();
  getReflectionPatterns.mockReset();
  dismissReflectionPattern.mockReset();
  listDiaryEntries.mockResolvedValue({ entries: [reflectionEntry] });
  getReflectionPatterns.mockResolvedValue({
    week_end: '2026-07-12',
    patterns: [{ detector_code: 'co_occurrence', summary: "'migration' recurred", pattern_key: 'co_occurrence:migration' }],
  });
  dismissReflectionPattern.mockResolvedValue({ dismissed: true, pattern_key: 'co_occurrence:migration' });
});

describe('useReflection', () => {
  it('feeds the structured patterns from the backend (no longer hardcoded to [])', async () => {
    const { result } = renderHook(() => useReflection('book-1'));
    await waitFor(() => expect(result.current.reflection).not.toBeNull());
    // cold-review H1: the chips are fetched FOR THE DISPLAYED DRAFT'S WEEK (entry_date), not week-agnostic.
    expect(getReflectionPatterns).toHaveBeenCalledWith('tok', '2026-07-12');
    expect(result.current.patterns).toHaveLength(1);
    expect(result.current.patterns[0].pattern_key).toBe('co_occurrence:migration');
  });

  it('dismiss tombstones via the API then re-fetches (server is SoT — the dismissed chip drops on refresh)', async () => {
    // after the dismiss, the backend excludes the tombstoned pattern.
    const { result } = renderHook(() => useReflection('book-1'));
    await waitFor(() => expect(result.current.patterns).toHaveLength(1));
    getReflectionPatterns.mockResolvedValue({ week_end: '2026-07-12', patterns: [] });
    await act(async () => {
      await result.current.dismiss('co_occurrence:migration');
    });
    expect(dismissReflectionPattern).toHaveBeenCalledWith('tok', 'co_occurrence:migration');
    await waitFor(() => expect(result.current.patterns).toHaveLength(0));
  });

  it('a failed patterns fetch does not blank the draft (chips are best-effort)', async () => {
    getReflectionPatterns.mockRejectedValue(new Error('chat down'));
    const { result } = renderHook(() => useReflection('book-1'));
    await waitFor(() => expect(result.current.reflection).not.toBeNull());
    expect(result.current.patterns).toEqual([]);
  });
});
