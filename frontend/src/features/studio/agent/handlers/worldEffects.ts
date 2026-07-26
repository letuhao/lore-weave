// S7 (spec 38) Lane-B effect handler for the `world-map` raster-map editor (Group B).
// Invalidates the query keys the WorldMapEditor reads (useWorldMapEditor / useWorldMaps:
// `['world-maps', worldId]` list + `['world-map', worldId, mapId]` detail) so an agent
// world_map_* write refreshes an open editor WITHOUT a manual reload — mirroring
// knowledgeEffects.ts / translationEffects.ts.
//
// SCOPE — this file owns ONLY the `world_map_*` raster domain. The Place-Graph panel (Group C)
// is refreshed by kg_* writes, which are the `knowledgeEffects` domain: its two composition
// worldmap keys were folded INTO knowledgeEffect (the integrator's resolution-(a)) rather than
// registered here as a second kg_* handler — a second kg_*-matching handler would make
// kg_create_node match 2 handlers and RED effectCoverage's `<=1` no-double-fire assertion.
// So worldEffects deliberately does NOT touch kg_* / composition keys.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

// Every world_map_* WRITE shape (book-service world_map tools): create/delete, add_marker/
// remove_marker, add_region/remove_region, and the drag/rename PATCHes update/update_marker/
// update_region. Explicit alternation with a `$` anchor so the two READS (world_map_get,
// world_map_list) do NOT match — effectCoverage's READ_TOOLS assertion reds if a read matches.
export const WORLD_MAP_WRITE_PATTERN =
  /^world_map_(create|delete|add_marker|remove_marker|add_region|remove_region|update|update_marker|update_region)$/;

let registered = false;

export function worldMapEffect(ctx: EffectContext): void {
  const { queryClient } = ctx;
  // Prefix-invalidate the maps list + the open map detail (worldId/mapId aren't in the
  // tool result, and a redundant refetch is a harmless idempotent read).
  queryClient.invalidateQueries({ queryKey: ['world-maps'] });
  queryClient.invalidateQueries({ queryKey: ['world-map'] });
}

/** Idempotent — register the world-map effect handler once. */
export function registerWorldEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(WORLD_MAP_WRITE_PATTERN, worldMapEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetWorldEffectHandlers(): void {
  registered = false;
}
