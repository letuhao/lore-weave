import { Archive, ArchiveRestore, Pencil, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Project } from '../types';

// K8 Track 1 renders the `disabled` state only. Other states
// (building/paused/ready/failed) land with Track 2 Gate 12. See
// SESSION_PATCH D-K8-02.

interface Props {
  project: Project;
  onEdit: (project: Project) => void;
  onArchive: (project: Project) => void;
  onRestore: (project: Project) => void;
  onDelete: (project: Project) => void;
}

export function ProjectCard({ project, onEdit, onArchive, onRestore, onDelete }: Props) {
  const { t } = useTranslation('memory');
  const isArchived = project.is_archived;
  const typeLabel = t(`projects.form.typeOptions.${project.project_type}`);

  return (
    <div className="rounded-lg border bg-card p-4 transition-colors hover:border-border/80">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h3 className="truncate font-serif text-[15px] font-semibold">
              {project.name}
            </h3>
            <span className="rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {t('projects.card.staticMemory')}
            </span>
            {isArchived && (
              <span className="rounded-md bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning">
                {t('projects.card.archivedBadge')}
              </span>
            )}
            <span className="text-[11px] text-muted-foreground">
              {typeLabel}
            </span>
          </div>
          {project.description && (
            <p className="line-clamp-2 text-xs text-muted-foreground">
              {project.description}
            </p>
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
    </div>
  );
}
