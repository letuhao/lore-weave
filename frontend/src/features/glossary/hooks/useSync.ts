import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '../tieringApi';
import type { SyncApplyItem, SyncChoice, SyncUpdateItem } from '../tieringTypes';

/**
 * Controller for the on-demand Sync screen (G5/04-sync). Loads the available diff
 * (`GET /sync/available`), holds a per-row keep_mine|take_theirs choice (default
 * keep_mine — your overrides are protected), and applies the chosen set
 * (`POST /sync/apply`). Only `update_available` rows are actionable; `source_retired`
 * rows are informational (the book copy stays frozen) and never sent to apply.
 *
 * Apply invalidates both the sync diff and the book ontology (take_theirs rewrites
 * book rows; keep_mine bumps the source_hash to silence the prompt).
 */
export function useSync(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ['glossary-sync', bookId];

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: key,
    queryFn: () => tieringApi.getSyncAvailable(bookId, accessToken!),
    enabled: !!accessToken,
  });

  const updates: SyncUpdateItem[] = data?.updates ?? [];
  const actionable = useMemo(() => updates.filter((u) => u.status === 'update_available'), [updates]);
  const retired = useMemo(() => updates.filter((u) => u.status === 'source_retired'), [updates]);

  // Per-row choice, keyed by the book row id. Defaults to keep_mine.
  const [choices, setChoices] = useState<Record<string, SyncChoice>>({});
  const choiceFor = (id: string): SyncChoice => choices[id] ?? 'keep_mine';
  const setChoice = (id: string, choice: SyncChoice) => setChoices((c) => ({ ...c, [id]: choice }));
  const setAll = (choice: SyncChoice) =>
    setChoices(Object.fromEntries(actionable.map((u) => [u.id, choice])));

  const [applying, setApplying] = useState(false);

  const apply = async (): Promise<number> => {
    const items: SyncApplyItem[] = actionable.map((u) => ({
      entity: u.entity,
      id: u.id,
      choice: choiceFor(u.id),
    }));
    if (items.length === 0) return 0;
    setApplying(true);
    try {
      const res = await tieringApi.applySync(bookId, items, accessToken!);
      setChoices({});
      void qc.invalidateQueries({ queryKey: key });
      void qc.invalidateQueries({ queryKey: ['glossary-ontology', bookId] });
      return res.applied;
    } finally {
      setApplying(false);
    }
  };

  return {
    updates,
    actionable,
    retired,
    isLoading,
    error,
    refetch,
    choiceFor,
    setChoice,
    setAll,
    apply,
    applying,
    count: actionable.length,
  };
}
