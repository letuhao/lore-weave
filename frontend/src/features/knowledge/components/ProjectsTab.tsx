import { useRef, useState } from 'react';
import { FolderOpen, Plus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog, EmptyState, SkeletonCard } from '@/components/shared';
import { useProjects } from '../hooks/useProjects';
import type { Project } from '../types';
import { ProjectFormModal } from './ProjectFormModal';
import { ProjectRow } from './ProjectRow';

export function ProjectsTab() {
  const { t } = useTranslation('knowledge');
  const [includeArchived, setIncludeArchived] = useState(false);
  const {
    items,
    hasMore,
    isLoading,
    isError,
    error,
    refetch,
    createProject,
    updateProject,
    archiveProject,
    deleteProject,
  } = useProjects(includeArchived);

  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null);
  const [editTarget, setEditTarget] = useState<Project | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Project | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [actionPending, setActionPending] = useState(false);

  // K8.2-R6: Radix keeps the ConfirmDialog mounted during its ~150ms
  // exit animation. Reading target?.name during that window flashes
  // empty quotes in the description, so we remember the last shown
  // name in a ref and fall back to it while the dialog is closing.
  const lastArchiveName = useRef('');
  const lastDeleteName = useRef('');
  if (archiveTarget) lastArchiveName.current = archiveTarget.name;
  if (deleteTarget) lastDeleteName.current = deleteTarget.name;

  const openCreate = () => {
    setEditTarget(null);
    setModalMode('create');
  };

  const openEdit = (project: Project) => {
    setEditTarget(project);
    setModalMode('edit');
  };

  const handleArchive = async () => {
    if (!archiveTarget) return;
    setActionPending(true);
    try {
      await archiveProject(archiveTarget.project_id);
      toast.success(t('projects.toast.archived'));
      setArchiveTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('projects.toast.archiveFailed'));
    } finally {
      setActionPending(false);
    }
  };

  const handleRestore = async (project: Project) => {
    try {
      await updateProject({
        projectId: project.project_id,
        payload: { is_archived: false },
        // D-K8-03: pass the captured version so a stale Show-archived
        // list snapshot can't silently win against an edit from
        // another device.
        expectedVersion: project.version,
      });
      toast.success(t('projects.toast.restored'));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('projects.toast.restoreFailed'));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setActionPending(true);
    try {
      await deleteProject(deleteTarget.project_id);
      toast.success(t('projects.toast.deleted'));
      setDeleteTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('projects.toast.deleteFailed'));
    } finally {
      setActionPending(false);
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            className="h-3.5 w-3.5 rounded border"
          />
          {t('projects.showArchived')}
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => void refetch()}
            title={t('projects.refresh')}
            className="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t('projects.refresh')}
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            {t('projects.newProject')}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex flex-col gap-2">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {isError && !isLoading && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-xs text-destructive">
          {t('projects.loadFailed', { error: error instanceof Error ? error.message : 'unknown error' })}
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={FolderOpen}
          title={t('projects.empty.title')}
          description={t('projects.empty.description')}
          action={
            <button
              onClick={openCreate}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" />
              {t('projects.createFirst')}
            </button>
          }
        />
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((project) => (
            <ProjectRow
              key={project.project_id}
              project={project}
              onEdit={openEdit}
              onArchive={setArchiveTarget}
              onRestore={(p) => void handleRestore(p)}
              onDelete={setDeleteTarget}
            />
          ))}
          {hasMore && (
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              {t('projects.paginationNote')}
            </p>
          )}
        </div>
      )}

      <ProjectFormModal
        open={modalMode !== null}
        onOpenChange={(o) => !o && setModalMode(null)}
        mode={modalMode ?? 'create'}
        project={editTarget}
        onCreate={createProject}
        onUpdate={(projectId, payload, expectedVersion) =>
          updateProject({ projectId, payload, expectedVersion })
        }
      />

      <ConfirmDialog
        open={archiveTarget !== null}
        onOpenChange={(o) => !o && setArchiveTarget(null)}
        title={t('projects.archiveDialog.title')}
        description={t('projects.archiveDialog.description', {
          name: archiveTarget?.name ?? lastArchiveName.current,
        })}
        confirmLabel={t('projects.archiveDialog.confirm')}
        onConfirm={() => void handleArchive()}
        loading={actionPending}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={t('projects.deleteDialog.title')}
        description={t('projects.deleteDialog.description', {
          name: deleteTarget?.name ?? lastDeleteName.current,
        })}
        confirmLabel={t('projects.deleteDialog.confirm')}
        variant="destructive"
        onConfirm={() => void handleDelete()}
        loading={actionPending}
      />
    </div>
  );
}
