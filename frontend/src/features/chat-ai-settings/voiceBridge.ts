// The voice reconciliation seam (spec §3.5, §7.1 MIG-4 · D-CHATAI-VOICE-TWO-STORES).
//
// Voice had TWO account stores that never spoke:
//   * Settings → Chat & AI → Voice wrote `user_chat_ai_prefs.voice.{chat,stt}` (chat-service)
//   * the chat VoiceSettingsPanel wrote `lw_voice_prefs` + auth-service `voice_prefs`
// and the voice RUNTIME reads the second one. So picking a TTS voice in the unified panel
// changed precisely nothing about what you heard. Spec §3.5 names
// `user_chat_ai_prefs.voice` the single home and §7.1 requires a compat dual-write to
// `voice_prefs` so a rollback loses nothing. This module is that bridge.
//
// It also reconciles a vocabulary split: the account panel writes `tts_source:
// 'user_model'` where the voice store uses `'ai_model'` for the same concept
// ('the audio comes from an AI model, not the browser'). `'user_model'` is the
// MODEL-SOURCE vocabulary (user_model | platform_model) — a different axis that leaked in.
// We accept both on read and always emit `'ai_model'`, so the two converge without a
// migration and without 422-ing a client that still sends the old word.
import { DEFAULT_VOICE_PREFS, type VoicePrefs } from '@/features/chat/voicePrefs';

/** The account-blob shape the Chat & AI panel edits (a subset of VoicePrefs). */
export type AccountVoiceBlob = {
  chat?: { tts_model_ref?: string | null; tts_voice_id?: string | null; tts_source?: string | null };
  stt?: { model_ref?: string | null; source?: string | null };
};

/** Both stores mean the same thing by 'ai_model'; only one of them says so. */
export function normalizeVoiceSource(value: unknown): 'browser' | 'ai_model' | null {
  if (value === 'browser') return 'browser';
  if (value === 'ai_model' || value === 'user_model') return 'ai_model';
  return null;
}

/** Fold the account blob's overlapping leaves into a VoicePrefs — what the runtime reads.
 *  Absent leaves leave `prefs` untouched: the blob is a partial override, not a snapshot. */
export function mergeAccountVoiceIntoPrefs(blob: AccountVoiceBlob | null | undefined, prefs: VoicePrefs): VoicePrefs {
  const out: VoicePrefs = { ...prefs };
  const chat = blob?.chat;
  if (chat) {
    if (chat.tts_model_ref !== undefined) out.ttsModelRef = chat.tts_model_ref ?? '';
    if (chat.tts_voice_id !== undefined) out.ttsVoiceId = chat.tts_voice_id ?? '';
    const src = normalizeVoiceSource(chat.tts_source);
    if (src) out.ttsSource = src;
  }
  const stt = blob?.stt;
  if (stt) {
    if (stt.model_ref !== undefined) out.sttModelRef = stt.model_ref ?? '';
    const src = normalizeVoiceSource(stt.source);
    if (src) out.sttSource = src;
  }
  return out;
}

/** The account blob for the leaves the two stores share. Always emits the `ai_model`
 *  vocabulary, so a round-trip through either panel converges on one word. */
export function accountVoiceFromPrefs(prefs: VoicePrefs): AccountVoiceBlob {
  return {
    chat: {
      tts_model_ref: prefs.ttsModelRef || null,
      tts_voice_id: prefs.ttsVoiceId || null,
      tts_source: prefs.ttsSource,
    },
    stt: {
      model_ref: prefs.sttModelRef || null,
      source: prefs.sttSource,
    },
  };
}

/** True when `blob` disagrees with `prefs` on any shared leaf — the mirror is a no-op
 *  otherwise, so a slider drag in the voice panel never fires an account PATCH. */
export function accountVoiceDiffers(blob: AccountVoiceBlob | null | undefined, prefs: VoicePrefs): boolean {
  const merged = mergeAccountVoiceIntoPrefs(blob, DEFAULT_VOICE_PREFS);
  const want = mergeAccountVoiceIntoPrefs(accountVoiceFromPrefs(prefs), DEFAULT_VOICE_PREFS);
  return (
    merged.ttsModelRef !== want.ttsModelRef ||
    merged.ttsVoiceId !== want.ttsVoiceId ||
    merged.ttsSource !== want.ttsSource ||
    merged.sttModelRef !== want.sttModelRef ||
    merged.sttSource !== want.sttSource
  );
}
