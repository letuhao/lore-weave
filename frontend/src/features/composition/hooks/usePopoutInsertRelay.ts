// LOOM Composition (T5.4 M4) — opener-side receiver for prose accepted in a pop-out.
//
// A popped-out Compose/co-writer panel has no editor of its own, so it relays accepted
// prose over the per-book BroadcastChannel. The opener (ChapterEditorPage) owns the
// Tiptap editor; this hook subscribes once per book and forwards each relayed insert to
// the caller, which writes it at the cursor — closing the loop "write on monitor 2,
// insert on monitor 1". No-op where BroadcastChannel is unavailable.
import { useEffect, useRef } from 'react';
import { openPopoutChannel } from '../workspace/popoutChannel';

export function usePopoutInsertRelay(bookId: string, chapterId: string, onInsert: (text: string, model?: string) => void) {
  // Latest handler without re-subscribing the channel on every render.
  const cb = useRef(onInsert);
  cb.current = onInsert;

  useEffect(() => {
    if (!bookId || !chapterId) return;
    // Per-(book, chapter) so a popout never inserts into a DIFFERENT chapter open in
    // another tab of the same book (/review-impl MED).
    const ch = openPopoutChannel(bookId, chapterId);
    const unsub = ch.subscribe((msg) => {
      if (msg.kind === 'insert-prose') cb.current(msg.text, msg.model);
    });
    return () => { unsub(); ch.close(); };
  }, [bookId, chapterId]);
}
