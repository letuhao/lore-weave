// D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — the post-commit binding surface wrapper.
// Owns the committed-outline read (so it runs ONLY when mounted — i.e. after a commit,
// not on every PlannerView render) and renders ChapterMotifBindings per just-committed
// chapter. Mounted conditionally by PlannerView (NEVER call useOutline unconditionally
// at the top of PlannerView — its test mocks usePlanner away + has no QueryClient).
import { useTranslation } from 'react-i18next';
import { useOutline } from '../../hooks/useOutline';
import type { RosterOption } from '../../hooks/useGlossaryRoster';
import { ChapterMotifBindings } from './ChapterMotifBindings';

type Props = {
  projectId: string;
  bookId: string;
  chapterIds: string[];
  roster?: RosterOption[];
  token: string | null;
  onDismiss: () => void;
  /** route a scene's commit→generate to the compose tab (optional, W2 seam). */
  onSelectScene?: (sceneId: string) => void;
};

export function CommittedSceneBindings({
  projectId, bookId, chapterIds, roster = [], token, onDismiss, onSelectScene,
}: Props) {
  const { t } = useTranslation('composition');
  const outline = useOutline(projectId, token);
  const scenesForChapter = (chapterId: string) =>
    (outline.data ?? [])
      .filter((n) => n.kind === 'scene' && n.chapter_id === chapterId && !n.is_archived)
      .sort((a, b) => (a.story_order ?? 1e9) - (b.story_order ?? 1e9) || a.rank.localeCompare(b.rank))
      .map((n) => ({ id: n.id, title: n.title }));

  return (
    <div className="space-y-3 rounded border border-border p-2" data-testid="planner-committed-bindings">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{t('motif.binding.committedTitle', { defaultValue: 'Bind scene motifs' })}</span>
        <button type="button" className="rounded border border-border px-2 py-0.5 text-xs" onClick={onDismiss}>
          {t('plan.done', { defaultValue: 'Done' })}
        </button>
      </div>
      {chapterIds.map((cid) => (
        <ChapterMotifBindings
          key={cid}
          projectId={projectId}
          bookId={bookId}
          chapterId={cid}
          scenes={scenesForChapter(cid)}
          roster={roster}
          token={token}
          onGenerate={onSelectScene ? (r) => onSelectScene(r.sceneId) : undefined}
        />
      ))}
    </div>
  );
}
