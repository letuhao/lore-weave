// #19 — Studio-scoped onboarding. Distinct from the global `/onboarding` intent fork
// (features/onboarding/): different pref keys, different i18n namespace (studio.intro.*),
// different purpose (role-tailoring the Welcome dock + a guided tour, not page-level routing).
export type StudioRole = 'writer' | 'worldbuilder' | 'translator' | 'enricher' | 'manager';

/** Server-side preferences via /v1/me/preferences (multi-device — never localStorage-only),
 *  same mechanism + naming convention as the existing `ONBOARDING_SEEN_PREF_KEY`. */
export const STUDIO_ONBOARDING_SEEN_PREF_KEY = 'hasSeenStudioOnboarding';
export const STUDIO_ROLE_PREF_KEY = 'studioRole';
