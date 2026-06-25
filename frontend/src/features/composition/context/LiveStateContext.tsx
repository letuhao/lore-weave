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
//
// T5.4 M4 Slice B: when windowing is on (or we're inside a pop-out) AND the browser has
// SharedWorker, the stream is owned by the SharedWorker (one stream shared across all
// windows, survives the opener closing). Otherwise — the default for every non-windowing
// user — the in-process hook runs, byte-identical to pre-Slice-B. Both hooks are called
// every render (rules-of-hooks); only the selected one is wired into the context, and
// only the worker hook actually connects a worker (and only when enabled).
import { createContext, useContext, type ReactNode } from 'react';
import { useCompositionStream } from '../hooks/useCompositionStream';
import { useSharedCompositionStream } from '../hooks/useSharedCompositionStream';
import { useWorkspaceLayoutOptional } from './WorkspaceLayoutContext';

type LiveState = {
  stream: ReturnType<typeof useCompositionStream>;
};

const LiveStateCtx = createContext<LiveState | null>(null);

export function LiveStateProvider({ token, children, forceShared }: { token: string | null; children: ReactNode; forceShared?: boolean }) {
  // Engage the SharedWorker when windowing is on (opener: the flag; pop-out: forceShared,
  // since the pop-out has no layout provider) AND SharedWorker exists.
  const ws = useWorkspaceLayoutOptional();
  const wantShared = (forceShared ?? false) || !!ws?.enabled;
  const useWorker = wantShared && typeof SharedWorker !== 'undefined';

  const inProcess = useCompositionStream(token);
  const shared = useSharedCompositionStream(token, useWorker);
  const stream = useWorker ? shared : inProcess;

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
