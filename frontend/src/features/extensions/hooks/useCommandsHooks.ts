// Controller hooks (MVC) — commands + hooks CRUD, no JSX.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import { useExtensionScope } from '../context/ExtensionScope';
import type { SlashCommand, Hook, CreateCommandReq, CreateHookReq } from '../types';

export function useCommands() {
  const { accessToken } = useAuth();
  const { bookId } = useExtensionScope();
  const [commands, setCommands] = useState<SlashCommand[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setCommands((await extensionsApi.listCommands(accessToken, { limit: 50, book_id: bookId ?? undefined })).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load commands');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const create = useCallback(async (body: CreateCommandReq): Promise<string | null> => {
    if (!accessToken) return null;
    try {
      await extensionsApi.createCommand(accessToken, { ...body, ...(bookId ? { tier: 'book' as const, book_id: bookId } : {}) });
      await refresh();
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'create failed';
    }
  }, [accessToken, bookId, refresh]);

  const remove = useCallback(async (c: SlashCommand) => {
    if (!accessToken) return;
    await extensionsApi.deleteCommand(accessToken, c.command_id);
    await refresh();
  }, [accessToken, refresh]);

  const toggle = useCallback(async (c: SlashCommand, enabled: boolean) => {
    if (!accessToken) return;
    await extensionsApi.patchCommand(accessToken, c.command_id, { enabled });
    await refresh();
  }, [accessToken, refresh]);

  return { commands, loading, error, refresh, create, remove, toggle };
}

export function useHooks() {
  const { accessToken } = useAuth();
  const { bookId } = useExtensionScope();
  const [hooks, setHooks] = useState<Hook[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setHooks((await extensionsApi.listHooks(accessToken, { limit: 50, book_id: bookId ?? undefined })).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load hooks');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const create = useCallback(async (body: CreateHookReq): Promise<string | null> => {
    if (!accessToken) return null;
    try {
      await extensionsApi.createHook(accessToken, { ...body, ...(bookId ? { tier: 'book' as const, book_id: bookId } : {}) });
      await refresh();
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'create failed';
    }
  }, [accessToken, bookId, refresh]);

  const remove = useCallback(async (h: Hook) => {
    if (!accessToken) return;
    await extensionsApi.deleteHook(accessToken, h.hook_id);
    await refresh();
  }, [accessToken, refresh]);

  const toggle = useCallback(async (h: Hook, enabled: boolean) => {
    if (!accessToken) return;
    await extensionsApi.patchHook(accessToken, h.hook_id, { enabled });
    await refresh();
  }, [accessToken, refresh]);

  return { hooks, loading, error, refresh, create, remove, toggle };
}
