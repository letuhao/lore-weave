import { useCallback, useMemo, useState } from 'react';
import { Archive, ArchiveRestore, Pencil, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { useProjectState, PROJECT_ACTION_KEYS } from '../hooks/useProjectState';
import { knowledgeApi, type ExtractionJobWire } from '../api';
import type { Project } from '../types';
import type { ExtractionJobSummary } from '../types/projectState';
import { ProjectStateCard, type ProjectStateCardActions } from './ProjectStateCard';
import { readBackendError } from '../lib/readBackendError';
import { BuildGraphDialog } from './BuildGraphDialog';
import { ErrorViewerDialog } from './ErrorViewerDialog';
import { ChangeModelDialog } from './ChangeModelDialog';

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
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const { state, actions: baseActions } = useProjectState(project);
  const isArchived = project.is_archived;
  const typeLabel = t(`projects.form.typeOptions.${project.project_type}`);

  // K19a.5 + K19a.6 — dialog + confirm state lifted to the row. The
  // hook returns silent no-ops for the 5 dialog/confirm-dependent
  // actions; we merge real open-dispatchers on top. For destructive
  // actions the hook still owns the raw BE call — we call it from the
  // ConfirmDialog's onConfirm after the user has acknowledged.
  //
  // `errorViewer` splits {job,error} so the Failed state (no job
  // summary) still has an `error` to show.
  const [buildOpen, setBuildOpen] = useState(false);
  const [errorViewer, setErrorViewer] = useState<{ job: ExtractionJobSummary | null; error: string } | null>(null);
  const [changeModelOpen, setChangeModelOpen] = useState(false);
  // Rebuild is double-confirm: step1 explains the destruction, step2
  // is the final "are you sure". Two booleans instead of a single
  // enum keeps the JSX readable.
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [rebuildConfirmStep1, setRebuildConfirmStep1] = useState(false);
  const [rebuildConfirmStep2, setRebuildConfirmStep2] = useState(false);
  const [disableConfirmOpen, setDisableConfirmOpen] = useState(false);
  // Single `submitting` flag shared across all destructive confirm
  // dialogs. Only one can be open at a time so a shared flag is safe;
  // ConfirmDialog's `loading` prop disables the confirm button while
  // set.
  const [destructiveSubmitting, setDestructiveSubmitting] = useState(false);

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
      // K19a.6 — destructive actions open a confirm dialog; the raw
      // BE call runs from the dialog's onConfirm (see invokeDelete /
      // invokeRebuild / invokeDisable below). The change-model flow
      // is a full form dialog, not a single confirm.
      onChangeModel: () => setChangeModelOpen(true),
      onDisable: () => setDisableConfirmOpen(true),
      onDeleteGraph: () => setDeleteConfirmOpen(true),
      onRebuild: () => setRebuildConfirmStep1(true),
    }),
    // errorPayloadKey captures job identity + error text — the only
    // fields the closure reads. See comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [baseActions, errorPayloadKey],
  );

  // K19a.6 — destructive-action invokers called from the confirm
  // dialogs. Each wraps the BE call in try/catch + toast.error +
  // shared submitting flag, then closes the dialog + invalidates the
  // jobs query so the state card flips on the next tick.
  const invalidateJobs = () => {
    void queryClient.invalidateQueries({
      queryKey: ['knowledge-project-jobs', project.project_id],
    });
    void queryClient.invalidateQueries({
      queryKey: ['knowledge-project-graph-stats', project.project_id],
    });
  };

  // K19a.7 — `labelKey` is the i18n key under `projects.state.actions.*`.
  // Translation happens inside the catch block so language switches
  // during the in-flight window are reflected in the toast (rare but
  // free to get right).
  const runDestructive = useCallback(
    async (labelKey: string, op: () => Promise<unknown>, close: () => void) => {
      setDestructiveSubmitting(true);
      try {
        await op();
        close();
        invalidateJobs();
      } catch (err) {
        toast.error(
          t('projects.toast.actionFailed', {
            label: t(labelKey),
            error: readBackendError(err),
          }),
        );
      } finally {
        setDestructiveSubmitting(false);
      }
    },
    // `invalidateJobs` depends only on queryClient + project.project_id,
    // both stable. `t` is stable unless language changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, project.project_id, t],
  );

  const invokeDelete = useCallback(() => {
    if (!accessToken) return;
    void runDestructive(
      PROJECT_ACTION_KEYS.deleteGraph,
      () => knowledgeApi.deleteGraph(project.project_id, accessToken),
      () => setDeleteConfirmOpen(false),
    );
  }, [accessToken, project.project_id, runDestructive]);

  // review-impl F1 — route rebuild through `runDestructive` so the
  // confirm dialog shows loading + surfaces BE errors in-dialog. We
  // read the latest job (model refs) from the same react-query cache
  // the hook polls, so no duplicate fetch. If no latest job exists
  // the rebuild can't be replayed — toast and abort.
  const invokeRebuild = useCallback(() => {
    if (!accessToken) return;
    const jobs = queryClient.getQueryData<ExtractionJobWire[]>([
      'knowledge-project-jobs',
      project.project_id,
    ]);
    const latest = jobs?.[0];
    if (!latest) {
      toast.error(t('projects.toast.rebuildNoPriorJob'));
      setRebuildConfirmStep2(false);
      return;
    }
    void runDestructive(
      PROJECT_ACTION_KEYS.rebuild,
      () =>
        knowledgeApi.rebuildGraph(
          project.project_id,
          {
            llm_model: latest.llm_model,
            embedding_model: latest.embedding_model,
          },
          accessToken,
        ),
      () => setRebuildConfirmStep2(false),
    );
  }, [accessToken, project.project_id, queryClient, runDestructive, t]);

  const invokeDisable = useCallback(() => {
    if (!accessToken) return;
    void runDestructive(
      PROJECT_ACTION_KEYS.disable,
      () => knowledgeApi.disableExtraction(project.project_id, accessToken),
      () => setDisableConfirmOpen(false),
    );
  }, [accessToken, project.project_id, runDestructive]);

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

      <ChangeModelDialog
        open={changeModelOpen}
        onOpenChange={setChangeModelOpen}
        project={project}
        onChanged={() => {
          invalidateJobs();
          // Invalidate the Project list too so the card picks up the
          // new embedding_model + refreshed extraction_enabled state.
          void queryClient.invalidateQueries({
            queryKey: ['knowledge-projects'],
          });
        }}
      />

      <ConfirmDialog
        open={deleteConfirmOpen}
        onOpenChange={(o) => {
          if (!destructiveSubmitting) setDeleteConfirmOpen(o);
        }}
        title={t('projects.confirmDestructive.deleteGraph.title')}
        description={t('projects.confirmDestructive.deleteGraph.description')}
        confirmLabel={t('projects.state.actions.deleteGraph')}
        cancelLabel={t('projects.confirmDestructive.cancel')}
        variant="destructive"
        loading={destructiveSubmitting}
        onConfirm={invokeDelete}
      />

      <ConfirmDialog
        open={rebuildConfirmStep1}
        onOpenChange={(o) => {
          if (!destructiveSubmitting) setRebuildConfirmStep1(o);
        }}
        title={t('projects.confirmDestructive.rebuildStep1.title')}
        description={t('projects.confirmDestructive.rebuildStep1.description')}
        confirmLabel={t('projects.confirmDestructive.rebuildStep1.confirmLabel')}
        cancelLabel={t('projects.confirmDestructive.cancel')}
        variant="destructive"
        onConfirm={() => {
          setRebuildConfirmStep1(false);
          setRebuildConfirmStep2(true);
        }}
      />

      <ConfirmDialog
        open={rebuildConfirmStep2}
        onOpenChange={(o) => {
          if (!destructiveSubmitting) setRebuildConfirmStep2(o);
        }}
        title={t('projects.confirmDestructive.rebuildStep2.title')}
        description={t('projects.confirmDestructive.rebuildStep2.description')}
        confirmLabel={t('projects.state.actions.rebuild')}
        cancelLabel={t('projects.confirmDestructive.cancel')}
        variant="destructive"
        loading={destructiveSubmitting}
        onConfirm={invokeRebuild}
      />

      <ConfirmDialog
        open={disableConfirmOpen}
        onOpenChange={(o) => {
          if (!destructiveSubmitting) setDisableConfirmOpen(o);
        }}
        title={t('projects.confirmDestructive.disable.title')}
        description={t('projects.confirmDestructive.disable.description')}
        confirmLabel={t('projects.state.actions.disable')}
        cancelLabel={t('projects.confirmDestructive.cancel')}
        variant="default"
        loading={destructiveSubmitting}
        onConfirm={invokeDisable}
      />
    </div>
  );
}
