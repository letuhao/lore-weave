// 13_glossary_panels.md A5 — Lane B effect handler for glossary_* MCP tool results. Invalidates
// every query key the `glossary` panel (GlossaryEntityList) and the classic GlossaryTab page
// read through, so an agent write is visible WITHOUT a manual reload (spec 12's LIVE gate).
// Also reloads the entity-editor hoist if its modal happens to be open for the affected entity
// (G7 dirty-safe — see reloadBoundGlossaryEntity).
import { registerEffectHandler, type EffectContext } from '../effectRegistry';
import { unwrapToolResult } from './resultEnvelope';
import { reloadBoundGlossaryEntity } from '@/features/glossary/documents/entityDocument';

// Every glossary_* write shape observed in the tool inventory (13_glossary_panels.md A5):
// propose_* (ontology/entity/merge/status/translation proposals), book_* admin writes
// (patch/delete/revert/set_*_genres/sync_apply — sync_available is a read but the harmless
// over-invalidation isn't worth hand-excluding one dry-run tool), entity_set_genres,
// create_chapter_link, create_evidence, adopt_standards, admin_*/user_* CRUD. Reads
// (get_/list_/search/deep_research/web_search) are excluded so a chatty read loop doesn't
// thrash the query cache. Exported so tests can assert the pattern without fighting the
// registry's module-level idempotency guard below.
export const GLOSSARY_WRITE_PATTERN = /^glossary_(?!get_|list_|search|deep_research|web_search)/;

let registered = false;

function readEntityIdDirect(o: unknown): string | null {
  if (o && typeof o === 'object') {
    const r = o as Record<string, unknown>;
    if (typeof r.entity_id === 'string') return r.entity_id;
    if (typeof r.entityId === 'string') return r.entityId;
  }
  return null;
}

// M-E class (resultEnvelope.ts) — the live stream wraps the domain payload in `{ok, result}`,
// possibly with `.result` itself a JSON string. /review-impl caught this handler missing the
// same unwrap bookEffects.ts already needed; the flat-mock trap it warns about is exactly what
// let glossaryEffects.test.ts stay green while this was broken.
function readEntityId(result: unknown): string | null {
  const direct = readEntityIdDirect(result);
  if (direct) return direct;
  return readEntityIdDirect(unwrapToolResult(result));
}

export function glossaryEffect(ctx: EffectContext): void {
  const { bookId, queryClient } = ctx;
  queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });
  queryClient.invalidateQueries({ queryKey: ['glossary-translation-languages', bookId] });
  queryClient.invalidateQueries({ queryKey: ['glossary-ontology', bookId] });
  queryClient.invalidateQueries({ queryKey: ['glossary-kinds'] });
  queryClient.invalidateQueries({ queryKey: ['glossary-unknown', bookId] });
  queryClient.invalidateQueries({ queryKey: ['glossary-ai-suggestions', bookId] });
  queryClient.invalidateQueries({ queryKey: ['glossary-merge-candidates', bookId] });

  const entityId = readEntityId(ctx.result);
  if (entityId) reloadBoundGlossaryEntity(entityId);
}

/** Idempotent — register the glossary effect handler once. */
export function registerGlossaryEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(GLOSSARY_WRITE_PATTERN, glossaryEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetGlossaryEffectHandlers(): void {
  registered = false;
}
