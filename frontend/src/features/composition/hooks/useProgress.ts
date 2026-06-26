// LOOM Composition (T4.2) — writing-progress controller.
import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';

/** The user's LOCAL calendar date as YYYY-MM-DD (NOT UTC) — streaks honor the
 *  writer's own midnight. Built from the local components, not toISOString. */
export function localDateKey(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * The Work's writing-progress stats anchored to the client's local "today". Keyed
 * by the date so a day-rollover (or a manual refetch after a report) re-anchors.
 * Read-only; the report side-channel (useReportProgress) drives invalidation.
 */
export function useProgress(projectId: string | undefined, token: string | null) {
  const today = localDateKey();
  return useQuery({
    queryKey: ['composition', 'progress', projectId, today],
    queryFn: () => compositionApi.getProgress(projectId!, today, token!),
    enabled: !!projectId && !!token,
  });
}

/**
 * Returns a stable `report(chapterId, words)` the editor calls after a successful
 * save — it snapshots the chapter's current total word count for today's local
 * date (idempotent server-side) and refreshes the progress query. Best-effort: a
 * failed report is swallowed so it NEVER disrupts the save it rides on.
 */
export function useReportProgress(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useCallback(
    (chapterId: string, words: number) => {
      if (!projectId || !token || !chapterId) return;
      compositionApi
        .reportProgress(projectId, { chapter_id: chapterId, words, date: localDateKey() }, token)
        .then(() => qc.invalidateQueries({ queryKey: ['composition', 'progress', projectId] }))
        .catch(() => {});
    },
    [projectId, token, qc],
  );
}

/**
 * Returns a stable `ensureBaseline(chapterId, words)` the editor calls when a chapter
 * LOADS — it records the chapter's pre-existing word count once (insert-once on the
 * server) so the chapter's first daily snapshot counts only the words written this
 * session, not pre-existing content. Best-effort: a failure is swallowed.
 */
export function useEnsureBaseline(projectId: string | undefined, token: string | null) {
  return useCallback(
    (chapterId: string, words: number) => {
      if (!projectId || !token || !chapterId) return;
      compositionApi.baselineProgress(projectId, { chapter_id: chapterId, words }, token).catch(() => {});
    },
    [projectId, token],
  );
}

/**
 * Persist the editable daily word goal into work.settings (the server REPLACES the
 * whole settings blob, so we MERGE current settings + { daily_goal } — same rule as
 * useSetWorkSettings). `goal <= 0` clears the goal (stored as null). Keyed by bookId
 * for the work-query invalidation so the panel reflects the new goal.
 */
export function useSetDailyGoal(
  bookId: string | undefined, token: string | null,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { projectId: string; currentSettings: Record<string, unknown>; goal: number }) =>
      compositionApi.patchWork(
        v.projectId,
        { settings: { ...v.currentSettings, daily_goal: v.goal > 0 ? v.goal : null } },
        token!,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] });
      qc.invalidateQueries({ queryKey: ['composition', 'progress'] });
    },
  });
}
