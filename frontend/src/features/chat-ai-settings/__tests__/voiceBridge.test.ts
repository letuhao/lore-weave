// D-CHATAI-VOICE-TWO-STORES. Voice had two account stores that never spoke:
// `user_chat_ai_prefs.voice` (what Settings → Chat & AI → Voice wrote) and
// `lw_voice_prefs`/`voice_prefs` (what the voice RUNTIME reads). Picking a TTS voice in
// the unified panel changed nothing you could hear. These pin the bridge that reconciles
// them — including the vocabulary split, which is the part a reader will not expect.
import { describe, it, expect } from 'vitest';
import { DEFAULT_VOICE_PREFS, type VoicePrefs } from '@/features/chat/voicePrefs';
import {
  normalizeVoiceSource,
  mergeAccountVoiceIntoPrefs,
  accountVoiceFromPrefs,
  accountVoiceDiffers,
} from '../voiceBridge';

const prefs = (over: Partial<VoicePrefs> = {}): VoicePrefs => ({ ...DEFAULT_VOICE_PREFS, ...over });

describe('normalizeVoiceSource', () => {
  it("accepts BOTH vocabularies for the same concept", () => {
    // The account panel wrote 'user_model' (the MODEL-SOURCE axis) where the voice store
    // uses 'ai_model' (the AUDIO-SOURCE axis). Accept both, emit one.
    expect(normalizeVoiceSource('ai_model')).toBe('ai_model');
    expect(normalizeVoiceSource('user_model')).toBe('ai_model');
    expect(normalizeVoiceSource('browser')).toBe('browser');
  });

  it('returns null for anything else, so an unknown word never silently means ai_model', () => {
    expect(normalizeVoiceSource('platform_model')).toBeNull();
    expect(normalizeVoiceSource(undefined)).toBeNull();
    expect(normalizeVoiceSource(null)).toBeNull();
    expect(normalizeVoiceSource(7)).toBeNull();
  });
});

describe('mergeAccountVoiceIntoPrefs', () => {
  it('folds the account blob into the store the runtime actually reads', () => {
    const out = mergeAccountVoiceIntoPrefs(
      { chat: { tts_model_ref: 'm1', tts_voice_id: 'af_heart', tts_source: 'user_model' } },
      prefs(),
    );
    expect(out.ttsModelRef).toBe('m1');
    expect(out.ttsVoiceId).toBe('af_heart');
    expect(out.ttsSource).toBe('ai_model'); // normalized, not stored verbatim
  });

  it('is a partial override — absent leaves keep their existing value', () => {
    const before = prefs({ ttsSpeed: 1.5, ttsVoiceId: 'keep-me', autoTTSResponses: false });
    const out = mergeAccountVoiceIntoPrefs({ chat: { tts_model_ref: 'm2' } }, before);
    expect(out.ttsModelRef).toBe('m2');
    expect(out.ttsVoiceId).toBe('keep-me');
    expect(out.ttsSpeed).toBe(1.5);
    expect(out.autoTTSResponses).toBe(false);
  });

  it('an explicit null clears the leaf to the store\'s empty string', () => {
    const out = mergeAccountVoiceIntoPrefs({ chat: { tts_voice_id: null } }, prefs({ ttsVoiceId: 'x' }));
    expect(out.ttsVoiceId).toBe('');
  });

  it('handles a missing/empty blob without touching prefs', () => {
    const before = prefs({ ttsVoiceId: 'x' });
    expect(mergeAccountVoiceIntoPrefs(null, before)).toEqual(before);
    expect(mergeAccountVoiceIntoPrefs({}, before)).toEqual(before);
  });

  it('maps the stt leaves too', () => {
    const out = mergeAccountVoiceIntoPrefs({ stt: { model_ref: 's1', source: 'ai_model' } }, prefs());
    expect(out.sttModelRef).toBe('s1');
    expect(out.sttSource).toBe('ai_model');
  });
});

describe('accountVoiceFromPrefs', () => {
  it('emits the ai_model vocabulary, never user_model', () => {
    const blob = accountVoiceFromPrefs(prefs({ ttsSource: 'ai_model', sttSource: 'ai_model' }));
    expect(blob.chat?.tts_source).toBe('ai_model');
    expect(blob.stt?.source).toBe('ai_model');
    expect(JSON.stringify(blob)).not.toContain('user_model');
  });

  it('sends null (clear) rather than an empty string for an unset ref', () => {
    const blob = accountVoiceFromPrefs(prefs({ ttsModelRef: '', ttsVoiceId: '' }));
    expect(blob.chat?.tts_model_ref).toBeNull();
    expect(blob.chat?.tts_voice_id).toBeNull();
  });

  it('round-trips through mergeAccountVoiceIntoPrefs', () => {
    const p = prefs({ ttsModelRef: 'm', ttsVoiceId: 'v', ttsSource: 'ai_model', sttModelRef: 's', sttSource: 'browser' });
    const back = mergeAccountVoiceIntoPrefs(accountVoiceFromPrefs(p), DEFAULT_VOICE_PREFS);
    expect(back.ttsModelRef).toBe('m');
    expect(back.ttsVoiceId).toBe('v');
    expect(back.ttsSource).toBe('ai_model');
    expect(back.sttModelRef).toBe('s');
    expect(back.sttSource).toBe('browser');
  });
});

describe('accountVoiceDiffers', () => {
  it('is false when the two stores already agree — a slider drag must not PATCH', () => {
    const p = prefs({ ttsModelRef: 'm', ttsVoiceId: 'v', ttsSource: 'ai_model' });
    expect(accountVoiceDiffers(accountVoiceFromPrefs(p), p)).toBe(false);
  });

  it('is false across the vocabulary split — user_model and ai_model are not a difference', () => {
    const p = prefs({ ttsSource: 'ai_model', sttSource: 'ai_model' });
    const legacy = { chat: { tts_source: 'user_model' }, stt: { source: 'user_model' } };
    expect(accountVoiceDiffers(legacy, p)).toBe(false);
  });

  it('is true when a shared leaf actually changed', () => {
    const p = prefs({ ttsVoiceId: 'new' });
    expect(accountVoiceDiffers({ chat: { tts_voice_id: 'old' } }, p)).toBe(true);
  });

  it('ignores leaves that only exist in the voice store', () => {
    const p = prefs({ ttsSpeed: 2, vadSilenceFrames: 20 });
    expect(accountVoiceDiffers(accountVoiceFromPrefs(prefs()), p)).toBe(false);
  });
});
