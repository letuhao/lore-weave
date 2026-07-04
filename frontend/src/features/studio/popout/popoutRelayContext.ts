// #16 2.8 — cross-window Apply relay for Studio's popped-out Compose panel.
//
// Studio's Compose is Chat-based (ComposePanel renders <Chat>, not CompositionPanel), and
// ProposeEditCard's Apply path normally reaches the opener's Tiptap editor through the
// module-singleton editorBridge (features/chat/context/editorBridge.ts). A popout is a
// SEPARATE React root / JS realm — that singleton only exists in the window that registered
// it (the main Studio window's EditorPanel), so getEditorTarget() inside a popout always
// returns null. This context is the escape hatch: StudioPopoutHost provides a `post` function
// that relays the proposed text over the per-(book,chapter) BroadcastChannel
// (features/composition/workspace/popoutChannel.ts) instead of writing locally.
// ProposeEditCard checks this context ONLY when getEditorTarget() is null — every existing
// surface (ChapterEditorPage's chat dock, Studio's docked ComposePanel) never provides it, so
// this is strictly additive.
import { createContext } from 'react';

export interface PopoutRelay {
  /** Relay accepted/applied prose to the opener for insertion at the cursor. `model` is
   *  best-effort provenance (undefined when not resolvable client-side, e.g. from a
   *  ProposeEditCard Apply, which has no model info). Resolves `true` only once the opener
   *  acks the insert; resolves `false` on an explicit rejection or if no ack arrives within
   *  the timeout (#16 2.8 /review-impl HIGH fix — the opener may have navigated to a
   *  different chapter and silently dropped the message; a bare fire-and-forget `post()`
   *  can't distinguish that from success). */
  post: (text: string, model?: string) => Promise<boolean>;
}

export const PopoutRelayContext = createContext<PopoutRelay | null>(null);
