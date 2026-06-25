// LOOM Composition (T5.2) — mention heatmap (top cast by mention_count).
import { useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '@/features/knowledge/api';

export type HeatEntity = {
  id: string;
  name: string;
  /** Other surface forms (titles/nicknames) the in-prose tint should ALSO match —
   *  mention_count counts every form, so tinting only the canonical name would miss
   *  most occurrences in alias-heavy (CJK/xianxia) prose. */
  aliases: string[];
  mention_count: number;
  /** 0..4 density band — ratio of this entity's count to the most-mentioned. */
  band: number;
};

const TOP_N = 15;
const BANDS = 5;

/**
 * The book's most-mentioned entities (top {@link TOP_N}) ranked by knowledge
 * `mention_count`, each bucketed into a 0..4 density band by ratio to the max.
 * The composition `projectId` IS the knowledge project id. NOTE (D-T5.2-WINDOWED-
 * MENTIONS): mention_count is WHOLE-BOOK (aggregate) — per-chapter windowing is
 * blocked on D-P2-PER-SCENE-FANOUT (no per-chapter mention edges exist yet).
 */
export function useMentionHeatmap(projectId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: ['composition', 'heatmap', projectId],
    queryFn: () =>
      knowledgeApi.listEntities({ project_id: projectId!, sort_by: 'mention_count', limit: TOP_N }, token!),
    enabled: !!projectId && !!token,
    select: (d): HeatEntity[] => {
      const ents = d.entities.filter((e) => e.mention_count > 0);
      const max = ents.reduce((m, e) => Math.max(m, e.mention_count), 0) || 1;
      return ents.map((e) => ({
        id: e.id,
        name: e.canonical_name || e.name,
        aliases: (e.aliases ?? []).filter((a) => a && a !== (e.canonical_name || e.name)),
        mention_count: e.mention_count,
        // ratio 1 → band 4 (clamped); a rare entity → band 0
        band: Math.min(BANDS - 1, Math.floor((e.mention_count / max) * BANDS)),
      }));
    },
  });
}
