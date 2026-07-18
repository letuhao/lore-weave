import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useCreateEntity } from '../hooks/useEntityMutations';
import {
  AUTHORABLE_ENTITY_KINDS,
  type AuthorableEntityKind,
} from '../lib/entityKinds';

// S7-1 — hand-author a new entity. Peer of EntityEditDialog (same FormDialog
// shell). `kind` is a CLOSED-SET radio-grid over the ONE constant — never a
// free `<input>`, never a free `<select>` value. New entities are always
// `discovered` (server-derived from provenance='human_authored' + no glossary
// anchor); the form offers NO status control (canonical is earned by anchoring).

export interface CreateEntityDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The project the entity is tagged to. Required — the caller (EntitiesTab)
   *  supplies the scoped/selected project and disables the trigger when none. */
  projectId: string;
}

export function CreateEntityDialog({
  open,
  onOpenChange,
  projectId,
}: CreateEntityDialogProps) {
  const { t } = useTranslation('knowledge');
  const [name, setName] = useState('');
  const [kind, setKind] = useState<AuthorableEntityKind>(
    AUTHORABLE_ENTITY_KINDS[0],
  );

  useEffect(() => {
    if (open) {
      setName('');
      setKind(AUTHORABLE_ENTITY_KINDS[0]);
    }
  }, [open]);

  const mutation = useCreateEntity({
    onSuccess: (entity) => {
      // OQ-2: merge_entity is idempotent — a duplicate (name, kind) returns the
      // EXISTING node (with its real mention_count), not a fresh 0-mention row.
      // Do NOT claim "created" unconditionally. A returned node with mentions
      // is a dedup hit; say so instead of lying.
      if (entity.mention_count > 0) {
        toast.info(
          t('entities.create.dedup', { name: entity.name, kind: entity.kind }),
        );
      } else {
        toast.success(
          t('entities.create.success', { name: entity.name, kind: entity.kind }),
        );
      }
      onOpenChange(false);
    },
    onError: (err) => {
      toast.error(t('entities.create.failed', { error: err.message }));
    },
  });

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      await mutation.create({ project_id: projectId, name: trimmed, kind });
    } catch {
      // surfaced via onError toast; swallow the rejection.
    }
  };

  const canSubmit = !!name.trim() && !mutation.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !mutation.isPending) onOpenChange(o);
      }}
      title={t('entities.create.title')}
      description={t('entities.create.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('entities.create.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            data-testid="entity-create-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-3 w-3" />
            {mutation.isPending
              ? t('entities.create.saving')
              : t('entities.create.save')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('entities.create.field.name')}
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            autoFocus
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="entity-create-name"
          />
        </label>

        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('entities.create.field.kind')}
          </span>
          <div
            className="grid grid-cols-3 gap-1.5"
            role="radiogroup"
            aria-label={t('entities.create.field.kind')}
            data-testid="entity-create-kind-grid"
          >
            {AUTHORABLE_ENTITY_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                onClick={() => setKind(k)}
                data-testid={`entity-create-kind-${k}`}
                className={`rounded-md border px-2 py-1.5 text-xs capitalize transition-colors ${
                  kind === k
                    ? 'border-primary bg-primary/10 text-foreground'
                    : 'hover:bg-secondary'
                }`}
              >
                {t(`entities.kind.${k}`)}
              </button>
            ))}
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground">
          {t('entities.create.discoveredHint')}
        </p>
      </div>
    </FormDialog>
  );
}
