import { useState } from 'react';
import { Loader2, Zap, ChevronLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { extractionApi } from './api';
import type { ExtractionProfile, ContextFilters, ExtractionProfileKind, CostEstimate } from './types';

interface StepConfirmProps {
  bookId: string;
  profile: ExtractionProfile;
  chapterIds: string[];
  modelRef: string;
  maxEntitiesPerKind: number;
  contextFilters: ContextFilters;
  kinds: ExtractionProfileKind[];
  selectedModelName: string;
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
  onJobCreated,
  onEditProfile,
}: StepConfirmProps) {
  const { t } = useTranslation('extraction');
  const { accessToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);

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
