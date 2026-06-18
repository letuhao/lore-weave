// C22 — Intent-branching onboarding types.
// The first-run "What do you want to do?" fork presents exactly four intents.
// Each routes to a tailored surface + the right container (never a generic shell).

export type IntentId = 'write' | 'world' | 'translate' | 'explore';

/** A single intent choice as presented on the first-run screen. */
export interface IntentChoice {
  id: IntentId;
  /** Destination route — the tailored surface + container for this intent. */
  route: string;
  /** i18n key (onboarding namespace) for the choice title. */
  titleKey: string;
  /** i18n key for the one-line description. */
  descKey: string;
  /** lucide-react icon name resolved by the view. */
  icon: 'PenLine' | 'Globe2' | 'Languages' | 'Compass';
}

/** Server-side preference key persisted via /v1/me/preferences (multi-device). */
export const ONBOARDING_SEEN_PREF_KEY = 'hasSeenOnboarding';
