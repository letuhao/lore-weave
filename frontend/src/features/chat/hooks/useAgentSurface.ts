import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentSurfacePhase, AgentSurfaceState, ChatSession } from '../types';

const INSPECTOR_EXPANDED_KEY = 'lw_chat_inspector_expanded';
// W6 — phase-transition trail cap (display-only; oldest entries drop).
const TRAIL_CAP = 8;

export function degradedSurfaceFromSession(session: ChatSession | null | undefined): AgentSurfaceState {
  return {
    phase: 'Idle',
    pinned_count: session?.enabled_tools?.length ?? 0,
    hot_seed_count: 0,
    activated_count: session?.activated_tools?.length ?? 0,
    injected_skills: session?.enabled_skills ?? [],
    running_tool: null,
    last_find_tools_query: null,
    find_tools_call_count: 0,
  };
}

export function useAgentSurface(session: ChatSession | null | undefined) {
  const [state, setState] = useState<AgentSurfaceState>(() => degradedSurfaceFromSession(session));
  // W6 — this turn's phase transitions (display-only trail for the inspector).
  const [trail, setTrail] = useState<AgentSurfacePhase[]>([]);
  const [expanded, setExpanded] = useState(() => {
    try {
      return localStorage.getItem(INSPECTOR_EXPANDED_KEY) === '1';
    } catch {
      return false;
    }
  });

  const lastPhaseRef = useRef<AgentSurfacePhase>('Idle');

  useEffect(() => {
    setState(degradedSurfaceFromSession(session));
    setTrail([]);
    lastPhaseRef.current = 'Idle';
  }, [session?.session_id, session?.enabled_tools, session?.enabled_skills, session?.activated_tools]);

  const applyEvent = useCallback((payload: AgentSurfaceState) => {
    const prevPhase = lastPhaseRef.current;
    if (payload.phase !== prevPhase) {
      lastPhaseRef.current = payload.phase;
      setTrail((prevTrail) => {
        // a transition out of Idle starts a new turn → reset the trail.
        const base = prevPhase === 'Idle' ? [] : prevTrail;
        return [...base, payload.phase].slice(-TRAIL_CAP);
      });
    }
    setState(payload);
  }, []);

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(INSPECTOR_EXPANDED_KEY, next ? '1' : '0');
      } catch {
        /* per-device preference — ignore */
      }
      return next;
    });
  }, []);

  return { state, trail, applyEvent, expanded, toggleExpanded };
}
