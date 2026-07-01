import { useCallback, useEffect, useState } from 'react';
import type { AgentSurfaceState, ChatSession } from '../types';

const INSPECTOR_EXPANDED_KEY = 'lw_chat_inspector_expanded';

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
  const [expanded, setExpanded] = useState(() => {
    try {
      return localStorage.getItem(INSPECTOR_EXPANDED_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    setState(degradedSurfaceFromSession(session));
  }, [session?.session_id, session?.enabled_tools, session?.enabled_skills, session?.activated_tools]);

  const applyEvent = useCallback((payload: AgentSurfaceState) => {
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

  return { state, applyEvent, expanded, toggleExpanded };
}
