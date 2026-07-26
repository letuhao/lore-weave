// 3b §3.2b — the SEAM into S2's PlanDrawer. S4 OWNS this component; S2 mounts it with a
// one-line import (<MotifBindingLens nodeId={…} …/>) — S4 never edits PlanDrawer.tsx
// (component-mounting keeps ownership disjoint per the 8-session coordination rule).
//
// It is the motif facet for a chapter/scene node selected in the plan: the current binding
// (swap/clear/roles) + the ranked "Suggest a motif" button — the same surface as the
// scene-inspector Motifs section, so there is ONE binding UX, not a fork.
import { useTranslation } from 'react-i18next';
import { SceneMotifsSection } from './SceneMotifsSection';
import type { RosterOption } from '../../hooks/useGlossaryRoster';

type Props = {
  projectId: string | null;
  bookId: string | null;
  chapterId: string | null;
  /** the outline node (scene) selected in the PlanDrawer */
  nodeId: string;
  roster?: RosterOption[];
  token: string | null;
};

export function MotifBindingLens({ projectId, bookId, chapterId, nodeId, roster = [], token }: Props) {
  const { t } = useTranslation('composition');
  return (
    <section data-testid="motif-binding-lens" className="flex flex-col gap-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-neutral-400">
        {t('motif.lens.title', { defaultValue: 'Motifs' })}
      </div>
      <SceneMotifsSection
        projectId={projectId}
        bookId={bookId}
        chapterId={chapterId}
        sceneId={nodeId}
        roster={roster}
        token={token}
      />
    </section>
  );
}
