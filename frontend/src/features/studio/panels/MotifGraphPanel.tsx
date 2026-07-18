// Wave-4 (D-MOTIF-GRAPH-CANVAS) — the `motif-graph` dock panel (category storyBible). A book-wide
// visual DAG of the caller's + book-shared motifs and their composed_of/precedes/variant_of edges,
// with PER-VIEWER persisted node positions. Unlike the per-motif graph SECTION (which is motif_id-
// scoped and stays a section), a book-wide graph is book-scoped (host.bookId) so it CAN be a first-
// class palette-openable panel. Thin wrapper: real identity from useAuth, bookId from the host.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { MotifGraphCanvas } from '@/features/composition/motif/components/MotifGraphCanvas';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function MotifGraphPanel(props: IDockviewPanelProps) {
  useStudioPanel('motif-graph', props.api);
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const bookId = host.bookId ?? null;

  if (!accessToken) {
    return (
      <div data-testid="studio-motif-graph-panel" className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('panels.motif-graph.signedOut', { defaultValue: 'Sign in to see the motif graph.' })}
      </div>
    );
  }
  if (!bookId) {
    return (
      <div data-testid="studio-motif-graph-panel" className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('panels.motif-graph.noBook', { defaultValue: 'Open a book to see its motif graph.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-motif-graph-panel" className="h-full min-h-0">
      <MotifGraphCanvas bookId={bookId} token={accessToken} />
    </div>
  );
}
