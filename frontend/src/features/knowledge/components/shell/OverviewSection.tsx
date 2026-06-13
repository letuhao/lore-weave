import { useTranslation } from 'react-i18next';
import type { Project } from '../../types';
import { ProjectRow } from '../ProjectRow';

interface Props {
  project: Project | null;
  // C6 (G6) — deep-link from the complete-card "Explore graph" CTA +
  // clickable stats into the shell's entities/graph section.
  onExploreGraph: () => void;
}

// C6 (G6 / KN-2 / KN-20) — the project-detail shell's Overview section:
// project state + stats + config for ONE route-scoped project. Reuses
// ProjectRow (state card + its dialogs) so the build/extract/model
// actions keep working unchanged, then threads the Explore-graph deep
// link through. Config is read-only here; full edit stays on ProjectsTab
// (no new BE, no scope creep into C7).
export function OverviewSection({ project, onExploreGraph }: Props) {
  const { t } = useTranslation('knowledge');

  if (!project) {
    return (
      <p
        className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
        data-testid="shell-overview-missing"
      >
        {t('shell.notFound')}
      </p>
    );
  }

  const noop = () => {};

  return (
    <div className="space-y-4" data-testid="shell-overview">
      {/* Reuse the project state card (build/extract/model dialogs all
          wired) — CRUD toolbar handlers are no-ops in the detail shell;
          project CRUD stays on the projects browser (C7). */}
      <ProjectRow
        project={project}
        onEdit={noop}
        onArchive={noop}
        onRestore={noop}
        onDelete={noop}
        onExploreGraph={onExploreGraph}
      />

      <section
        className="rounded-lg border bg-card p-4 text-[13px]"
        data-testid="shell-overview-config"
      >
        <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {t('shell.overview.configHeading')}
        </h2>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
          <dt className="text-muted-foreground">
            {t('shell.overview.embeddingModel')}
          </dt>
          <dd className="font-mono text-[12px]">
            {project.embedding_model ?? t('shell.overview.none')}
          </dd>

          <dt className="text-muted-foreground">
            {t('shell.overview.rerankModel')}
          </dt>
          <dd className="font-mono text-[12px]">
            {project.rerank_model ?? t('shell.overview.none')}
          </dd>

          <dt className="text-muted-foreground">
            {t('shell.overview.extraction')}
          </dt>
          <dd>
            {project.extraction_enabled
              ? t('shell.overview.extractionEnabled')
              : t('shell.overview.extractionDisabled')}
          </dd>

          {project.book_id && (
            <>
              <dt className="text-muted-foreground">
                {t('shell.overview.bookId')}
              </dt>
              <dd className="font-mono text-[12px]">{project.book_id}</dd>
            </>
          )}
        </dl>
      </section>
    </div>
  );
}
