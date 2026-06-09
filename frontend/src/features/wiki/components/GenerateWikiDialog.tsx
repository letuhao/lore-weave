import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { glossaryApi } from '@/features/glossary/api';
import { cn } from '@/lib/utils';
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
}: {
  open: boolean;
  onClose: () => void;
  /** Resolves on success (dialog closes), rejects on failure (stays open). */
  onTrigger: (args: TriggerArgs) => Promise<unknown>;
  busy: boolean;
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

  const isLlm = modelRef !== '';
  const maxSpendValid = maxSpend === '' || DECIMAL_RE.test(maxSpend);
  const canConfirm = !busy && maxSpendValid;

  const handleConfirm = async () => {
    if (!canConfirm) return;
    try {
      await onTrigger({
        ...(modelRef ? { model_ref: modelRef } : {}),
        ...(kindCodes.length ? { kind_codes: kindCodes } : {}),
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
      title={t('gen.title')}
      description={t('gen.description')}
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
            {busy ? t('gen.starting') : isLlm ? t('gen.confirmLlm') : t('gen.confirmStub')}
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
            <option value="">{t('gen.model.deterministic')}</option>
            {chatModels.map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>
                {m.alias ? `${m.alias} (${m.provider_model_name})` : `${m.provider_kind}/${m.provider_model_name}`}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-muted-foreground">
            {isLlm ? t('gen.model.llmHint') : t('gen.model.deterministicHint')}
          </span>
        </label>

        {/* Optional kind filter */}
        {kinds.length > 0 && (
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
      </div>
    </FormDialog>
  );
}
