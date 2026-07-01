import { useCallback, useRef } from 'react';
import { toast } from 'sonner';
import { chatApi } from '../api';
import type { ChatSession } from '../types';

const TOOL_SOFT_LIMIT = 8;
const SKILL_SOFT_LIMIT = 4;

export type StreamPins = {
  enabledTools?: string[];
  enabledSkills?: string[];
};

type UseContextRackArgs = {
  session: ChatSession | null | undefined;
  accessToken: string | null;
  onSessionUpdate: (session: ChatSession) => void;
  hidden?: boolean;
};

function toStreamPins(tools: string[], skills: string[]): StreamPins {
  return {
    enabledTools: tools.length ? tools : undefined,
    enabledSkills: skills.length ? skills : undefined,
  };
}

export function useContextRack({
  session,
  accessToken,
  onSessionUpdate,
  hidden = false,
}: UseContextRackArgs) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const enabledTools = session?.enabled_tools ?? [];
  const enabledSkills = session?.enabled_skills ?? [];
  const activatedTools = session?.activated_tools ?? [];

  /** Latest pins for POST body — updated synchronously on pin/unpin (before PATCH flush). */
  const streamPinsRef = useRef<StreamPins>(toStreamPins(enabledTools, enabledSkills));
  streamPinsRef.current = toStreamPins(enabledTools, enabledSkills);

  const patchSession = useCallback(    (payload: { enabled_tools?: string[]; enabled_skills?: string[]; activated_tools?: string[] }) => {
      if (!accessToken || !session) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        chatApi
          .patchSession(accessToken, session.session_id, payload)
          .then(onSessionUpdate)
          .catch((err) => toast.error((err as Error).message));
      }, 300);
    },
    [accessToken, session, onSessionUpdate],
  );

  const addTool = useCallback(
    (name: string) => {
      if (!session || hidden) return;
      if (enabledTools.includes(name)) return;
      const next = [...enabledTools, name];
      if (next.length > TOOL_SOFT_LIMIT) {
        toast.warning(`Pinned ${next.length} tools (soft limit ${TOOL_SOFT_LIMIT})`);
      }
      streamPinsRef.current = toStreamPins(next, enabledSkills);
      onSessionUpdate({ ...session, enabled_tools: next });
      patchSession({ enabled_tools: next });
    },
    [session, enabledTools, hidden, onSessionUpdate, patchSession],
  );

  const removeTool = useCallback(
    (name: string) => {
      if (!session) return;
      const next = enabledTools.filter((t) => t !== name);
      streamPinsRef.current = toStreamPins(next, enabledSkills);
      onSessionUpdate({ ...session, enabled_tools: next });
      patchSession({ enabled_tools: next });
    },
    [session, enabledTools, onSessionUpdate, patchSession],
  );

  const addSkill = useCallback(
    (id: string) => {
      if (!session || hidden) return;
      if (enabledSkills.includes(id)) return;
      const next = [...enabledSkills, id];
      if (next.length > SKILL_SOFT_LIMIT) {
        toast.warning(`Pinned ${next.length} skills (soft limit ${SKILL_SOFT_LIMIT})`);
      }
      streamPinsRef.current = toStreamPins(enabledTools, next);
      onSessionUpdate({ ...session, enabled_skills: next });
      patchSession({ enabled_skills: next });
    },
    [session, enabledSkills, hidden, onSessionUpdate, patchSession],
  );

  const removeSkill = useCallback(
    (id: string) => {
      if (!session) return;
      const next = enabledSkills.filter((s) => s !== id);
      streamPinsRef.current = toStreamPins(enabledTools, next);
      onSessionUpdate({ ...session, enabled_skills: next });
      patchSession({ enabled_skills: next });
    },
    [session, enabledSkills, onSessionUpdate, patchSession],
  );

  const clearDiscovered = useCallback(() => {
    if (!session) return;
    onSessionUpdate({ ...session, activated_tools: [] });
    patchSession({ activated_tools: [] });
  }, [session, onSessionUpdate, patchSession]);

  return {
    enabledTools,
    enabledSkills,
    activatedTools,
    addTool,
    removeTool,
    addSkill,
    removeSkill,
    clearDiscovered,
    streamPins: streamPinsRef.current,
    streamPinsRef,
    toolSoftLimit: TOOL_SOFT_LIMIT,
    skillSoftLimit: SKILL_SOFT_LIMIT,
  };
}
