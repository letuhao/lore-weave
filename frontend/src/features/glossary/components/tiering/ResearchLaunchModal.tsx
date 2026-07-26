import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import type { CreateResearchJobReq, ResearchEstimate } from '../../researchApi';

type Props = {
  kindName: string;
  fetchEstimate: () => Promise<ResearchEstimate>;
  onCreate: (req: CreateResearchJobReq) => Promise<void>;
  onClose: () => void;
};

/** D-BATCH-RESEARCH-JOB M3 — launch a batch entity-research job over a kind. Shows the
 *  pre-flight entity count + an INDICATIVE cost estimate (cost is BYOK; not metered). */
export function ResearchLaunchModal({ kindName, fetchEstimate, onCreate, onClose }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const [est, setEst] = useState<ResearchEstimate | null>(null);
  const [query, setQuery] = useState('');
  const [maxEntities, setMaxEntities] = useState(10);
  const [maxResults, setMaxResults] = useState(5);
  const [error, setError] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Fetch the estimate ONCE on mount. The guard is load-bearing: fetchEstimate is a fresh
  // closure each parent render, so a [fetchEstimate] dep would re-run the effect and reset
  // maxEntities back to the default — clobbering the user's edits. The modal mounts fresh
  // each open, so mount-once is correct.
  const fetched = useRef(false);
  useEffect(() => {
    if (fetched.current) return;
    fetched.current = true;
    let alive = true;
    fetchEstimate()
      .then((e) => {
        if (!alive) return;
        setEst(e);
        // default to the whole kind, bounded by the hard cap.
        setMaxEntities(Math.min(e.entity_count || 10, e.hard_cap));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [fetchEstimate]);

  const planned = est ? Math.min(maxEntities, est.entity_count) : maxEntities;
  const estCost = est ? (planned * parseFloat(est.per_search_usd)).toFixed(4) : '—';

  const submit = async () => {
    if (!query.trim()) { setError(true); return; }
    setError(false);
    setSubmitting(true);
    try {
      await onCreate({ query_template: query.trim(), max_entities: maxEntities, max_results: maxResults });
      onClose();
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <FormDialog
      open
      onOpenChange={(next) => { if (!next && !submitting) onClose(); }}
      title={t('research.modal.title', { kind: kindName })}
      description={t('research.modal.subtitle')}
      size="md"
      footer={
        <>
          <button onClick={onClose} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">
            {t('research.modal.cancel')}
          </button>
          <button
            onClick={() => void submit()}
            disabled={submitting || (est?.entity_count === 0)}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            data-testid="research-submit"
          >
            {submitting ? t('research.modal.starting') : t('research.modal.submit')}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <label className="block space-y-1">
          <span className="text-xs font-medium text-muted-foreground">{t('research.modal.query_label')}</span>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('research.modal.query_placeholder')}
            className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm"
            data-testid="research-query"
          />
          <span className="text-[11px] text-muted-foreground">{t('research.modal.query_hint')}</span>
          {error && <span className="block text-xs text-destructive">{t('research.modal.query_required')}</span>}
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{t('research.modal.max_entities')}</span>
            <input
              type="number" min={1} max={est?.hard_cap ?? 500} value={maxEntities}
              onChange={(e) => setMaxEntities(Math.max(1, parseInt(e.target.value, 10) || 1))}
              className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm"
              data-testid="research-max-entities"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{t('research.modal.max_results')}</span>
            <input
              type="number" min={1} max={10} value={maxResults}
              onChange={(e) => setMaxResults(Math.min(10, Math.max(1, parseInt(e.target.value, 10) || 1)))}
              className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm"
            />
          </label>
        </div>

        <div className="rounded-md border bg-card px-3 py-2 text-xs text-muted-foreground">
          {est ? (
            <>
              <div>{t('research.modal.entities', { planned, total: est.entity_count })}</div>
              <div>{t('research.modal.cost', { cost: estCost })} <span className="opacity-70">({t('research.modal.indicative')})</span></div>
            </>
          ) : (
            <div>{t('research.modal.estimating')}</div>
          )}
        </div>
      </div>
    </FormDialog>
  );
}
