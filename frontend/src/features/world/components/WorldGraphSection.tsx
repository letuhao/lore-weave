import { useTranslation } from 'react-i18next';
import { ProjectGraphView } from '@/features/knowledge/components/ProjectGraphView';
import { useWorldProject } from '../hooks/useWorldProject';

interface WorldGraphSectionProps {
  /** The world's bible book — used to resolve its knowledge project. */
  bibleBookId: string | null;
}

// C21 — embeds the C19 read-only ProjectGraphView, scoped to the world's
// knowledge project (resolved by bible book). Read-only (graph editing is out of
// scope — G5); when the world has no project yet, ProjectGraphView renders its
// own empty state. No new graph code — pure reuse.
export function WorldGraphSection({ bibleBookId }: WorldGraphSectionProps) {
  const { t } = useTranslation('world');
  const { projectId } = useWorldProject(bibleBookId);

  return (
    <section className="space-y-2" data-testid="world-graph-section">
      <h2 className="font-medium">{t('graph.title', { defaultValue: 'World graph' })}</h2>
      <p className="text-xs text-muted-foreground">
        {t('graph.subtitle', { defaultValue: 'A read-only view of how your world’s lore connects.' })}
      </p>
      {/* Read-only reuse of the C19 canvas. bookId threads the bible book for the
          detail panel's pin control; the canvas itself never mutates. */}
      <ProjectGraphView projectId={projectId ?? undefined} bookId={bibleBookId} />
    </section>
  );
}
