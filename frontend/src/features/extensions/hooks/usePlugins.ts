// Controller hook (MVC) — plugins list + bundle import/export, no JSX.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import type { Plugin, PluginBundle } from '../types';

export function usePlugins() {
  const { accessToken } = useAuth();
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setPlugins((await extensionsApi.listPlugins(accessToken, { limit: 50 })).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load plugins');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => { void refresh(); }, [refresh]);

  const remove = useCallback(async (p: Plugin) => {
    if (!accessToken) return;
    await extensionsApi.deletePlugin(accessToken, p.plugin_id);
    await refresh();
  }, [accessToken, refresh]);

  // Export → trigger a browser download of the bundle JSON.
  const exportBundle = useCallback(async (p: Plugin) => {
    if (!accessToken) return;
    const bundle = await extensionsApi.exportBundle(accessToken, p.plugin_id);
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${p.name.replace(/\//g, '-')}-${p.version}.loreweave-bundle.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [accessToken]);

  // Import a parsed bundle → returns an error string or null.
  const importBundle = useCallback(async (bundle: PluginBundle): Promise<string | null> => {
    if (!accessToken) return 'not signed in';
    try {
      await extensionsApi.importBundle(accessToken, bundle);
      await refresh();
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'import failed';
    }
  }, [accessToken, refresh]);

  return { plugins, loading, error, refresh, remove, exportBundle, importBundle };
}
