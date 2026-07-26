// AI-Task Standard — the effort/reasoning level primitive, single source of truth.
// The canonical vocabulary is the UNIFIED 5-level set (off|low|medium|high|auto),
// the SAME vocabulary chat-service stores per session and accepts per message — so
// the FE dropdown, the wire, and the session default all speak one language (the
// old fast|standard|deep was a lossy 3-level FE-only reskin of this). `auto` =
// passthrough: let an adaptive model / policy self-decide (BE resolve_reasoning).

export type EffortLevel = 'off' | 'low' | 'medium' | 'high' | 'auto';

export const EFFORT_LEVELS: readonly EffortLevel[] = ['off', 'low', 'medium', 'high', 'auto'];

/** Derive the dropdown level from a session's stored reasoning_effort (already the
 *  5-level vocab), falling back to the legacy `thinking` boolean. */
export function effortLevelFromGenerationParams(
  gp?: { reasoning_effort?: string | null; thinking?: boolean | null } | null,
): EffortLevel {
  const re = gp?.reasoning_effort;
  if (re === 'off' || re === 'low' || re === 'medium' || re === 'high' || re === 'auto') return re;
  return gp?.thinking ? 'medium' : 'off';
}

/** The value persisted on the session (`generation_params.reasoning_effort`). The
 *  level IS the stored vocabulary now — identity, kept as a named seam so callers
 *  read intent, not a bare passthrough. */
export function reasoningEffortForLevel(level: EffortLevel): EffortLevel {
  return level;
}

/** The legacy `thinking` boolean the wire still carries alongside reasoning_effort.
 *  `auto` → undefined (let the model/policy decide); `off` → false; else true. */
export function thinkingForLevel(level: EffortLevel): boolean | undefined {
  if (level === 'auto') return undefined;
  return level !== 'off';
}
