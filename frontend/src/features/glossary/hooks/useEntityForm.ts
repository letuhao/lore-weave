import { useMemo, useState } from 'react';
import { useAuth } from '@/auth';
import { useBookOntology } from './useBookOntology';
import { glossaryApi } from '../api';
import type { BookAttribute, BookGenre } from '../tieringTypes';

export interface EntityFieldRow {
  attr: BookAttribute;
  labelCode: string; // namespaced code·genre on a cross-genre keep-both conflict
}
export interface EntityGenreSection {
  genre: BookGenre;
  fields: EntityFieldRow[];
}

/**
 * Controller for the merged tiered entity CREATE form (03-entity-form). Given a kind,
 * it derives the applicable (kind × genre) attribute fields across the entity's genre
 * set, grouping by genre and namespacing a code that appears in 2+ genres (keep-both).
 * The entity's genres default to the book's active genres and are editable per entity
 * (D2). Submit = create entity → set its genre override → persist the filled values.
 */
export function useEntityForm(bookId: string, kindId: string | null) {
  const { accessToken } = useAuth();
  const ont = useBookOntology(bookId);
  const { genres, kinds, attributes } = ont.ontology;

  const defaultGenreIds = useMemo(
    () => genres.filter((g) => g.active).map((g) => g.genre_id),
    [genres],
  );
  const [overrideIds, setOverrideIds] = useState<string[] | null>(null);
  const selectedGenreIds = overrideIds ?? defaultGenreIds;
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const setValue = (attrId: string, v: string) => setValues((s) => ({ ...s, [attrId]: v }));

  // The kind's attributes restricted to the entity's selected genres.
  const effective = useMemo(
    () => attributes.filter((a) => a.kind_id === kindId && selectedGenreIds.includes(a.genre_id)),
    [attributes, kindId, selectedGenreIds],
  );

  // A code present in 2+ selected genres is kept both → namespaced code·genre.
  const sections: EntityGenreSection[] = useMemo(() => {
    const codeSpan = new Map<string, number>();
    for (const a of effective) codeSpan.set(a.code, (codeSpan.get(a.code) ?? 0) + 1);
    const genreById = new Map(genres.map((g) => [g.genre_id, g]));
    const out: EntityGenreSection[] = [];
    for (const gid of selectedGenreIds) {
      const genre = genreById.get(gid);
      if (!genre) continue;
      const fields = effective
        .filter((a) => a.genre_id === gid)
        .sort((a, b) => a.sort_order - b.sort_order)
        .map((attr) => ({
          attr,
          labelCode: (codeSpan.get(attr.code) ?? 0) > 1 ? `${attr.code}·${genre.code}` : attr.code,
        }));
      if (fields.length > 0) out.push({ genre, fields });
    }
    return out;
  }, [effective, selectedGenreIds, genres]);

  const kindName = kinds.find((k) => k.book_kind_id === kindId)?.name ?? '';

  // The override is "real" only when the user changed the genre set away from the book
  // default — otherwise we leave entity_genres empty so the entity FOLLOWS the book's
  // active genres (spec §3: override else book_active_genres) instead of freezing a copy.
  const sameAsDefault = (ids: string[]) => {
    if (ids.length !== defaultGenreIds.length) return false;
    const def = new Set(defaultGenreIds);
    return ids.every((id) => def.has(id));
  };

  const submit = async (): Promise<string> => {
    if (!kindId) throw new Error('no kind');
    setSubmitting(true);
    try {
      // Pass the genre override AT create so the backend seeds exactly the right value
      // rows in one tx (incl. keep-both conflicts) — D-GKA-ENTITY-MULTIGENRE-VALUES.
      // Omit when the selection equals the book default so the entity FOLLOWS the book.
      const override = sameAsDefault(selectedGenreIds) ? undefined : selectedGenreIds;
      const entity = await glossaryApi.createEntity(bookId, kindId, accessToken!, override);
      // Map each filled field (book attr_id) → its attribute_value row, then write it.
      const detail = await glossaryApi.getEntity(bookId, entity.entity_id, accessToken!);
      const byDef = new Map(detail.attribute_values.map((v) => [v.attr_def_id, v.attr_value_id]));
      for (const a of effective) {
        const v = values[a.attr_id];
        const avId = byDef.get(a.attr_id);
        if (v && v.trim() && avId) {
          await glossaryApi.patchAttributeValue(bookId, entity.entity_id, avId, { original_value: v }, accessToken!);
        }
      }
      return entity.entity_id;
    } finally {
      setSubmitting(false);
    }
  };

  return {
    isLoading: ont.isLoading,
    isAdopted: ont.isAdopted,
    genres,
    kindName,
    selectedGenreIds,
    setSelectedGenreIds: setOverrideIds,
    sections,
    values,
    setValue,
    submit,
    submitting,
  };
}
