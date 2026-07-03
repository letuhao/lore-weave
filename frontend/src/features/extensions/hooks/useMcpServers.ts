// Controller hook (MVC) — owns MCP-server list + detail state & logic, no JSX.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import type { McpServer, CreateMcpServerReq } from '../types';

export function useMcpServers() {
  const { accessToken } = useAuth();
  const [servers, setServers] = useState<McpServer[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const limit = 20;

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extensionsApi.listMcpServers(accessToken, { status, limit, offset: page * limit });
      setServers(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load servers');
    } finally {
      setLoading(false);
    }
  }, [accessToken, status, page]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Client-side name filter over the current page (the list endpoint is status-paged).
  const filtered = q
    ? servers.filter((s) => (s.display_name + ' ' + s.endpoint_url).toLowerCase().includes(q.toLowerCase()))
    : servers;

  const remove = useCallback(
    async (s: McpServer) => {
      if (!accessToken) return;
      await extensionsApi.deleteMcpServer(accessToken, s.mcp_server_id);
      await refresh();
    },
    [accessToken, refresh],
  );

  const toggle = useCallback(
    async (s: McpServer, enabled: boolean) => {
      if (!accessToken) return;
      await extensionsApi.setMcpEnabled(accessToken, s.mcp_server_id, enabled);
    },
    [accessToken],
  );

  return { servers: filtered, total, loading, error, status, setStatus, q, setQ, page, setPage, limit, refresh, remove, toggle };
}

/** useMcpServerDetail — one server's detail + the security actions (rescan / accept-risk /
 * oauth connect). Used by both the wizard's Health & Scan step and the detail page. */
export function useMcpServerDetail(id: string | null) {
  const { accessToken } = useAuth();
  const [server, setServer] = useState<McpServer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken || !id) return;
    try {
      setServer(await extensionsApi.getMcpServer(accessToken, id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load server');
    }
  }, [accessToken, id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rescan = useCallback(async () => {
    if (!accessToken || !id) return;
    setBusy(true);
    setError(null);
    try {
      await extensionsApi.rescanMcpServer(accessToken, id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'rescan failed');
    } finally {
      setBusy(false);
    }
  }, [accessToken, id, refresh]);

  const acceptRisk = useCallback(async () => {
    if (!accessToken || !id) return;
    setBusy(true);
    try {
      await extensionsApi.acceptRiskMcpServer(accessToken, id);
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [accessToken, id, refresh]);

  const connectOAuth = useCallback(async () => {
    if (!accessToken || !id) return;
    const { authorization_url } = await extensionsApi.startMcpOAuth(accessToken, id);
    window.open(authorization_url, '_blank', 'noopener'); // consent in a new tab; callback returns to /extensions
  }, [accessToken, id]);

  const setEnabled = useCallback(async (enabled: boolean) => {
    if (!accessToken || !id) return;
    await extensionsApi.setMcpEnabled(accessToken, id, enabled);
    await refresh();
  }, [accessToken, id, refresh]);

  return { server, busy, error, refresh, rescan, acceptRisk, connectOAuth, setEnabled };
}

export function useCreateMcpServer() {
  const { accessToken } = useAuth();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback(
    async (body: CreateMcpServerReq): Promise<McpServer | null> => {
      if (!accessToken) return null;
      setCreating(true);
      setError(null);
      try {
        return await extensionsApi.createMcpServer(accessToken, body);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'registration failed');
        return null;
      } finally {
        setCreating(false);
      }
    },
    [accessToken],
  );

  return { create, creating, error };
}
