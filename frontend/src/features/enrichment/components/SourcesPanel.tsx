import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/shared';
import { useEnrichmentSources } from '../hooks/useEnrichmentSources';
import { useEnrichmentContext } from '../context/EnrichmentContext';
import { isRecookable } from '../types';

/** The corpus side: license-tagged source material for retrieval / recook.
 *  Default-deny — only public_domain / licensed corpora are recookable (① layer). */
export function SourcesPanel() {
  const { t } = useTranslation('enrichment');
  const { bookId } = useEnrichmentContext();
  const { items, isLoading, register, busy } = useEnrichmentSources(bookId);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState('history');
  const [license, setLicense] = useState('public_domain');

  const submit = async () => {
    if (!name.trim()) return;
    const s = await register({ name: name.trim(), kind, license });
    if (s) {
      setOpen(false);
      setName('');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t('sources.title')}</h3>
          <p className="text-xs text-muted-foreground">{t('sources.subtitle')}</p>
        </div>
        <button
          onClick={() => setOpen(!open)}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-3.5 w-3.5" /> {t('sources.register')}
        </button>
      </div>

      {open && (
        <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">{t('sources.name')}</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded border bg-background px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">{t('sources.kind')}</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)} className="rounded border bg-background px-2 py-1">
              <option value="fengshen">fengshen</option>
              <option value="shanhaijing">shanhaijing</option>
              <option value="history">history</option>
              <option value="other">other</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">{t('sources.license')}</span>
            <select value={license} onChange={(e) => setLicense(e.target.value)} className="rounded border bg-background px-2 py-1">
              <option value="public_domain">public_domain</option>
              <option value="licensed">licensed</option>
              <option value="copyrighted">copyrighted</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <button
            onClick={() => void submit()}
            disabled={busy}
            className="rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground disabled:opacity-50"
          >
            {t('actions.save')}
          </button>
        </div>
      )}

      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : items.length === 0 ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          {t('sources.none')}
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {items.map((s) => {
            const ok = isRecookable(s.license);
            return (
              <div key={s.corpus_id} className="rounded-lg border bg-card px-4 py-3">
                <div className="flex items-center justify-between">
                  <span className="font-serif font-medium">{s.name}</span>
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[10px] font-medium',
                      ok ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive',
                    )}
                  >
                    {t(`license.${s.license}`, { defaultValue: s.license })}
                  </span>
                </div>
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                  kind={s.kind} · {ok ? t('sources.recook_ok') : t('sources.recook_refused')}
                </p>
              </div>
            );
          })}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">{t('sources.default_deny')}</p>
    </div>
  );
}
