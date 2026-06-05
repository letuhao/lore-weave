import { useTranslation } from 'react-i18next';
import { BookCheck, BookOpen } from 'lucide-react';

import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { usePublishChapter, type EditorialStatus } from '@/features/books/hooks/usePublishChapter';

interface PublishControlProps {
  token: string;
  bookId: string;
  chapterId: string;
  draftVersion?: number;
  editorialStatus?: EditorialStatus;
  /** Editor has unsaved changes → publishing would snapshot the STALE server
   * draft, so the action is disabled until the user saves. */
  dirty?: boolean;
  /** Composition chapter-gate (M9 / OI-1): when set, the chapter has composition
   * scenes that aren't all 'done' yet → Publish is disabled with this as the
   * tooltip, so no unreviewed scene is canonized. Unpublish is unaffected. */
  blockedReason?: string;
  onChanged: () => void | Promise<void>;
}

/**
 * CM-FE view — the chapter editor's Publish affordance. Renders a status badge
 * + a Publish/Re-publish action + (when published) an Unpublish action behind a
 * destructive confirm. All logic lives in usePublishChapter.
 */
export function PublishControl({
  token,
  bookId,
  chapterId,
  draftVersion,
  editorialStatus,
  dirty,
  blockedReason,
  onChanged,
}: PublishControlProps) {
  const { t } = useTranslation('editor');
  const { busy, confirmOpen, setConfirmOpen, publish, requestUnpublish, confirmUnpublish } =
    usePublishChapter({ token, bookId, chapterId, draftVersion, onChanged });

  // Until the chapter's editorial_status is known, render nothing. This covers
  // (a) the pre-load window and (b) an older book-service that doesn't return
  // editorial_status at all — in both, showing a publish affordance would be
  // misleading (and could POST without the concurrency guard / hit a route the
  // BE can't honor). The control appears once getChapter resolves.
  if (editorialStatus === undefined) return null;

  const isPublished = editorialStatus === 'published';

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={
          'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ' +
          (isPublished ? 'bg-success/12 text-success' : 'bg-muted text-muted-foreground')
        }
        data-testid="editorial-badge"
        data-status={editorialStatus}
      >
        {isPublished ? <BookCheck className="h-3 w-3" /> : <BookOpen className="h-3 w-3" />}
        {isPublished ? t('publish.published_badge') : t('publish.draft_badge')}
      </span>

      <button
        data-testid="publish-button"
        onClick={() => void publish()}
        disabled={busy || dirty || !!blockedReason}
        title={blockedReason ?? (dirty ? t('publish.save_first') : undefined)}
        className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors hover:border-primary/50 hover:text-primary disabled:opacity-50"
      >
        {isPublished ? t('publish.republish') : t('publish.publish')}
      </button>

      {isPublished && (
        <button
          onClick={requestUnpublish}
          disabled={busy}
          className="inline-flex items-center rounded-md px-2 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-destructive disabled:opacity-50"
        >
          {t('publish.unpublish')}
        </button>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t('publish.confirm_title')}
        description={t('publish.confirm_body')}
        confirmLabel={t('publish.unpublish')}
        variant="destructive"
        loading={busy}
        onConfirm={() => void confirmUnpublish()}
      />
    </div>
  );
}
