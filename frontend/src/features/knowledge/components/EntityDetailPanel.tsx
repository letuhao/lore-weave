import { useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, ArrowRight, ArrowLeft, Pencil, Merge } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useEntityDetail } from '../hooks/useEntityDetail';
import type { EntityRelation } from '../api';
import { TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS } from '../lib/touchTarget';
import { EntityEditDialog } from './EntityEditDialog';
import { EntityMergeDialog } from './EntityMergeDialog';

// K19d.3 — slide-over entity detail panel (read-only MVP).
// Opens when EntitiesTab sets `selectedEntityId`; closes via X,
// Escape, or overlay click. Edit/merge CTAs land in Cycle γ.
//
// Loading state: uses Skeleton-like placeholders so a slow network
// doesn't render an empty shell.
// Error state: inline error div with the message.
// Truncation: when BE reports `relations_truncated`, the panel shows
// a "and N more relations" banner so users know to filter/search
// instead of scrolling.

export interface EntityDetailPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityId: string | null;
}

function RelationRow({
  relation,
  entityId,
}: {
  relation: EntityRelation;
  entityId: string;
}) {
  const { t } = useTranslation('knowledge');
  const isOutgoing = relation.subject_id === entityId;
  const other = isOutgoing
    ? { id: relation.object_id, name: relation.object_name, kind: relation.object_kind }
    : { id: relation.subject_id, name: relation.subject_name, kind: relation.subject_kind };
  return (
    <li
      className="flex items-center gap-2 rounded-md border px-3 py-2 text-[12px]"
      data-testid="entity-detail-relation"
    >
      {isOutgoing ? (
        <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden />
      ) : (
        <ArrowLeft className="h-3 w-3 text-muted-foreground" aria-hidden />
      )}
      <span className="font-medium">{relation.predicate}</span>
      <span className="text-muted-foreground">
        {t('entities.detail.relationArrow')}
      </span>
      <span className="min-w-0 flex-1 truncate" title={other.name ?? other.id}>
        {other.name ?? other.id}
      </span>
      {other.kind && (
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {other.kind}
        </span>
      )}
      {relation.pending_validation && (
        <span
          className="rounded bg-warning/20 px-1.5 py-0.5 text-[10px] text-warning"
          title={t('entities.detail.pendingValidation')}
        >
          {t('entities.detail.pendingBadge')}
        </span>
      )}
    </li>
  );
}

