// Controller hook (MVC) — official-registry ingest curation (admin-only). Pull the
// upstream registry, list the queue, approve/reject entries. Degrade-safe like the rest.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import type { IngestEntry, IngestPullCounts, IngestStatus } from '../types';

export function useIngest() {
  const { accessToken } = useAuth();
  const [entries, setEntries] = useState<IngestEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<IngestStatus | 'all'>('pending');
  const [pulling, setPulling] = useState(false);
  const [lastPull, setLastPull] = useState<IngestPullCounts | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extensionsApi.listIngestQueue(accessToken, {
        status: status === 'all' ? undefined : status,
        limit: 50,
      });
      setEntries(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load the ingest queue');
    } finally {
      setLoading(false);
    }
  }, [accessToken, status]);

  useEffect(() => { void refresh(); }, [refresh]);

  const pull = useCallback(async (): Promise<string | null> => {
    if (!accessToken) return null;
    setPulling(true);
    try {
      const counts = await extensionsApi.ingestPull(accessToken);
      setLastPull(counts);
      await refresh();
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'pull failed';
    } finally {
      setPulling(false);
    }
  }, [accessToken, refresh]);

  const approve = useCallback(async (e: IngestEntry): Promise<string | null> => {
    if (!accessToken) return null;
    try {
      await extensionsApi.approveIngest(accessToken, e.ingest_id);
      await refresh();
      return null;
    } catch (err) {
      return err instanceof Error ? err.message : 'approve failed';
    }
  }, [accessToken, refresh]);

  const reject = useCallback(async (e: IngestEntry, reason = ''): Promise<string | null> => {
    if (!accessToken) return null;
    try {
      await extensionsApi.rejectIngest(accessToken, e.ingest_id, reason);
      await refresh();
      return null;
    } catch (err) {
      return err instanceof Error ? err.message : 'reject failed';
    }
  }, [accessToken, refresh]);

  return { entries, loading, error, status, setStatus, pulling, lastPull, refresh, pull, approve, reject };
}
