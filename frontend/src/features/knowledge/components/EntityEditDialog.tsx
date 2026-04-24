import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pencil } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import type { Entity } from '../api';
import { useUpdateEntity } from '../hooks/useEntityMutations';

// K19d γ-b — edit dialog. Splits aliases on newlines; trims + dedupes
// before submit. On success, hook invalidation refreshes the open
// detail panel so the new values appear without manual reload.

export interface EntityEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entity: Entity;
}

function splitAliases(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out;
}

export function EntityEditDialog({
  open,
  onOpenChange,
  entity,
}: EntityEditDialogProps) {
  const { t } = useTranslation('knowledge');
  const [name, setName] = useState(entity.name);
  const [kind, setKind] = useState(entity.kind);
  const [aliasesText, setAliasesText] = useState(entity.aliases.join('\n'));

  // Reset form fields each time a different entity opens the dialog.
  useEffect(() => {
    if (open) {
      setName(entity.name);
      setKind(entity.kind);
      setAliasesText(entity.aliases.join('\n'));
    }
  }, [open, entity.id, entity.name, entity.kind, entity.aliases]);

  const mutation = useUpdateEntity({
    onSuccess: () => {
      toast.success(t('entities.edit.success'));
      onOpenChange(false);
    },
    onError: (err) => {
      // C9 (D-K19d-γa-01): 412 conflict surfaces a dedicated message +
      // closes the dialog so the user re-opens from the refreshed
      // detail (the hook already invalidated the detail query).
      const status = (err as Error & { status?: number }).status;
      if (status === 412) {
        toast.error(t('entities.edit.conflict'));
        onOpenChange(false);
        return;
      }
      toast.error(t('entities.edit.failed', { error: err.message }));
    },
  });

  const submit = async () => {
    const aliases = splitAliases(aliasesText);
    const payload = {
      name: name !== entity.name ? name : undefined,
      kind: kind !== entity.kind ? kind : undefined,
      aliases:
        JSON.stringify(aliases) !== JSON.stringify(entity.aliases)
          ? aliases
          : undefined,
    };
    if (
      payload.name === undefined
      && payload.kind === undefined
      && payload.aliases === undefined
    ) {
      // No-op. Close without a call.
      onOpenChange(false);
      return;
    }
    try {
      await mutation.update({
        entityId: entity.id,
        payload,
        // C9: send the entity's current version as If-Match.
        ifMatchVersion: entity.version,
      });
    } catch {
      // Errors are surfaced via useMutation's onError (toast); swallow
      // the rejected promise to keep vitest's unhandled-rejection
      // detector quiet on handled failures.
    }
  };

  const canSubmit = !!name.trim() && !!kind.trim() && !mutation.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !mutation.isPending) onOpenChange(o);
      }}
      title={t('entities.edit.title')}
      description={t('entities.edit.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('entities.edit.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            data-testid="entity-edit-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Pencil className="h-3 w-3" />
            {mutation.isPending
              ? t('entities.edit.saving')
              : t('entities.edit.save')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('entities.edit.field.name')}
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="entity-edit-name"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('entities.edit.field.kind')}
          </span>
          <input
            type="text"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            maxLength={100}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="entity-edit-kind"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('entities.edit.field.aliases')}
          </span>
          <textarea
            value={aliasesText}
            onChange={(e) => setAliasesText(e.target.value)}
            rows={4}
            placeholder={t('entities.edit.aliasesPlaceholder')}
            className="rounded-md border bg-input px-3 py-2 font-mono text-xs outline-none focus:border-ring"
            data-testid="entity-edit-aliases"
          />
          <span className="text-[10px] text-muted-foreground">
            {t('entities.edit.aliasesHint')}
          </span>
        </label>
        <p className="text-[11px] text-muted-foreground">
          {t('entities.edit.userEditedHint')}
        </p>
      </div>
    </FormDialog>
  );
}
