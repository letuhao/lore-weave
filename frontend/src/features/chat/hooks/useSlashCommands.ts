// D-REG-P4-SLASH-AUTOCOMPLETE — the user's registry slash commands, for the in-chat
// `/` autocomplete. These are the `/name` commands authored in the Extensions →
// Commands GUI; the chat-service router expands `/name args` server-side before the
// turn, so the picker only needs to COMPLETE the token (set the input to `/name `).
// Degrade-safe: any failure → no commands (the built-in template picker still works).
import { useCallback, useEffect, useState } from 'react';
import { apiJson } from '@/api';
import { useAuth } from '@/auth';
import { agentRegistryHealth } from '@/lib/agentRegistryHealth';

export interface SlashCommandItem {
  command_id: string;
  name: string;
  description: string;
}

interface CommandListResp {
  items: { command_id: string; name: string; description?: string }[];
}

export function useSlashCommands() {
  const { accessToken } = useAuth();
  const [commands, setCommands] = useState<SlashCommandItem[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    // F12 — if the registry just failed, skip the slow 504 round-trip on this
    // (re)mount. The built-in template picker still works, so degrading silently
    // to "no custom commands" is fine here.
    if (agentRegistryHealth.likelyDown()) {
      setCommands([]);
      return;
    }
    let live = true;
    (async () => {
      try {
        const r = await apiJson<CommandListResp>('/v1/agent-registry/commands?limit=50', { token: accessToken });
        if (live) {
          setCommands(
            (r.items ?? []).map((c) => ({ command_id: c.command_id, name: c.name, description: c.description ?? '' })),
          );
          agentRegistryHealth.noteUp();
        }
      } catch {
        if (live) {
          setCommands([]); // degrade — the built-in template picker still works
          agentRegistryHealth.noteDown();
        }
      }
    })();
    return () => { live = false; };
  }, [accessToken]);

  // Match on the token after "/" (prefix, case-insensitive). Empty filter → all.
  const match = useCallback(
    (filter: string): SlashCommandItem[] => {
      const f = filter.trim().toLowerCase();
      if (!f) return commands;
      return commands.filter((c) => c.name.toLowerCase().startsWith(f));
    },
    [commands],
  );

  return { commands, match };
}
