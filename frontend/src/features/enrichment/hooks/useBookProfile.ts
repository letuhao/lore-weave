import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { BookProfile, BookProfileInput, SuggestedProfile } from '../types';

/** Controller for the per-book de-bias profile (load / save / AI-suggest).
 *  `save` is a FULL REPLACE — the SettingsPanel passes the whole profile so an
 *  omitted field never silently wipes the seeded markers (BE review #3). */
export function useBookProfile(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('enrichment');
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);

  const query = useQuery({
    queryKey: ['book-profile', bookId],
    queryFn: () => enrichmentApi.getBookProfile(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
  });

  const save = async (body: BookProfileInput): Promise<BookProfile | null> => {
    setSaving(true);
    try {
      const saved = await enrichmentApi.putBookProfile(bookId, body, accessToken!);
      qc.setQueryData(['book-profile', bookId], saved);
      toast.success(t('settings.saved'));
      return saved;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const suggest = async (
    suggestModelRef: string,
    sampleChapterIds?: string[],
  ): Promise<SuggestedProfile | null> => {
    setSuggesting(true);
    try {
      const draft = await enrichmentApi.suggestBookProfile(
        bookId,
        { project_id: bookId, suggest_model_ref: suggestModelRef, sample_chapter_ids: sampleChapterIds },
        accessToken!,
      );
      toast.success(t('settings.suggested'));
      return draft;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setSuggesting(false);
    }
  };

  return {
    profile: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    save,
    suggest,
    saving,
    suggesting,
  };
}
