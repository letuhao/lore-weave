import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { knowledgeApi, type ChangeEmbeddingModelResponse } from '../api';
import type { Project } from '../types';
import { readBackendError } from '../lib/readBackendError';
import { EmbeddingModelPicker } from './EmbeddingModelPicker';

// K19a.6 — modal for switching a project's embedding model.

// Narrow the discriminated union to the "model unchanged" no-op shape.
// BE returns this body when current_model === new_model, regardless of
// the `?confirm=true` flag — the same-model guard runs first.
function isNoopResponse(
  resp: ChangeEmbeddingModelResponse,
): resp is Extract<ChangeEmbeddingModelResponse, { message: string; current_model: string }> {
  return 'message' in resp && 'current_model' in resp && !('nodes_deleted' in resp);
}

//
// Switching embedding model is destructive: the BE K16.10 endpoint
// deletes the existing Neo4j graph + sets extraction_enabled=false +
// sets extraction_status='disabled'. The user must start a new
// extraction job afterwards to regenerate the graph in the new vector
// space.
//
// The dialog surfaces the destructive nature up-front with a warning
// banner and renders `EmbeddingModelPicker` (with projectId) so the
// K17.9 benchmark badge is visible for the new model before the user
// commits. Confirm is disabled when selected model === current (BE
// returns a no-op, but we block the round-trip).

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
  onChanged: () => void;
}

export function ChangeModelDialog({ open, onOpenChange, project, onChanged }: Props) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const [selected, setSelected] = useState<string | null>(project.embedding_model);
  const [submitting, setSubmitting] = useState(false);

  // Reset selection each time the dialog opens — picks up any
  // external project.embedding_model update that happened while the
  // dialog was closed.
  useEffect(() => {
    if (!open) return;
    setSelected(project.embedding_model);
    setSubmitting(false);
  }, [open, project.embedding_model]);

  const sameAsCurrent = selected === project.embedding_model;
  const canConfirm = !submitting && !!selected && !sameAsCurrent;

  const handleConfirm = async () => {
    if (!accessToken || !selected) return;
    if (sameAsCurrent) return;
    setSubmitting(true);
    try {
      const resp = await knowledgeApi.updateEmbeddingModel(
        project.project_id,
        selected,
        accessToken,
        { confirm: true },
      );
      // review-impl F2 — BE checks same-model BEFORE the confirm gate.
      // If another device switched the model to our `selected` value
      // between open and Confirm, BE returns `{message: "model unchanged"}`
      // and we must NOT treat that as a real change (no invalidation,
      // no close). Detect the no-op shape by the presence of `message`
      // plus absence of `nodes_deleted`; surface a neutral toast.
      if (isNoopResponse(resp)) {
        toast.info(
          t('projects.changeModelDialog.alreadyAtModel', {
            model: 'current_model' in resp ? resp.current_model : selected,
          }),
        );
        return;
      }
      onChanged();
      onOpenChange(false);
    } catch (err) {
      toast.error(
        t('projects.changeModelDialog.failed', { error: readBackendError(err) }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('projects.changeModelDialog.title')}
      description={t('projects.changeModelDialog.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-secondary disabled:opacity-60"
          >
            {t('projects.changeModelDialog.cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60"
          >
            {submitting
              ? t('projects.changeModelDialog.submitting')
              : t('projects.changeModelDialog.confirm')}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <div className="flex flex-col gap-1">
            <span className="font-medium">
              {t('projects.changeModelDialog.warningTitle')}
            </span>
            <span className="text-[11px] leading-relaxed">
              {t('projects.changeModelDialog.warningBody', {
                currentModel: project.embedding_model ?? '(none)',
              })}
            </span>
          </div>
        </div>

        <EmbeddingModelPicker
          value={selected}
          onChange={setSelected}
          projectId={project.project_id}
        />

        {sameAsCurrent && selected !== null && (
          <span className="text-[11px] text-muted-foreground">
            {t('projects.changeModelDialog.sameModel')}
          </span>
        )}
      </div>
    </FormDialog>
  );
}
