// View (MVC) — plugins list + bundle import/export (REG-P5-04). Render-only.
import { useRef, useState } from 'react';
import { usePlugins } from '../hooks/usePlugins';
import type { Plugin, PluginBundle } from '../types';

export function PluginsView() {
  const p = usePlugins();
  const fileRef = useRef<HTMLInputElement>(null);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const onFile = async (file: File) => {
    setImportErr(null);
    setImporting(true);
    try {
      const text = await file.text();
      let bundle: PluginBundle;
      try {
        bundle = JSON.parse(text) as PluginBundle;
      } catch {
        setImportErr('That file is not valid JSON.');
        return;
      }
      if (!bundle.manifest?.name) {
        setImportErr('Not a LoreWeave bundle (missing manifest.name).');
        return;
      }
      const err = await p.importBundle(bundle);
      if (err) setImportErr(err);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div className="space-y-3" data-testid="plugins-view">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">A plugin bundles skills, commands & hooks — export to share, import to install.</p>
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            data-testid="plugin-import-file"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void onFile(f); }}
          />
          <button onClick={() => fileRef.current?.click()} disabled={importing} data-testid="plugin-import-btn" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40">
            {importing ? 'Importing…' : 'Import bundle'}
          </button>
        </div>
      </div>

      {importErr && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400" data-testid="plugin-import-error">{importErr}</div>}
      {p.error && <div className="text-xs text-red-400">{p.error}</div>}
      {!p.loading && p.plugins.length === 0 && !p.error && (
        <div data-testid="plugins-empty" className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground">
          No plugins yet. Import a bundle to install one.
        </div>
      )}

      <ul className="divide-y rounded-md border">
        {p.plugins.map((pl) => (
          <PluginRow key={pl.plugin_id} plugin={pl} onExport={() => void p.exportBundle(pl)} onRemove={() => void p.remove(pl)} />
        ))}
      </ul>
    </div>
  );
}

function PluginRow({ plugin, onExport, onRemove }: { plugin: Plugin; onExport: () => void; onRemove: () => void }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2" data-testid="plugin-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs">{plugin.name}</span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">v{plugin.version}</span>
          {plugin.tier === 'system' && <span className="text-[10px] uppercase text-indigo-400">system</span>}
        </div>
        {plugin.description && <div className="truncate text-xs text-muted-foreground">{plugin.description}</div>}
      </div>
      <button onClick={onExport} data-testid="plugin-export" className="rounded border px-2 py-0.5 text-[11px]">Export</button>
      {plugin.tier !== 'system' && <button onClick={onRemove} data-testid="plugin-delete" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">Delete</button>}
    </li>
  );
}
