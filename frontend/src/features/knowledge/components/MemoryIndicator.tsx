import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Trans, useTranslation } from 'react-i18next';
import { Brain, ExternalLink, Globe, Folder } from 'lucide-react';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { knowledgeApi } from '../api';

// K8.4: chat header memory-mode indicator + popover.
//
// Track 1 derives the mode client-side from `session.project_id`:
//   null      → Mode 1 (no_project) — global bio only
//   non-null  → Mode 2 (static)     — project memory injected
//
// Degraded state (knowledge-service down) isn't surfaced because
// chat-service calls knowledge server-side and doesn't echo the
// build_context response back to the frontend. Tracked as
// D-K8-04 — add `memory_mode` to the chat-service session/stream
// metadata so the FE can show a "degraded" badge.

interface Props {
  projectId: string | null;
}

export function MemoryIndicator({ projectId }: Props) {
  const { t } = useTranslation('memory');
  const [open, setOpen] = useState(false);
  const { accessToken } = useAuth();

  // Fetch the project name whenever one is linked. The button label
  // is the whole point of the indicator — gating this on `open` would
  // mean every session with memory shows the literal "Project"
  // fallback until the user clicks. Sessions without memory skip the
  // request entirely via the `!!projectId` guard, so this only costs
  // one cached GET per project (60s staleTime) on chat mount.
  const projectQuery = useQuery({
    queryKey: ['knowledge-project', projectId] as const,
    queryFn: () => knowledgeApi.getProject(projectId!, accessToken!),
    enabled: !!projectId && !!accessToken,
    staleTime: 60_000,
  });

  const isProject = projectId !== null;
  const label = isProject
    ? projectQuery.data?.name ?? t('indicator.modes.project')
    : t('indicator.modes.global');

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={t('indicator.title')}
        aria-label={t('indicator.label')}
        aria-expanded={open ? 'true' : 'false'}
        className={cn(
          'flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors',
          isProject
            ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/15'
            : 'border-border bg-secondary/40 text-muted-foreground hover:bg-secondary',
        )}
      >
        <Brain className="h-3 w-3" />
        <span className="max-w-[120px] truncate">{label}</span>
      </button>

      {open && (
        <>
          {/* Backdrop — matches NotificationBell pattern. Clicking
              anywhere outside the panel dismisses it. */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-[calc(100%+4px)] z-50 w-72 rounded-lg border bg-popover p-3 shadow-xl">
            <div className="mb-2 flex items-center gap-2">
              {isProject ? (
                <Folder className="h-3.5 w-3.5 text-primary" />
              ) : (
                <Globe className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <span className="font-serif text-xs font-semibold">
                {isProject ? t('indicator.popover.projectHeading') : t('indicator.popover.globalHeading')}
              </span>
            </div>

            <p className="mb-3 text-[11px] leading-relaxed text-muted-foreground">
              {isProject ? (
                <Trans
                  i18nKey="indicator.popover.projectBody"
                  ns="memory"
                  values={{
                    name: projectQuery.isLoading
                      ? t('indicator.popover.loading')
                      : projectQuery.data?.name ?? t('indicator.popover.fallbackProject'),
                  }}
                  components={{ strong: <span className="font-medium text-foreground" /> }}
                />
              ) : (
                t('indicator.popover.globalBody')
              )}
            </p>

            <Link
              to="/memory"
              onClick={() => setOpen(false)}
              className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <span>{t('indicator.popover.manage')}</span>
              <ExternalLink className="h-3 w-3" />
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
