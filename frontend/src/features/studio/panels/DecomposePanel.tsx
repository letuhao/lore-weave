// S-13 (G-STORY-STRUCTURE) — the studio decompose panel. Closes the D-S01-USE-IN-DECOMPOSE loop:
// a user authors a story structure in `structure-templates`, then decomposes their book against it
// WITHOUT leaving the studio. This is a PORT, not a re-implementation — it hosts the existing
// PlannerView/usePlanner decompose flow (template picker → premise → preview arc→chapter→scene tree
// → inline edit → commit, 409→replace). The panel only resolves project_id + handles the no-Work
// empty state + threads the deep-linked template. No new engine, route, or MCP tool.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { WorkSetupCta } from './WorkSetupCta';
import { PlannerView } from '@/features/composition/components/PlannerView';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';

const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined);

export function DecomposePanel(props: IDockviewPanelProps) {
  useStudioPanel('decompose', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const bookId = host.bookId;

  // DOCK-6 — the deep-linked template ("Use in decompose" from S-01): read at mount AND on a
  // retarget of the already-open singleton. Keying PlannerView on it re-seeds usePlanner.
  const [templateId, setTemplateId] = useState<string | undefined>(
    () => str((props.params as Record<string, unknown> | undefined)?.templateId),
  );
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) =>
      setTemplateId(str(next?.templateId)),
    );
    return () => d?.dispose?.();
  }, [props.api]);

  const work = useWorkResolution(bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(bookId, accessToken);
  const active = resolveActiveWork(work.data, activeWorkId);
  const projectId = active?.project_id ?? null;
  const modelRef = str(active?.settings?.['default_model_ref']) ?? '';

  if (work.isLoading) {
    return (
      <div data-testid="decompose-loading" className="p-4 text-xs text-muted-foreground">
        {t('panels.decompose.loading', { defaultValue: 'Resolving your book…' })}
      </div>
    );
  }

  // review-impl LOW-1 — a LOAD FAILURE is not "no Work". Don't show the setup CTA (which would tell the
  // user to create a Work when one may already exist) — surface the error + a retry.
  if (work.isError) {
    return (
      <div data-testid="decompose-error" className="p-4 text-xs text-muted-foreground">
        <p className="mb-2 text-destructive">{t('panels.decompose.loadError', { defaultValue: "Couldn't load this book's plan — try again." })}</p>
        <button type="button" data-testid="decompose-retry" onClick={() => void work.refetch()}
          className="rounded border border-border px-2.5 py-1 text-[11px] hover:bg-secondary">
          {t('panels.decompose.retry', { defaultValue: 'Retry' })}
        </button>
      </div>
    );
  }

  // ENTRY-from-empty (no Work yet) — the setup CTA, NOT a blank/blocked pane (usability gate §7).
  if (projectId == null) {
    return (
      <div className="p-3" data-testid="decompose-no-work">
        <WorkSetupCta bookId={bookId} token={accessToken} />
      </div>
    );
  }

  return (
    <div data-testid="decompose-panel" className="h-full overflow-auto p-3">
      <PlannerView
        key={templateId ?? 'none'}
        projectId={projectId}
        bookId={bookId}
        modelRef={modelRef}
        modelSource="user_model"
        token={accessToken}
        initialTemplateId={templateId}
      />
    </div>
  );
}
