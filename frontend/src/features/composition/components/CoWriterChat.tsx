// LOOM Composition (T3.1) — AI co-writer chat: a book-memory-grounded brainstorm
// partner. Reuses the chat feature's embeddable <Chat> (streaming + the book-memory
// binding + degrade warning) and adds the Insert/Use-as-guide bridge via the action
// slot. Embedded with bookId (RAG memory) + composeMode (prose-only, no tools) and
// NO editorContext — the assistant brainstorms; the author Inserts manually.
import { Chat } from '../../chat/Chat';
import { CoWriterActions } from './CoWriterActions';

export function CoWriterChat({
  bookId, onAccept, onUseAsGuide, windowingEnabled, forceShared,
}: {
  bookId: string;
  onAccept: (text: string) => void;
  onUseAsGuide: (text: string) => void;
  // M2 (D-T5.4-CHAT-HOIST): forwarded from CompositionPanel so the chat turn runs
  // in the SharedWorker when the panel can float/pop-out (opener: windowingEnabled;
  // pop-out: forceShared) — so a popped cowriter chat keeps streaming.
  windowingEnabled?: boolean;
  forceShared?: boolean;
}) {
  return (
    <Chat
      bookId={bookId}
      composeMode
      className="h-full"
      actionBar={<CoWriterActions onInsert={onAccept} onUseAsGuide={onUseAsGuide} />}
      windowingEnabled={windowingEnabled}
      forceShared={forceShared}
    />
  );
}
