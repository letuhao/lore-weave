import type { IntentChoice, IntentId } from '../types';

// C22 — pure intent → tailored-surface mapping (BL-15 LOCKED).
// Each of the four intents lands on its OWN surface + the right container:
//   - write     → /books            (book workspace: write / continue a book)
//   - world     → /worlds           (C20/C21 world container — NO new world model)
//   - translate → /books?intent=translate  (translation surface is per-book in the
//                 workspace; ROUTE-ONLY, no new translator flow — LOCKED non-goal)
//   - explore   → /knowledge/projects (C7/C19 read-only project/graph browse)
// Pure + side-effect-free so it is trivially unit-tested and reused by the hook.

export const INTENT_CHOICES: readonly IntentChoice[] = [
  { id: 'write', route: '/books', titleKey: 'intent.write.title', descKey: 'intent.write.desc', icon: 'PenLine' },
  { id: 'world', route: '/worlds', titleKey: 'intent.world.title', descKey: 'intent.world.desc', icon: 'Globe2' },
  {
    id: 'translate',
    route: '/books?intent=translate',
    titleKey: 'intent.translate.title',
    descKey: 'intent.translate.desc',
    icon: 'Languages',
  },
  {
    id: 'explore',
    route: '/knowledge/projects',
    titleKey: 'intent.explore.title',
    descKey: 'intent.explore.desc',
    icon: 'Compass',
  },
] as const;

/** Resolve the tailored route for an intent. Throws on an unknown id (never expected). */
export function routeForIntent(id: IntentId): string {
  const choice = INTENT_CHOICES.find((c) => c.id === id);
  if (!choice) throw new Error(`unknown intent: ${id}`);
  return choice.route;
}
