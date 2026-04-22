import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Trash2 } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { knowledgeApi, type Entity } from '../api';
import { useUserEntities } from '../hooks/useUserEntities';

// K19c.4 — cross-project preferences extracted by Track 2 from chat
// turns. Consumes useUserEntities('global') and renders a compact
// list with a delete (soft archive) affordance per row. The BE
// returns entities already filtered to active + global-scope, so
// this component is a thin presentation layer.
//
// "Delete" maps to DELETE /v1/knowledge/me/entities/{id} which soft-
// archives via the existing archive_entity helper. The user won't
// see the entity in this list after archive. BE-side DELETE is
// idempotent per RFC 9110 (see K19c Cycle α /review-impl L6).

interface ConfirmDeleteState {
  entity: Entity;
}

export function PreferencesSection() {
  const { t } = useTranslation('knowledge');
  const { accessToken, user } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.user_id ?? 'anon';
  const { entities, isLoading, error } = useUserEntities();
  const [confirmDelete, setConfirmDelete] = useState<ConfirmDeleteState | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (entity: Entity) => {
    if (!accessToken || deletingId) return;
    setDeletingId(entity.id);
    try {
      await knowledgeApi.archiveMyEntity(entity.id, accessToken);
      // review-impl L7: this 3-element key is a PREFIX of the hook's
      // actual key (`['knowledge-user-entities', userId, scope, limit]`).
      // React Query matches by prefix, so this invalidates every
      // `limit` variant for this (user, scope). If someone later adds a
      // 4th segment to the hook's queryKey (e.g. filter), the invalidation
      // continues to work; if someone changes the prefix ordering, this
      // silently stops matching — the test catches it via the spy.
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-user-entities', userId, 'global'],
      });
      toast.success(
        t('global.preferences.deleteSuccess', { name: entity.name }),
      );
      setConfirmDelete(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(t('global.preferences.deleteFailed', { error: msg }));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="mt-6" data-testid="preferences-section">
      <h3 className="mb-2 font-serif text-sm font-semibold">
        {t('global.preferences.title')}
      </h3>
      <p className="mb-3 text-[12px] text-muted-foreground">
        {t('global.preferences.description')}
      </p>

      {isLoading && (
        <p
          className="text-[12px] text-muted-foreground"
          data-testid="preferences-loading"
        >
          {t('global.preferences.loading')}
        </p>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="preferences-error"
        >
          {t('global.preferences.loadFailed')}
          <span className="ml-2 text-destructive/80">{error.message}</span>
        </div>
      )}

      {!isLoading && !error && entities.length === 0 && (
        <p
          className="rounded-md border border-dashed px-3 py-4 text-center text-[12px] text-muted-foreground"
          data-testid="preferences-empty"
        >
          {t('global.preferences.empty')}
        </p>
      )}

      {!isLoading && !error && entities.length > 0 && (
        <ul className="space-y-1" data-testid="preferences-list">
          {entities.map((entity) => (
            <li
              key={entity.id}
              className="flex items-center gap-3 rounded-md border bg-card px-3 py-2"
              data-testid="preferences-row"
              data-entity-id={entity.id}
            >
              <span
                className={cn(
                  'inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                  'bg-muted text-muted-foreground',
                )}
              >
                {entity.kind}
              </span>
              <span className="min-w-0 flex-1 truncate text-[13px]" title={entity.name}>
                {entity.name}
              </span>
              <button
                type="button"
                onClick={() => setConfirmDelete({ entity })}
                disabled={deletingId === entity.id}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                aria-label={t('global.preferences.deleteAria', { name: entity.name })}
                data-testid="preferences-delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {confirmDelete && (
        <FormDialog
          open={true}
          onOpenChange={(o) => {
            if (!o && !deletingId) setConfirmDelete(null);
          }}
          title={t('global.preferences.confirmTitle')}
          description={t('global.preferences.confirmBody', {
            name: confirmDelete.entity.name,
          })}
          footer={
            <>
              <button
                type="button"
                onClick={() => setConfirmDelete(null)}
                disabled={deletingId != null}
                className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t('global.preferences.cancel')}
              </button>
              <button
                type="button"
                onClick={() => handleDelete(confirmDelete.entity)}
                disabled={deletingId != null}
                className="rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="preferences-confirm-delete"
              >
                {deletingId != null
                  ? t('global.preferences.deleting')
                  : t('global.preferences.delete')}
              </button>
            </>
          }
        >
          <p className="text-[12px] text-muted-foreground">
            {t('global.preferences.confirmNote')}
          </p>
        </FormDialog>
      )}
    </section>
  );
}
