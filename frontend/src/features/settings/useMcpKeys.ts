import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { mcpKeysApi, type McpKey, type McpKeyCreatePayload, type McpKeyCreated } from './api';

/**
 * Controller for the Settings → MCP access tab: owns the key list + the
 * create/revoke flows. The view (McpAccessTab) renders only. `create` returns
 * the created key (incl. the once-only secret) so the view can reveal it; the
 * secret is NEVER stored here or anywhere persistent.
 */
export function useMcpKeys() {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [keys, setKeys] = useState<McpKey[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const data = await mcpKeysApi.list(accessToken);
      setKeys(data.items ?? []);
    } catch {
      toast.error(t('mcp.toast.load_failed'));
    } finally {
      setLoading(false);
    }
  }, [accessToken, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(
    async (payload: McpKeyCreatePayload): Promise<McpKeyCreated | null> => {
      if (!accessToken) return null;
      try {
        const created = await mcpKeysApi.create(accessToken, payload);
        toast.success(t('mcp.toast.created', { name: created.name }));
        await refresh();
        return created;
      } catch (e) {
        toast.error((e as Error).message || t('mcp.toast.create_failed'));
        return null;
      }
    },
    [accessToken, refresh, t],
  );

  const revoke = useCallback(
    async (keyId: string) => {
      if (!accessToken) return;
      try {
        await mcpKeysApi.revoke(accessToken, keyId);
        toast.success(t('mcp.toast.revoked'));
        await refresh();
      } catch (e) {
        toast.error((e as Error).message || t('mcp.toast.revoke_failed'));
      }
    },
    [accessToken, refresh, t],
  );

  return { keys, loading, create, revoke, refresh };
}
