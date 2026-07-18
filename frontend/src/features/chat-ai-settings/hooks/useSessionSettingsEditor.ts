// Chat & AI settings — the SESSION-tier editor controller (MVC "controller": owns
// logic + state, no JSX). Spec docs/specs/2026-07-05-chat-ai-settings.md §3, §8.
//
// The account editor (`useAiPrefsEditor`) resolves Account▸System. This one layers the
// Session tier on top of the full cascade — Session ▸ Book ▸ Account ▸ System — by
// asking the ONE backend resolver for this session's context. It is the same endpoint
// chat and every studio tool call, so a chip here can never disagree with what the turn
// actually uses (spec §3.1 "one authoritative source").
//
// Two things this deliberately does NOT do:
//   * it never invents a default. `temperature ?? 0.7` in the old panel was a client-side
//     literal that had nothing to do with the system default. Every value comes from the
//     cascade, and the tier that supplied it is shown.
//   * it never treats "equal to the parent" as "inherited". A field is overridden here
//     iff the SESSION row carries it (finding UX-5) — so "set here · matches account"
//     stays distinguishable from "inherited", and clearing is always offered.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '@/features/chat/api';
import type { ChatSession, PatchSessionPayload } from '@/features/chat/types';
import { aiSettingsApi } from '../api';
import type { EffectiveSettings, FieldResolution } from '../types';

/** Debounce for the session PATCH. The old panel used 500ms; a settings slider drags. */
const PATCH_DEBOUNCE_MS = 400;

export type SessionSettingsEditor = {
  session: ChatSession;
  effective: EffectiveSettings | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  /** The resolved field, or null while the cascade is loading. */
  field: (category: EffectiveCategory, name: string) => FieldResolution | null;
  /** True iff THIS session row carries the override (not value-equality). */
  isOverridden: (category: EffectiveCategory, name: string) => boolean;
  /** The value this field would fall back to if the session override were cleared. */
  inheritedValue: (category: EffectiveCategory, name: string) => unknown;
  /** Merge a patch into the session row (debounced) and re-resolve the cascade. */
  patch: (p: PatchSessionPayload) => void;
  /** Flush any pending debounced patch immediately (call on unmount / close). */
  flush: () => Promise<void>;
};

export type EffectiveCategory = 'behavior' | 'grounding' | 'context' | 'voice';

/** Which session column carries each category's override (spec §3.5). `behavior`
 *  lives in `generation_params` + the top-level `system_prompt` column. */
const CATEGORY_COLUMN: Record<Exclude<EffectiveCategory, 'behavior'>, keyof ChatSession> = {
  grounding: 'grounding_enabled',
  context: 'context_overrides',
  voice: 'voice_overrides',
};

/** Does the SESSION row itself carry `category.name`? */
export function sessionCarriesOverride(
  session: ChatSession,
  category: EffectiveCategory,
  name: string,
): boolean {
  if (category === 'behavior') {
    if (name === 'system_prompt') return !!session.system_prompt;
    const gp = (session.generation_params ?? {}) as Record<string, unknown>;
    return gp[name] != null;
  }
  if (category === 'grounding') {
    // The only session-scoped grounding leaf today. `project_ids` is a session concept
    // that never cascades, so it is not a tiered field.
    return name === 'grounding_enabled' && session.grounding_enabled != null;
  }
  const blob = (session[CATEGORY_COLUMN[category]] ?? {}) as Record<string, unknown>;
  return blob[name] != null;
}

