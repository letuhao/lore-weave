// #09 Lane B — the effect registry. After an MCP domain tool SUCCEEDS, code (not the LLM) refreshes
// the GUI: invalidate queries / reload a Tier-4 hoist / publish a bus slice. Handlers extract IDs
// from the structured tool result — NEVER paste a prose body into state (G5). This is the SKELETON:
// the registry + one book-draft handler; the Tier-4 `reload` lands with #04.
import type { QueryClient } from '@tanstack/react-query';
import type { StudioHost } from '../host/StudioHostProvider';

export interface EffectContext {
  tool: string;
  result: unknown;
  bookId: string;
  host: StudioHost;
  queryClient: QueryClient;
  /** G7 DIRTY-GUARD — is this chapter's Tier-4 hoist dirty (unsaved user edits)? A reconciler
   * MUST NOT blind-reload a dirty hoist (that clobbers keystrokes). No Tier-4 hoist exists yet
   * (#04) so this is undefined → treated as clean; #04 wires the real check. */
  isChapterDirty?: (chapterId: string) => boolean;
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
