// The ONE system-prompt preset list (spec 2026-07-05-chat-ai-settings.md §3.3, §8).
//
// It used to be two client-side constants that had silently diverged:
//   NewChatDialog        → 4 presets, keys `novel|translator|worldbuilder|editor`
//   SessionSettingsPanel → 6 presets, keys `Custom|Novelist|Translator|Worldbuilder|Editor|Analyst`
// Different keys, different capitalisation, and different prompt TEXT for the "same"
// role — so the prompt you got when creating a chat was not the prompt the settings
// panel would show you as that preset. Picking "Novelist" in the panel silently
// replaced the prompt "novel" had seeded.
//
// Per §3.3 these stay a client-side seed constant — NOT a resolvable tier and NOT a
// user-authorable store (a shared preset row would need `UNIQUE(owner_user_id, code)`
// and admin-only System rows; explicitly out of scope). A "Custom" prompt persists as
// the resolved `system_prompt` string on whichever tier the user edited.
//
// `CUSTOM_PRESET_KEY` is a UI sentinel, not a preset: it means "the prompt does not
// match any preset". It is never written as a prompt.

export const CUSTOM_PRESET_KEY = 'custom';

export type PromptPreset = {
  /** Stable, lowercase id. Persisted nowhere — only the resolved prompt text is. */
  key: string;
  icon: string;
  /** i18n key `chat:presets.<key>`; the English label is the fallback. */
  label: string;
  prompt: string;
};

export const PROMPT_PRESETS: readonly PromptPreset[] = [
  {
    key: 'novelist',
    icon: '📖',
    label: 'Novelist',
    prompt:
      'You are a creative writing assistant specializing in novels. Analyze character arcs, plot structure, and worldbuilding with a focus on internal consistency. When suggesting changes, provide concrete scene rewrites.',
  },
  {
    key: 'translator',
    icon: '🌐',
    label: 'Translator',
    prompt:
      'You are a literary translator. Preserve the tone, style, and nuance of the original text. Explain translation choices when they involve cultural adaptation or idiomatic expressions.',
  },
  {
    key: 'worldbuilder',
    icon: '🗺️',
    label: 'Worldbuilder',
    prompt:
      'You are a worldbuilding consultant for fantasy and sci-fi settings. Help create consistent magic systems, political structures, geography, and cultural details. Flag inconsistencies.',
  },
  {
    key: 'editor',
    icon: '✏️',
    label: 'Editor',
    prompt:
      'You are a professional book editor. Focus on pacing, dialogue quality, show-vs-tell, and narrative voice. Be specific and constructive in feedback.',
  },
  {
    key: 'analyst',
    icon: '🔍',
    label: 'Analyst',
    prompt:
      'You are a literary analyst. Examine themes, symbolism, narrative techniques, and character psychology. Support observations with textual evidence.',
  },
] as const;

/** The preset whose prompt matches `prompt` exactly, or null ("custom"/unset). */
export function presetForPrompt(prompt: string | null | undefined): PromptPreset | null {
  if (!prompt) return null;
  return PROMPT_PRESETS.find((p) => p.prompt === prompt) ?? null;
}

/** The prompt text for a key. `CUSTOM_PRESET_KEY` and unknown keys yield null —
 *  selecting "Custom" must never overwrite what the user typed. */
export function promptForPreset(key: string): string | null {
  if (key === CUSTOM_PRESET_KEY) return null;
  return PROMPT_PRESETS.find((p) => p.key === key)?.prompt ?? null;
}