export function useSessionSettingsEditor(
  session: ChatSession,
  onSessionUpdate: (s: ChatSession) => void,
): SessionSettingsEditor {
  const { accessToken } = useAuth();
  const [effective, setEffective] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Accumulate leaves across a debounce window so dragging two sliders sends ONE patch
  // whose bodies deep-merge, rather than two that race and lose a leaf.
  const pending = useRef<PatchSessionPayload>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The session a pending patch BELONGS TO, captured when the first leaf is enqueued.
  //
  // This must NOT be "whatever session is current when the timer fires". The panel stays
  // mounted across a session switch (ChatView keeps `settingsOpen`), and the switch itself
  // flushes the debounce — so a `latest.current` read at send time delivered session A's
  // half-typed system prompt to session B. A cross-session write: one chat silently
  // overwriting another's settings.
  const pendingFor = useRef<string | null>(null);
  /** The session currently on screen — read only to decide whether a completed PATCH's
   *  row is still the one the user is looking at. Never used as a PATCH target. */
  const sessionIdRef = useRef(session.session_id);
  sessionIdRef.current = session.session_id;

  const reload = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setEffective(
        await aiSettingsApi.getEffective(accessToken, {
          sessionId: session.session_id,
          bookId: session.book_id ?? null,
        }),
      );
    } catch (err) {
      // The panel must still render (with "unavailable" chips) — a settings surface that
      // blanks out when the resolver hiccups is worse than one that says so.
      setError(err instanceof Error ? err.message : 'failed to resolve settings');
    } finally {
      setLoading(false);
    }
  }, [accessToken, session.session_id, session.book_id]);

  useEffect(() => { void reload(); }, [reload]);

  const send = useCallback(async () => {
    const body = pending.current;
    const targetId = pendingFor.current;
    pending.current = {};
    pendingFor.current = null;
    if (!accessToken || !targetId || Object.keys(body).length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await chatApi.patchSession(accessToken, targetId, body);
      // Only hand the row back if it is still the session on screen. Pushing session A's
      // row into the provider while B is active would swap the user's open chat.
      if (targetId === sessionIdRef.current) {
        onSessionUpdate(updated);
        // Re-resolve so the tier chips reflect the write. Without this a cleared override
        // still shows "session" until the panel remounts — a lying chip.
        await reload();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to save');
    } finally {
      setSaving(false);
    }
  }, [accessToken, onSessionUpdate, reload]);

  const patch = useCallback((p: PatchSessionPayload) => {
    // Bind the pending body to the session it was authored on. If a switch somehow lands
    // between two leaves of one window, the earlier body is flushed to ITS session first
    // rather than merged into a stranger's.
    if (pendingFor.current && pendingFor.current !== sessionIdRef.current) {
      if (timer.current) clearTimeout(timer.current);
      void send();
    }
    pendingFor.current = sessionIdRef.current;

    // Deep-merge into the pending body for the two JSONB categories, so patching
    // `context_overrides.mode` then `context_overrides.trigger_ratio` inside one window
    // sends both — a shallow spread would drop the first.
    const prev = pending.current;
    const next: PatchSessionPayload = { ...prev, ...p };
    for (const key of ['voice_overrides', 'context_overrides'] as const) {
      const a = prev[key];
      const b = p[key];
      // An explicit null (clear-the-category) must WIN over an earlier merge, not merge into it.
      if (b !== null && a && b) next[key] = { ...a, ...b };
    }
    if (p.generation_params && prev.generation_params) {
      next.generation_params = { ...prev.generation_params, ...p.generation_params };
    }
    pending.current = next;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void send(); }, PATCH_DEBOUNCE_MS);
  }, [send]);

  const flush = useCallback(async () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    await send();
  }, [send]);

  // Flush on unmount — closing the panel mid-debounce must not silently drop the edit.
  useEffect(() => () => {
    if (timer.current) { clearTimeout(timer.current); void send(); }
  }, [send]);

  const field = useCallback(
    (category: EffectiveCategory, name: string): FieldResolution | null =>
      effective?.[category]?.[name] ?? null,
    [effective],
  );

  const isOverridden = useCallback(
    (category: EffectiveCategory, name: string) => sessionCarriesOverride(session, category, name),
    [session],
  );

  const inheritedValue = useCallback(
    (category: EffectiveCategory, name: string) => {
      const stack = effective?.[category]?.[name]?.tier_stack ?? {};
      // The first tier BELOW session that carries a value — what "clear override" reveals.
      return stack.book ?? stack.account ?? stack.system ?? null;
    },
    [effective],
  );

  return {
    session, effective, loading, saving, error,
    field, isOverridden, inheritedValue, patch, flush,
  };
}
