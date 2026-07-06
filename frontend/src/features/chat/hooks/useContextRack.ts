import { useCallback, useRef } from 'react';
import { toast } from 'sonner';
import { chatApi } from '../api';
import type { ChatSession } from '../types';

const TOOL_SOFT_LIMIT = 8;
const SKILL_SOFT_LIMIT = 4;
// Matches the backend's PatchSessionRequest.pinned_legacy_tools max_length=16 —
// a hard cap there, so this is the point past which the PATCH itself 422s.
const PINNED_LEGACY_LIMIT = 16;

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
  // review-impl: a single shared timer replaced its OWN pending payload on every
  // call — two different-field mutations (e.g. addTool then addPinnedLegacyTool)
  // within the 300ms window silently dropped the earlier one's PATCH body. Now
  // MERGED across calls and flushed as one PATCH, then cleared.
  const pendingPatchRef = useRef<Record<string, unknown>>({});

  const enabledTools = session?.enabled_tools ?? [];
  const enabledSkills = session?.enabled_skills ?? [];
  const activatedTools = session?.activated_tools ?? [];
  const pinnedLegacyTools = session?.pinned_legacy_tools ?? [];

  /** Latest pins for POST body — updated synchronously on pin/unpin (before PATCH flush). */
  const streamPinsRef = useRef<StreamPins>(toStreamPins(enabledTools, enabledSkills));
  streamPinsRef.current = toStreamPins(enabledTools, enabledSkills);

  const patchSession = useCallback(    (payload: { enabled_tools?: string[]; enabled_skills?: string[]; activated_tools?: string[]; pinned_legacy_tools?: string[] }) => {
      if (!accessToken || !session) return;
      Object.assign(pendingPatchRef.current, payload);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const merged = pendingPatchRef.current;
        pendingPatchRef.current = {};
        chatApi
          .patchSession(accessToken, session.session_id, merged)
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

  // Tool-catalog-simplification Part D (CAT-4) — the manual escape hatch back
  // to a legacy (superseded, find_tools-invisible) tool for THIS session only.
  // Deliberately a SEPARATE list from enabledTools: pinning one here must not
  // flip the whole session into curated mode (see catalog.py's default
  // visibility filter) — it's additive on top of whatever mode is already active.
  const addPinnedLegacyTool = useCallback(
    (name: string) => {
      if (!session || hidden) return;
      if (pinnedLegacyTools.includes(name)) return;
      const next = [...pinnedLegacyTools, name];
      if (next.length > PINNED_LEGACY_LIMIT) {
        toast.warning(`Pinned ${next.length} legacy tools (limit ${PINNED_LEGACY_LIMIT})`);
        return;
      }
      onSessionUpdate({ ...session, pinned_legacy_tools: next });
      patchSession({ pinned_legacy_tools: next });
    },
    [session, pinnedLegacyTools, hidden, onSessionUpdate, patchSession],
  );

  const removePinnedLegacyTool = useCallback(
    (name: string) => {
      if (!session) return;
      const next = pinnedLegacyTools.filter((t) => t !== name);
      onSessionUpdate({ ...session, pinned_legacy_tools: next });
      patchSession({ pinned_legacy_tools: next });
    },
    [session, pinnedLegacyTools, onSessionUpdate, patchSession],
  );

  return {
    enabledTools,
    enabledSkills,
    activatedTools,
    pinnedLegacyTools,
    addTool,
    removeTool,
    addSkill,
    removeSkill,
    addPinnedLegacyTool,
    removePinnedLegacyTool,
    clearDiscovered,
    streamPins: streamPinsRef.current,
    streamPinsRef,
    toolSoftLimit: TOOL_SOFT_LIMIT,
    skillSoftLimit: SKILL_SOFT_LIMIT,
    pinnedLegacyLimit: PINNED_LEGACY_LIMIT,
  };
}
