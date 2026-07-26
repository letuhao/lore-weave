// Controller hook (MVC) — subagent-persona CRUD, no JSX. Mirrors useCommands:
// a create returns an error STRING (surfaced verbatim, no silent no-op) or null.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import { useExtensionScope } from '../context/ExtensionScope';
import type { Subagent, CreateSubagentReq } from '../types';

export function useSubagents() {
  const { accessToken } = useAuth();
  const { bookId } = useExtensionScope();
  const [subagents, setSubagents] = useState<Subagent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setSubagents((await extensionsApi.listSubagents(accessToken, { limit: 50, book_id: bookId ?? undefined })).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load subagents');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const create = useCallback(async (body: CreateSubagentReq): Promise<string | null> => {
    if (!accessToken) return null;
    try {
      await extensionsApi.createSubagent(accessToken, { ...body, ...(bookId ? { tier: 'book' as const, book_id: bookId } : {}) });
      await refresh();
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'create failed';
    }
  }, [accessToken, bookId, refresh]);

  const remove = useCallback(async (s: Subagent) => {
    if (!accessToken) return;
    await extensionsApi.deleteSubagent(accessToken, s.subagent_id);
    await refresh();
  }, [accessToken, refresh]);

  const toggle = useCallback(async (s: Subagent, enabled: boolean) => {
    if (!accessToken) return;
    await extensionsApi.patchSubagent(accessToken, s.subagent_id, { enabled });
    await refresh();
  }, [accessToken, refresh]);

  return { subagents, loading, error, refresh, create, remove, toggle };
}
