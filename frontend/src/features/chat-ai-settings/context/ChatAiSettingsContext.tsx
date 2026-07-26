// Chat & AI settings — the shared effective-settings source (spec §8).
//
// Hoisted by WorkspaceShell OUTSIDE LiveStateProvider (settings changes must not
// interact with the co-writer stream, and per-token stream re-renders must not
// touch settings). The context value is MEMOIZED with structural sharing — NOT
// the un-memoized `{ stream }` pattern in LiveStateContext (which re-renders
// consumers every streamed chunk). Studio tools read `useEffectiveModel(role)`
// to inherit the model instead of defaulting to modelList[0].
//
// M1 scope: read-only (effective settings + refetch). The mutation methods that
// write the prefs blob + invalidate on write arrive with the M2 settings panel.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode,
} from 'react';
import { aiSettingsApi } from '../api';
import type { EffectiveSettings, ModelRole } from '../types';

type ChatAiSettings = {
  effective: EffectiveSettings | null;
  loading: boolean;
  refetch: () => void;
};

const Ctx = createContext<ChatAiSettings | null>(null);

export function ChatAiSettingsProvider({
  token, bookId, sessionId, children,
}: {
  token: string | null;
  bookId?: string | null;
  sessionId?: string | null;
  children: ReactNode;
}) {
  const [effective, setEffective] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const e = await aiSettingsApi.getEffective(token, { bookId, sessionId });
      setEffective(e);
    } catch {
      // best-effort: a resolver hiccup must never break the studio; tools fall
      // back to their own list default until the next successful load.
      setEffective(null);
    } finally {
      setLoading(false);
    }
  }, [token, bookId, sessionId]);

  // Synchronization (fetch on identity change) — not event handling.
  useEffect(() => { void load(); }, [load]);

  const value = useMemo<ChatAiSettings>(
    () => ({ effective, loading, refetch: load }),
    [effective, loading, load],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Optional — returns null outside a provider (bare unit mounts / pop-out roots),
 *  so a consumer degrades to its own default rather than throwing. */
export function useChatAiSettingsOptional(): ChatAiSettings | null {
  return useContext(Ctx);
}

/** The effective model_ref for a role from the resolved cascade, or null when
 *  there is no provider / nothing resolved. Studio tools use this as the inherit
 *  base (spec §8): `localOverride ?? useEffectiveModel(role) ?? list[0]`. */
export function useEffectiveModel(role: ModelRole): string | null {
  const ctx = useContext(Ctx);
  const m = ctx?.effective?.models?.[role];
  return m?.effective_value?.model_ref ?? null;
}
