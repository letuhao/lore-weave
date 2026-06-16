import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { jobsApi } from '../api';
import type { Job, JobControlAction } from '../types';

export type ControlArgs = { service: string; jobId: string; action: JobControlAction };

/** Cancel / pause / resume a job. Routes to the owning service (which re-verifies
 *  ownership); a stale-state 409 / unreachable 502 surfaces to onError. On success,
 *  invalidates ['jobs'] so the list + detail reflect the new state at once. */
export function useJobControl(opts?: {
  onSuccess?: (job: Job, args: ControlArgs) => void;
  onError?: (err: Error, args: ControlArgs) => void;
}) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ service, jobId, action }: ControlArgs) =>
      jobsApi.control(service, jobId, action, accessToken!),
    onSuccess: async (job, args) => {
      await qc.invalidateQueries({ queryKey: ['jobs'] });
      opts?.onSuccess?.(job, args);
    },
    onError: async (err, args) => {
      // A 409 (state drifted) or 404 (gone) means our projection row is stale —
      // re-sync so the bad action's button disappears and the "refreshed" toast
      // is actually true (without this the same stale button just 409s again).
      const status = (err as { status?: number }).status;
      if (status === 409 || status === 404) {
        await qc.invalidateQueries({ queryKey: ['jobs'] });
      }
      opts?.onError?.(err as Error, args);
    },
  });
}
