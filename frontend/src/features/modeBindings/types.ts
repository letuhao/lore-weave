// M6 — the mode→capability binding settings (WS-3 / C6). A "binding" answers: when the user is in
// a given MODE (ask / write / plan), which workflows/skills does the assistant auto-seed? It is a
// per-USER setting resolved over three tiers (System defaults → the user's own → per-book), and the
// panel must show the EFFECTIVE value AND the tier it came from (Settings & Config: no silent hidden
// default) and let the user VETO a System pin (or it would be a global flag in disguise).

export type Mode = 'ask' | 'write' | 'plan';
export const MODES: Mode[] = ['ask', 'write', 'plan'];

export type Tier = 'system' | 'user' | 'book';

/** One tier's stored contribution (System is read-only to a user; they override into their own). */
export interface ModeBindingRow {
  tier: Tier;
  inject_skills: string[];
  inject_workflows: string[];
  seed_tool_categories: string[];
  disable_workflows: string[];
}

/** The resolved binding for a mode: the effective (unioned, then user-vetoed) value + its sources. */
export interface ModeBinding {
  mode: Mode;
  inject_skills: string[];
  inject_workflows: string[];
  seed_tool_categories: string[];
  disable_workflows: string[];
  sources?: Record<string, ModeBindingRow>;
}
