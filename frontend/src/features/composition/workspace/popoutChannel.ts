// LOOM Composition (T5.4 M4) — the cross-window message channel (opener <-> popouts).
//
// A popped-out panel runs in a SEPARATE OS window with its OWN React root (so its
// buttons/inputs actually work — React synthetic events don't cross a window). State
// the two windows must agree on travels over a BroadcastChannel keyed by bookId:
//   • insert-prose — a popped Compose/co-writer accepted prose; the OPENER owns the
//     Tiptap editor, so the popout relays the text for the opener to insert at cursor.
//   • dock-back    — a popout asked to re-dock (its window also closes; the opener's
//     PopoutBridge close-poll is the backstop, this is just the fast path).
// Slice B adds live-stream fan-out here (or via a SharedWorker); the channel is the
// seam both slices share.
import type { ChapterGeneration } from '../types';
import type { WorkspacePanelId } from './types';

/** WS-D (D-T5.4-PANEL-STREAM-HOIST) — the at-risk Assemble-tab draft that a pop-out
 *  (a separate React root) would otherwise lose: the generated result + the human's
 *  in-progress edits + which mode produced it. Synced across windows over the channel. */
export type AssembleSnapshot = {
  result: ChapterGeneration | null;
  edited: string;
  last: 'chapter' | 'stitch';
};

export type PopoutMessage =
  // #16 2.8 /review-impl HIGH fix — `reqId` is OPTIONAL so legacy senders (PopoutHost's
  // generate-and-accept flow) are unaffected. A sender that DOES set `reqId` (Studio's
  // human-gated ProposeEditCard Apply) can await a matching `insert-ack` to know whether the
  // opener actually applied it, instead of assuming success once the message left the window.
  // Without this, an opener that has since navigated to a different chapter unsubscribes from
  // this channel (usePopoutInsertRelay re-keys on chapterId) — the message vanishes silently
  // and the popout's "Applied ✓" was a false positive (the LLM and the user were both lied to).
  | { kind: 'insert-prose'; text: string; model?: string; reqId?: string }
  | { kind: 'insert-ack'; reqId: string; ok: boolean }
  | { kind: 'dock-back'; panel: WorkspacePanelId }
  // WS-D: the Assemble draft sync. `assemble-request` asks the other window(s) for the
  // current draft (a fresh pop-out hydrates from the opener); `assemble-state` carries it.
  | { kind: 'assemble-request' }
  | { kind: 'assemble-state'; state: AssembleSnapshot };

const PREFIX = 'loom.workspace.popout';

/** The channel is per-(book, chapter): a popout belongs to one chapter, and scoping by
 *  book alone would let a popout's relayed prose insert into a DIFFERENT chapter open in
 *  another tab of the same book (cross-chapter mis-insert, /review-impl MED). */
export function popoutChannelName(bookId: string, chapterId: string): string {
  return `${PREFIX}.${bookId}.${chapterId}`;
}

export type PopoutChannel = {
  post: (msg: PopoutMessage) => void;
  /** Returns an unsubscribe fn. */
  subscribe: (handler: (msg: PopoutMessage) => void) => () => void;
  close: () => void;
};

/** Open the per-(book, chapter) channel. Degrades to a no-op channel where
 *  BroadcastChannel is unavailable (older browsers / SSR) so callers never need to
 *  feature-detect. */
export function openPopoutChannel(bookId: string, chapterId: string): PopoutChannel {
  if (typeof BroadcastChannel === 'undefined') {
    return { post: () => {}, subscribe: () => () => {}, close: () => {} };
  }
  const bc = new BroadcastChannel(popoutChannelName(bookId, chapterId));
  return {
    post: (msg) => bc.postMessage(msg),
    subscribe: (handler) => {
      const listener = (e: MessageEvent) => handler(e.data as PopoutMessage);
      bc.addEventListener('message', listener);
      return () => bc.removeEventListener('message', listener);
    },
    close: () => bc.close(),
  };
}
