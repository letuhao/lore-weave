import { useState } from 'react';
import { useAuth } from '@/auth';
import { ChatSessionProvider, ChatStreamProvider, ChatLiveStateProvider, useChatSession } from './providers';
import { ChatView } from './components/ChatView';
import { NewChatDialog } from './components/NewChatDialog';
import { ChatEmptyState } from './components/ChatEmptyState';
import { SessionSwitcher } from './components/SessionSwitcher';
import { useEmbeddedChatBinding } from './useEmbeddedChatBinding';
import { useGlossaryDisplayLanguage } from '@/features/glossary/hooks/useGlossaryDisplayLanguage';

interface ChatProps {
  /** When set, the chat binds to this book's knowledge project (memory/RAG)
   *  and a book-scoped session is auto-selected or created. */
  bookId?: string;
  /** ARCH-1 C6: editor panel context — enables the write-back frontend tool
   *  (propose_edit) and carries the chapter the assistant can edit. */
  editorContext?: { book_id: string; chapter_id: string };
  /** #09 Lane A: present in the Writing Studio compose panel — enables the studio
   *  dock-nav frontend tools (ui_open_studio_panel / ui_focus_manuscript_unit). */
  studioContext?: { book_id?: string; project_id?: string; active_chapter_id?: string; active_panel_ids?: string[]; context_revision?: number };
  /** Editor "Compose" mode — when true, turns advertise no tools (prose-only;
   *  the model drafts and the user Applies manually). Best for reasoning models. */
  composeMode?: boolean;
  /** T3.1: host-supplied slot rendered inside the chat (between messages + input).
   *  The co-writer panel passes its Insert/Use-as-guide bar + starters here so it
   *  can read the live chat stream via useChatStream/useChatSession. */
  actionBar?: React.ReactNode;
  /** M2 (D-T5.4-CHAT-HOIST): opener — chat windowing is on, so the turn must run in
   *  the SharedWorker (a panel float/pop-out would otherwise kill it). The composition
   *  host sets this from its windowing flag; off everywhere else → in-process, unchanged. */
  windowingEnabled?: boolean;
  /** M2 (D-T5.4-CHAT-HOIST): pop-out — force the worker path (a pop-out window has no
   *  windowing host of its own, but must share the opener's in-flight turn). */
  forceShared?: boolean;
  /** T-4 / WS-1.10: when 'assistant', a session auto-created here is stamped
   *  session_kind='assistant' (the discriminator recall + capture gate on). Omit
   *  everywhere else → the server defaults to 'chat'. */
  sessionKind?: 'chat' | 'assistant';
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
export function Chat({ bookId, editorContext, studioContext, composeMode, actionBar, windowingEnabled, forceShared, sessionKind, className }: ChatProps) {
  // Glossary-assistant P3: any book-scoped chat (incl. the editor) advertises the
  // glossary edit-existing tool. The editor also passes editorContext (chapter
  // prose tool); a glossary-page/reader chat passes only bookContext.
  const bookContext = bookId ? { book_id: bookId } : undefined;
  // S6: the user's per-book display language (set only when viewing a translation).
  // Forwarded so knowledge composes entity aliases in it for the chat context.
  const { apiDisplayLanguage } = useGlossaryDisplayLanguage(bookId ?? '');
  const { accessToken } = useAuth();
  return (
    <ChatSessionProvider embedded>
      {/* M2 (D-T5.4-CHAT-HOIST): mount ABOVE ChatStreamProvider — the future chat
          windowing host sits between them. windowingEnabled defaults false, so
          this is an inert pass-through today (useChatMessages owns the in-process
          stream, byte-identical to pre-M2). When a host flips windowing on, the
          turn moves into the SharedWorker and survives pop-out. */}
      <ChatLiveStateProvider token={accessToken ?? null} windowingEnabled={windowingEnabled} forceShared={forceShared}>
        <ChatStreamProvider
          editorContext={editorContext}
          studioContext={studioContext}
          composeMode={composeMode}
          bookContext={bookContext}
          displayLanguage={apiDisplayLanguage}
        >
          <EmbeddedChat bookId={bookId} actionBar={actionBar} className={className} composeMode={composeMode} sessionKind={sessionKind} />
        </ChatStreamProvider>
      </ChatLiveStateProvider>
    </ChatSessionProvider>
  );
}

function EmbeddedChat({ bookId, actionBar, className, composeMode, sessionKind }: ChatProps) {
  const {
    sessions,
    sessionsLoading,
    activeSession,
    selectSession,
    createSession,
    updateActiveSession,
    showNewDialog,
    setShowNewDialog,
  } = useChatSession();
  // The user can dismiss the create dialog without making a session.
  const [dialogDismissed, setDialogDismissed] = useState(false);

  const { projectId, needsNewSession } = useEmbeddedChatBinding({
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
  // The session switcher's "New chat" (showNewDialog) opens it on demand too,
  // even when a session is already active (bug #17).
  const dialogOpen = (needsNewSession && !activeSession && !dialogDismissed) || showNewDialog;

  return (
    <div className={`flex h-full flex-col overflow-hidden ${className ?? ''}`}>
      <ChatView
        className={!activeSession ? 'hidden' : 'flex-1'}
        composeMode={composeMode}
        footerSlot={actionBar}
        headerSlot={<SessionSwitcher scopeProjectId={projectId} />}
      />
      {!activeSession && <ChatEmptyState className="flex-1" />}
      <NewChatDialog
        open={dialogOpen}
        onClose={() => {
          setDialogDismissed(true);
          setShowNewDialog(false);
        }}
        onCreate={(modelRef, systemPrompt) => {
          void createSession({
            model_source: 'user_model',
            model_ref: modelRef,
            title: sessionKind === 'assistant' ? 'Work Assistant' : 'New Chat',
            system_prompt: systemPrompt,
            // D-COMPOSE-SESSION-RESTORE: tag at creation so this book's next
            // Compose open can find it again (JSON.stringify drops `undefined`
            // when there's no bookId — e.g. a non-book embedded host).
            book_id: bookId,
            // T-4 / WS-1.10: stamp the assistant discriminator so recall + capture
            // gate on it (undefined for a normal chat → server defaults to 'chat').
            session_kind: sessionKind,
          });
        }}
      />
    </div>
  );
}
