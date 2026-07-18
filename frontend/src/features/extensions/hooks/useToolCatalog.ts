// Controller hook (MVC) — the real tool catalog, so the permissions panel can offer a
// PICKER instead of a free-text box. Track C WS-3.
//
// Why this exists: a free-text "block a tool" field let a typo create a permission row
// for a tool that does not exist, which the panel then rendered as "Blocked — never runs".
// That is a security guarantee about nothing, and it is exactly the write-only-behavior
// bug class the consent slice was built to kill.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import type { ToolCatalogItem } from '../types';

export function useToolCatalog() {
  const { accessToken } = useAuth();
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extensionsApi.listToolCatalog(accessToken);
      setTools(res.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load the tool catalog');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const names = useMemo(() => new Set(tools.map((t) => t.name)), [tools]);

  return { tools, names, loading, error, refresh };
}
