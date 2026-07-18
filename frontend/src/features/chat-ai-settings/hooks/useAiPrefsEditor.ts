// Chat & AI settings — the account-tier editor controller (MVC "controller":
// owns logic + state, no JSX). Loads the user's prefs blob + the account-context
// effective cascade, and writes via a deep-merge PATCH with an If-Match version
// guard. On every write it invalidates the shared model-list cache so any open
// studio picker re-derives (spec §8 EC-2: writes flow through here, no silent
// stale submit).
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { invalidateUserModelsCache } from '@/components/model-picker';
import { loadVoicePrefs, saveVoicePrefs } from '@/features/chat/voicePrefs';
import { aiSettingsApi } from '../api';
import { accountVoiceDiffers, mergeAccountVoiceIntoPrefs, type AccountVoiceBlob } from '../voiceBridge';
import type { AiPrefs, AiPrefsPatch, EffectiveSettings } from '../types';

export type AiPrefsEditor = {
  prefs: AiPrefs | null;
  effective: EffectiveSettings | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  /** Deep-merge patch (null leaf clears). Optimistic version bump + reload. */
  patch: (p: AiPrefsPatch) => Promise<void>;
  reload: () => void;
};

export function useAiPrefsEditor(): AiPrefsEditor {
  const { accessToken } = useAuth();
  const [prefs, setPrefs] = useState<AiPrefs | null>(null);
  const [effective, setEffective] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      // account context: no book_id / session_id → the pure Account▸System view.
      const [p, e] = await Promise.all([
        aiSettingsApi.getPrefs(accessToken),
        aiSettingsApi.getEffective(accessToken, {}),
      ]);
      setPrefs(p);
      setEffective(e);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load settings');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => { void reload(); }, [reload]);

  const patch = useCallback(async (p: AiPrefsPatch) => {
    if (!accessToken || !prefs) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await aiSettingsApi.patchPrefs(accessToken, p, prefs.version);
      setPrefs(updated);
      invalidateUserModelsCache();
      // D-CHATAI-VOICE-TWO-STORES — dual-write the shared voice leaves into the store the
      // voice RUNTIME actually reads (`lw_voice_prefs` + auth-service `voice_prefs`). Until
      // now, picking a TTS voice here changed nothing you could hear: the runtime never
      // looks at `user_chat_ai_prefs.voice`. Spec §7.1 MIG-4 requires this dual-write during
      // compat so a rollback loses nothing. Best-effort — a settings save must not fail
      // because the legacy mirror did.
      if (p.voice) {
        try {
          const blob = updated.voice as AccountVoiceBlob;
          const current = loadVoicePrefs();
          // Skip a no-op mirror: `saveVoicePrefs` also POSTs to auth-service, so writing an
          // identical blob costs a request per edit. `accountVoiceDiffers` compares only the
          // SHARED leaves, and treats the `user_model`/`ai_model` split as equal — so a
          // legacy-worded blob doesn't look like a change forever.
          if (accountVoiceDiffers(blob, current)) {
            saveVoicePrefs(mergeAccountVoiceIntoPrefs(blob, current), accessToken);
          }
        } catch {
          /* the authoritative write already succeeded; the mirror self-heals on next save */
        }
      }
      // refetch the effective cascade so source-tier chips reflect the change.
      const e = await aiSettingsApi.getEffective(accessToken, {});
      setEffective(e);
    } catch (err) {
      // 412 → someone else edited (another device); reload to the current row so
      // the next save has the fresh version, and surface it (no silent clobber).
      const status = (err as { status?: number })?.status;
      setError(status === 412 ? 'settings changed on another device — reloaded' : (err instanceof Error ? err.message : 'save failed'));
      await reload();
    } finally {
      setSaving(false);
    }
  }, [accessToken, prefs, reload]);

  return { prefs, effective, loading, saving, error, patch, reload };
}
