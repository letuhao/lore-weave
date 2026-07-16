// S5-B4 — the branch prose-diff data hook. A dị bản is COW: its project holds only
// the scenes the writer diverged, so its outline scenes ARE the changed/added set.
// For each chapter that has a delta scene, fetch scene-drafts from BOTH the derivative
// and its source, correspond by (chapter_id, story_order), and classify each scene.
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../api';
import { isUnchanged } from '../lib/lineDiff';

export type BranchDiffScene = {
  chapterId: string;
  nodeId: string;
  storyOrder: number;
  title: string;
  status: 'changed' | 'added' | 'unchanged';
  canonText: string; // '' when the scene is all-new (no canon counterpart drafted)
  branchText: string;
};

export function useBranchDiff(
  derivativeProjectId: string | null | undefined,
  sourceProjectId: string | null | undefined,
  token: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['composition', 'branch-diff', derivativeProjectId, sourceProjectId],
    enabled: enabled && !!derivativeProjectId && !!sourceProjectId && !!token,
    queryFn: async (): Promise<BranchDiffScene[]> => {
      const outline = await compositionApi.getOutline(derivativeProjectId!, token!);
      const scenes = outline.nodes.filter(
        (n) => n.kind === 'scene' && !n.is_archived && !!n.chapter_id,
      );
      const chapters = [...new Set(scenes.map((s) => s.chapter_id as string))];
      const perChapter = await Promise.all(
        chapters.map(async (chId) => {
          const [deriv, source] = await Promise.all([
            compositionApi.getChapterSceneDrafts(derivativeProjectId!, chId, token),
            compositionApi.getChapterSceneDrafts(sourceProjectId!, chId, token),
          ]);
          const sourceByOrder = new Map(source.items.map((s) => [s.story_order, s]));
          const sourceByNode = new Map(source.items.map((s) => [s.node_id, s]));
          return deriv.items.map((d): BranchDiffScene => {
            // Prefer the RELIABLE anchor back-ref (a promoted take records the canon
            // scene it's an alternate of); fall back to story_order only when absent
            // (a wizard-created scene with no anchor). No match ⇒ added (never mis-pair).
            const src = (d.anchor_node_id && sourceByNode.get(d.anchor_node_id)) || sourceByOrder.get(d.story_order);
            return {
              chapterId: chId,
              nodeId: d.node_id,
              storyOrder: d.story_order,
              title: d.title,
              status: src ? (isUnchanged(src.text, d.text) ? 'unchanged' : 'changed') : 'added',
              canonText: src?.text ?? '',
              branchText: d.text,
            };
          });
        }),
      );
      return perChapter
        .flat()
        .sort((a, b) => a.chapterId.localeCompare(b.chapterId) || a.storyOrder - b.storyOrder);
    },
  });
}
