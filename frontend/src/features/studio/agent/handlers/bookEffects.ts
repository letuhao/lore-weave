// #09 Lane B — v1 effect handlers for book/composition draft writes. Extracts the chapter id from
// the structured MCP result and refreshes the GUI via CODE (invalidate + bus publish) — never by
// pasting the tool result body into state (G5). Registration is idempotent (guarded) so the
// reconciler can call it on every mount without duplicating handlers.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';
import { unwrapToolResult } from './resultEnvelope';

let registered = false;

function readChapterId(o: unknown): string | null {
  if (o && typeof o === 'object') {
    const r = o as Record<string, unknown>;
    if (typeof r.chapter_id === 'string') return r.chapter_id;
    if (typeof r.chapterId === 'string') return r.chapterId;
  }
  return null;
}

function chapterIdFromResult(result: unknown): string | null {
  // The live stream delivers the chat-service TOOL_CALL_RESULT envelope `{ok, result}` — the
  // domain payload (the node dump carrying chapter_id) is NESTED, and may itself still be a JSON
  // string (MCP text content). The M-E live gate caught the bare top-level read returning null →
  // Lane B never reloaded the Scene Rail (unit tests fed the payload unwrapped, so stayed green —
  // the cross-boundary-normalization bug class). See resultEnvelope.ts for the shared unwrap.
  const direct = readChapterId(result);
  if (direct) return direct;
  return readChapterId(unwrapToolResult(result));
}

/** After a book/composition draft-or-save write: refresh the affected chapter AND the manuscript
 * navigator tree. Invalidates the query cache; publishes `manuscriptChanged` so the hand-rolled tree
 * reloads (see below); reloads the Tier-4 editor hoist ONLY if that chapter is the ACTIVE unit and
 * NOT dirty (G7). It deliberately does NOT publish the `chapter` FOCUS event — that would hijack the
 * user's editor to the agent-saved chapter (the bus `chapter` slice is user-intent focus only).
 * `manuscriptChanged` is a DIFFERENT, safe event: it only bumps `manuscriptChangeSeq` → tree reload,
 * it does not move the editor. */
export function bookDraftEffect(ctx: EffectContext): void {
  const chapterId = chapterIdFromResult(ctx.result);
  if (!chapterId) return;
  ctx.queryClient.invalidateQueries({ queryKey: ['chapter', ctx.bookId, chapterId] });
  // The manuscript navigator tree is hand-rolled (NOT react-query), so invalidateQueries can't reach
  // it (the invalidatequeries-cannot-reach-hand-rolled-state class) — it reloads ONLY when
  // `manuscriptChangeSeq` bumps on the studio bus. An AGENT chapter CREATE adds a row the tree must
  // show; without this publish the rail stayed on "0 chapters" until a full page reload (dogfood
  // 2026-07-18, "Cursor-for-writing" newcomer run). Published BEFORE the G7 dirty-guard so a dirty
  // editor never blocks the tree from surfacing a newly-created sibling chapter.
  ctx.host?.publish?.({ type: 'manuscriptChanged' });
  // G7: never clobber a dirty hoist. reloadChapter is a no-op unless this IS the active unit.
  if (ctx.isChapterDirty?.(chapterId)) return;
  ctx.reloadChapter?.(chapterId);
}

/** #12 M-D — after an agent outline write (composition_outline_node_update, _create, _delete,
 * _restore, scene_link_*): refresh every outline consumer. The scenes[] hoist reload is
 * scene-only (dirty-safe, R6 — no G7 guard needed); react-query invalidation covers the
 * navigator tree + Scene Rail sources + publish-gate. */
export function outlineEffect(ctx: EffectContext): void {
  // Outline queries are keyed ['composition','outline',projectId] — prefix-invalidate them all.
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'outline'] });
  const chapterId = chapterIdFromResult(ctx.result);
  if (chapterId) ctx.reloadScenes?.(chapterId);
}

/** Idempotent — register the default studio effect handlers once. */
export function registerDefaultEffectHandlers(): void {
  if (registered) return;
  registered = true;
  // book_save_chapter_draft, book_update_chapter, composition prose WRITES (proxied draft).
  registerEffectHandler(/^book_.*(draft|chapter)/, bookDraftEffect);
  // S1-A3 fix: was /^composition_.*(prose|draft)/ — that also matched the READ `composition_get_prose`,
  // so an effect handler fired on a chatty read = query-cache thrash. Pin to the WRITE tool only
  // (composition_write_prose is the sole composition prose-write; composition_get_prose is a read).
  registerEffectHandler(/^composition_write_prose/, bookDraftEffect);
  // #12 M-D — agent outline/scene-metadata writes → Scene Rail + navigator + json-editor refresh.
  registerEffectHandler(/^composition_(outline_node|scene_link)_/, outlineEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetDefaultEffectHandlers(): void {
  registered = false;
}
