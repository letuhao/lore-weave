// LOOM Composition (T5.4 M4) — the OS pop-out window's page (its own React root).
//
// Mounted at /composition/popout in a window opened by PopoutBridge. Because it's a
// SEPARATE root (a real second window), its inputs/buttons actually work — unlike a
// cross-window portal, whose React events would be dead. It reuses the app's root
// providers (QueryClient/Auth/i18n/Theme from App.tsx, same-origin) and adds the
// per-window LiveStateProvider, then renders ONE panel via CompositionPanel's solo
// mode. Accepted prose has no editor here, so it's relayed to the opener (which owns
// the Tiptap editor) over the per-book BroadcastChannel; "Dock" re-docks + closes.
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { CompositionPanel } from '../CompositionPanel';
import { LiveStateProvider } from '../../context/LiveStateContext';
import { AssembleStateProvider } from '../../context/AssembleStateContext';
import { openPopoutChannel } from '../../workspace/popoutChannel';
import { isWorkspacePanelId } from '../../workspace/types';

export function PopoutHost() {
  const { t } = useTranslation('composition');
  const { accessToken } = useAuth();
  const [params] = useSearchParams();
  const bookId = params.get('book') ?? '';
  const chapterId = params.get('chapter') ?? '';
  const sceneId = params.get('scene') ?? undefined;
  const panelParam = params.get('panel') ?? '';
  const panel = isWorkspacePanelId(panelParam) ? panelParam : null;

  // One channel for this window's lifetime (per book+chapter). useMemo so it isn't
  // reopened on every render.
  const channel = useMemo(
    () => (bookId && chapterId ? openPopoutChannel(bookId, chapterId) : null),
    [bookId, chapterId],
  );

  if (!bookId || !chapterId || !panel) {
    return <div className="p-4 text-sm text-neutral-500">{t('popout.invalid', { defaultValue: 'This pop-out link is invalid.' })}</div>;
  }

  const dockBack = () => {
    channel?.post({ kind: 'dock-back', panel });
    window.close();
  };

  return (
    <div className="flex h-screen flex-col bg-white dark:bg-neutral-950">
      <div className="flex shrink-0 items-center gap-2 border-b border-neutral-200 px-3 py-1.5 text-sm dark:border-neutral-700">
        <span className="font-medium">{t(panel, { defaultValue: panel })}</span>
        <button
          type="button"
          data-testid="popout-dock-back"
          onClick={dockBack}
          className="ml-auto rounded border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800"
        >
          ⤓ {t('dock.dock', { defaultValue: 'Dock' })}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <LiveStateProvider token={accessToken} forceShared>
          {/* WS-D: a popped Assemble panel hydrates the in-progress draft from the
              opener (and keeps it live two-way) over the same per-(book,chapter) channel. */}
          <AssembleStateProvider bookId={bookId} chapterId={chapterId}>
            <CompositionPanel
              bookId={bookId}
              chapterId={chapterId}
              token={accessToken}
              sceneId={sceneId}
              soloPanel={panel}
              // The opener owns the editor — relay accepted prose for it to insert at cursor. Return
              // true: insertion happens in the opener (out of this window's control), so the popout
              // clears its draft optimistically after relaying, same as before the boolean contract.
              onAccept={(text, meta) => { channel?.post({ kind: 'insert-prose', text, model: meta?.model }); return true; }}
            />
          </AssembleStateProvider>
        </LiveStateProvider>
      </div>
    </div>
  );
}
