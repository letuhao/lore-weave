import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Link2 } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useEntities } from '../hooks/useEntities';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { useCreateRelation } from '../hooks/useEntityMutations';
import { RELATION_PREDICATES, type RelationPredicate } from '../lib/entityKinds';

// S7-1 — build a relation: subject → predicate → object. The subject is seeded
// from the node/row the user acted on. `predicate` is a closed-set enum over the
// ONE constant (a GUI convention — the wire accepts a free string; see
// entityKinds.ts). `object` is a TYPEAHEAD over the project's own entities
// (never a render-all `<select>` — a subgraph is thousands of nodes). Both
// endpoints must be the caller's entities or the server 409s.

export interface CreateRelationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  subjectId: string;
  subjectName: string;
}

export function CreateRelationDialog({
  open,
  onOpenChange,
  projectId,
  subjectId,
  subjectName,
}: CreateRelationDialogProps) {
  const { t } = useTranslation('knowledge');
  const [predicate, setPredicate] = useState<RelationPredicate>(
    RELATION_PREDICATES[0],
  );
  const [objectId, setObjectId] = useState<string>('');
  const [objectQuery, setObjectQuery] = useState<string>('');

  useEffect(() => {
    if (open) {
      setPredicate(RELATION_PREDICATES[0]);
      setObjectId('');
      setObjectQuery('');
    }
  }, [open]);

  const debouncedQuery = useDebouncedValue(objectQuery, 300);
  const { entities } = useEntities({
    project_id: projectId,
    search: debouncedQuery.length >= 2 ? debouncedQuery : undefined,
    limit: 20,
    offset: 0,
  });
  // The subject can't be its own object (the server 422s a self-loop anyway).
  const candidates = entities.filter((e) => e.id !== subjectId);

  const mutation = useCreateRelation({
    onSuccess: () => {
      toast.success(t('relations.create.success'));
      onOpenChange(false);
    },
    onError: (err) => {
      const status = (err as Error & { status?: number }).status;
      if (status === 409) {
        toast.error(t('relations.create.notYours'));
        return;
      }
      if (status === 422) {
        toast.error(t('relations.create.selfLoop'));
        return;
      }
      toast.error(t('relations.create.failed', { error: err.message }));
    },
  });

  const submit = async () => {
    if (!objectId) return;
    try {
      await mutation.createRelation({
        subject_id: subjectId,
        object_id: objectId,
        predicate,
      });
    } catch {
      // surfaced via onError toast.
    }
  };

  const canSubmit = !!objectId && !mutation.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !mutation.isPending) onOpenChange(o);
      }}
      title={t('relations.create.title')}
      description={t('relations.create.description', { subject: subjectName })}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('relations.create.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            data-testid="relation-create-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Link2 className="h-3 w-3" />
            {mutation.isPending
              ? t('relations.create.saving')
              : t('relations.create.save')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <div className="rounded-md border bg-secondary/30 px-3 py-2">
          <span className="text-[11px] text-muted-foreground">
            {t('relations.create.subject')}
          </span>
          <div className="font-medium" data-testid="relation-create-subject">
            {subjectName}
          </div>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('relations.create.predicate')}
          </span>
          <select
            value={predicate}
            onChange={(e) => setPredicate(e.target.value as RelationPredicate)}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="relation-create-predicate"
          >
            {RELATION_PREDICATES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('relations.create.object')}
          </span>
          <input
            type="text"
            value={objectQuery}
            onChange={(e) => {
              setObjectQuery(e.target.value);
              setObjectId('');
            }}
            placeholder={t('relations.create.objectPlaceholder')}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="relation-create-object-search"
          />
          {debouncedQuery.length >= 2 && (
            <ul
              className="max-h-40 overflow-y-auto rounded-md border"
              data-testid="relation-create-object-list"
            >
              {candidates.length === 0 && (
                <li className="px-3 py-2 text-[11px] text-muted-foreground">
                  {t('relations.create.noMatches')}
                </li>
              )}
              {candidates.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setObjectId(e.id);
                      setObjectQuery(e.name);
                    }}
                    data-testid={`relation-create-object-${e.id}`}
                    className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition-colors hover:bg-secondary ${
                      objectId === e.id ? 'bg-primary/10' : ''
                    }`}
                  >
                    <span>{e.name}</span>
                    <span className="text-[10px] capitalize text-muted-foreground">
                      {e.kind}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </label>
      </div>
    </FormDialog>
  );
}
