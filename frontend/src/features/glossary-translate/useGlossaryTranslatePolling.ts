import { useState, useEffect, useRef, useCallback } from 'react';
import { glossaryTranslateApi } from './api';
import type { GlossaryTranslateJobStatus } from './types';

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'completed_with_errors']);

export function useGlossaryTranslatePolling(
  jobId: string | null,
  token: string | null,
  intervalMs = 3000,
) {
  const [status, setStatus] = useState<GlossaryTranslateJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId || !token) return;

    const poll = async () => {
      try {
        const data = await glossaryTranslateApi.getJobStatus(jobId, token);
        setStatus(data);
        setError(null); // S1: a recovered poll clears a prior transient error
        if (TERMINAL_STATUSES.has(data.status)) {
          stopPolling();
        }
      } catch (e) {
        setError((e as Error).message);
      }
    };

    void poll();
    intervalRef.current = setInterval(() => void poll(), intervalMs);

    return stopPolling;
  }, [jobId, token, intervalMs, stopPolling]);

  const isTerminal = status ? TERMINAL_STATUSES.has(status.status) : false;

  return { status, error, isTerminal, stopPolling };
}
