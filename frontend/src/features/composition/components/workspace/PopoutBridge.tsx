// LOOM Composition (T5.4 M4) — the opener-side OS pop-out manager (view-less).
// #16 2.8 — generalized (route prop) so Studio's Compose pop-out reuses this same
// window-lifecycle implementation instead of duplicating the open/close-poll/dock-back
// logic in a second component. `route` defaults to '/composition/popout' — every
// existing composition-workspace call site is byte-identical to before.
//
// Renders NOTHING in the opener: a popped panel lives in its OWN window (the
// route above, mounted as a separate React root so its inputs work). This bridge just
// owns that window's lifecycle — it opens it once, and when the window is closed (the
// user clicks the OS close button, or the popout's "Dock" button which closes itself),
// it calls onClosed so the caller re-docks the panel. If the opener unmounts (navigates
// away / closes), it closes the popout too, so a popout never outlives its opener in
// Slice A (survive-opener-close is Slice B, D-T5.4-POPOUT-SURVIVE-CLOSE).
import { useEffect, useRef } from 'react';
import type { WorkspacePanelId } from '../../workspace/types';
import { openPopoutChannel } from '../../workspace/popoutChannel';

const POLL_MS = 500;
const DEFAULT_ROUTE = '/composition/popout';

export function PopoutBridge({ id, bookId, chapterId, sceneId, route = DEFAULT_ROUTE, onClosed }: {
  id: WorkspacePanelId;
  bookId: string;
  chapterId: string;
  sceneId?: string;
  /** #16 2.8 — which popout page to open. Defaults to the composition workspace's own
   *  route; Studio's Compose pop-out passes '/studio/popout'. */
  route?: string;
  onClosed: () => void;
}) {
  // Latest onClosed without re-running the open effect (which must fire ONCE per popout
  // — re-opening on a prop change would spawn duplicate windows).
  const onClosedRef = useRef(onClosed);
  onClosedRef.current = onClosed;

  useEffect(() => {
    // The window opens with the CURRENT scene; the popout then owns its own scene
    // selector (independent per window), so there's no live scene push-down to sync.
    const params = new URLSearchParams({ book: bookId, chapter: chapterId, panel: id });
    if (sceneId) params.set('scene', sceneId);
    // The window NAME includes the route so a composition-workspace popout and a Studio
    // popout for the same (book, chapter, panel-id) never collide into one reused window
    // (window.open re-navigates an existing same-named window instead of opening a second).
    const win = window.open(
      `${route}?${params.toString()}`,
      `loom-popout-${route.replace(/\//g, '_')}-${bookId}-${chapterId}-${id}`,
      'popup,width=560,height=680',
    );
    // Popup blocked (or unavailable) → revert to dock so the panel isn't lost.
    if (!win) { onClosedRef.current(); return; }

    // Re-dock exactly once, whether triggered by the popout's "Dock" message (instant)
    // or the close-poll backstop (≤POLL_MS after the OS window is closed).
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      window.clearInterval(timer);
      unsub();
      onClosedRef.current();
    };

    const channel = openPopoutChannel(bookId, chapterId);
    const unsub = channel.subscribe((msg) => {
      if (msg.kind === 'dock-back' && msg.panel === id) finish();
    });
    const timer = window.setInterval(() => { if (win.closed) finish(); }, POLL_MS);

    return () => {
      window.clearInterval(timer);
      unsub();
      channel.close();
      if (!win.closed) win.close();   // opener going away → take the popout with it
    };
    // Open exactly once per (panel) popout. bookId/chapterId are stable for the panel's
    // lifetime (CompositionPanel is keyed by bookId; chapter nav remounts the editor).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return null;
}
