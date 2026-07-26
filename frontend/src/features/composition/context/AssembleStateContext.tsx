// LOOM Composition (T5.4 / WS-D — D-T5.4-PANEL-STREAM-HOIST) — the cross-window
// owner of the Assemble-tab draft.
//
// The Assemble tab's at-risk state ({result, edited, last}) lived in ChapterAssembleView
// (local useState). Float re-parents the panel (state survives), but a POP-OUT mounts a
// FRESH React root in a separate OS window — so the un-accepted draft + edits were lost.
// React context can't cross a window; this provider syncs the draft over the per-(book,
// chapter) BroadcastChannel (the same seam the prose-relay uses):
//   • on mount it posts `assemble-request` → whoever holds a draft replies `assemble-state`
//     (a fresh pop-out hydrates from the opener);
//   • every local change broadcasts `assemble-state` (echo-guarded so a hydrate doesn't
//     bounce back → no broadcast loop);
//   • a change that ORIGINATED from the channel is applied without re-broadcasting.
// Mounted in BOTH roots (WorkspaceShell + PopoutHost). ChapterAssembleView consumes it
// via the OPTIONAL hook and falls back to local state when no provider is present
// (bare unit mounts) — mirroring useLiveStreamOptional / useCriticStateOptional.
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { openPopoutChannel, type AssembleSnapshot, type PopoutChannel } from '../workspace/popoutChannel';
import type { ChapterGeneration } from '../types';

export type AssembleState = {
  result: ChapterGeneration | null;
  edited: string;
  last: 'chapter' | 'stitch';
  setResult: (r: ChapterGeneration | null) => void;
  setEdited: (s: string) => void;
  setLast: (l: 'chapter' | 'stitch') => void;
};

const Ctx = createContext<AssembleState | null>(null);

// Debounce the broadcast so per-keystroke `edited` changes coalesce into ONE
// cross-window post (a postMessage of the whole draft on every keystroke would be a
// write-storm + structured-clone churn).
const BROADCAST_DEBOUNCE_MS = 250;

export function AssembleStateProvider({
  bookId, chapterId, children,
}: { bookId: string; chapterId?: string; children: ReactNode }) {
  const [result, setResult] = useState<ChapterGeneration | null>(null);
  const [edited, setEdited] = useState('');
  const [last, setLast] = useState<'chapter' | 'stitch'>('chapter');

  const channelRef = useRef<PopoutChannel | null>(null);
  // The last snapshot (serialized) the channel KNOWS — set both when we send and when
  // we receive. A change whose serialization equals this is an echo (received) or a
  // no-op (already sent) → don't re-broadcast. Value-compare is batching-independent
  // (a boolean "from channel" flag breaks if the 3 setStates don't batch into 1 effect).
  const lastChannelRef = useRef<string>('');
  const firstRef = useRef(true);            // skip the initial empty-state broadcast (mount)
  const bcastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Latest snapshot for the request-reply (read without re-subscribing).
  const snapRef = useRef<AssembleSnapshot>({ result, edited, last });
  snapRef.current = { result, edited, last };

  useEffect(() => {
    if (!bookId || !chapterId || typeof BroadcastChannel === 'undefined') return;
    const ch = openPopoutChannel(bookId, chapterId);
    channelRef.current = ch;
    const unsub = ch.subscribe((m) => {
      if (m.kind === 'assemble-request') {
        // Reply only if we actually hold a draft (avoid an empty window clobbering a full one).
        const s = snapRef.current;
        if (s.result || s.edited) ch.post({ kind: 'assemble-state', state: s });
      } else if (m.kind === 'assemble-state') {
        // Mark this value as channel-known BEFORE applying, so the resulting broadcast
        // effect recognises it as an echo and skips re-emitting it (→ no loop).
        lastChannelRef.current = JSON.stringify(m.state);
        setResult(m.state.result);
        setEdited(m.state.edited);
        setLast(m.state.last);
      }
    });
    ch.post({ kind: 'assemble-request' });   // ask the opener (or any peer) for the current draft
    return () => {
      // Flush a pending debounced broadcast BEFORE closing — else edits made in the
      // last <250ms before the window/panel closes (e.g. a pop-out dock-back) would be
      // dropped on unmount and never reach the opener.
      if (bcastTimer.current) clearTimeout(bcastTimer.current);
      const s = snapRef.current;
      if (JSON.stringify(s) !== lastChannelRef.current) {
        try { ch.post({ kind: 'assemble-state', state: s }); } catch { /* channel already gone */ }
      }
      unsub(); ch.close(); channelRef.current = null;
      firstRef.current = true;
    };
  }, [bookId, chapterId]);

  // Broadcast a local change (debounced), EXCEPT the initial mount and any value the
  // channel already knows (echo from a receive, or unchanged from our last send).
  useEffect(() => {
    if (firstRef.current) { firstRef.current = false; return; }
    const snap: AssembleSnapshot = { result, edited, last };
    const json = JSON.stringify(snap);
    if (json === lastChannelRef.current) return;   // echo / no-op vs the channel-known value
    if (bcastTimer.current) clearTimeout(bcastTimer.current);
    bcastTimer.current = setTimeout(() => {
      lastChannelRef.current = json;
      channelRef.current?.post({ kind: 'assemble-state', state: snap });
    }, BROADCAST_DEBOUNCE_MS);
  }, [result, edited, last]);

  const value = useMemo<AssembleState>(
    () => ({ result, edited, last, setResult, setEdited, setLast }),
    [result, edited, last],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Optional, non-throwing read — returns null outside a provider so ChapterAssembleView
 *  can fall back to local state in a bare mount (unit tests / non-windowing). */
export function useAssembleStateOptional(): AssembleState | null {
  return useContext(Ctx);
}
