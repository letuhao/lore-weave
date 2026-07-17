import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BookOpen, Globe2 } from 'lucide-react';
import type { Project } from '../../types';
import { useProjectBacklinks } from '../../hooks/useProjectBacklinks';
import { useProjects } from '../../hooks/useProjects';
import { ProjectRow } from '../ProjectRow';
import { ProjectFormModal } from '../ProjectFormModal';

interface Props {
  project: Project | null;
  // C6 (G6) — deep-link from the complete-card "Explore graph" CTA +
  // clickable stats into the shell's entities/graph section.
  onExploreGraph: () => void;
  // 14_kg_panels.md DOCK-7 fix — this section used to hard-code <Link>s to
  // the book/world detail routes. Threaded as callbacks (same extraction
  // shape as ProjectsBrowser's `onOpen`, 14_kg_panels.md A2) so the classic
  // `ProjectDetailShell` route can still navigate() while a studio panel
  // (`KgOverviewPanel`) instead goes through the studio link resolver (F3)
  // without this component importing react-router at all.
  onOpenBook: (bookId: string) => void;
  onOpenWorld: (worldId: string) => void;
}

// C6 (G6 / KN-2 / KN-20) — the project-detail shell's Overview section:
// project state + stats + config for ONE route-scoped project. Reuses
// ProjectRow (state card + its dialogs) so the build/extract/model
// actions keep working unchanged, then threads the Explore-graph deep
// link through. Config is read-only here; full edit stays on ProjectsTab
// (no new BE, no scope creep into C7).
export function OverviewSection({ project, onExploreGraph, onOpenBook, onOpenWorld }: Props) {
  const { t } = useTranslation('knowledge');
  // D-WORLD-PROJECT-BACKLINK (G3) — resolve the project's book + world so the
  // overview cross-links out instead of showing a raw book UUID.
  const backlinks = useProjectBacklinks(project?.book_id);

  // The detail-view edit affordance (KN — the pen button used to be a dead
  // no-op here). ProjectDetailShell already mounts useProjects(false) to
  // resolve this project, so the same react-query cache serves createProject/
  // updateProject with NO extra fetch (dedup by queryKey). Same modal +
  // If-Match update the ProjectsTab browser uses.
  const { createProject, updateProject } = useProjects(false);
  const [editing, setEditing] = useState(false);

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

  return (
    <div className="space-y-4" data-testid="shell-overview">
      {/* Reuse the project state card (build/extract/model dialogs all
          wired). Edit opens the project form modal in-place (KN — the pen
          was previously a dead no-op here). Archive/restore/delete stay on
          the projects browser (destructive CRUD lives with the list) — so we
          OMIT those handlers and ProjectRow hides the buttons. Passing `noop`
          here (what this did until the 2026-07-17 audit) rendered a live
          Archive + Delete that silently did nothing on click. */}
      <ProjectRow
        project={project}
        onEdit={() => setEditing(true)}
        onExploreGraph={onExploreGraph}
      />

      <ProjectFormModal
        open={editing}
        onOpenChange={setEditing}
        mode="edit"
        project={project}
        onCreate={createProject}
        onUpdate={(projectId, payload, expectedVersion) =>
          updateProject({ projectId, payload, expectedVersion })
        }
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
                {t('shell.overview.book', { defaultValue: 'Book' })}
              </dt>
              <dd>
                <button
                  type="button"
                  onClick={() => onOpenBook(project.book_id!)}
                  data-testid="overview-book-link"
                  className="inline-flex items-center gap-1.5 text-primary hover:underline"
                >
                  <BookOpen className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{backlinks.bookTitle ?? project.book_id}</span>
                </button>
              </dd>

              {backlinks.worldId && (
                <>
                  <dt className="text-muted-foreground">
                    {t('shell.overview.world', { defaultValue: 'World' })}
                  </dt>
                  <dd>
                    <button
                      type="button"
                      onClick={() => onOpenWorld(backlinks.worldId!)}
                      data-testid="overview-world-link"
                      className="inline-flex items-center gap-1.5 text-primary hover:underline"
                    >
                      <Globe2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{backlinks.worldName ?? backlinks.worldId}</span>
                    </button>
                  </dd>
                </>
              )}
            </>
          )}
        </dl>
      </section>
    </div>
  );
}
