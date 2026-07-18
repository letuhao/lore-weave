// C8 / SD-C8 — the weekly-reflection controller (CLAUDE.md MVC: logic here, ReflectionCard only renders).
// Surfaces the LATEST reflection draft (a diary entry with journal_kind='reflection', from the same
// listDiaryEntries the review uses) + the structured patterns (R1 / D-REFLECTION-PATTERNS-FEED, fed from
// the BFF, already tombstone-filtered server-side) so the card can render DISMISSABLE chips + the dismiss
// action (→ the C2 tombstone via the BFF; a re-fetch drops the dismissed pattern, server is SoT).
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { DiaryEntry, ReflectionPattern } from '../types';

export function useReflection(bookId: string | null) {
  const { accessToken } = useAuth();
  const [reflection, setReflection] = useState<DiaryEntry | null>(null);
  const [patterns, setPatterns] = useState<ReflectionPattern[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!accessToken || !bookId) return;
    setLoading(true);
    try {
      // Fetch the draft first, THEN the chips FOR THAT DRAFT'S WEEK (entry_date == week_end). Tying the
      // chip fetch to the displayed draft's week is load-bearing (cold-review H1): a CALM latest week has
      // no stored patterns, and a week-agnostic "latest patterns" read would fall back to a STALE prior
      // week's chips under a calm draft. The chips are best-effort — a failed fetch renders the draft
      // with no chips, never blanks the draft.
      const entries = await assistantApi.listDiaryEntries(accessToken, bookId);
      const latest = entries.entries.find((e) => e.journal_kind === 'reflection') ?? null;
      setReflection(latest);
      if (latest) {
        const pats = await assistantApi
          .getReflectionPatterns(accessToken, latest.entry_date)
          .catch(() => ({ week_end: null, patterns: [] }));
        setPatterns(pats.patterns ?? []);
      } else {
        setPatterns([]);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const dismiss = useCallback(
    async (patternKey: string) => {
      if (!accessToken) return;
      await assistantApi.dismissReflectionPattern(accessToken, patternKey); // server is SoT
      // cold-review LOW-5 — reconcile with server truth (the tombstone) rather than relying solely on
      // the card's ephemeral optimistic-hide, so a remount doesn't resurrect a dismissed pattern.
      await refresh();
    },
    [accessToken, refresh],
  );

  return { reflection, patterns, loading, refresh, dismiss };
}
