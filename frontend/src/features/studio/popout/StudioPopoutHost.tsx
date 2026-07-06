// #16 2.8 — Studio's OS pop-out window for the Compose (AI co-writer chat) panel.
//
// Mounted at /studio/popout in a window opened by ComposePanel's pop-out toolbar button
// (via the shared PopoutBridge — features/composition/components/workspace/PopoutBridge.tsx,
// route='/studio/popout'). A SEPARATE React root (a real second window — its inputs/buttons
// actually work, unlike a cross-window portal whose React events would be dead). Reuses the
// app's root providers (QueryClient/Auth/i18n/Theme from App.tsx, same-origin) and renders the
// SAME <Chat> component the docked Compose panel uses — no fork, no LiveStateProvider /
// AssembleStateProvider (those are CompositionPanel-specific, irrelevant to Chat).
//
// Studio's Compose is Chat-based, not CompositionPanel — so propose_edit's Apply path can't
// reach the opener's editor via the module-singleton editorBridge (a popout is a separate JS
// realm; getEditorTarget() there is always null). PopoutRelayContext is the escape hatch:
// while this host is mounted, ProposeEditCard sees a non-null relay and posts the applied text
// over the per-(book,chapter) BroadcastChannel instead; the opener's EditorPanel relays it back
// in via usePopoutInsertRelay -> checkpoints.applyProposedEdit (see spec #16 Phase 2 write-up).
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Chat } from '@/features/chat/Chat';
import { openPopoutChannel } from '@/features/composition/workspace/popoutChannel';
import { PopoutRelayContext, type PopoutRelay } from './popoutRelayContext';

export function StudioPopoutHost() {
  const { t } = useTranslation('studio');
  const [params] = useSearchParams();
  const bookId = params.get('book') ?? '';
  const chapterId = params.get('chapter') ?? '';

  // One channel for this window's lifetime (per book+chapter). useMemo so it isn't
  // reopened on every render.
  const channel = useMemo(
    () => (bookId && chapterId ? openPopoutChannel(bookId, chapterId) : null),
    [bookId, chapterId],
  );

  // #16 2.8 /review-impl HIGH fix — wait for the opener's ack instead of assuming a bare
  // `post()` succeeded. The opener may have navigated to a different chapter since this
  // window was popped out (usePopoutInsertRelay re-keys its subscription on chapterId), in
  // which case nothing is listening on this channel anymore and the message would otherwise
  // vanish silently while ProposeEditCard still reported "Applied ✓" to the user and the LLM.
  const relay = useMemo<PopoutRelay>(() => ({
    post: (text, model) => new Promise<boolean>((resolve) => {
      if (!channel) { resolve(false); return; }
      const reqId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      let settled = false;
      const finish = (ok: boolean) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        unsub();
        resolve(ok);
      };
      const unsub = channel.subscribe((msg) => {
        if (msg.kind === 'insert-ack' && msg.reqId === reqId) finish(msg.ok);
      });
      // The opener applies synchronously once its message handler fires — 4s is generous
      // slack for the round trip, not a real processing wait.
      const timer = setTimeout(() => finish(false), 4000);
      channel.post({ kind: 'insert-prose', text, model, reqId });
    }),
  }), [channel]);

  if (!bookId || !chapterId) {
    return (
      <div className="p-4 text-sm text-neutral-500">
        {t('popout.invalid', { defaultValue: 'This pop-out link is invalid.' })}
      </div>
    );
  }

  const dockBack = () => {
    channel?.post({ kind: 'dock-back', panel: 'compose' });
    window.close();
  };

  return (
    <div className="flex h-screen flex-col bg-white dark:bg-neutral-950">
      <div className="flex shrink-0 items-center gap-2 border-b border-neutral-200 px-3 py-1.5 text-sm dark:border-neutral-700">
        <span className="font-medium">{t('panels.compose.title', { defaultValue: 'Compose' })}</span>
        <button
          type="button"
          data-testid="studio-popout-dock-back"
          onClick={dockBack}
          className="ml-auto rounded border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800"
        >
          ⤓ {t('dock.dock', { defaultValue: 'Dock' })}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <PopoutRelayContext.Provider value={relay}>
          <Chat
            bookId={bookId}
            editorContext={{ book_id: bookId, chapter_id: chapterId }}
            studioContext={{ book_id: bookId, active_chapter_id: chapterId }}
            windowingEnabled
            className="h-full"
          />
        </PopoutRelayContext.Provider>
      </div>
    </div>
  );
}
