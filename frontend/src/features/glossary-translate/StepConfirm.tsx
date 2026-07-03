import { useState } from 'react';
import { Loader2, Zap, ChevronLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { getLanguageName } from '@/lib/languages';
import { glossaryTranslateApi } from './api';
import { isSameLanguageTarget } from './useGlossaryTranslateState';
import type { EffortLevel } from '@/components/ai-task';
import type { OverwriteMode, GlossaryTranslateCostEstimate } from './types';

interface StepConfirmProps {
  bookId: string;
  targetLanguage: string;
  overwriteMode: OverwriteMode;
  modelRef: string;
  selectedModelName: string;
  effort: EffortLevel;
  sourceLanguage?: string;
  onJobCreated: (jobId: string, totalEntities: number, costEstimate: GlossaryTranslateCostEstimate) => void;
  onEditConfig: () => void;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `~${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `~${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export function StepConfirm({
  bookId,
  targetLanguage,
  overwriteMode,
  modelRef,
  selectedModelName,
  effort,
  sourceLanguage,
  onJobCreated,
  onEditConfig,
}: StepConfirmProps) {
  const { t } = useTranslation('glossaryTranslate');
  const { accessToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  // bug #4: how many entities translate in parallel. 1 = sequential (default). Raise it if
  // your model/GPU serves concurrent requests (mirrors the glossary-extraction wizard).
  const [concurrency, setConcurrency] = useState(1);
  const sameLanguage = isSameLanguageTarget(sourceLanguage, targetLanguage);

  const handleStart = async () => {
    if (!accessToken || submitting || !modelRef || sameLanguage) return;
    setSubmitting(true);
    try {
      const resp = await glossaryTranslateApi.startJob(
        bookId,
        {
          target_language: targetLanguage,
          model_source: 'user_model',
          model_ref: modelRef,
          overwrite_mode: overwriteMode,
          reasoning_effort: effort,
          ...(concurrency > 1 ? { concurrency_level: concurrency } : {}),
        },
        accessToken,
      );
      onJobCreated(resp.job_id, resp.total_entities, resp.cost_estimate);
    } catch (e) {
      toast.error((e as Error).message || t('confirm.startFailed'));
    }
    setSubmitting(false);
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.languages')}</p>
          <p className="text-sm font-bold mt-1">
            {sourceLanguage ? getLanguageName(sourceLanguage) : '?'} → {getLanguageName(targetLanguage)}
          </p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.mode')}</p>
          <p className="text-sm font-bold mt-1">{t(`config.mode.${overwriteMode}.label`)}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-[10px] text-muted-foreground">{t('confirm.model')}</p>
          <p className="text-sm font-bold truncate mt-1">{selectedModelName || '—'}</p>
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground text-center">
        {effort !== 'off' ? t('confirm.thinkingOn') : t('confirm.thinkingOff')}
      </p>

      {/* bug #4 — parallel entity translation. */}
      <div className="flex items-center justify-center gap-2">
        <label htmlFor="glossary-translate-concurrency" className="text-[11px] font-medium">
          {t('confirm.concurrency', { defaultValue: 'Parallel LLM calls' })}
        </label>
        <input
          id="glossary-translate-concurrency"
          type="number"
          min={1}
          max={16}
          value={concurrency}
          onChange={(e) => setConcurrency(Math.min(16, Math.max(1, Number(e.target.value) || 1)))}
          className="w-16 rounded-md border bg-background px-2 py-1 text-center text-xs"
          data-testid="glossary-translate-concurrency"
        />
        <span className="text-[10px] text-muted-foreground">
          {t('confirm.concurrencyHint', {
            defaultValue: '1 = sequential. Raise it if your model serves concurrent requests.',
          })}
        </span>
      </div>

      <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2">
        <p className="text-[10px] text-amber-500">{t('confirm.estimateNote')}</p>
      </div>

      <div className="flex items-center justify-between pt-2">
        <button
          onClick={onEditConfig}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          {t('confirm.editConfig')}
        </button>
        <button
          onClick={() => void handleStart()}
          disabled={submitting || !modelRef || sameLanguage}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-5 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          {t('confirm.startTranslate')}
        </button>
      </div>
    </div>
  );
}

export { formatTokens };
