import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { History, RotateCcw, Eye, X } from 'lucide-react';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { useEntityRevisions, useEntityRevisionDetail } from '../hooks/useEntityRevisions';
import type { EntityRevisionSummary, RevisionSnapshot } from '../types';

interface EntityHistoryPanelProps {
  bookId: string;
  entityId: string;
  /** Called after a successful restore so the editor re-fetches the entity. */
  onRestored: () => void;
  onClose: () => void;
}

/**
 * View (render-only) for the entity version history (VG-3). Lists revisions,
 * lets the user inspect a revision's full snapshot, and restore to it (behind a
 * confirm). All logic lives in useEntityRevisions.
 */
export function EntityHistoryPanel({ bookId, entityId, onRestored, onClose }: EntityHistoryPanelProps) {
  const { t } = useTranslation('glossaryEditor');
  const { revisions, isLoading, error, restore } = useEntityRevisions(bookId, entityId);
  const [viewId, setViewId] = useState<string | null>(null);
  const [confirmRev, setConfirmRev] = useState<EntityRevisionSummary | null>(null);
  const [restoring, setRestoring] = useState(false);
  const { detail } = useEntityRevisionDetail(bookId, entityId, viewId);

  const doRestore = async () => {
    if (!confirmRev) return;
    setRestoring(true);
    try {
      await restore(confirmRev.revision_id);
      toast.success(t('history.toast_restored', { num: confirmRev.revision_num }));
      onRestored();
    } catch (e) {
      toast.error((e as Error).message);
    }
    setRestoring(false);
    setConfirmRev(null);
  };

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center justify-between border-b px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <History className="h-4 w-4" />
          {t('history.title')}
        </div>
        <button
          onClick={onClose}
          aria-label={t('history.close')}
          className="inline-flex items-center rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <p className="px-4 py-6 text-xs text-muted-foreground">{t('history.loading')}</p>
        ) : error ? (
          // Distinct from "empty" — a fetch failure must NOT read as "history is gone".
          <p className="px-4 py-6 text-xs text-destructive">{t('history.error')}</p>
        ) : revisions.length === 0 ? (
          <p className="px-4 py-6 text-xs text-muted-foreground">{t('history.empty')}</p>
        ) : (
          <ul>
            {revisions.map((rev) => (
              <li key={rev.revision_id} className="border-b px-4 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs min-w-0">
                    <span className="font-mono font-semibold">#{rev.revision_num}</span>
                    <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px]">
                      {t(`history.op.${rev.op}`, rev.op)}
                    </span>
                    <span className="text-muted-foreground">
                      {t(`history.actor.${rev.actor_type}`, rev.actor_type)}
                    </span>
                    <span className="text-muted-foreground truncate">{rev.created_at}</span>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => setViewId(viewId === rev.revision_id ? null : rev.revision_id)}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] hover:bg-secondary"
                    >
                      <Eye className="h-3 w-3" />
                      {t('history.view')}
                    </button>
                    <button
                      onClick={() => setConfirmRev(rev)}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] hover:bg-secondary"
                    >
                      <RotateCcw className="h-3 w-3" />
                      {t('history.restore')}
                    </button>
                  </div>
                </div>
                {viewId === rev.revision_id && detail && (
                  <RevisionSnapshotView snapshot={detail.snapshot} />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={!!confirmRev}
        onOpenChange={(o) => !o && setConfirmRev(null)}
        title={t('history.restore_confirm_title')}
        description={t('history.restore_confirm_desc', { num: confirmRev?.revision_num ?? 0 })}
        confirmLabel={t('history.restore')}
        cancelLabel={t('history.cancel')}
        onConfirm={doRestore}
        loading={restoring}
      />
    </div>
  );
}

/** Renders a revision's full whole-entity snapshot readably (PO: full viewer). */
function RevisionSnapshotView({ snapshot }: { snapshot: RevisionSnapshot }) {
  const { t } = useTranslation('glossaryEditor');
  const attrs = snapshot.attributes ?? [];
  const links = (snapshot.chapter_links ?? []).map((cl) => cl.chapter_title).filter(Boolean);
  return (
    <div className="mt-2 rounded-md bg-muted/40 p-3 text-[11px] space-y-2">
      <div className="text-muted-foreground">
        {t('history.snap_status')}: <span className="font-medium text-foreground">{snapshot.status}</span>
        {snapshot.tags && snapshot.tags.length > 0 && <> · {snapshot.tags.join(', ')}</>}
      </div>
      {attrs.map((a, i) => (
        <div key={i}>
          <div className="font-medium">
            {a.name || a.code}: {a.original_value || <span className="text-muted-foreground">—</span>}
          </div>
          {(a.translations ?? []).map((tr, j) => (
            <div key={j} className="pl-3 text-muted-foreground">
              {tr.language_code}: {tr.value}
              {tr.confidence && <span className="opacity-70"> ({tr.confidence})</span>}
            </div>
          ))}
          {(a.evidences ?? []).map((ev, j) => (
            <div key={j} className="pl-3 italic text-muted-foreground">“{ev.original_text}”</div>
          ))}
        </div>
      ))}
      {links.length > 0 && (
        <div className="text-muted-foreground">
          {t('history.snap_chapters')}: {links.join(', ')}
        </div>
      )}
    </div>
  );
}
