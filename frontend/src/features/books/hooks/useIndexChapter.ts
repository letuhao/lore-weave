import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { booksApi } from '@/features/books/api';

interface UseIndexChapterArgs {
  token: string;
  bookId: string;
  chapterId: string;
  /** Called after a successful index / forget / allow so the page can refetch the
   * authoritative chapter row (server is the source of truth). */
  onChanged: () => void | Promise<void>;
}

/**
 * WS-0.9 controller — "add this chapter to my knowledge graph".
 *
 * Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md.
 *
 * Indexing is INDEPENDENT of publishing. A user can add a draft chapter to their
 * knowledge graph and never publish it (and a diary book never publishes at all). This
 * hook owns the three transitions; the chapter's kg state itself is owned by the page and
 * passed to the view, so the hook is stateless w.r.t. status.
 *
 * Self-contained: no parent useEffect needed (repo rule — hooks own their own state and
 * cleanup).
 */
export function useIndexChapter({ token, bookId, chapterId, onChanged }: UseIndexChapterArgs) {
  const { t } = useTranslation('editor');
  const [busy, setBusy] = useState(false);
  const [forgetOpen, setForgetOpen] = useState(false);

  const index = useCallback(async () => {
    setBusy(true);
    try {
      const res = await booksApi.indexChapter(token, bookId, chapterId);
      // No-silent-success: re-indexing an unchanged draft is a legitimate no-op, and the
      // user must be told that rather than shown a success that implies fresh work.
      toast.success(
        res.reused_revision ? t('knowledge.reused_toast') : t('knowledge.indexed_toast'),
      );
      await onChanged();
    } catch (e) {
      // Speak the two actionable failures by name; a generic error would leave the user
      // clicking forever with no idea their own "kept out" flag is what's blocking it.
      const code = (e as { code?: string })?.code;
      if (code === 'BOOK_KG_EXCLUDED') toast.error(t('knowledge.excluded_toast'));
      else if (code === 'BOOK_INVALID_LIFECYCLE') toast.error(t('knowledge.empty_toast'));
      else toast.error(t('knowledge.failed_toast'));
    } finally {
      setBusy(false);
    }
  }, [token, bookId, chapterId, onChanged, t]);

  const requestForget = useCallback(() => setForgetOpen(true), []);

  const confirmForget = useCallback(async () => {
    setBusy(true);
    try {
      await booksApi.setChapterKgExclude(token, bookId, chapterId, true);
      toast.success(t('knowledge.forgotten_toast'));
      await onChanged();
    } catch {
      toast.error(t('knowledge.failed_toast'));
    } finally {
      setBusy(false);
      setForgetOpen(false);
    }
  }, [token, bookId, chapterId, onChanged, t]);

  /** Clearing the exclusion only RE-ALLOWS indexing — it deliberately does NOT re-index.
   * A toggle that silently re-ingests the user's prose is a privacy surprise, so the
   * toast tells them the next step is theirs. */
  const allow = useCallback(async () => {
    setBusy(true);
    try {
      await booksApi.setChapterKgExclude(token, bookId, chapterId, false);
      toast.success(t('knowledge.allowed_toast'));
      await onChanged();
    } catch {
      toast.error(t('knowledge.failed_toast'));
    } finally {
      setBusy(false);
    }
  }, [token, bookId, chapterId, onChanged, t]);

  return { busy, forgetOpen, setForgetOpen, index, requestForget, confirmForget, allow };
}
