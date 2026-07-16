// WS-2.6a / D17 controller — "Correct a memory": the user edits a diary day's distilled entry text.
// CLAUDE.md MVC: all flow logic here; the journal view only renders the editor + calls `correct`.
// The re-extract model rides the caller's chosen chat model, read off the assistant session exactly
// like useEndOfDay (Q8 server-side resolution is a shared follow-up). A non-fatal reconcile failure
// (SSOT amended but graph reconcile enqueue failed) is surfaced as a toast, not thrown — the entry is
// already corrected.
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { chatApi } from '@/features/chat/api';
import { assistantApi } from '../api';
import type { CorrectResult } from '../types';

export function useDiaryCorrection(bookId: string | null) {
  const { accessToken } = useAuth();
  const [correctingId, setCorrectingId] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const correct = useCallback(
    async (chapterId: string, body: string, title?: string): Promise<CorrectResult | null> => {
      const text = body.trim();
      if (!accessToken || !bookId || !chapterId || !text) return null;
      setCorrectingId(chapterId);
      try {
        // Resolve the re-extract model off the assistant session (same source as end-of-day).
        const sess = await chatApi.listSessions(accessToken, 'active', bookId);
        const assistant = sess.items.find((s) => s.session_kind === 'assistant') ?? sess.items[0];
        if (!assistant) {
          throw new Error('The assistant needs a model to re-read your correction — say a few things first.');
        }
        const res = await assistantApi.correctDiaryEntry(accessToken, {
          book_id: bookId,
          chapter_id: chapterId,
          body: text,
          title,
          model_source: assistant.model_source,
          model_ref: assistant.model_ref,
        });
        // Leg 1 (SSOT amend) is done. Leg 2/3 (graph reconcile) is non-fatal: tell the user their
        // correction is safe even if the memory sync is still pending.
        if (res.reextract_enqueued) {
          toast.success('Corrected — the old memory is being replaced.');
        } else {
          toast.warning('Correction saved. Updating your memory is taking a moment.');
        }
        return res;
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not save your correction.');
        return null;
      } finally {
        if (mounted.current) setCorrectingId(null);
      }
    },
    [accessToken, bookId],
  );

  return { correct, correctingId };
}
