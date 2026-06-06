import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { booksApi } from '@/features/books/api';

export type EditorialStatus = 'draft' | 'published';

interface UsePublishChapterArgs {
  token: string;
  bookId: string;
  chapterId: string;
  /** Current editor draft_version → sent as expected_draft_version for CM1
   * optimistic-concurrency (409 CHAPTER_DRAFT_CONFLICT on a stale publish). */
  draftVersion?: number;
  /** Called after a successful publish/unpublish so the page can refetch the
   * authoritative editorial_status (server is the source of truth). */
  onChanged: () => void | Promise<void>;
}

/**
 * CM-FE controller — owns the publish/unpublish actions + the unpublish
 * confirm-dialog state. Self-contained: no parent useEffect needed. The
 * editorial_status itself is owned by the page (passed to the view), so this
 * hook is stateless w.r.t. status and only drives the transitions.
 */
export function usePublishChapter({
  token,
  bookId,
  chapterId,
  draftVersion,
  onChanged,
}: UsePublishChapterArgs) {
  const { t } = useTranslation('editor');
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const publish = useCallback(async () => {
    setBusy(true);
    try {
      await booksApi.publishChapter(token, bookId, chapterId, draftVersion);
      toast.success(t('publish.published_toast'));
      await onChanged();
    } catch (e) {
      const err = e as { code?: string; status?: number; message?: string };
      // CM1 concurrency: the server draft advanced since this editor loaded.
      if (err.code === 'CHAPTER_DRAFT_CONFLICT' || err.status === 409) {
        toast.error(t('publish.conflict_toast'));
      } else if (err.code === 'CHAPTER_EMPTY_PUBLISH') {
        // Empty-prose guard (book-service 422): canon must carry real text.
        toast.error(t('publish.empty_toast'));
      } else {
        toast.error(err.message || t('publish.published_toast'));
      }
    } finally {
      setBusy(false);
    }
  }, [token, bookId, chapterId, draftVersion, onChanged, t]);

  const requestUnpublish = useCallback(() => setConfirmOpen(true), []);

  const confirmUnpublish = useCallback(async () => {
    setBusy(true);
    try {
      await booksApi.unpublishChapter(token, bookId, chapterId);
      toast.success(t('publish.unpublished_toast'));
      await onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  }, [token, bookId, chapterId, onChanged, t]);

  return { busy, confirmOpen, setConfirmOpen, publish, requestUnpublish, confirmUnpublish };
}
