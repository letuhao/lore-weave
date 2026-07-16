import { useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';

/**
 * M6a — human-fix flywheel: confirm a corrected name into the glossary from the
 * translation review view. Resolution chain (reuses the glossary API):
 *   search by source name → pick entity (exact display-name match, else first)
 *   → load entity → find the `name` attribute value → patch/create its
 *   target-language translation with confidence='verified'.
 *
 * Confirming raises the glossary term to TRUST-1, and the glossary change emits
 * `glossary.entity_updated` → M5c flags the book's translations stale → the user
 * re-translates (M5b publish gate). One fix, propagated by the existing loop.
 *
 * Returns a typed outcome instead of throwing so the dialog can show a precise
 * message (the name might not be in the glossary yet, etc.).
 */
export type ConfirmNameResult = 'confirmed' | 'not_found' | 'no_name_attr' | 'error';

export function useConfirmName(bookId: string, targetLang: string) {
  const { accessToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);

  async function confirm(sourceName: string, correctedTarget: string): Promise<ConfirmNameResult> {
    const src = sourceName.trim();
    const tgt = correctedTarget.trim();
    if (!accessToken || !src || !tgt || !targetLang) return 'error';
    setSubmitting(true);
    try {
      const list = await glossaryApi.listEntities(
        bookId, { kindCodes: [], status: 'all', searchQuery: src }, accessToken,
      );
      const items = list.items ?? [];
      // Only confirm on an EXACT (case-insensitive) display-name match. Search can
      // return fuzzy hits; falling back to items[0] would silently write
      // confidence='verified' to the WRONG entity. No exact match → not_found
      // (the user resolves aliases/fuzzy cases in the glossary editor).
      const match = items.find((e) => e.display_name.toLowerCase() === src.toLowerCase());
      if (!match) return 'not_found';

      const entity = await glossaryApi.getEntity(bookId, match.entity_id, accessToken);
      const nameAv = entity.attribute_values.find((av) => av.attribute_def.code === 'name');
      if (!nameAv) return 'no_name_attr';

      const existing = nameAv.translations.find((tr) => tr.language_code === targetLang);
      if (existing) {
        await glossaryApi.patchTranslation(
          bookId, entity.entity_id, nameAv.attr_value_id, existing.translation_id,
          { value: tgt, confidence: 'verified' }, accessToken,
        );
      } else {
        await glossaryApi.createTranslation(
          bookId, entity.entity_id, nameAv.attr_value_id,
          { language_code: targetLang, value: tgt, confidence: 'verified' }, accessToken,
        );
      }
      return 'confirmed';
    } catch (e) {
      // S8: don't discard the exception silently — the generic 'error' result stays, but log
      // the cause so a real failure (auth, 5xx) is diagnosable rather than invisible.
      console.error('useConfirmName: confirm failed', e);
      return 'error';
    } finally {
      setSubmitting(false);
    }
  }

  return { confirm, submitting };
}
