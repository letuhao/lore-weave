import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Merge, Search } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useEntities } from '../hooks/useEntities';
import { useMergeEntity, type MergeEntityError } from '../hooks/useEntityMutations';
import type { Entity } from '../api';

// K19d γ-b — merge dialog. Source is the entity the user opened the
// detail panel on. Target is picked via a search-to-select on
// listEntities. Same min-2-chars rule as EntitiesTab so short
// keystrokes don't round-trip to a 422.

export interface EntityMergeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  source: Entity;
  /** After a successful merge the source is deleted — parent
   *  should close the detail panel. */
  onMerged?: (targetEntityId: string) => void;
}

export function EntityMergeDialog({
  open,
  onOpenChange,
  source,
  onMerged,
}: EntityMergeDialogProps) {
  const { t } = useTranslation('knowledge');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Entity | null>(null);

  // Reset local state each time the dialog opens on a different source.
  useEffect(() => {
    if (open) {
      setSearch('');
      setSelected(null);
    }
  }, [open, source.id]);

  // FE min-2-chars matches BE Query(min_length=2). When the search
  // is shorter than 2 chars, drop the search param so BE doesn't
  // 422 — useEntities still returns the default-page list which
  // we filter out below (hide source + already-selected).
  const effectiveSearch = search.trim().length >= 2 ? search.trim() : undefined;
  const { entities, isLoading } = useEntities({
    search: effectiveSearch,
    limit: 20,
    offset: 0,
  });

  const candidates = entities.filter((e) => e.id !== source.id);

  const mutation = useMergeEntity({
    onSuccess: (resp) => {
      toast.success(
        t('entities.merge.success', {
          source: source.name,
          target: resp.target.name,
        }),
      );
      onMerged?.(resp.target.id);
      onOpenChange(false);
    },
    onError: (err: MergeEntityError) => {
      switch (err.errorCode) {
        case 'same_entity':
          toast.error(t('entities.merge.errSameEntity'));
          break;
        case 'entity_not_found':
          toast.error(t('entities.merge.errNotFound'));
          break;
        case 'entity_archived':
          toast.error(t('entities.merge.errArchived'));
          break;
        case 'glossary_conflict':
          toast.error(t('entities.merge.errGlossaryConflict'));
          break;
        default:
          toast.error(
            t('entities.merge.errUnknown', {
              reason: err.detailMessage || err.message,
            }),
          );
      }
    },
  });

  const submit = async () => {
    if (!selected) return;
    try {
      await mutation.merge({ sourceId: source.id, targetId: selected.id });
    } catch {
      // Errors are surfaced via useMutation's onError (toast); swallow
      // the rejected promise here so vitest's unhandled-rejection
      // detector doesn't flag a handled failure as an error.
    }
  };

  const canSubmit = selected != null && !mutation.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !mutation.isPending) onOpenChange(o);
      }}
      title={t('entities.merge.title')}
      description={t('entities.merge.description', { name: source.name })}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('entities.merge.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            data-testid="entity-merge-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Merge className="h-3 w-3" />
            {mutation.isPending
              ? t('entities.merge.merging')
              : t('entities.merge.confirm')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <p className="rounded-md bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
          {t('entities.merge.warning')}
        </p>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('entities.merge.targetLabel')}
          </span>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('entities.merge.searchPlaceholder')}
              disabled={mutation.isPending}
              className="w-full rounded-md border bg-input py-1.5 pl-7 pr-2 text-xs outline-none focus:border-ring disabled:opacity-60"
              data-testid="entity-merge-search"
            />
          </div>
          {effectiveSearch == null && search.length > 0 && (
            <span className="text-[10px] text-muted-foreground">
              {t('entities.merge.searchMinHint')}
            </span>
          )}
        </label>

        {selected && (
          <div
            className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-[12px]"
            data-testid="entity-merge-selected"
          >
            <div className="flex items-center justify-between">
              <span className="truncate font-medium">{selected.name}</span>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="text-[11px] text-muted-foreground hover:text-foreground"
              >
                {t('entities.merge.clear')}
              </button>
            </div>
            <span className="text-[10px] text-muted-foreground">
              {selected.kind} · {selected.mention_count} {t('entities.merge.mentions')}
            </span>
          </div>
        )}

        {!selected && effectiveSearch != null && (
          <div className="max-h-48 overflow-y-auto rounded-md border">
            {isLoading ? (
              <p className="px-3 py-2 text-[11px] text-muted-foreground">
                {t('entities.merge.searching')}
              </p>
            ) : candidates.length === 0 ? (
              <p className="px-3 py-2 text-[11px] text-muted-foreground">
                {t('entities.merge.noMatches')}
              </p>
            ) : (
              <ul className="divide-y" data-testid="entity-merge-candidates">
                {candidates.map((e) => (
                  <li key={e.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(e)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-[12px] transition-colors hover:bg-muted/50"
                      data-testid="entity-merge-candidate"
                    >
                      <span className="min-w-0 flex-1 truncate">{e.name}</span>
                      <span className="ml-2 text-[10px] text-muted-foreground">
                        {e.kind}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </FormDialog>
  );
}
