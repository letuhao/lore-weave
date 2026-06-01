// ── useMessageFeedback — chat-turn feedback controller (Q3b) ───────────────────
// Owns the rating state + the submit mutation for one assistant message. Server
// is the source of truth (the rating is POSTed + persisted to the quality
// plane); this hook keeps only an ephemeral highlight of the user's choice for
// the current view (no localStorage). Self-contained: state + side-effect +
// toast live here, not in the component.

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { useAuth } from '@/auth';
import { chatApi } from '../api';

export type FeedbackRating = 1 | -1;

interface SubmitOptions {
  reason?: string;
  regeneratedFromMessageId?: string;
}

export function useMessageFeedback(messageId?: string) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('chat');
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = useCallback(
    async (next: FeedbackRating, opts?: SubmitOptions) => {
      if (!accessToken || !messageId || submitting) return;
      setSubmitting(true);
      const previous = rating;
      setRating(next); // optimistic highlight
      try {
        await chatApi.submitMessageFeedback(accessToken, messageId, {
          rating: next,
          reason: opts?.reason,
          regenerated_from_message_id: opts?.regeneratedFromMessageId,
        });
        // Only surface a toast for an EXPLICIT thumb — the implicit
        // regenerate-as-negative (carries a reason) is silent.
        if (!opts?.reason) toast.success(t('message.feedback_thanks'));
      } catch {
        setRating(previous); // rollback the optimistic highlight
        toast.error(t('message.feedback_error'));
      } finally {
        setSubmitting(false);
      }
    },
    [accessToken, messageId, rating, submitting, t],
  );

  return { rating, submit, submitting };
}
