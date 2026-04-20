import { useMemo, useState } from 'react';
import { Archive, ArchiveRestore, Pencil, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useProjectState } from '../hooks/useProjectState';
import type { Project } from '../types';
import type { ExtractionJobSummary } from '../types/projectState';
import { ProjectStateCard, type ProjectStateCardActions } from './ProjectStateCard';
import { BuildGraphDialog } from './BuildGraphDialog';
import { ErrorViewerDialog } from './ErrorViewerDialog';

// K19a.4 — replaces the Track 1 ProjectCard. One row per project:
// header + CRUD toolbar (edit/archive/delete) above, state card
// (K19a.3 dispatcher) below. CRUD actions stay side-by-side with
// state-card actions per CLARIFY decision — keeps each button's
// language clean ("Build graph" vs "Archive").

interface Props {
  project: Project;
  onEdit: (p: Project) => void;
  onArchive: (p: Project) => void;
  onRestore: (p: Project) => void;
  onDelete: (p: Project) => void;
}

export function ProjectRow({ project, onEdit, onArchive, onRestore, onDelete }: Props) {
  const { t } = useTranslation('knowledge');
  const queryClient = useQueryClient();
  const { state, actions: baseActions } = useProjectState(project);
  const isArchived = project.is_archived;
  const typeLabel = t(`projects.form.typeOptions.${project.project_type}`);

  // K19a.5 — dialog state lifted to the row. The hook returns silent no-ops
  // for the 3 dialog-dependent actions; we merge real open-dispatchers on
  // top. `errorViewer` splits {job,error} so the Failed state (no job
  // summary) still has an `error` to show.
  const [buildOpen, setBuildOpen] = useState(false);
  const [errorViewer, setErrorViewer] = useState<{ job: ExtractionJobSummary | null; error: string } | null>(null);

  // review-impl F4 — narrow the actions deps. `state` object reference
  // changes every poll tick (items_processed advances). Extract only
  // the fields the onViewError closure reads so the merged `actions`
  // doesn't recreate for a progress-bar update. Projecting to a single
  // payload object keeps both the snapshot we'd pass to the viewer and
  // the dep list compact.
  let errorPayload: { job: ExtractionJobSummary | null; error: string } | null = null;
  if (state.kind === 'building_paused_error') {
    errorPayload = { job: state.job, error: state.error };
  } else if (state.kind === 'failed') {
    errorPayload = { job: null, error: state.error };
  }
  // Stable JSON key — converts the conditional payload into a single
  // string the memo can compare by value instead of reference.
  const errorPayloadKey = errorPayload
    ? `${errorPayload.job?.job_id ?? 'none'}|${errorPayload.error}`
    : '';

  const actions = useMemo<ProjectStateCardActions>(
    () => ({
      ...baseActions,
      onBuildGraph: () => setBuildOpen(true),
      onViewError: () => {
        if (errorPayload) setErrorViewer(errorPayload);
      },
    }),
    // errorPayloadKey captures job identity + error text — the only
    // fields the closure reads. See comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [baseActions, errorPayloadKey],
  );

  return (
    <div className="rounded-lg border bg-card p-4 transition-colors hover:border-border/80">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h3 className="truncate font-serif text-[15px] font-semibold">{project.name}</h3>
            {isArchived && (
              <span className="rounded-md bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning">
                {t('projects.card.archivedBadge')}
              </span>
            )}
            <span className="text-[11px] text-muted-foreground">{typeLabel}</span>
          </div>
          {project.description && (
            <p className="line-clamp-2 text-xs text-muted-foreground">{project.description}</p>
          )}
          {project.book_id && (
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              {t('projects.card.bookId')}: {project.book_id}
            </p>
          )}
        </div>

        <div className="flex flex-shrink-0 gap-1">
          <button
            onClick={() => onEdit(project)}
            title={t('projects.card.edit')}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {!isArchived ? (
            <button
              onClick={() => onArchive(project)}
              title={t('projects.card.archive')}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Archive className="h-3.5 w-3.5" />
            </button>
          ) : (
            <button
              onClick={() => onRestore(project)}
              title={t('projects.card.restore')}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <ArchiveRestore className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={() => onDelete(project)}
            title={t('projects.card.delete')}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <ProjectStateCard state={state} actions={actions} />

      <BuildGraphDialog
        open={buildOpen}
        onOpenChange={setBuildOpen}
        project={project}
        onStarted={() => {
          // Flip the card to BuildingRunning on the next tick without
          // waiting for the 2s poll.
          void queryClient.invalidateQueries({
            queryKey: ['knowledge-project-jobs', project.project_id],
          });
        }}
      />

      <ErrorViewerDialog
        open={errorViewer !== null}
        onOpenChange={(open) => {
          if (!open) setErrorViewer(null);
        }}
        job={errorViewer?.job ?? null}
        error={errorViewer?.error ?? ''}
      />
    </div>
  );
}
