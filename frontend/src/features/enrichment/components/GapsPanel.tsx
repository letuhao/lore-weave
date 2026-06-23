import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useGaps } from '../hooks/useGaps';
import { useUserModels } from '../hooks/useUserModels';
import { useEnrichmentContext } from '../context/EnrichmentContext';
import { gapToTarget, type Gap, type EnrichTarget } from '../types';

/** The trigger side: detect under-described entities (read-only) then auto-enrich
 *  chosen gaps as a background job (technique + gen/embed model + cost-cap). P2/P3
 *  are gate-enforced server-side (the runner refuses them until the eval gate clears). */
export function GapsPanel() {
  const { t } = useTranslation('enrichment');
  const { bookId, setGapCount } = useEnrichmentContext();
  const { gaps, needsExtraction, detect, detecting, autoEnrich, enriching } = useGaps(bookId);
  const [technique, setTechnique] = useState('recook');
  const [genModel, setGenModel] = useState('');
  const [embedModel, setEmbedModel] = useState('');
  const [maxGaps, setMaxGaps] = useState(3);
  // Cost-cap (USD). Empty = no cap (backend default). The spend-safety control.
  const [maxSpend, setMaxSpend] = useState('');
  // Retrieval breadth — defaults to the backend default (5) so untouched = no change.
  const [topK, setTopK] = useState(5);

  // Shared model-picker seam (also used by the Compose config) — one query per
  // capability, cache shared (no double fetch). /review-impl #3 — was inline here.
  const gens = useUserModels('chat');
  const embeds = useUserModels('embedding');
  const canEnrich = !!genModel && !!embedModel && !enriching;
  // LE-064 — which row's per-gap enrich is in flight (for its spinner).
  const [enrichingName, setEnrichingName] = useState<string | null>(null);

  // One enrich call for both the batch (top-N) + per-row (targets) paths.
  const runEnrich = (targets?: EnrichTarget[]) =>
    autoEnrich({
      generation_model_ref: genModel,
      embedding_model_ref: embedModel,
      technique,
      max_gaps: maxGaps,
      max_spend_tokens: maxSpend.trim() === '' ? null : Number(maxSpend),
      top_k: topK,
      ...(targets ? { targets } : {}),
    });

  const enrichOne = async (g: Gap) => {
    setEnrichingName(g.canonical_name);
    await runEnrich([gapToTarget(g)]);
    setEnrichingName(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t('gaps.title')}</h3>
          <p className="text-xs text-muted-foreground">{t('gaps.subtitle')}</p>
        </div>
        <button
          onClick={async () => {
            const r = await detect();
            setGapCount(r ? r.gaps.length : null);
          }}
          disabled={detecting}
          data-testid="enrichment-detect-gaps"
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', detecting && 'animate-spin')} /> {t('gaps.detect')}
        </button>
      </div>

      {gaps == null ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          {t('gaps.detect_hint')}
        </p>
      ) : gaps.length === 0 ? (
        <p
          data-testid={needsExtraction ? 'enrichment-gaps-extract-first' : 'enrichment-gaps-none'}
          className={cn(
            'rounded-lg border border-dashed p-6 text-center text-xs',
            needsExtraction ? 'border-warning/40 text-warning' : 'text-muted-foreground',
          )}
        >
          {needsExtraction ? t('gaps.extract_first') : t('gaps.none')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-card/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">{t('gaps.col.entity')}</th>
                <th className="px-3 py-2 text-left font-medium">{t('gaps.col.kind')}</th>
                <th className="px-3 py-2 text-left font-medium">{t('gaps.col.missing')}</th>
                <th className="px-3 py-2 text-left font-medium">{t('gaps.col.rank')}</th>
                <th className="px-3 py-2 text-right font-medium">{t('gaps.col.action')}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {gaps.map((g) => (
                <tr key={g.canonical_name} className="hover:bg-secondary/30">
                  <td className="px-3 py-2 font-serif font-medium">{g.canonical_name}</td>
                  <td className="px-3 py-2 text-muted-foreground">{g.entity_kind}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-warning">
                    {g.missing_dimensions.join('·')}
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-warning/12 px-1.5 py-0.5 font-mono text-[11px] text-warning">
                      {g.score.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => void enrichOne(g)}
                      disabled={!canEnrich}
                      title={canEnrich ? undefined : t('gaps.enrich_one_hint')}
                      data-testid={`enrichment-enrich-gap-${g.canonical_name}`}
                      className="inline-flex items-center gap-1 rounded-md border border-primary/30 px-2 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 disabled:opacity-40"
                    >
                      <Sparkles className={cn('h-3 w-3', enrichingName === g.canonical_name && 'animate-pulse')} />
                      {enrichingName === g.canonical_name ? t('gaps.enriching') : t('gaps.enrich_one')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-3 rounded-lg border bg-card px-4 py-3">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('gaps.technique')}</span>
            <select
              value={technique}
              onChange={(e) => setTechnique(e.target.value)}
              className="rounded border bg-background px-2 py-1"
            >
              <option value="retrieval">P1 retrieval</option>
              <option value="fabrication">P2 fabrication</option>
              <option value="recook">P3 recook</option>
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('gaps.gen_model')}</span>
            <select
              value={genModel}
              onChange={(e) => setGenModel(e.target.value)}
              className="rounded border bg-background px-2 py-1"
            >
              <option value="">{t('gaps.select_model')}</option>
              {gens.map((m) => (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {m.alias || m.provider_model_name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('gaps.embed_model')}</span>
            <select
              value={embedModel}
              onChange={(e) => setEmbedModel(e.target.value)}
              className="rounded border bg-background px-2 py-1"
            >
              <option value="">{t('gaps.select_model')}</option>
              {embeds.map((m) => (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {m.alias || m.provider_model_name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('gaps.max_gaps')}</span>
            <input
              type="number"
              min={1}
              max={50}
              value={maxGaps}
              onChange={(e) => setMaxGaps(Number(e.target.value))}
              className="w-16 rounded border bg-background px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('gaps.max_spend')}</span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={maxSpend}
              placeholder={t('gaps.no_cap')}
              onChange={(e) => setMaxSpend(e.target.value)}
              data-testid="enrichment-max-spend"
              className="w-20 rounded border bg-background px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('gaps.top_k')}</span>
            <input
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-16 rounded border bg-background px-2 py-1"
            />
          </label>
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-muted-foreground">{t('gaps.gate_note')}</p>
          <button
            onClick={() => void runEnrich()}
            disabled={!canEnrich}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Sparkles className="h-3.5 w-3.5" />{' '}
            {enriching && !enrichingName ? t('gaps.enriching') : t('gaps.auto_enrich')}
          </button>
        </div>
      </div>
    </div>
  );
}
