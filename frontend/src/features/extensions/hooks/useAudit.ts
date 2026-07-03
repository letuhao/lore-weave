// Controller hook (MVC) — the registry activity log (owner-scoped audit). Read-only
// with a kind + time-range filter; a filter change re-queries.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import type { AuditEntry } from '../types';

export type AuditRange = 'all' | '7d' | '30d';

export function useAudit() {
  const { accessToken } = useAuth();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState('');
  const [range, setRange] = useState<AuditRange>('all');

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extensionsApi.listAudit(accessToken, {
        kind: kind || undefined,
        range: range === 'all' ? undefined : range,
        limit: 50,
      });
      setEntries(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load activity');
    } finally {
      setLoading(false);
    }
  }, [accessToken, kind, range]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { entries, loading, error, kind, setKind, range, setRange, refresh };
}
