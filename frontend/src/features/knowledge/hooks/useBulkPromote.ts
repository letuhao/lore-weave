import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type Entity } from '../api';

// C10 (C10-gap-report) — sequential BULK-promote over the gap report.
//
// LOCKED: bulk-promote is NOT a batch endpoint and NOT a re-implemented
// promote. It is a SEQUENTIAL loop of the C9 single-promote
// (knowledgeApi.promoteEntity, POST /entities/{id}/promote) — the exact
// same draft-create→anchor orchestration. This hook adds only the
// progress indicator + partial-failure survival on top.
//
// Sequential (one await at a time, NOT a parallel fan-out) on purpose:
//   - each promote does two cross-service calls (glossary draft + anchor);
//     firing N in parallel would hammer the glossary writeback path.
//   - a single failed item must NOT abort the rest — we catch per-item
//     and keep going, then report which failed.

export interface BulkPromoteFailure {
  entityId: string;
  error: Error;
}

export interface BulkPromoteProgress {
  done: number;
  total: number;
  failed: number;
}

export interface UseBulkPromoteResult {
  run: (entityIds: string[]) => Promise<void>;
  isRunning: boolean;
  progress: BulkPromoteProgress;
  /** Ids that promoted successfully (now canonical). */
  succeeded: string[];
  /** Ids that failed, with their error — surfaced, never swallowed. */
  failures: BulkPromoteFailure[];
  /** Clear the last run's progress/result (e.g. before a new selection). */
  reset: () => void;
}

const EMPTY_PROGRESS: BulkPromoteProgress = { done: 0, total: 0, failed: 0 };

export function useBulkPromote(options?: {
  onItemSuccess?: (entity: Entity) => void;
  onComplete?: (summary: {
    succeeded: string[];
    failures: BulkPromoteFailure[];
  }) => void;
}): UseBulkPromoteResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState<BulkPromoteProgress>(EMPTY_PROGRESS);
  const [succeeded, setSucceeded] = useState<string[]>([]);
  const [failures, setFailures] = useState<BulkPromoteFailure[]>([]);

  const reset = useCallback(() => {
    setProgress(EMPTY_PROGRESS);
    setSucceeded([]);
    setFailures([]);
  }, []);

  const run = useCallback(
    async (entityIds: string[]) => {
      if (!accessToken || entityIds.length === 0) return;
      setIsRunning(true);
      setProgress({ done: 0, total: entityIds.length, failed: 0 });
      const localSucceeded: string[] = [];
      const localFailures: BulkPromoteFailure[] = [];

      // Sequential — await each before the next. A throw is caught so one
      // bad item never aborts the batch.
      for (const id of entityIds) {
        try {
          const entity = await knowledgeApi.promoteEntity(id, accessToken);
          localSucceeded.push(id);
          options?.onItemSuccess?.(entity);
        } catch (err) {
          localFailures.push({ entityId: id, error: err as Error });
        }
        setProgress((p) => ({
          done: p.done + 1,
          total: p.total,
          failed: localFailures.length,
        }));
      }

      setSucceeded(localSucceeded);
      setFailures(localFailures);
      setIsRunning(false);

      // Promoted entities flipped discovered → canonical: invalidate the
      // gap report (they leave the list) AND the entities browse list.
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-gaps', userId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entities', userId],
      });

      options?.onComplete?.({
        succeeded: localSucceeded,
        failures: localFailures,
      });
    },
    [accessToken, options, queryClient, userId],
  );

  return { run, isRunning, progress, succeeded, failures, reset };
}
