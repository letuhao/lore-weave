import { useEffect, useMemo, useState } from 'react';
import { Search, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useStudioHost } from '../host/StudioHostProvider';
import { OPENABLE_STUDIO_PANELS } from '../panels/catalog';

export function PanelPicker() {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const [query, setQuery] = useState('');
  const [openIds, setOpenIds] = useState<string[]>([]);
  const api = host._dockApiRef.current;
  const refresh = () => setOpenIds((api?.panels ?? []).map((p) => p.id));
  useEffect(() => { refresh(); const d = api?.onDidLayoutChange(refresh); return () => d?.dispose(); }, [api]);
  const visible = useMemo(() => { const q = query.trim().toLowerCase(); return OPENABLE_STUDIO_PANELS.filter((p) => { const label = t(p.titleKey, { defaultValue: p.id }); return !q || (label + ' ' + p.id).toLowerCase().includes(q); }); }, [query, t]);
  const toggle = (id: string) => { if (openIds.includes(id)) host.closePanel(id); else { const p = OPENABLE_STUDIO_PANELS.find((x) => x.id === id); host.openPanel(id, { title: p ? t(p.titleKey, { defaultValue: id }) : id }); } window.setTimeout(refresh, 0); };
  return <div className="w-[320px] rounded-lg border bg-card p-2 shadow-xl" data-testid="studio-panel-picker">
    <div className="mb-2 px-1 text-xs font-semibold">{t('panelsPicker.title', { defaultValue: 'Workspace panels' })}</div>
    <div className="relative mb-2"><Search className="pointer-events-none absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('panelsPicker.search', { defaultValue: 'Find a panel…' })} className="h-8 w-full rounded border bg-background pl-7 pr-2 text-xs outline-none focus:ring-1 focus:ring-primary" /></div>
    <div className="max-h-[min(60vh,460px)] space-y-0.5 overflow-y-auto pr-1">{visible.map((panel) => { const checked = openIds.includes(panel.id); return <button key={panel.id} type="button" onClick={() => toggle(panel.id)} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-secondary" aria-pressed={checked}><span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${checked ? 'border-primary bg-primary text-primary-foreground' : 'border-border'}`}>{checked && <Check className="h-3 w-3" />}</span><span className="min-w-0 flex-1 truncate">{t(panel.titleKey, { defaultValue: panel.id })}</span><span className="text-[10px] text-muted-foreground">{panel.category}</span></button>; })}</div>
    <p className="mt-2 px-1 text-[10px] text-muted-foreground">{t('panelsPicker.hint', { defaultValue: 'Choose which panels stay visible. Your choice is saved with this workspace.' })}</p>
  </div>;
}
