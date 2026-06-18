import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FolderOpen, Plus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog, EmptyState, SkeletonCard } from '@/components/shared';
import { useProjects } from '../hooks/useProjects';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import type { Project } from '../types';
import {
  narrowProjects,
  toServerParams,
  type ProjectSort,
  type ProjectStateFilter,
} from '../lib/projectBrowser';
import { ProjectFormModal } from './ProjectFormModal';
import { ProjectRow } from './ProjectRow';
import { ProjectsBrowserControls } from './ProjectsBrowserControls';

export function ProjectsTab() {
  const { t } = useTranslation('knowledge');
  const navigate = useNavigate();
  const [includeArchived, setIncludeArchived] = useState(false);

  // C7 (G6) + C7-followup (KN-7) — HOME-browser narrowing state. Explicit
  // handlers (no useEffect-for-events). The narrowing now runs
  // SERVER-SIDE: the control state maps to BE query params via
  // `toServerParams`, so search / sort / filter span ALL projects, not
  // just the loaded cursor pages.
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<ProjectSort>('recent');
  const [stateFilter, setStateFilter] = useState<ProjectStateFilter>('all');

  // The "archived" state filter implies we must have archived rows
  // loaded. Either the explicit checkbox OR an archived filter pulls
  // them in.
  const wantArchived = includeArchived || stateFilter === 'archived';

  // The raw `search` keeps the input controlled/responsive (and drives
  // the presentational `narrowProjects` fallback below, so typing
  // narrows the loaded rows instantly). Only the DEBOUNCED term feeds
  // the server query key, so a fast typist triggers ONE network round-
  // trip after they pause — not one per keystroke.
  const debouncedSearch = useDebouncedValue(search, 250);

  const serverParams = useMemo(
    () => toServerParams({ search: debouncedSearch, sort, stateFilter }),
    [debouncedSearch, sort, stateFilter],
  );

  const {
    items,
    hasMore,
    loadMore,
    isFetchingMore,
    isLoading,
    isError,
    error,
    refetch,
    createProject,
    updateProject,
    archiveProject,
    deleteProject,
  } = useProjects({
    includeArchived: wantArchived,
    search: serverParams.search,
    sortBy: serverParams.sort_by,
    sortDir: serverParams.sort_dir,
    status: serverParams.status,
  });

  // Presentational fallback only — the server already returned the
  // narrowed/ordered set; this re-applies the same predicate so a brief
  // refetch window can't flash a stale row. Never widens past `items`.
  const visible = useMemo(
    () => narrowProjects(items, { search, sort, stateFilter }),
    [items, search, sort, stateFilter],
  );

  const openProject = (p: Project) =>
    navigate(`/knowledge/projects/${p.project_id}/overview`);

  // C7: selecting the archived filter also flips the checkbox so the
  // "Show archived" affordance stays in sync with the active narrowing.
  const handleStateFilterChange = (next: ProjectStateFilter) => {
    setStateFilter(next);
    if (next === 'archived') setIncludeArchived(true);
  };

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

      {!isLoading && !isError && (
        <ProjectsBrowserControls
          search={search}
          onSearchChange={setSearch}
          sort={sort}
          onSortChange={setSort}
          stateFilter={stateFilter}
          onStateFilterChange={handleStateFilterChange}
        />
      )}

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

      {/* Truly-empty (no projects at all) — offer to create the first. */}
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

      {/* Loaded rows exist but the current search/filter hides them all. */}
      {!isLoading && !isError && items.length > 0 && visible.length === 0 && (
        <div
          className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground"
          data-testid="projects-no-matches"
        >
          {t('projects.browser.noMatches')}
        </div>
      )}

      {!isLoading && !isError && visible.length > 0 && (
        <div className="flex flex-col gap-2">
          {visible.map((project) => (
            <ProjectRow
              key={project.project_id}
              project={project}
              onOpen={openProject}
              onEdit={openEdit}
              onArchive={setArchiveTarget}
              onRestore={(p) => void handleRestore(p)}
              onDelete={setDeleteTarget}
            />
          ))}
          {hasMore && (
            <button
              type="button"
              onClick={() => void loadMore()}
              disabled={isFetchingMore}
              data-testid="projects-load-more"
              className="mt-2 self-center rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-60"
            >
              {isFetchingMore
                ? t('projects.browser.loadingMore')
                : t('projects.browser.loadMore')}
            </button>
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
