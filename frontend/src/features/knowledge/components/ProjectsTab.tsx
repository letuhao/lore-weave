import { useState } from 'react';
import { FolderOpen, Plus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog, EmptyState, SkeletonCard } from '@/components/shared';
import { useProjects } from '../hooks/useProjects';
import type { Project } from '../types';
import { ProjectCard } from './ProjectCard';
import { ProjectFormModal } from './ProjectFormModal';

export function ProjectsTab() {
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
      toast.success('Project archived');
      setArchiveTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Archive failed');
    } finally {
      setActionPending(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setActionPending(true);
    try {
      await deleteProject(deleteTarget.project_id);
      toast.success('Project deleted');
      setDeleteTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
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
          Show archived
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => void refetch()}
            title="Refresh"
            className="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            New project
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
          Failed to load projects: {error instanceof Error ? error.message : 'unknown error'}
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={FolderOpen}
          title="No projects yet"
          description="Projects scope what the AI remembers for a specific piece of work."
          action={
            <button
              onClick={openCreate}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" />
              Create your first project
            </button>
          }
        />
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((project) => (
            <ProjectCard
              key={project.project_id}
              project={project}
              onEdit={openEdit}
              onArchive={setArchiveTarget}
              onDelete={setDeleteTarget}
            />
          ))}
          {hasMore && (
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Showing first 100 projects — full pagination lands with Track 2.
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
        onUpdate={(projectId, payload) => updateProject({ projectId, payload })}
      />

      <ConfirmDialog
        open={archiveTarget !== null}
        onOpenChange={(o) => !o && setArchiveTarget(null)}
        title="Archive project?"
        description={`"${archiveTarget?.name ?? ''}" will be hidden from the active list. You can restore it later.`}
        confirmLabel="Archive"
        onConfirm={() => void handleArchive()}
        loading={actionPending}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete project?"
        description={`"${deleteTarget?.name ?? ''}" and its summary will be permanently deleted. This cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => void handleDelete()}
        loading={actionPending}
      />
    </div>
  );
}
