// #09 Lane B — v1 effect handlers for book/composition draft writes. Extracts the chapter id from
// the structured MCP result and refreshes the GUI via CODE (invalidate + bus publish) — never by
// pasting the tool result body into state (G5). Registration is idempotent (guarded) so the
// reconciler can call it on every mount without duplicating handlers.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

function chapterIdFromResult(result: unknown): string | null {
  if (result && typeof result === 'object') {
    const r = result as Record<string, unknown>;
    if (typeof r.chapter_id === 'string') return r.chapter_id;
    if (typeof r.chapterId === 'string') return r.chapterId;
  }
  return null;
}

/** After a book/composition draft-or-save write: refresh the affected chapter. Invalidates the
 * query cache always; reloads the Tier-4 editor hoist ONLY if that chapter is the ACTIVE unit and
 * NOT dirty (G7). It deliberately does NOT publish a `chapter` bus event — that would hijack the
 * user's editor to the agent-saved chapter (the bus `chapter` slice is user-intent focus only). */
export function bookDraftEffect(ctx: EffectContext): void {
  const chapterId = chapterIdFromResult(ctx.result);
  if (!chapterId) return;
  ctx.queryClient.invalidateQueries({ queryKey: ['chapter', ctx.bookId, chapterId] });
  // G7: never clobber a dirty hoist. reloadChapter is a no-op unless this IS the active unit.
  if (ctx.isChapterDirty?.(chapterId)) return;
  ctx.reloadChapter?.(chapterId);
}

/** Idempotent — register the default studio effect handlers once. */
export function registerDefaultEffectHandlers(): void {
  if (registered) return;
  registered = true;
  // book_save_chapter_draft, book_update_chapter, composition_* prose writes (proxied draft).
  registerEffectHandler(/^book_.*(draft|chapter)/, bookDraftEffect);
  registerEffectHandler(/^composition_.*(prose|draft)/, bookDraftEffect);
}
