// AI-Task Standard — the effort/reasoning level primitive, single source of truth.
// Moved out of features/chat/ChatInputBar so BOTH the chat composer and the
// one-shot generate dialogs share ONE mapping (ChatInputBar re-exports these).

/** The effort dropdown's values. fast → thinking:false, standard → thinking:true,
 *  deep → thinking:true + reasoning_effort:"high" on the wire. */
export type EffortLevel = 'fast' | 'standard' | 'deep';

/** Derive the dropdown level from a session's granular reasoning_effort (the SSOT
 *  the settings panel writes), falling back to the legacy `thinking` boolean.
 *  high→deep, off→fast, low/medium/auto→standard. */
export function effortLevelFromGenerationParams(
  gp?: { reasoning_effort?: string | null; thinking?: boolean | null } | null,
): EffortLevel {
  const re = gp?.reasoning_effort;
  if (re === 'high') return 'deep';
  if (re === 'off') return 'fast';
  if (re === 'low' || re === 'medium' || re === 'auto') return 'standard';
  return gp?.thinking ? 'standard' : 'fast';
}

/** Session-persist mapping (the SAME generation_params key the settings panel
 *  writes, so the two surfaces can never disagree): fast→off, standard→medium,
 *  deep→high. */
export function reasoningEffortForLevel(level: EffortLevel): 'off' | 'medium' | 'high' {
  return level === 'fast' ? 'off' : level === 'deep' ? 'high' : 'medium';
}
