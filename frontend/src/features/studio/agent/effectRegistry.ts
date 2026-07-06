// #09 Lane B — the effect registry. After an MCP domain tool SUCCEEDS, code (not the LLM) refreshes
// the GUI: invalidate queries / reload a Tier-4 hoist / publish a bus slice. Handlers extract IDs
// from the structured tool result — NEVER paste a prose body into state (G5). Real handlers are
// registered per-domain in `handlers/*.ts` (book/glossary/knowledge/translation as of 2026-07-05);
// see `useStudioEffectReconciler.ts` for the registration call sites.
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

interface Entry { pattern: string | RegExp; handler: EffectHandler; }
const registry: Entry[] = [];

/** Register a handler for a tool-name pattern (string ⇒ exact-or-prefix; RegExp ⇒ test). */
export function registerEffectHandler(pattern: string | RegExp, handler: EffectHandler): void {
  registry.push({ pattern, handler });
}

/** Test-only: drop all handlers. */
export function clearEffectHandlers(): void {
  registry.length = 0;
}

function matches(pattern: string | RegExp, tool: string): boolean {
  return typeof pattern === 'string' ? tool === pattern || tool.startsWith(pattern) : pattern.test(tool);
}

export function matchEffectHandlers(tool: string): EffectHandler[] {
  return registry.filter((e) => matches(e.pattern, tool)).map((e) => e.handler);
}

export async function runEffectHandlers(ctx: EffectContext): Promise<void> {
  for (const handler of matchEffectHandlers(ctx.tool)) {
    await handler(ctx);
  }
}
