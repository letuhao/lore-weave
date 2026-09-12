// T6 — the ✨ narration-attach button used to `return` in silence on five separate branches and
// fire a raw English `alert()` on a sixth, so it looked active and did nothing. A 2026-09-06
// human-sim run toggled it, saw no generation UI at all, and recorded the feature as broken.
//
// These pin the two properties that make that impossible to repeat: every blocked state is
// NAMED, and every name has a message.
import { describe, expect, it } from 'vitest';
import {
  resolveTtsBlocker,
  TTS_BLOCKER_MESSAGES,
  type TtsBlocker,
} from '../AudioAttachActionsExtension';

const ok = {
  currentPos: 3,
  hasContext: true,
  ttsModelId: 'model-1',
  hasNode: true,
  text: 'the gate of ash',
  language: 'vi',
};

describe('resolveTtsBlocker (T6)', () => {
  it('returns null — and ONLY null — when every precondition is met', () => {
    expect(resolveTtsBlocker(ok)).toBeNull();
  });

  it('names a caret outside any block', () => {
    expect(resolveTtsBlocker({ ...ok, currentPos: -1 })).toBe('no-block');
  });

  it('names a missing upload context (editor still loading)', () => {
    expect(resolveTtsBlocker({ ...ok, hasContext: false })).toBe('no-context');
  });

  it('names a missing TTS model — this was the raw alert()', () => {
    expect(resolveTtsBlocker({ ...ok, ttsModelId: null })).toBe('no-tts-model');
  });

  it('names a block that has no text', () => {
    expect(resolveTtsBlocker({ ...ok, text: '   ' })).toBe('empty-block');
  });

  // The one that was not merely silent but WRONG: the old code sent `language: 'en'`
  // unconditionally, generating English audio for a Vietnamese manuscript.
  it('refuses rather than defaulting the language to English', () => {
    expect(resolveTtsBlocker({ ...ok, language: undefined })).toBe('no-language');
  });

  it('passes the book language through untouched when present (never normalised to en)', () => {
    expect(resolveTtsBlocker({ ...ok, language: 'vi' })).toBeNull();
    expect(resolveTtsBlocker({ ...ok, language: 'ja' })).toBeNull();
  });

  // NV-3 — a message table that covers only the blockers someone remembered is default-uncovered
  // for the next one added. Drive the assertion off the type's own members.
  it('every blocker has a user-facing message', () => {
    const all: Exclude<TtsBlocker, null>[] = [
      'no-block', 'no-context', 'no-tts-model', 'empty-block', 'no-language',
    ];
    for (const b of all) {
      expect(TTS_BLOCKER_MESSAGES[b], `no message for ${b}`).toBeTruthy();
      expect(TTS_BLOCKER_MESSAGES[b].key).toMatch(/^audio\./);
      expect(TTS_BLOCKER_MESSAGES[b].fallback.length).toBeGreaterThan(10);
    }
    // …and the table carries nothing BEYOND the known blockers, so a stale entry can't hide here.
    expect(Object.keys(TTS_BLOCKER_MESSAGES).sort()).toEqual([...all].sort());
  });
});
