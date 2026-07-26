import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useRegenerateBio, type RegenerateError } from '../hooks/useRegenerateBio';

// K20α — Regenerate dialog. W5: renders the shared ModelPicker
// (capability='chat'); the raw model list (via useUserModels, which
// shares the picker's fetch cache) is still read here because the
// regenerate edge takes the model's `provider_model_name` as
// `model_ref` — the picker binds `user_model_id`, so submit resolves
// id → provider_model_name. Calls the public regenerate edge via
// useRegenerateBio and surfaces the 3 error classes distinctly:
//   - 409 user_edit_lock → inline warning banner (30-day protection)
//   - 409 regen_concurrent_edit → toast + auto-close (refetch will
//     pick up the newer row)
//   - 422 regen_guardrail_failed → toast with BE-supplied reason
//   - 502 provider_error → toast with BE-supplied provider message
//
// Cost hint: intentionally vague ("Estimated cost: small (<$0.05)")
// — D-K20α-01 will replace it with a cost_per_token lookup when
// those pricing values come from the BE instead of a frontend
// constant table. For now, the server already caps output at 500
// tokens so the worst realistic call is ~$0.05 on gpt-4o.

export interface RegenerateBioDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RegenerateBioDialog({ open, onOpenChange }: RegenerateBioDialogProps) {
  const { t } = useTranslation('knowledge');
  // The picker binds the user_model_id; submit resolves it to the
  // model's provider_model_name (the regenerate edge's model_ref).
  const [modelId, setModelId] = useState<string | null>(null);
  const [editLockMessage, setEditLockMessage] = useState<string | null>(null);

  // useUserModels shares the ModelPicker's 15s fetch cache, so this is
  // NOT a duplicate GET — it's the same in-flight promise the picker
  // consumes (W5 replacement for the old shared react-query key).
  const { models } = useUserModels({ capability: 'chat', enabled: open });
  const selectedModel =
    (modelId && models?.find((m) => m.user_model_id === modelId)) || null;

  const regen = useRegenerateBio({
    onSuccess: (resp) => {
      if (resp.status === 'regenerated') {
        toast.success(t('global.regenerate.success'));
      } else if (resp.status === 'no_op_similarity') {
        toast.info(t('global.regenerate.noOpSimilarity'));
      } else if (resp.status === 'no_op_empty_source') {
        toast.info(t('global.regenerate.noOpEmptySource'));
      }
      onOpenChange(false);
    },
    onError: (err: RegenerateError) => {
      switch (err.errorCode) {
        case 'user_edit_lock':
          // Inline banner instead of toast — the user needs to
          // understand WHY regen is blocked before they dismiss.
          setEditLockMessage(
            err.detailMessage ?? t('global.regenerate.editLockDefault'),
          );
          break;
        case 'regen_concurrent_edit':
          toast.error(t('global.regenerate.concurrentEdit'));
          onOpenChange(false);
          break;
        case 'regen_guardrail_failed':
          toast.error(
            t('global.regenerate.guardrailFailed', {
              reason: err.detailMessage ?? 'quality check failed',
            }),
          );
          break;
        case 'provider_error':
          toast.error(
            t('global.regenerate.providerError', {
              reason: err.detailMessage ?? 'provider call failed',
            }),
          );
          break;
        default:
          toast.error(
            t('global.regenerate.unknownError', {
              reason: err.message || 'unknown',
            }),
          );
          break;
      }
    },
  });

  const submit = () => {
    if (!selectedModel) return;
    setEditLockMessage(null);
    // Payload contract unchanged by W5: model_ref is the model's
    // provider_model_name (resolved from the picked user_model_id).
    regen.mutate({
      model_source: 'user_model',
      model_ref: selectedModel.provider_model_name,
    });
  };

  const canSubmit = !!selectedModel && !regen.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !regen.isPending) {
          setEditLockMessage(null);
          onOpenChange(o);
        }
      }}
      title={t('global.regenerate.title')}
      description={t('global.regenerate.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => {
              setEditLockMessage(null);
              onOpenChange(false);
            }}
            disabled={regen.isPending}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('global.regenerate.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            data-testid="regenerate-bio-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Sparkles className="h-3 w-3" />
            {regen.isPending
              ? t('global.regenerate.regenerating')
              : t('global.regenerate.confirm')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <p className="text-muted-foreground">
          {t('global.regenerate.editLockHint')}
        </p>

        <div className="flex flex-col gap-1" data-testid="regenerate-bio-model">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('global.regenerate.modelLabel')}
          </span>
          <ModelPicker
            capability="chat"
            value={modelId}
            onChange={setModelId}
            disabled={regen.isPending}
            compact
            placeholder={t('global.regenerate.modelPlaceholder')}
            ariaLabel={t('global.regenerate.modelLabel')}
            emptyState={
              <span className="text-[11px] text-warning">
                {t('global.regenerate.noModels')}
              </span>
            }
          />
        </div>

        <p className="text-[11px] text-muted-foreground">
          {t('global.regenerate.costHint')}
        </p>

        {editLockMessage && (
          <div
            role="alert"
            data-testid="regenerate-bio-edit-lock"
            className="rounded-md border border-warning/40 bg-warning/5 px-3 py-2 text-[11px] text-warning"
          >
            {editLockMessage}
          </div>
        )}
      </div>
    </FormDialog>
  );
}
