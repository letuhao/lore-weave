import { useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  X,
  ArrowRight,
  ArrowLeft,
  Pencil,
  Merge,
  Unlock,
  Sparkles,
  Pin,
  PinOff,
  Archive,
  Plus,
  Ban,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useEntityDetail } from '../hooks/useEntityDetail';
import {
  useEntityFacts,
  useCreateEntityFact,
  useInvalidateFact,
} from '../hooks/useEntityFacts';
import { useAnchoredGlossaryEntity } from '../hooks/useAnchoredGlossaryEntity';
import {
  useUnlockEntity,
  usePromoteEntity,
  useToggleGlossaryPin,
  useArchiveEntity,
  useRestoreEntity,
} from '../hooks/useEntityMutations';
import type { EntityFact, EntityRelation } from '../api';
import { TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS } from '../lib/touchTarget';
import { EntityEditDialog } from './EntityEditDialog';
import { EntityMergeDialog } from './EntityMergeDialog';
import { RelationEditDialog } from './RelationEditDialog';
import { CreateRelationDialog } from './CreateRelationDialog';
import { Link2 } from 'lucide-react';
import { TemporalTab } from '../../knowledge-temporal/components/TemporalTab';

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
  // C9 (C9-promote-flow) — the scoped project's linked book. Required for
  // the glossary context-pin toggle (which is book-scoped); when absent the
  // unpin control is hidden (a project with no book can't anchor or pin).
  bookId?: string | null;
}

const FACT_TYPE_LABEL: Record<EntityFact['type'], string> = {
  decision: 'entities.detail.factType.decision',
  preference: 'entities.detail.factType.preference',
  milestone: 'entities.detail.factType.milestone',
  negation: 'entities.detail.factType.negation',
  statement: 'entities.detail.factType.statement',
  commitment: 'entities.detail.factType.commitment',
};

// S-05 — the closed authoring order (mirrors the BE FactType). The order the
// select offers; every value here MUST have a FACT_TYPE_LABEL entry.
const AUTHORABLE_FACT_TYPES: EntityFact['type'][] = [
  'decision', 'preference', 'milestone', 'negation', 'statement', 'commitment',
];

function RelationRow({
  relation,
  entityId,
  onEdit,
}: {
  relation: EntityRelation;
  entityId: string;
  onEdit: (relation: EntityRelation) => void;
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
      {/* Phase B C-FE — correct / mark-wrong this relation. Icon-only, so it
          needs the square 44×44 tap target on mobile. Opens the SINGLE
          panel-scoped dialog (not one per row) via onEdit. */}
      <button
        type="button"
        onClick={() => onEdit(relation)}
        title={t('relations.edit.cta')}
        aria-label={t('relations.edit.cta')}
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground',
          TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS,
        )}
        data-testid="entity-detail-relation-edit"
      >
        <Pencil className="h-3 w-3" />
      </button>
    </li>
  );
}

