import { useState, useEffect, useRef, useCallback } from 'react';
import { extractionApi } from './api';
import type { ExtractionJobStatus } from './types';

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'completed_with_errors']);

export function useExtractionPolling(
  jobId: string | null,
  token: string | null,
  intervalMs = 3000,
) {
  const [status, setStatus] = useState<ExtractionJobStatus | null>(null);
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
        const data = await extractionApi.getJobStatus(jobId, token);
        setStatus(data);
        if (TERMINAL_STATUSES.has(data.status)) {
          stopPolling();
        }
      } catch (e) {
        setError((e as Error).message);
      }
    };

    // Initial poll immediately
    void poll();

    // Then poll on interval
    intervalRef.current = setInterval(() => void poll(), intervalMs);

    return stopPolling;
  }, [jobId, token, intervalMs, stopPolling]);

  const isPolling = intervalRef.current !== null;
  const isTerminal = status ? TERMINAL_STATUSES.has(status.status) : false;

  return { status, error, isPolling, isTerminal, stopPolling };
}
