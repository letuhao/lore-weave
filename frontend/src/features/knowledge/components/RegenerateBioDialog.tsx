import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { useRegenerateBio, type RegenerateError } from '../hooks/useRegenerateBio';

// K20α — Regenerate dialog. Reads `aiModelsApi.listUserModels` with
// capability='chat' to populate the model picker (same query as
// BuildGraphDialog — keeps behaviour consistent). Calls the public
// regenerate edge via useRegenerateBio and surfaces the 3 error
// classes distinctly:
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
  const { accessToken } = useAuth();
  const [modelRef, setModelRef] = useState('');
  const [editLockMessage, setEditLockMessage] = useState<string | null>(null);

  // Share the queryKey with BuildGraphDialog so opening the regen
  // dialog after the build dialog (or vice versa) reuses the cache
  // instead of issuing a duplicate GET /v1/ai-models/user call. The
  // filter params on listUserModels are identical to BuildGraphDialog's
  // — any divergence would create a stale-cache bug so they must stay
  // in lock-step. Review-impl M1.
  const modelsQuery = useQuery<{ items: UserModel[] }>({
    queryKey: ['ai-models', 'chat'],
    queryFn: () =>
      aiModelsApi.listUserModels(accessToken!, {
        capability: 'chat',
        include_inactive: false,
      }),
    enabled: open && !!accessToken,
  });

  const chatModels = useMemo(
    () => modelsQuery.data?.items ?? [],
    [modelsQuery.data],
  );

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
    setEditLockMessage(null);
    regen.mutate({ model_source: 'user_model', model_ref: modelRef });
  };

  const canSubmit = !!modelRef && !regen.isPending;

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

        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('global.regenerate.modelLabel')}
          </span>
          <select
            value={modelRef}
            onChange={(e) => setModelRef(e.target.value)}
            disabled={modelsQuery.isLoading || regen.isPending}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring disabled:opacity-60"
            data-testid="regenerate-bio-model"
          >
            <option value="">
              {modelsQuery.isLoading
                ? t('global.regenerate.modelLoading')
                : t('global.regenerate.modelPlaceholder')}
            </option>
            {chatModels.map((m) => {
              const label = m.alias
                ? `${m.alias} (${m.provider_model_name})`
                : `${m.provider_kind}/${m.provider_model_name}`;
              return (
                <option key={m.user_model_id} value={m.provider_model_name}>
                  {label}
                </option>
              );
            })}
          </select>
          {!modelsQuery.isLoading && chatModels.length === 0 && (
            <span className="text-[11px] text-warning">
              {t('global.regenerate.noModels')}
            </span>
          )}
        </label>

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