export function EntityDetailPanel({
  open,
  onOpenChange,
  entityId,
}: EntityDetailPanelProps) {
  const { t } = useTranslation('knowledge');
  const { detail, isLoading, error } = useEntityDetail(
    open ? entityId : null,
  );
  const [showEdit, setShowEdit] = useState(false);
  const [showMerge, setShowMerge] = useState(false);

  const { outgoing, incoming } = useMemo(() => {
    if (!detail || !entityId) {
      return { outgoing: [] as EntityRelation[], incoming: [] as EntityRelation[] };
    }
    const outgoing: EntityRelation[] = [];
    const incoming: EntityRelation[] = [];
    for (const r of detail.relations) {
      if (r.subject_id === entityId) outgoing.push(r);
      else incoming.push(r);
    }
    return { outgoing, incoming };
  }, [detail, entityId]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          // C5 (D-K19d-β-01) — drop the 448px cap on mobile so the
          // slide-over fills the viewport on a 375px phone instead
          // of cramping metadata + relation list into < half the
          // screen width.
          className="fixed right-0 top-0 z-50 flex h-full w-full flex-col overflow-y-auto border-l bg-background shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right md:max-w-md"
          data-testid="entity-detail-panel"
        >
          <div className="flex items-start justify-between border-b px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="truncate font-serif text-base font-semibold">
                {detail?.entity.name ?? t('entities.detail.loading')}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 truncate text-[12px] text-muted-foreground">
                {detail?.entity.kind ?? ''}
              </Dialog.Description>
            </div>
            <div className="flex items-center gap-1">
              {/* Edit / Merge CTAs — disabled until detail loads
                  so we have a full Entity object to hand the
                  dialogs. */}
              <button
                type="button"
                onClick={() => setShowEdit(true)}
                disabled={!detail}
                title={t('entities.detail.edit')}
                aria-label={t('entities.detail.edit')}
                className="rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="entity-detail-edit"
              >
                <Pencil className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setShowMerge(true)}
                disabled={!detail}
                title={t('entities.detail.merge')}
                aria-label={t('entities.detail.merge')}
                className="rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="entity-detail-merge"
              >
                <Merge className="h-4 w-4" />
              </button>
              <Dialog.Close asChild>
                <button
                  // C5 /review-impl HIGH — mobile full-width panel
                  // blocks the overlay-dismiss path, so this X
                  // button is the sole dismiss on touch. Needs the
                  // square tap target (44×44) on mobile; desktop
                  // keeps the compact 24px hit area.
                  className={cn(
                    'inline-flex items-center justify-center rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground',
                    TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS,
                  )}
                  aria-label={t('entities.detail.close')}
                  data-testid="entity-detail-close"
                >
                  <X className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>
          </div>

          <div className="flex-1 space-y-5 px-5 py-4">
            {isLoading && (
              <div
                className="text-[12px] text-muted-foreground"
                data-testid="entity-detail-loading"
              >
                {t('entities.detail.loading')}
              </div>
            )}

            {error && !isLoading && (
              <div
                role="alert"
                className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
                data-testid="entity-detail-error"
              >
                {t('entities.detail.loadFailed', { error: error.message })}
              </div>
            )}

            {detail && !isLoading && !error && (
              <>
                <section className="space-y-2">
                  <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {t('entities.detail.metadata')}
                  </h3>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
                    <dt className="text-muted-foreground">
                      {t('entities.detail.field.project')}
                    </dt>
                    <dd className={cn('truncate', !detail.entity.project_id && 'text-muted-foreground')}>
                      {detail.entity.project_id ?? t('entities.detail.field.global')}
                    </dd>
                    <dt className="text-muted-foreground">
                      {t('entities.detail.field.confidence')}
                    </dt>
                    <dd className="tabular-nums">
                      {Math.round(detail.entity.confidence * 100)}%
                    </dd>
                    <dt className="text-muted-foreground">
                      {t('entities.detail.field.mentions')}
                    </dt>
                    <dd className="tabular-nums">{detail.entity.mention_count}</dd>
                    <dt className="text-muted-foreground">
                      {t('entities.detail.field.anchor')}
                    </dt>
                    <dd className="tabular-nums">
                      {detail.entity.anchor_score?.toFixed(2) ?? '0.00'}
                    </dd>
                  </dl>
                </section>

                {detail.entity.aliases.length > 1 && (
                  <section className="space-y-2">
                    <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {t('entities.detail.aliases')}
                    </h3>
                    <div
                      className="flex flex-wrap gap-1.5"
                      data-testid="entity-detail-aliases"
                    >
                      {detail.entity.aliases.map((a) => (
                        <span
                          key={a}
                          className="rounded bg-muted px-2 py-0.5 text-[11px]"
                        >
                          {a}
                        </span>
                      ))}
                    </div>
                  </section>
                )}

                <section className="space-y-2">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {t('entities.detail.relations', {
                        count: detail.total_relations,
                      })}
                    </h3>
                    {detail.relations_truncated && (
                      <span
                        className="text-[10px] text-warning"
                        data-testid="entity-detail-truncated"
                      >
                        {t('entities.detail.truncated', {
                          shown: detail.relations.length,
                          total: detail.total_relations,
                        })}
                      </span>
                    )}
                  </div>
                  {detail.relations.length === 0 ? (
                    <p
                      className="rounded-md border border-dashed px-3 py-4 text-center text-[12px] text-muted-foreground"
                      data-testid="entity-detail-no-relations"
                    >
                      {t('entities.detail.noRelations')}
                    </p>
                  ) : (
                    <>
                      {outgoing.length > 0 && (
                        <ul className="space-y-1" data-testid="entity-detail-outgoing">
                          {outgoing.map((r) => (
                            <RelationRow key={r.id} relation={r} entityId={entityId!} />
                          ))}
                        </ul>
                      )}
                      {incoming.length > 0 && (
                        <ul className="space-y-1" data-testid="entity-detail-incoming">
                          {incoming.map((r) => (
                            <RelationRow key={r.id} relation={r} entityId={entityId!} />
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </section>
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>

      {/* Edit + Merge dialogs mounted as peers so they sit ABOVE
          the detail slide-over's overlay. Radix portals each one
          to document.body; z-index inherits from our Dialog.Content
          shared `z-50`. */}
      {detail && (
        <>
          <EntityEditDialog
            open={showEdit}
            onOpenChange={setShowEdit}
            entity={detail.entity}
          />
          <EntityMergeDialog
            open={showMerge}
            onOpenChange={setShowMerge}
            source={detail.entity}
            onMerged={() => {
              // Source was deleted — close the detail panel so
              // the user isn't left looking at a 404-bound id.
              onOpenChange(false);
            }}
          />
        </>
      )}
    </Dialog.Root>
  );
}
