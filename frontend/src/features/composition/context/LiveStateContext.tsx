// LOOM Composition (T5.4 M1) — the live-state owner (AH-2 hoist).
//
// The co-writer SSE stream (useCompositionStream: ghost/streaming/jobId + the
// AbortController + fetch/ReadableStream) was owned INSIDE ComposeView. Windowing
// (T5.4) moves a panel's host node — which would REMOUNT ComposeView and kill an
// in-flight generation. So the stream is hoisted here, ABOVE the windowing layer:
// the provider owns ONE stream instance and ComposeView (docked, floated, or
// popped) is a thin consumer via useLiveStream(). The provider is mounted by
// WorkspaceShell, which sits above the dock/float/pop-out hosts — so a placement
// change re-parents the consumer without disturbing the stream.
//
// M1 hoists the co-writer stream only (the headline live state). The chat SSE +
// Tiptap follow in later milestones via this same provider.
import { createContext, useContext, type ReactNode } from 'react';
import { useCompositionStream } from '../hooks/useCompositionStream';

type LiveState = {
  stream: ReturnType<typeof useCompositionStream>;
};

const LiveStateCtx = createContext<LiveState | null>(null);

export function LiveStateProvider({ token, children }: { token: string | null; children: ReactNode }) {
  // ONE co-writer stream for the whole studio, owned here (above any window host).
  const stream = useCompositionStream(token);
  return <LiveStateCtx.Provider value={{ stream }}>{children}</LiveStateCtx.Provider>;
}

/** The hoisted co-writer stream. Throws if used outside LiveStateProvider so a
 *  panel can't silently spin up its own (un-hoisted) stream that dies on a move. */
export function useLiveStream(): ReturnType<typeof useCompositionStream> {
  const ctx = useContext(LiveStateCtx);
  if (ctx === null) {
    throw new Error('useLiveStream must be used within a LiveStateProvider');
  }
  return ctx.stream;
}
