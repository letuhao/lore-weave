import { useState } from 'react';
import { ChatSessionProvider, ChatStreamProvider, useChatSession } from './providers';
import { ChatView } from './components/ChatView';
import { NewChatDialog } from './components/NewChatDialog';
import { ChatEmptyState } from './components/ChatEmptyState';
import { useEmbeddedChatBinding } from './useEmbeddedChatBinding';

interface ChatProps {
  /** When set, the chat binds to this book's knowledge project (memory/RAG)
   *  and a book-scoped session is auto-selected or created. */
  bookId?: string;
  /** ARCH-1 C6: editor panel context — enables the write-back frontend tool
   *  (propose_edit) and carries the chapter the assistant can edit. */
  editorContext?: { book_id: string; chapter_id: string };
  /** Editor "Compose" mode — when true, turns advertise no tools (prose-only;
   *  the model drafts and the user Applies manually). Best for reasoning models. */
  composeMode?: boolean;
  className?: string;
}

/**
 * ARCH-1 C5 — the reusable chat surface.
 *
 * Wraps the chat providers + ChatView so any host (here, the editor AI panel)
 * mounts the whole feature in one place, without the chat page's sidebar/route
 * chrome. In `embedded` mode the providers don't touch the URL; the binding
 * hook owns which session is active and binds it to the book's knowledge
 * project so the assistant has the book's lore/memory.
 */
export function Chat({ bookId, editorContext, composeMode, className }: ChatProps) {
  // Glossary-assistant P3: any book-scoped chat (incl. the editor) advertises the
  // glossary edit-existing tool. The editor also passes editorContext (chapter
  // prose tool); a glossary-page/reader chat passes only bookContext.
  const bookContext = bookId ? { book_id: bookId } : undefined;
  return (
    <ChatSessionProvider embedded>
      <ChatStreamProvider editorContext={editorContext} composeMode={composeMode} bookContext={bookContext}>
        <EmbeddedChat bookId={bookId} className={className} />
      </ChatStreamProvider>
    </ChatSessionProvider>
  );
}

function EmbeddedChat({ bookId, className }: ChatProps) {
  const { sessions, sessionsLoading, activeSession, selectSession, createSession, updateActiveSession } =
    useChatSession();
  // The user can dismiss the create dialog without making a session.
  const [dialogDismissed, setDialogDismissed] = useState(false);

  const { needsNewSession } = useEmbeddedChatBinding({
    bookId,
    sessions,
    sessionsLoading,
    activeSession,
    selectSession,
    updateActiveSession,
  });

  // Derived, not stored: show the create dialog while a book-scoped session is
  // needed and none is active — until the user dismisses it. No setState in
  // render (CLAUDE.md: don't drive UI off a useEffect/render side-effect).
  const dialogOpen = needsNewSession && !activeSession && !dialogDismissed;

  return (
    <div className={`flex h-full flex-col overflow-hidden ${className ?? ''}`}>
      <ChatView className={!activeSession ? 'hidden' : 'flex-1'} />
      {!activeSession && <ChatEmptyState className="flex-1" />}
      <NewChatDialog
        open={dialogOpen}
        onClose={() => setDialogDismissed(true)}
        onCreate={(modelRef, systemPrompt) => {
          void createSession({
            model_source: 'user_model',
            model_ref: modelRef,
            title: 'Editor Chat',
            system_prompt: systemPrompt,
          });
        }}
      />
    </div>
  );
}
