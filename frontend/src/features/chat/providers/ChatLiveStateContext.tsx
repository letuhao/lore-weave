// L-chat (T5.4 M2 / D-T5.4-CHAT-HOIST) — the chat live-stream owner (hoist).
//
// Mirrors composition's LiveStateContext. The cowriter chat SSE turn — owned
// INSIDE useChatMessages today — would be killed by a pop-out remount. So when
// chat windowing is on (or we're inside a pop-out) AND the browser has
// SharedWorker, the turn is owned by the SharedWorker (one turn shared across all
// windows, survives the opener closing). Otherwise — the default for every
// non-windowing user — useChatMessages keeps the in-process stream, byte-identical
// to pre-M2.
//
// There is NO chat windowing layer yet (M2 introduces the selector; a later
// milestone mounts the windowing host above this provider). So `windowingEnabled`
// defaults false → this provider is an inert pass-through and chat behaves exactly
// as before. When a future host flips the flag, the provider engages the worker
// hook and ChatStreamContext consumes the snapshot instead of owning the stream.
//
// Both hooks are referenced every render (rules-of-hooks) via the selector below;
// only the selected one is exposed, and only the worker hook actually connects a
// worker (and only when enabled).
import { createContext, useContext, type ReactNode } from 'react';
import { useSharedChatStream } from '../hooks/useSharedChatStream';

type SharedStream = ReturnType<typeof useSharedChatStream>;

type ChatLiveState = {
  /** True when the SharedWorker owns the turn (windowing on + worker present). */
  useWorker: boolean;
  /** The worker-backed stream snapshot + commands. Only meaningful when
   *  `useWorker`; an inert EMPTY-mirroring instance otherwise. */
  shared: SharedStream;
};

const ChatLiveStateCtx = createContext<ChatLiveState | null>(null);

export function ChatLiveStateProvider({
  token,
  children,
  windowingEnabled,
  forceShared,
}: {
  token: string | null;
  children: ReactNode;
  /** Opener: chat windowing is on. (No host sets this yet → default false.) */
  windowingEnabled?: boolean;
  /** Pop-out: force the worker path (a pop-out has no windowing host of its own). */
  forceShared?: boolean;
}) {
  const wantShared = (forceShared ?? false) || (windowingEnabled ?? false);
  const useWorker = wantShared && typeof SharedWorker !== 'undefined';

  // Called unconditionally (rules-of-hooks); only connects a worker when enabled.
  const shared = useSharedChatStream(token, useWorker);

  return (
    <ChatLiveStateCtx.Provider value={{ useWorker, shared }}>
      {children}
    </ChatLiveStateCtx.Provider>
  );
}

/** Optional read — returns null outside a provider (the default: no provider
 *  mounted → useChatMessages owns the in-process stream, unchanged). A consumer
 *  uses `useWorker` to decide whether to mirror the worker snapshot or keep its
 *  own stream. */
export function useChatLiveStateOptional(): ChatLiveState | null {
  return useContext(ChatLiveStateCtx);
}
