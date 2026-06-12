import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Check, Ban } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import type { EntityRelation } from '../api';
import { useCorrectRelation, useInvalidateRelation } from '../hooks/useRelationMutations';

// Phase B C-FE — relation correction dialog. Two user actions on one relation:
//   - Correct: change the predicate → invalidate old edge + recreate corrected
//     (predicate-fix). The endpoints are kept (the common correction is a
//     wrong predicate, e.g. ally_of → enemy_of).
//   - Mark wrong: invalidate the edge (spurious-drop) — the relation should
//     never have been extracted.
// The user sees one logical "fix"; the invalidate+recreate is hidden BE detail.

export interface RelationEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  relation: EntityRelation;
}

export function RelationEditDialog({ open, onOpenChange, relation }: RelationEditDialogProps) {
  const { t } = useTranslation('knowledge');
  const [predicate, setPredicate] = useState(relation.predicate);

  useEffect(() => {
    if (open) setPredicate(relation.predicate);
  }, [open, relation.id, relation.predicate]);

  const correctMutation = useCorrectRelation({
    onSuccess: () => {
      toast.success(t('relations.edit.correctSuccess'));
      onOpenChange(false);
    },
    onError: (err) => toast.error(t('relations.edit.failed', { error: err.message })),
  });

  const invalidateMutation = useInvalidateRelation({
    onSuccess: () => {
      toast.success(t('relations.edit.invalidateSuccess'));
      onOpenChange(false);
    },
    onError: (err) => toast.error(t('relations.edit.failed', { error: err.message })),
  });

  const busy = correctMutation.isPending || invalidateMutation.isPending;

  const submitCorrect = async () => {
    const next = predicate.trim();
    if (!next || next === relation.predicate) {
      onOpenChange(false);
      return;
    }
    try {
      await correctMutation.correct({
        payload: {
          old_relation_id: relation.id,
          subject_id: relation.subject_id,
          predicate: next,
          object_id: relation.object_id,
        },
      });
    } catch {
      // onError toast; swallow handled rejection.
    }
  };

  const markWrong = async () => {
    if (!window.confirm(t('relations.edit.invalidateConfirm'))) return;
    try {
      await invalidateMutation.invalidate({ relationId: relation.id });
    } catch {
      // onError toast; swallow.
    }
  };

  const subjectLabel = relation.subject_name ?? relation.subject_id;
  const objectLabel = relation.object_name ?? relation.object_id;
  const canCorrect = !!predicate.trim() && !busy;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !busy) onOpenChange(o);
      }}
      title={t('relations.edit.title')}
      description={t('relations.edit.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={busy}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('relations.edit.cancel')}
          </button>
          <button
            type="button"
            onClick={submitCorrect}
            disabled={!canCorrect}
            data-testid="relation-edit-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
            {correctMutation.isPending ? t('relations.edit.saving') : t('relations.edit.save')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-[12px]">
          <span className="min-w-0 flex-1 truncate font-medium" title={subjectLabel}>
            {subjectLabel}
          </span>
          <span className="font-mono text-[11px] text-muted-foreground">→</span>
          <span className="min-w-0 flex-1 truncate font-medium" title={objectLabel}>
            {objectLabel}
          </span>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('relations.edit.field.predicate')}
          </span>
          <input
            type="text"
            value={predicate}
            onChange={(e) => setPredicate(e.target.value)}
            maxLength={100}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="relation-edit-predicate"
          />
        </label>
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
          <p className="text-[11px] text-muted-foreground">{t('relations.edit.invalidateHint')}</p>
          <button
            type="button"
            onClick={markWrong}
            disabled={busy}
            data-testid="relation-edit-invalidate"
            className="mt-2 inline-flex items-center gap-1 rounded-md border border-destructive/40 px-2 py-1 text-[11px] text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Ban className="h-3 w-3" />
            {invalidateMutation.isPending
              ? t('relations.edit.invalidating')
              : t('relations.edit.markWrong')}
          </button>
        </div>
      </div>
    </FormDialog>
  );
}