export function EntityDetailPanel({
  open,
  onOpenChange,
  entityId,
  bookId,
}: EntityDetailPanelProps) {
  const { t } = useTranslation('knowledge');
  const { detail, isLoading, error } = useEntityDetail(
    open ? entityId : null,
  );
  // C9 — provenance MVP: known-facts list (+ each fact's source_chapter).
  const { facts } = useEntityFacts(open ? entityId : null);
  // S-05 — author a fact ABOUT this entity (direct-write) + mark a fact wrong.
  const [showAddFact, setShowAddFact] = useState(false);
  const [factType, setFactType] = useState<EntityFact['type']>('decision');
  const [factContent, setFactContent] = useState('');
  const [factPredicate, setFactPredicate] = useState('');
  const [factObject, setFactObject] = useState('');
  const createFact = useCreateEntityFact(open ? entityId : null, {
    onSuccess: () => {
      toast.success(t('entities.detail.addFactSuccess'));
      setShowAddFact(false);
      setFactContent('');
      setFactPredicate('');
      setFactObject('');
      setFactType('decision');
    },
    onError: (e) =>
      toast.error(t('entities.detail.addFactFailed', { error: e.message })),
  });
  const invalidateFactMutation = useInvalidateFact(open ? entityId : null, {
    onSuccess: () => toast.success(t('entities.detail.markWrongSuccess')),
    onError: (e) =>
      toast.error(t('entities.detail.markWrongFailed', { error: e.message })),
  });
  const handleAddFact = async () => {
    if (!factContent.trim()) return;
    try {
      await createFact.create({
        fact_type: factType,
        content: factContent.trim(),
        predicate: factPredicate.trim() || null,
        object: factObject.trim() || null,
      });
    } catch {
      // onError owns the toast; swallow the rejection (vitest guard).
    }
  };
  const handleMarkWrong = async (factId: string) => {
    if (!window.confirm(t('entities.detail.markWrongConfirm'))) return;
    try {
      await invalidateFactMutation.invalidate(factId);
    } catch {
      // onError owns the toast; swallow the rejection (vitest guard).
    }
  };
  const [showEdit, setShowEdit] = useState(false);
  const [showMerge, setShowMerge] = useState(false);
  const [showLink, setShowLink] = useState(false);
  // X6c — the "Temporal" tab (knowledge-temporal surfaces). Lazy-mounted on first open so its
  // KAL reads don't fire until viewed; once opened it stays mounted (CSS hidden on switch-back)
  // so the as-of slider state survives a Current↔Temporal toggle (no-conditional-unmount rule).
  const [panelTab, setPanelTab] = useState<'current' | 'temporal'>('current');
  const [temporalOpened, setTemporalOpened] = useState(false);
  const canTemporal = !!entityId && !!bookId;
  // Phase B C-FE — ONE relation-edit dialog at panel scope (not one per row),
  // keyed by the relation the user clicked. Mirrors the entity edit/merge
  // single-dialog pattern below.
  const [editingRelation, setEditingRelation] = useState<EntityRelation | null>(null);

  // C9 (D-K19d-γa-02) — unlock user_edited so extractions can
  // contribute aliases again. No confirm dialog state — a single
  // `window.confirm` is lightweight enough; the action is non-
  // destructive (flips a flag) and idempotent.
  const unlockMutation = useUnlockEntity({
    onSuccess: () => toast.success(t('entities.detail.unlockSuccess')),
    onError: (err) =>
      toast.error(
        t('entities.detail.unlockFailed', { error: err.message }),
      ),
  });
  const handleUnlock = async () => {
    if (!detail) return;
    if (!window.confirm(t('entities.detail.unlockConfirm'))) return;
    try {
      await unlockMutation.unlock({ entityId: detail.entity.id });
    } catch {
      // Error toast owned by onError; swallow to keep the rejected
      // promise from triggering vitest's unhandled-rejection guard.
    }
  };

  // C9 (C9-promote-flow) — promote a DISCOVERED entity → glossary draft
  // (status=draft, tag ai-suggested) + anchor (anchor_score=1.0). The BE
  // orchestrates both calls; the human reviews the draft IN glossary.
  const promoteMutation = usePromoteEntity({
    onSuccess: () => toast.success(t('entities.detail.promoteSuccess')),
    onError: (err) =>
      toast.error(t('entities.detail.promoteFailed', { error: err.message })),
  });
  const handlePromote = async () => {
    if (!detail) return;
    try {
      await promoteMutation.promote({ entityId: detail.entity.id });
    } catch {
      // onError owns the toast; swallow the rejection (vitest guard).
    }
  };

  // C9 — unpin the canonical entity's glossary context-pin
  // (is_pinned_for_context). The pin lives on the glossary entity; we
  // only ever UNpin from here (the detail surfaces a remove-from-context
  // control), so the toggle is fixed to pinned=false.
  const pinMutation = useToggleGlossaryPin({
    onSuccess: () => toast.success(t('entities.detail.unpinSuccess')),
    onError: (err) =>
      toast.error(t('entities.detail.unpinFailed', { error: err.message })),
  });
  // #11 — KG entities carry no description of their own; when anchored to a
  // glossary entity, surface that entity's authored short description here.
  const { shortDescription, scopeLabel } = useAnchoredGlossaryEntity(
    bookId ?? null,
    detail?.entity.glossary_entity_id,
  );
  const handleUnpin = async () => {
    if (!detail?.entity.glossary_entity_id || !bookId) return;
    try {
      await pinMutation.toggle({
        entityId: detail.entity.id,
        bookId,
        glossaryEntityId: detail.entity.glossary_entity_id,
        pinned: false,
      });
    } catch {
      // onError owns the toast; swallow the rejection (vitest guard).
    }
  };

  // S7-1 — soft archive (Delete = retire, NOT Merge). Wraps the EXISTING
  // archiveMyEntity route: preserves edges + the glossary anchor, hides the row
  // from the active list. No OCC (the route takes none).
  // D-KG-ENTITY-RESTORE (S7) — archive is no longer a one-way trap: the success
  // toast offers an Undo that calls the new restore route.
  const restoreMutation = useRestoreEntity({
    onSuccess: () => toast.success(t('entities.restore.success')),
    onError: (err) =>
      toast.error(t('entities.restore.failed', { error: err.message })),
  });
  const archiveMutation = useArchiveEntity({
    onError: (err) =>
      toast.error(t('entities.archive.failed', { error: err.message })),
  });
  const handleArchive = async () => {
    if (!detail) return;
    if (!window.confirm(t('entities.archive.confirm'))) return;
    const id = detail.entity.id;
    try {
      await archiveMutation.archive({ entityId: id });
      toast.success(t('entities.archive.success'), {
        action: {
          label: t('entities.archive.undo'),
          onClick: () => { void restoreMutation.restore({ entityId: id }); },
        },
      });
      onOpenChange(false);
    } catch {
      // onError owns the toast; swallow the rejection (vitest guard).
    }
  };

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
              <button
                type="button"
                onClick={() => setShowLink(true)}
                disabled={!detail?.entity.project_id}
                title={t('relations.create.action')}
                aria-label={t('relations.create.action')}
                className="rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="entity-detail-link"
              >
                <Link2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={handleArchive}
                disabled={!detail || archiveMutation.isPending}
                title={t('entities.archive.action')}
                aria-label={t('entities.archive.action')}
                className="rounded-sm p-1 text-muted-foreground transition-colors hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="entity-detail-archive"
              >
                <Archive className="h-4 w-4" />
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

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {canTemporal && (
              <div className="mb-4 flex gap-3 border-b text-[12px]" data-testid="entity-detail-tabs">
                <button
                  type="button"
                  onClick={() => setPanelTab('current')}
                  className={cn(
                    '-mb-px border-b-2 pb-2 transition-colors',
                    panelTab === 'current'
                      ? 'border-foreground font-medium text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                  data-testid="entity-detail-tab-current"
                >
                  {t('entities.detail.tabs.current', 'Current')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPanelTab('temporal');
                    setTemporalOpened(true);
                  }}
                  className={cn(
                    '-mb-px border-b-2 pb-2 transition-colors',
                    panelTab === 'temporal'
                      ? 'border-foreground font-medium text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                  data-testid="entity-detail-tab-temporal"
                >
                  {t('entities.detail.tabs.temporal', 'Temporal')}
                </button>
              </div>
            )}

            <div hidden={panelTab !== 'current'} className="space-y-5">
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
                {shortDescription && (
                  <section className="space-y-1.5" data-testid="entity-detail-description">
                    <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {t('entities.detail.description')}
                    </h3>
                    <p className="whitespace-pre-wrap text-[12px] leading-relaxed">
                      {shortDescription}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {t('entities.detail.descriptionSource')}
                    </p>
                  </section>
                )}
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
                    {scopeLabel && (
                      <>
                        <dt className="text-muted-foreground">
                          {t('entities.detail.field.scope')}
                        </dt>
                        <dd className="truncate">{scopeLabel}</dd>
                      </>
                    )}
                  </dl>
                </section>

                {/* C9 (C9-promote-flow) — curation actions.
                    Promote shows ONLY for a `discovered` entity (the
                    LOCKED gate); on success it becomes canonical and the
                    button disappears. Unpin shows for a `canonical`
                    entity that has a glossary anchor + a book to scope the
                    pin toggle (is_pinned_for_context, NOT delete/archive). */}
                {detail.entity.status === 'discovered' && (
                  <section
                    className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2"
                    data-testid="entity-detail-promote-section"
                  >
                    <p className="text-[11px] text-muted-foreground">
                      {t('entities.detail.promoteHint')}
                    </p>
                    <button
                      type="button"
                      onClick={handlePromote}
                      disabled={promoteMutation.isPending}
                      className="mt-2 inline-flex items-center gap-1 rounded-md border border-primary/40 px-2 py-1 text-[11px] text-primary transition-colors hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
                      data-testid="entity-detail-promote"
                    >
                      <Sparkles className="h-3 w-3" />
                      {promoteMutation.isPending
                        ? t('entities.detail.promotePending')
                        : t('entities.detail.promote')}
                    </button>
                  </section>
                )}

                {detail.entity.status === 'canonical' &&
                  detail.entity.glossary_entity_id &&
                  bookId && (
                    <section
                      className="rounded-md border px-3 py-2"
                      data-testid="entity-detail-unpin-section"
                    >
                      <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                        <Pin className="h-3 w-3" />
                        {t('entities.detail.unpinHint')}
                      </p>
                      <button
                        type="button"
                        onClick={handleUnpin}
                        disabled={pinMutation.isPending}
                        className="mt-2 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="entity-detail-unpin"
                      >
                        <PinOff className="h-3 w-3" />
                        {t('entities.detail.unpin')}
                      </button>
                    </section>
                  )}

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

                {/* C9 (D-K19d-γa-02) — Unlock CTA visible only when
                    the entity is user_edited. Allows the user to
                    let future extractions contribute aliases again. */}
                {detail.entity.user_edited && (
                  <section
                    className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2"
                    data-testid="entity-detail-unlock-section"
                  >
                    <p className="text-[11px] text-muted-foreground">
                      {t('entities.detail.unlockHint')}
                    </p>
                    <button
                      type="button"
                      onClick={handleUnlock}
                      disabled={unlockMutation.isPending}
                      className="mt-2 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                      data-testid="entity-detail-unlock"
                    >
                      <Unlock className="h-3 w-3" />
                      {t('entities.detail.unlock')}
                    </button>
                  </section>
                )}

                {/* S-05 — known-facts list + the AUTHOR affordance. The section
                    ALWAYS renders (header + "Add fact") even with zero facts, so an
                    empty entity — the one that most needs authoring — can add one.
                    Each committed fact carries a "mark wrong" (invalidate) action,
                    mirroring the relation mark-wrong; facts become as correctable as
                    relations (the asymmetry the audit named). */}
                <section className="space-y-2" data-testid="entity-detail-facts">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {t('entities.detail.facts', { count: facts.length })}
                    </h3>
                    <button
                      type="button"
                      onClick={() => setShowAddFact((v) => !v)}
                      className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                      data-testid="entity-detail-add-fact"
                    >
                      <Plus className="h-3 w-3" />
                      {t('entities.detail.addFact')}
                    </button>
                  </div>

                  {showAddFact && (
                    <div
                      className="space-y-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2"
                      data-testid="entity-detail-add-fact-form"
                    >
                      <label className="block text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        {t('entities.detail.factTypeLabel')}
                      </label>
                      <select
                        value={factType}
                        onChange={(e) =>
                          setFactType(e.target.value as EntityFact['type'])
                        }
                        className="w-full rounded-md border bg-background px-2 py-1 text-[12px]"
                        data-testid="entity-detail-add-fact-type"
                      >
                        {AUTHORABLE_FACT_TYPES.map((ft) => (
                          <option key={ft} value={ft}>
                            {t(FACT_TYPE_LABEL[ft])}
                          </option>
                        ))}
                      </select>
                      <textarea
                        value={factContent}
                        onChange={(e) => setFactContent(e.target.value)}
                        placeholder={t('entities.detail.factContentPlaceholder')}
                        rows={2}
                        className="w-full rounded-md border bg-background px-2 py-1 text-[12px]"
                        data-testid="entity-detail-add-fact-content"
                      />
                      <div className="flex gap-2">
                        <input
                          value={factPredicate}
                          onChange={(e) => setFactPredicate(e.target.value)}
                          placeholder={t('entities.detail.factPredicatePlaceholder')}
                          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-[11px]"
                          data-testid="entity-detail-add-fact-predicate"
                        />
                        <input
                          value={factObject}
                          onChange={(e) => setFactObject(e.target.value)}
                          placeholder={t('entities.detail.factObjectPlaceholder')}
                          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-[11px]"
                          data-testid="entity-detail-add-fact-object"
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setShowAddFact(false)}
                          className="rounded-md border px-2 py-1 text-[11px] transition-colors hover:bg-secondary"
                          data-testid="entity-detail-add-fact-cancel"
                        >
                          {t('entities.detail.addFactCancel')}
                        </button>
                        <button
                          type="button"
                          onClick={handleAddFact}
                          disabled={!factContent.trim() || createFact.isPending}
                          className="inline-flex items-center gap-1 rounded-md border border-primary/40 px-2 py-1 text-[11px] text-primary transition-colors hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
                          data-testid="entity-detail-add-fact-save"
                        >
                          {t('entities.detail.addFactSave')}
                        </button>
                      </div>
                    </div>
                  )}

                  {facts.length > 0 && (
                    <ul className="space-y-1">
                      {facts.map((f) => (
                        <li
                          key={f.id}
                          className="rounded-md border px-3 py-2 text-[12px]"
                          data-testid="entity-detail-fact"
                        >
                          <div className="flex items-start gap-2">
                            <span className="mt-0.5 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                              {t(FACT_TYPE_LABEL[f.type])}
                            </span>
                            <span className="min-w-0 flex-1">{f.content}</span>
                            <button
                              type="button"
                              onClick={() => handleMarkWrong(f.id)}
                              disabled={invalidateFactMutation.isPending}
                              title={t('entities.detail.markWrong')}
                              aria-label={t('entities.detail.markWrong')}
                              className={cn(
                                'inline-flex shrink-0 items-center justify-center rounded-sm p-1 text-muted-foreground transition-colors hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50',
                                TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS,
                              )}
                              data-testid="entity-detail-fact-mark-wrong"
                            >
                              <Ban className="h-3 w-3" />
                            </button>
                          </div>
                          {f.source_chapter && (
                            <p
                              className="mt-1 text-[10px] text-muted-foreground"
                              data-testid="entity-detail-fact-source"
                            >
                              {t('entities.detail.factSource', {
                                chapter: f.source_chapter,
                              })}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

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
                            <RelationRow key={r.id} relation={r} entityId={entityId!} onEdit={setEditingRelation} />
                          ))}
                        </ul>
                      )}
                      {incoming.length > 0 && (
                        <ul className="space-y-1" data-testid="entity-detail-incoming">
                          {incoming.map((r) => (
                            <RelationRow key={r.id} relation={r} entityId={entityId!} onEdit={setEditingRelation} />
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </section>
              </>
            )}
            </div>

            {/* X6c Temporal tab — lazy-mounted on first open, then kept mounted (hidden) so the
                as-of slider state survives a tab toggle. Keyed by entityId to reset on switch. */}
            {canTemporal && temporalOpened && (
              <div hidden={panelTab !== 'temporal'} data-testid="entity-detail-temporal">
                <TemporalTab key={entityId} bookId={bookId!} entityId={entityId!} />
              </div>
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
          {editingRelation && (
            <RelationEditDialog
              open={editingRelation !== null}
              onOpenChange={(o) => {
                if (!o) setEditingRelation(null);
              }}
              relation={editingRelation}
            />
          )}
          {detail.entity.project_id && (
            <CreateRelationDialog
              open={showLink}
              onOpenChange={setShowLink}
              projectId={detail.entity.project_id}
              subjectId={detail.entity.id}
              subjectName={detail.entity.name}
            />
          )}
        </>
      )}
    </Dialog.Root>
  );
}
