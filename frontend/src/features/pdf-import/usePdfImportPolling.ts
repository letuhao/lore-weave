import { useCallback, useEffect, useRef, useState } from 'react';
import { booksApi, type ImportJob } from '@/features/books/api';

// docs/specs/2026-07-06-pdf-book-import.md — mirrors
// features/extraction/useExtractionPolling.ts's self-contained polling-
// hook shape (NOT components/import/ImportDialog.tsx's inlined
// setInterval-in-component anti-pattern). This is the FALLBACK path;
// useImportEvents' WebSocket push is primary — see StepProgress.tsx.

const TERMINAL_STATUSES = new Set(['completed', 'failed']);

export function usePdfImportPolling(
  token: string | null,
  bookId: string | null,
  jobId: string | null,
  intervalMs = 5000,
) {
  const [job, setJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!token || !bookId || !jobId) return;

    const poll = async () => {
      try {
        const data = await booksApi.getImportJob(token, bookId, jobId);
        setJob(data);
        if (TERMINAL_STATUSES.has(data.status)) stopPolling();
      } catch (e) {
        setError((e as Error).message);
      }
    };

    void poll();
    intervalRef.current = setInterval(() => void poll(), intervalMs);
    return stopPolling;
  }, [token, bookId, jobId, intervalMs, stopPolling]);

  const isTerminal = job ? TERMINAL_STATUSES.has(job.status) : false;
  return { job, error, isTerminal, stopPolling };
}
