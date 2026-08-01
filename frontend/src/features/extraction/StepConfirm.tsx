import { useState } from 'react';
import { Loader2, Zap, ChevronLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { extractionApi } from './api';
import type { EffortLevel } from '@/components/ai-task';
import type {
  ExtractionProfile, ContextFilters, ExtractionProfileKind, CostEstimate,
  ExtractionStrategy, CachePolicy,
} from './types';

interface StepConfirmProps {
  bookId: string;
  profile: ExtractionProfile;
  chapterIds: string[];
  modelRef: string;
  maxEntitiesPerKind: number;
  contextFilters: ContextFilters;
  kinds: ExtractionProfileKind[];
  selectedModelName: string;
  effort: EffortLevel;
  onJobCreated: (jobId: string, costEstimate: CostEstimate) => void;
  onEditProfile: () => void;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `~${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `~${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export function StepConfirm({
  bookId,
  profile,
  chapterIds,
  modelRef,
  maxEntitiesPerKind,
  contextFilters,
  kinds,
  selectedModelName,
  effort,
  onJobCreated,
  onEditProfile,
}: StepConfirmProps) {
  const { t } = useTranslation('extraction');
  const { accessToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  // D-EXTRACTION-BATCH-CONCURRENCY: how many of a chapter's batch LLM calls run at
  // once. 1 = sequential (default). Raise it if your model/GPU serves multiple
  // concurrent requests (e.g. a 200K-context local model can comfortably do 4).
  const [concurrency, setConcurrency] = useState(1);
  // The prompt SHAPE. `batched` is the shipped default and stays the default here — the
  // cheaper shapes were measured to lose coverage on the rare kinds (−80% and −68% on the
  // two thinnest), so they are a deliberate trade, not a free win. The measurement was a
  // BETWEEN-SHAPE comparison on one fixed catalogue, so the deltas stand even though one of
  // those kinds has since been redefined and split (power_system → power_system+technique).
  const [strategy, setStrategy] = useState<ExtractionStrategy>('batched');
  // How to treat the raw-output cache. Default REFRESHES when anything looks stale: the
  // cache can serve a whole job at zero tokens, and before this existed a user who edited
  // a kind definition and re-extracted was silently served the parse from before the edit.
  const [cachePolicy, setCachePolicy] = useState<CachePolicy>('refresh_if_stale');

  const enabledKinds = Object.keys(profile);
  const enabledKindsMeta = kinds.filter((k) => enabledKinds.includes(k.code));

  // Rough batch estimate (same logic as backend: 2000 token budget, 20 + n_attrs * 40 per kind)
  const schemaTokens = enabledKinds.reduce((sum, code) => {
    const attrCount = Object.values(profile[code] || {}).filter((a) => a !== 'skip').length;
    return sum + 20 + attrCount * 40;
  }, 0);
  const batchesPerChapter = Math.max(1, Math.ceil(schemaTokens / 2000));
  const llmCalls = chapterIds.length * batchesPerChapter;

  const handleStart = async () => {
    if (!accessToken || submitting) return;
    setSubmitting(true);
    try {
      const resp = await extractionApi.startJob(
        bookId,
        {
          chapter_ids: chapterIds,
          extraction_profile: profile,
          model_source: 'user_model',
          model_ref: modelRef,
          max_entities_per_kind: maxEntitiesPerKind,
          context_filters: contextFilters,
          reasoning_effort: effort,
          extraction_strategy: strategy,
          cache_policy: cachePolicy,
          ...(concurrency > 1 ? { concurrency_level: concurrency } : {}),
        },
        accessToken,
      );
      onJobCreated(resp.job_id, resp.cost_estimate);
    } catch (e) {
      const err = e as Error & { code?: string };
      toast.error(err.message || 'Failed to start extraction');
    }
    setSubmitting(false);
  };

  return (
    <div className="space-y-4">
      {/* Summary grid */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.chapters')}</p>
          <p className="text-xl font-bold">{chapterIds.length}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.kinds')}</p>
          <p className="text-xl font-bold">{enabledKinds.length}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.batchesPerChapter')}</p>
          <p className="text-xl font-bold">{batchesPerChapter}</p>
          <p className="text-[9px] text-muted-foreground mt-0.5">
            {t('confirm.llmCalls', { count: llmCalls })}
          </p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.provider')}</p>
          <p className="text-sm font-bold truncate">{selectedModelName}</p>
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground text-center">
        {effort !== 'off' ? t('confirm.thinkingOn') : t('confirm.thinkingOff')}
      </p>

      {/* D-EXTRACTION-BATCH-CONCURRENCY — parallel LLM calls per chapter. */}
      <div className="flex items-center justify-center gap-2">
        <label htmlFor="extraction-concurrency" className="text-[11px] font-medium">
          {t('confirm.concurrency', { defaultValue: 'Parallel LLM calls' })}
        </label>
        <input
          id="extraction-concurrency"
          type="number"
          min={1}
          max={16}
          value={concurrency}
          onChange={(e) => setConcurrency(Math.min(16, Math.max(1, Number(e.target.value) || 1)))}
          className="w-16 rounded-md border bg-background px-2 py-1 text-center text-xs"
          data-testid="extraction-concurrency"
        />
        <span className="text-[10px] text-muted-foreground">
          {t('confirm.concurrencyHint', {
            defaultValue: '1 = sequential. Raise it if your model serves concurrent requests.',
          })}
        </span>
      </div>

      {/* Prompt SHAPE. Measured trade-offs, so the labels carry the number rather than
          leaving the user to guess which one is "better". */}
      <div className="flex items-center justify-center gap-2">
        <label htmlFor="extraction-strategy" className="text-[11px] font-medium">
          {t('confirm.strategy', { defaultValue: 'Prompt shape' })}
        </label>
        <select
          id="extraction-strategy"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value as ExtractionStrategy)}
          className="rounded-md border bg-background px-2 py-1 text-xs"
          data-testid="extraction-strategy"
        >
          <option value="batched">
            {t('confirm.strategyBatched', { defaultValue: 'Batched — most thorough (default)' })}
          </option>
          <option value="single_call">
            {t('confirm.strategySingle', { defaultValue: 'One call — ~66% cheaper, misses rare kinds' })}
          </option>
          <option value="single_call_delta">
            {t('confirm.strategyDelta', { defaultValue: 'One call + deltas — cheapest' })}
          </option>
          <option value="edc_cited">
            {t('confirm.strategyEdc', { defaultValue: 'Sweep then type — ~56% cheaper, best grounding' })}
          </option>
        </select>
      </div>

      {/* CACHE POLICY. The default REFRESHES on staleness. Before this control existed a
          re-extraction after editing a kind definition was silently served from cache. */}
      <div className="flex items-center justify-center gap-2">
        <label htmlFor="extraction-cache-policy" className="text-[11px] font-medium">
          {t('confirm.cachePolicy', { defaultValue: 'Cached results' })}
        </label>
        <select
          id="extraction-cache-policy"
          value={cachePolicy}
          onChange={(e) => setCachePolicy(e.target.value as CachePolicy)}
          className="rounded-md border bg-background px-2 py-1 text-xs"
          data-testid="extraction-cache-policy"
        >
          <option value="refresh_if_stale">
            {t('confirm.cacheAuto', { defaultValue: 'Re-run when anything changed (default)' })}
          </option>
          <option value="prefer_cache">
            {t('confirm.cacheReuse', { defaultValue: 'Reuse cached results where possible' })}
          </option>
          <option value="always_refresh">
            {t('confirm.cacheForce', { defaultValue: 'Always re-extract — ignore the cache' })}
          </option>
        </select>
        <span className="text-[10px] text-muted-foreground">
          {t('confirm.cacheHint', {
            defaultValue: 'Edited a kind definition? The default already re-runs.',
          })}
        </span>
      </div>

      {/* Profile summary */}
      <div className="rounded-lg border p-3">
        <h3 className="text-xs font-medium mb-2">{t('confirm.profileSummary')}</h3>
        <div className="flex flex-wrap gap-2">
          {enabledKindsMeta.map((kind) => {
            const activeAttrs = Object.values(profile[kind.code] || {}).filter((a) => a !== 'skip').length;
            return (
              <div
                key={kind.code}
                className="flex items-center gap-1.5 rounded-md border bg-card/50 px-2.5 py-1.5"
              >
                <span className="text-sm">{kind.icon}</span>
                <span className="text-xs font-medium">{kind.name}</span>
                <span className="text-[9px] text-muted-foreground">
                  {t('confirm.attrs', { count: activeAttrs })}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Estimate note */}
      <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2">
        <p className="text-[10px] text-amber-500">{t('confirm.estimateNote')}</p>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={onEditProfile}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          {t('confirm.editProfile')}
        </button>
        <button
          onClick={() => void handleStart()}
          disabled={submitting}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-5 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          {t('confirm.startExtraction')}
        </button>
      </div>
    </div>
  );
}
