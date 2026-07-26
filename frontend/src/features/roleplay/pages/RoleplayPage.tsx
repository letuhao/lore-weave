// Roleplay-practice page. The persona picker is the entry; once started it
// REUSES the chat feature's ChatView (text + voice, no fork) for the turn loop,
// and adds a scorecard overlay on "End & evaluate". The chat providers are
// driven in embedded mode — the host injects the active session via
// selectSession() (see ChatSessionContext). Interview is a preset genre.

import { useCallback } from 'react';
import { ChatSessionProvider, ChatStreamProvider, useChatSession } from '@/features/chat/providers';
import { ChatView } from '@/features/chat/components/ChatView';
import { useRoleplaySetup } from '../hooks/useRoleplaySetup';
import { useEvaluation } from '../hooks/useEvaluation';
import { PersonaPicker } from '../components/PersonaPicker';
import { EndEvaluateBar } from '../components/EndEvaluateBar';
import { PracticeProgressHeader } from '../components/PracticeProgressHeader';
import { ScorecardView } from '../components/ScorecardView';

export function RoleplayPage() {
  return (
    <ChatSessionProvider embedded>
      <ChatStreamProvider>
        <RoleplayRoom />
      </ChatStreamProvider>
    </ChatSessionProvider>
  );
}

function RoleplayRoom() {
  const { activeSession, selectSession } = useChatSession();
  const setup = useRoleplaySetup();
  const { scorecard, evaluating, evaluate, reset } = useEvaluation();
  // A4.3 — the script whose charter drives the Q-progress/wrap (interview presets only).
  const selectedScript = setup.scripts.find((s) => s.script_id === setup.selectedScriptId);

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
      {/* A4.3 — the Practice progress/wrap header (interview sessions only; renders null for
          freeform). Mobile + desktop both get it; the server enforces the wrap, this mirrors it. */}
      {activeSession && (
        <PracticeProgressHeader
          messageCount={activeSession.message_count}
          startedAt={activeSession.created_at}
          script={selectedScript}
        />
      )}
      <ChatView
        className={!activeSession ? 'hidden' : 'flex-1'}
        footerSlot={activeSession ? <EndEvaluateBar evaluating={evaluating} onEvaluate={handleEvaluate} /> : undefined}
      />
      {scorecard && <ScorecardView card={scorecard} onClose={reset} onRestart={handleRestart} />}
    </div>
  );
}
