import { useCallback, useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type {
  TranslationCandidateEntity,
  ApplyTranslationsResponse,
  ApplyTranslationItem,
} from '../types';

const CANDIDATE_PAGE = 100;

/** Key a draft by (entity, attribute value) so one entity's multiple translatable
 *  attributes (name, aliases, …) each get their own target-language input. */
export function draftKey(entityId: string, attrValueId: string): string {
  return `${entityId}:${attrValueId}`;
}

/**
 * Controller for the S4 batch-translate dialog. Pick a target language → load the book's
 * untranslated candidates → edit a per-(entity,attribute) draft value → submit. Submit
 * writes drafts via apply-translations (never overwrites a verified value) and surfaces
 * the server's partial-failure report (translated / skipped_verified / skipped_empty /
 * failed). No business logic lives in the view.
 */
export function useBatchTranslate(bookId: string) {
  const { accessToken } = useAuth();
  const [targetLanguage, setTargetLanguage] = useState('');
  const [candidates, setCandidates] = useState<TranslationCandidateEntity[]>([]);
  const [total, setTotal] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApplyTranslationsResponse | null>(null);

  const load = useCallback(
    async (lang: string) => {
      if (!accessToken || !lang) return;
      setLoading(true);
      setError(null);
      try {
        const resp = await glossaryApi.listTranslationCandidates(
          bookId,
          lang,
          { limit: CANDIDATE_PAGE },
          accessToken,
        );
        setCandidates(resp.items);
        setTotal(resp.total);
        // Pre-fill with any existing translation so the user edits rather than retypes.
        const pre: Record<string, string> = {};
        for (const ent of resp.items) {
          for (const a of ent.attributes) {
            if (a.existing_value) pre[draftKey(ent.entity_id, a.attr_value_id)] = a.existing_value;
          }
        }
        setDrafts(pre);
      } catch (e) {
        setError((e as Error).message);
        setCandidates([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [accessToken, bookId],
  );

  const selectLanguage = useCallback(
    (lang: string) => {
      setTargetLanguage(lang);
      setResult(null); // a fresh language pick clears the previous run's report
      void load(lang);
    },
    [load],
  );

  const setDraft = useCallback((entityId: string, attrValueId: string, value: string) => {
    setDrafts((d) => ({ ...d, [draftKey(entityId, attrValueId)]: value }));
  }, []);

  const submit = useCallback(async () => {
    if (!accessToken || !targetLanguage || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const items: ApplyTranslationItem[] = [];
      for (const ent of candidates) {
        for (const a of ent.attributes) {
          const v = drafts[draftKey(ent.entity_id, a.attr_value_id)];
          if (v && v.trim()) {
            items.push({ entity_id: ent.entity_id, attr_value_id: a.attr_value_id, value: v.trim() });
          }
        }
      }
      const resp = await glossaryApi.applyTranslations(
        bookId,
        { target_language: targetLanguage, items },
        accessToken,
      );
      setResult(resp);
      // Reload so freshly-translated rows drop out of the candidate list.
      await load(targetLanguage);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, bookId, candidates, drafts, targetLanguage, submitting, load]);

  return {
    targetLanguage,
    selectLanguage,
    candidates,
    total,
    drafts,
    setDraft,
    submit,
    loading,
    submitting,
    error,
    result,
  };
}
