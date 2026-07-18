// S4 · 3a — the `motif-library` dock panel (category storyBible). The narrative-craft
// hub (套路/爽点/打脸): browse/create/adopt/mine motifs, inspect the detail drawer, and
// (3a) read the motif GRAPH. Was reachable ONLY inside the legacy ChapterEditorPage's
// Compose-mode sub-tab (spec 33: "built, tested, and unreachable"); this promotes it to a
// registered Studio panel that opens unconditionally from the palette.
//
// Detail is a DRAWER, create an inline FORM, adopt a MODAL, the graph a SECTION — none is
// a panel (plan 30 X-12: ui_open_studio_panel carries a bare id, so a motif_id-scoped panel
// would fall out of the palette). This wrapper stays thin: it mounts the SimpleMode provider
// (the §2.4 trap — the toggle silently no-ops outside it) and passes the real identity from
// useAuth (not the localStorage shim), then reuses MotifLibraryView with the arc toggle hidden.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { MotifLibraryView } from '@/features/composition/motif/components/MotifLibraryView';
import { MotifSimpleModeProvider } from '@/features/composition/motif/context/MotifSimpleModeContext';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function MotifLibraryPanel(props: IDockviewPanelProps) {
  useStudioPanel('motif-library', props.api);
  const { t } = useTranslation('studio');
  const { accessToken, user } = useAuth();
  const host = useStudioHost();
  const bookId = host.bookId ?? null;

  if (!accessToken) {
    return (
      <div data-testid="studio-motif-library-panel" className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('panels.motif-library.signedOut', { defaultValue: 'Sign in to browse your motif library.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-motif-library-panel" className="h-full min-h-0">
      <MotifSimpleModeProvider token={accessToken}>
        <MotifLibraryView
          token={accessToken}
          meUserId={user?.user_id ?? null}
          bookId={bookId}
          hideArcTabs
        />
      </MotifSimpleModeProvider>
    </div>
  );
}
