// C8 / SD-C8 — the weekly-reflection controller (CLAUDE.md MVC: logic here, ReflectionCard only renders).
// Surfaces the LATEST reflection draft (a diary entry with journal_kind='reflection', from the same
// listDiaryEntries the review uses) + the dismiss action (→ the C2 tombstone via the BFF). The structured
// pattern list (with dismissable keys) is fed by `patterns` when the backend exposes it
// (D-REFLECTION-PATTERNS-FEED); until then the card renders the descriptive draft.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { DiaryEntry, ReflectionPattern } from '../types';

export function useReflection(bookId: string | null) {
  const { accessToken } = useAuth();
  const [reflection, setReflection] = useState<DiaryEntry | null>(null);
  const [patterns] = useState<ReflectionPattern[]>([]); // fed once the backend exposes structured patterns
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!accessToken || !bookId) return;
    setLoading(true);
    try {
      const res = await assistantApi.listDiaryEntries(accessToken, bookId);
      // newest-first already; take the most recent reflection entry.
      setReflection(res.entries.find((e) => e.journal_kind === 'reflection') ?? null);
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
