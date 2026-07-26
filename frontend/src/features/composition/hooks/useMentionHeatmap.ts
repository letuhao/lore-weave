// LOOM Composition (T5.2 + M7) — per-chapter mention-frequency heatmap.
//
// M7 (D-T5.2-WINDOWED-MENTIONS, CLEARED): the heatmap now reflects TRUE per-chapter
// mention FREQUENCY for the chapter in focus — the glossary
// `chapter_entity_links.mention_count` column (a CJK-aware longest-match count over
// canonical + alias surface forms, written by the translation-service extraction pass).
// This replaces the prior WHOLE-BOOK knowledge scalar: the tint is now windowed to the
// chapter being edited (spoiler-safe + locally relevant), not a global importance rank.
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { glossaryApi } from '@/features/glossary/api';

export type HeatEntity = {
  id: string;
  name: string;
  /** Other surface forms (titles/nicknames) the in-prose tint should ALSO match —
   *  mention_count counts every form, so tinting only the canonical name would miss
   *  most occurrences in alias-heavy (CJK/xianxia) prose. */
  aliases: string[];
  mention_count: number;
  /** 0..4 density band — ratio of this entity's per-chapter count to the most-mentioned. */
  band: number;
};

const TOP_N = 15;
const BANDS = 5;

/**
 * The chapter-in-focus's most-mentioned entities (top {@link TOP_N}) ranked by the
 * per-chapter `mention_count`, each bucketed into a 0..4 density band by ratio to the
 * max. Windowed to `chapterId` (the M7 cutoff). Aliases are merged from the glossary
 * known-entities list (same glossary id-space as chapter-entities) so the tint matches
 * every surface form.
 */
export function useMentionHeatmap(
  bookId: string | undefined,
  chapterId: string | undefined,
  token: string | null,
) {
  const on = !!bookId && !!chapterId && !!token;

  // Per-chapter mention FREQUENCY for THIS chapter (the M7 mention_count column).
  const presentQ = useQuery({
    queryKey: ['composition', 'heatmap', 'present', bookId, chapterId],
    queryFn: () => glossaryApi.chapterEntities(bookId!, chapterId!, token!),
    enabled: on,
    retry: false,
  });
  // Aliases (glossary id-space — same as chapter-entities). Whole-book lookup (no
  // before_chapter_index → the handler returns every entity; a name form is not a
  // spoiler), filtered to this chapter's entities below. min_frequency:1 so a
  // single-chapter entity still carries its aliases.
  const aliasQ = useQuery({
    queryKey: ['composition', 'heatmap', 'aliases', bookId],
    queryFn: () => glossaryApi.knownEntitiesAsOf(bookId!, { minFrequency: 1, limit: 500 }, token!),
    enabled: on,
    retry: false,
  });

  // Memoized so the derived array keeps a stable identity across renders (the editor
  // pushes `data` into Tiptap via a useEffect — a fresh array each render would re-tint
  // every frame).
  const data = useMemo<HeatEntity[]>(() => {
    const present = presentQ.data;
    if (!present) return [];
    const aliasMap = new Map((aliasQ.data ?? []).map((e) => [e.entity_id, e.aliases ?? []]));
    const top = present
      .filter((e) => e.mention_count > 0)
      .sort((a, b) => b.mention_count - a.mention_count)
      .slice(0, TOP_N);
    const max = top[0]?.mention_count || 1;
    return top.map((e) => ({
      id: e.entity_id,
      name: e.name,
      aliases: (aliasMap.get(e.entity_id) ?? []).filter((a) => a && a !== e.name),
      mention_count: e.mention_count,
      band: Math.min(BANDS - 1, Math.floor((e.mention_count / max) * BANDS)),
    }));
  }, [presentQ.data, aliasQ.data]);

  return {
    data,
    isLoading: on && (presentQ.isLoading || aliasQ.isLoading),
    isError: presentQ.isError,
  };
}
