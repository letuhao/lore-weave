// One preset list, one vocabulary (spec §8 "unify the 6-vs-4 preset lists into one PRESETS").
//
// NewChatDialog declared 4 presets keyed `novel|translator|worldbuilder|editor`;
// SessionSettingsPanel declared 6 keyed `Custom|Novelist|Translator|Worldbuilder|Editor|Analyst`.
// Different keys, different capitalisation, and different prompt TEXT for the same role —
// so the prompt a new chat was seeded with was NOT the prompt the settings panel showed
// under that name, and re-picking it there silently rewrote the user's system prompt.
import { describe, it, expect } from 'vitest';
import {
  PROMPT_PRESETS,
  CUSTOM_PRESET_KEY,
  presetForPrompt,
  promptForPreset,
} from '../presets';

describe('PROMPT_PRESETS', () => {
  it('is the single list both surfaces use, with unique lowercase keys', () => {
    const keys = PROMPT_PRESETS.map((p) => p.key);
    expect(keys).toEqual(['novelist', 'translator', 'worldbuilder', 'editor', 'analyst']);
    expect(new Set(keys).size).toBe(keys.length);
    for (const k of keys) expect(k).toBe(k.toLowerCase());
  });

  it('never contains the Custom sentinel — Custom is a UI state, not a preset', () => {
    expect(PROMPT_PRESETS.some((p) => p.key === CUSTOM_PRESET_KEY)).toBe(false);
  });

  it('every preset carries a non-empty prompt, icon and label', () => {
    for (const p of PROMPT_PRESETS) {
      expect(p.prompt.length).toBeGreaterThan(40);
      expect(p.icon).toBeTruthy();
      expect(p.label).toBeTruthy();
    }
  });

  it('no two presets share a prompt — otherwise presetForPrompt is ambiguous', () => {
    const prompts = PROMPT_PRESETS.map((p) => p.prompt);
    expect(new Set(prompts).size).toBe(prompts.length);
  });
});

describe('promptForPreset', () => {
  it('returns the exact prompt for a known key', () => {
    expect(promptForPreset('novelist')).toBe(PROMPT_PRESETS[0].prompt);
  });

  it('returns null for Custom — selecting it must NEVER overwrite what the user typed', () => {
    expect(promptForPreset(CUSTOM_PRESET_KEY)).toBeNull();
  });

  it('returns null for an unknown key rather than an empty prompt', () => {
    // The old panel mapped `Custom: ''`, so choosing it wiped the prompt.
    expect(promptForPreset('nonsense')).toBeNull();
  });
});

describe('presetForPrompt', () => {
  it('round-trips every preset', () => {
    for (const p of PROMPT_PRESETS) {
      expect(presetForPrompt(p.prompt)?.key).toBe(p.key);
    }
  });

  it('is null for a hand-written prompt (that is what "Custom" means)', () => {
    expect(presetForPrompt('write like a pirate')).toBeNull();
    expect(presetForPrompt('')).toBeNull();
    expect(presetForPrompt(null)).toBeNull();
    expect(presetForPrompt(undefined)).toBeNull();
  });
});
