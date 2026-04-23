import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight, Sparkles } from 'lucide-react';
import { Skeleton } from '@/components/shared';
import { cn } from '@/lib/utils';
import { useProjects } from '../../hooks/useProjects';
import { TOUCH_TARGET_CLASS } from '../../lib/touchTarget';
import type { Project } from '../../types';
import { BuildGraphDialog } from '../BuildGraphDialog';

// K19f.2 — mobile Projects list. Stacked cards per project keeping
// only the read-heavy surface: name + project_type + extraction_status
// + description preview + Build button. Taps on the card body toggle
// an inline expand (full description + book link + last_extracted_at).
//
// DROPPED from desktop ProjectsTab: Create / Edit / Archive / Delete
// dialogs, the includeArchived filter toggle, the 13-state machine
// action buttons (Pause / Resume / Cancel / Retry / ChangeModel).
// Users wanting any of those on mobile land on the desktop-only
// banner in MobileKnowledgePage and switch device. Plan's
// "read-heavy, simple edits only" rule.
//
// Build button opens the existing BuildGraphDialog — not a mobile
// variant. The dialog is cramped on a phone but functional; building
// the graph is the one workflow power-users legitimately want
// anywhere. A dedicated mobile dialog variant is Cycle δ polish if
// usage shows friction.

const DESCRIPTION_PREVIEW_MAX = 100;

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).trimEnd() + '…';
}

function formatLastExtracted(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Map raw extraction_status to a subtle Tailwind color class. Raw
// status (5 values) is simpler than the 13-state machine desktop
// uses, and users on mobile aren't taking the actions those finer
// states gate anyway.
const STATUS_CLASS: Record<Project['extraction_status'], string> = {
  disabled: 'bg-muted text-muted-foreground',
  building: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
  paused: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  ready: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  failed: 'bg-destructive/15 text-destructive',
};

const TYPE_CLASS = 'bg-secondary text-secondary-foreground';

export function ProjectsMobile() {
  const { t } = useTranslation('knowledge');
  const { items, isLoading, isError, error, refetch } = useProjects(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [buildProject, setBuildProject] = useState<Project | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="mobile-projects-loading">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive"
        data-testid="mobile-projects-error"
      >
        {t('mobile.projects.loadFailed', {
          error: error instanceof Error ? error.message : 'unknown error',
        })}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <p
        className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
        data-testid="mobile-projects-empty"
      >
        {t('mobile.projects.empty')}
      </p>
    );
  }

  return (
    <>
      <ul className="space-y-2" data-testid="mobile-projects-list">
        {items.map((project) => {
          const isExpanded = expandedId === project.project_id;
          const canBuild =
            project.extraction_status !== 'building' &&
            !!project.embedding_model;
          return (
            <li key={project.project_id}>
              <div
                className={cn(
                  'rounded-lg border bg-card',
                  isExpanded && 'ring-1 ring-primary/30',
                )}
                data-testid="mobile-project-card"
                data-project-id={project.project_id}
              >
                <button
                  type="button"
                  onClick={() =>
                    setExpandedId(isExpanded ? null : project.project_id)
                  }
                  aria-expanded={isExpanded ? 'true' : 'false'}
                  className={cn(
                    TOUCH_TARGET_CLASS,
                    'flex w-full items-start gap-3 px-3 py-3 text-left',
                  )}
                  data-testid="mobile-project-toggle"
                >
                  <span className="pt-0.5 text-muted-foreground">
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className="block truncate font-serif text-sm font-semibold"
                      title={project.name}
                    >
                      {project.name}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                      <span
                        className={cn(
                          'rounded px-1.5 py-0.5 uppercase tracking-wide',
                          TYPE_CLASS,
                        )}
                      >
                        {project.project_type}
                      </span>
                      <span
                        className={cn(
                          'rounded px-1.5 py-0.5 uppercase tracking-wide',
                          STATUS_CLASS[project.extraction_status],
                        )}
                      >
                        {t(
                          `mobile.projects.status.${project.extraction_status}`,
                        )}
                      </span>
                    </span>
                    {!isExpanded && project.description && (
                      <span className="mt-1.5 block text-[12px] text-muted-foreground">
                        {truncate(project.description, DESCRIPTION_PREVIEW_MAX)}
                      </span>
                    )}
                  </span>
                </button>

                {isExpanded && (
                  <div
                    className="border-t px-3 py-3 text-[12px]"
                    data-testid="mobile-project-detail"
                  >
                    {project.description ? (
                      <p className="mb-2 whitespace-pre-wrap text-foreground">
                        {project.description}
                      </p>
                    ) : (
                      <p className="mb-2 italic text-muted-foreground">
                        {t('mobile.projects.noDescription')}
                      </p>
                    )}
                    <dl className="grid grid-cols-[110px_1fr] gap-y-1 gap-x-2 text-[11px]">
                      <dt className="text-muted-foreground">
                        {t('mobile.projects.detail.lastExtracted')}
                      </dt>
                      <dd>{formatLastExtracted(project.last_extracted_at)}</dd>
                      <dt className="text-muted-foreground">
                        {t('mobile.projects.detail.embeddingModel')}
                      </dt>
                      <dd>
                        {project.embedding_model ??
                          t('mobile.projects.detail.noEmbedding')}
                      </dd>
                    </dl>
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          setBuildProject(project);
                        }}
                        disabled={!canBuild}
                        className={cn(
                          TOUCH_TARGET_CLASS,
                          'inline-flex items-center gap-1.5 rounded-md border border-primary/40 px-3 text-[12px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50',
                        )}
                        data-testid="mobile-project-build"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        {t('mobile.projects.build')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {buildProject && (
        <BuildGraphDialog
          open={!!buildProject}
          onOpenChange={(o) => {
            if (!o) setBuildProject(null);
          }}
          project={buildProject}
          onStarted={() => {
            setBuildProject(null);
            // Refetch so the status badge flips to "building".
            void refetch();
          }}
        />
      )}
    </>
  );
}
