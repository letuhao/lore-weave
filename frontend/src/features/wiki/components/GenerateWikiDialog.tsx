import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { glossaryApi } from '@/features/glossary/api';
import { cn } from '@/lib/utils';
import { wikiApi } from '../api';
import type { WikiGenConfig } from '../types';
import type { TriggerArgs } from '../hooks/useWikiGenJob';

const DECIMAL_RE = /^\d+(\.\d{1,2})?$/;

/**
 * wiki-llm M7b-2a — the unified Generate dialog (PO decision A). The model
 * dropdown defaults to "Deterministic stubs (no LLM)"; picking a chat model
 * switches to LLM generation (delegated to the M6 batch generator) and reveals
 * the spend cap. An optional kind filter scopes which entities are generated.
 */
export function GenerateWikiDialog({
  open,
  onClose,
  onTrigger,
  busy,
  bookId,
  entityIds,
  regenName,
}: {
  open: boolean;
  onClose: () => void;
  /** Resolves on success (dialog closes), rejects on failure (stays open). */
  onTrigger: (args: TriggerArgs) => Promise<unknown>;
  busy: boolean;
  /** Book context — used to fetch the per-article cost estimate. Optional: the
   *  estimate line is a non-essential enhancement and is simply omitted without it. */
  bookId?: string;
  /** Single-article REGENERATE (M7b-2b): scope generation to these entities. In
   *  this mode a model is REQUIRED (deterministic stubs skip entities that
   *  already have an article) and the kind filter is hidden. */
  entityIds?: string[];
  /** The article's display name, shown in the regenerate title. */
  regenName?: string;
}) {
  const { t } = useTranslation('wiki');
  const { accessToken } = useAuth();
  const [modelRef, setModelRef] = useState('');
  const [kindCodes, setKindCodes] = useState<string[]>([]);
  const [maxSpend, setMaxSpend] = useState('');

  // Reset to the safe defaults whenever the dialog (re)opens. The dialog stays
  // mounted between opens (no conditional unmount), so without this a prior LLM
  // selection persists — defeating the "Deterministic stubs" default and risking
  // an unintended token-spend on the next confirm (/review-impl F1).
  useEffect(() => {
    if (open) {
      setModelRef('');
      setKindCodes([]);
      setMaxSpend('');
    }
  }, [open]);

  const modelsQuery = useQuery<{ items: UserModel[] }>({
    queryKey: ['ai-models', 'chat'],
    queryFn: () =>
      aiModelsApi.listUserModels(accessToken!, { capability: 'chat', include_inactive: false }),
    enabled: open && !!accessToken,
    staleTime: 60_000,
  });
  const chatModels = useMemo(() => modelsQuery.data?.items ?? [], [modelsQuery.data]);

  const kindsQuery = useQuery({
    queryKey: ['glossary-kinds'],
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled: open && !!accessToken,
    staleTime: 60_000,
  });
  const kinds = kindsQuery.data ?? [];

  const isRegen = !!entityIds?.length;
  const isLlm = modelRef !== '';
  const maxSpendValid = maxSpend === '' || DECIMAL_RE.test(maxSpend);

  // Pre-flight cost estimate (D-WIKI-P2B-COST-ESTIMATE) — fetched only when an LLM
  // model is picked (the deterministic path is free). The per-article rate is the
  // flat figure the budget gate charges, so the estimate matches the live spend.
  const configQuery = useQuery<WikiGenConfig>({
    queryKey: ['wiki-gen-config', bookId],
    queryFn: () => wikiApi.getGenConfig(bookId!, accessToken!),
    enabled: open && isLlm && !!accessToken && !!bookId,
    staleTime: 5 * 60_000,
  });
  const rawPerArticle = configQuery.data ? Number(configQuery.data.cost_per_article_usd) : NaN;
  const perArticle = Number.isFinite(rawPerArticle) ? rawPerArticle : null;
  const fmtUsd = (n: number) => `$${n.toFixed(2)}`;
  // Regenerate needs a model (the deterministic path skips entities that already
  // have an article, so a deterministic "regenerate" would be a no-op).
  const canConfirm = !busy && maxSpendValid && (!isRegen || isLlm);

  const handleConfirm = async () => {
    if (!canConfirm) return;
    try {
      await onTrigger({
        ...(modelRef ? { model_ref: modelRef } : {}),
        // Regenerate scopes by explicit entity ids; batch scopes by kind.
        ...(isRegen ? { entity_ids: entityIds } : kindCodes.length ? { kind_codes: kindCodes } : {}),
        ...(isLlm && maxSpend !== '' ? { max_spend_usd: Number(maxSpend) } : {}),
      });
      onClose();
    } catch {
      /* toast already shown by the hook; keep the dialog open */
    }
  };

  if (!open) return null;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={isRegen ? t('gen.regenTitle', { name: regenName || '' }) : t('gen.title')}
      description={isRegen ? t('gen.regenDescription') : t('gen.description')}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-secondary disabled:opacity-60"
          >
            {t('gen.cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            data-testid="wiki-gen-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:brightness-110 disabled:opacity-60"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {busy
              ? t('gen.starting')
              : isRegen
                ? t('gen.confirmRegen')
                : isLlm
                  ? t('gen.confirmLlm')
                  : t('gen.confirmStub')}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {/* Model picker — '' = deterministic stubs */}
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t('gen.model.label')}</span>
          <select
            value={modelRef}
            onChange={(e) => setModelRef(e.target.value)}
            disabled={modelsQuery.isLoading}
            data-testid="wiki-gen-model"
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
          >
            {/* Regenerate requires a model (deterministic skips article-having
                entities); batch generate offers the deterministic default. */}
            <option value="" disabled={isRegen}>
              {isRegen ? t('gen.model.pickRequired') : t('gen.model.deterministic')}
            </option>
            {chatModels.map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>
                {m.alias ? `${m.alias} (${m.provider_model_name})` : `${m.provider_kind}/${m.provider_model_name}`}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-muted-foreground">
            {isRegen
              ? t('gen.regenHint')
              : isLlm
                ? t('gen.model.llmHint')
                : t('gen.model.deterministicHint')}
          </span>
        </label>

        {/* Optional kind filter — batch generate only (regen is one entity) */}
        {!isRegen && kinds.length > 0 && (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="text-xs font-medium text-muted-foreground">{t('gen.kinds.label')}</legend>
            <div className="flex flex-wrap gap-1.5">
              {kinds.map((k) => {
                const selected = kindCodes.includes(k.code);
                return (
                  <button
                    key={k.code}
                    type="button"
                    onClick={() =>
                      setKindCodes((prev) =>
                        selected ? prev.filter((c) => c !== k.code) : [...prev, k.code],
                      )
                    }
                    className={cn(
                      'rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors',
                      selected ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {k.icon} {k.name}
                  </button>
                );
              })}
            </div>
            <span className="text-[11px] text-muted-foreground">{t('gen.kinds.hint')}</span>
          </fieldset>
        )}

        {/* Spend cap — LLM path only */}
        {isLlm && (
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">{t('gen.maxSpend.label')}</span>
            <input
              type="text"
              inputMode="decimal"
              value={maxSpend}
              onChange={(e) => setMaxSpend(e.target.value)}
              placeholder="0.00"
              aria-invalid={!maxSpendValid}
              data-testid="wiki-gen-maxspend"
              className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring aria-[invalid=true]:border-destructive"
            />
            <span className="text-[11px] text-muted-foreground">{t('gen.maxSpend.hint')}</span>
            {!maxSpendValid && <span className="text-[11px] text-destructive">{t('gen.maxSpend.invalid')}</span>}
          </label>
        )}

        {/* Pre-flight cost estimate — LLM path only. Precise (N × rate) when
            regenerating a known set; rate-only for batch (count unknown pre-flight). */}
        {isLlm && bookId && (
          <p data-testid="wiki-gen-estimate" className="text-[11px] text-muted-foreground">
            {configQuery.isLoading || perArticle == null
              ? t('gen.estimate.loading')
              : isRegen
                ? t('gen.estimate.forN', {
                    count: entityIds!.length,
                    perArticle: fmtUsd(perArticle),
                    total: fmtUsd(entityIds!.length * perArticle),
                  })
                : t('gen.estimate.perArticle', { perArticle: fmtUsd(perArticle) })}
          </p>
        )}
      </div>
    </FormDialog>
  );
}
