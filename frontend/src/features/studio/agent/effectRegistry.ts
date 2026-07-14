// #09 Lane B — the effect registry. After an MCP domain tool SUCCEEDS, code (not the LLM) refreshes
// the GUI: invalidate queries / reload a Tier-4 hoist / publish a bus slice. Handlers extract IDs
// from the structured tool result — NEVER paste a prose body into state (G5).
//
// Handlers are registered per-domain in `handlers/*.ts`; §8.0b of spec 30 is the ONE-FILE-PER-DOMAIN
// owner map. Registration goes through the `handlers/index.ts` barrel. Coverage is machine-checked by
// `__tests__/effectCoverage.contract.test.ts` — DO NOT ADD A DOMAIN WITHOUT A ROW THERE.
//
// ⚠ `matchEffectHandlers` returns EVERY match and `runEffectHandlers` awaits ALL of them, so two files
// registering one domain do NOT shadow — they DOUBLE-FIRE. The ledger asserts <=1 handler per tool.
import type { QueryClient } from '@tanstack/react-query';
import type { StudioHost } from '../host/StudioHostProvider';

export interface EffectContext {
  tool: string;
  result: unknown;
  bookId: string;
  host: StudioHost;
  queryClient: QueryClient;
  /** G7 DIRTY-GUARD — is this chapter's Tier-4 hoist dirty (unsaved user edits)? A reconciler
   * MUST NOT blind-reload a dirty hoist (that clobbers keystrokes). */
  isChapterDirty?: (chapterId: string) => boolean;
  /** Reload the Tier-4 unit for this chapter IF it is the active unit (else a no-op). The
   * reconciler supplies it from useManuscriptUnit; absent when no editor is mounted. */
  reloadChapter?: (chapterId: string) => void;
  /** #12 M-D — reload ONLY the unit's scenes[] buffer for this chapter (active unit only).
   * Dirty-safe by construction (never touches the body buffers — R6), so no G7 guard. */
  reloadScenes?: (chapterId: string) => void;
}

export type EffectHandler = (ctx: EffectContext) => void | Promise<void>;

interface Entry { pattern: RegExp; handler: EffectHandler; }
const registry: Entry[] = [];

/** Register a handler for a tool-name RegExp (anchored, e.g. /^composition_arc_/).
 *  Strings are REJECTED — see plan 30 §8.0b. */
export function registerEffectHandler(pattern: RegExp, handler: EffectHandler): void {
  // X-4.0 — the string branch is DELETED, not documented. It was `tool === p || tool.startsWith(p)`:
  // exact-or-prefix, NOT a pattern. tsc now rejects a string, but TS types are ERASED — an `as any`
  // or a JS caller must still fail LOUDLY, because a silently-unmatched handler is invisible
  // (runEffectHandlers only iterates MATCHING handlers, so a no-op registration raises nothing).
  if (!(pattern instanceof RegExp)) {
    throw new Error(
      `registerEffectHandler: pattern must be a RegExp, got ${typeof pattern}. A string was exact-or-prefix, `
      + `NOT a pattern — 'composition_(style|voice)_' would have matched NOTHING and shipped a silent no-op handler.`,
    );
  }
  if (pattern.global) {
    throw new Error(
      'registerEffectHandler: pattern must not use the /g flag — RegExp.test() with /g advances lastIndex '
      + 'and alternates true/false across calls.',
    );
  }
  registry.push({ pattern, handler });
}

/** Test-only: drop all handlers. */
export function clearEffectHandlers(): void {
  registry.length = 0;
}

/** Test-only: the registered patterns (the coverage ledger reads this). */
export function listEffectHandlers(): readonly Entry[] {
  return registry;
}

export function matchEffectHandlers(tool: string): EffectHandler[] {
  return registry.filter((e) => e.pattern.test(tool)).map((e) => e.handler);
}

export async function runEffectHandlers(ctx: EffectContext): Promise<void> {
  for (const handler of matchEffectHandlers(ctx.tool)) {
    await handler(ctx);
  }
}
