// Interview-practice page (M7). The persona picker is the entry; once started it
// REUSES the chat feature's ChatView (text + voice, no fork) for the turn loop,
// and adds a scorecard overlay on "End & evaluate". The chat providers are
// driven in embedded mode — the host injects the active session via
// selectSession() (see ChatSessionContext).

import { useCallback } from 'react';
import { ChatSessionProvider, ChatStreamProvider, useChatSession } from '@/features/chat/providers';
import { ChatView } from '@/features/chat/components/ChatView';
import { useInterviewSetup } from '../hooks/useInterviewSetup';
import { useEvaluation } from '../hooks/useEvaluation';
import { PersonaPicker } from '../components/PersonaPicker';
import { EndEvaluateBar } from '../components/EndEvaluateBar';
import { ScorecardView } from '../components/ScorecardView';

export function InterviewPage() {
  return (
    <ChatSessionProvider embedded>
      <ChatStreamProvider>
        <InterviewRoom />
      </ChatStreamProvider>
    </ChatSessionProvider>
  );
}

function InterviewRoom() {
  const { activeSession, selectSession } = useChatSession();
  const setup = useInterviewSetup();
  const { scorecard, evaluating, evaluate, reset } = useEvaluation();

  const handleStart = useCallback(async () => {
    const session = await setup.start();
    if (session) selectSession(session);
  }, [setup, selectSession]);

  const handleEvaluate = useCallback(() => {
    if (activeSession) void evaluate(activeSession.session_id);
  }, [activeSession, evaluate]);

  const handleRestart = useCallback(() => {
    reset();
    selectSession(null); // back to the persona picker for a fresh session
  }, [reset, selectSession]);

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      {/* Picker shown until a session is active; ChatView stays mounted (never
          conditionally unmounted) so voice/audio state survives — CLAUDE.md. */}
      {!activeSession && <PersonaPicker setup={setup} onStart={handleStart} />}
      <ChatView
        className={!activeSession ? 'hidden' : 'flex-1'}
        footerSlot={activeSession ? <EndEvaluateBar evaluating={evaluating} onEvaluate={handleEvaluate} /> : undefined}
      />
      {scorecard && <ScorecardView card={scorecard} onClose={reset} onRestart={handleRestart} />}
    </div>
  );
}
