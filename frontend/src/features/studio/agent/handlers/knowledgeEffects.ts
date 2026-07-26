// 14_kg_panels.md A4 — Lane B effect handler for kg_* MCP tool results. Invalidates the
// query keys the `knowledge` hub panel (ProjectsBrowser/useProjects) reads, plus the keys
// every future Phase-B panel already reads via its existing hook (those hooks and their
// classic-route pages exist today; only the dock panel is new) — so an agent write is
// visible WITHOUT a manual reload the moment each panel lands, mirroring glossaryEffects.ts
// (13_glossary_panels.md A5).
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

// Every kg_* write shape observed in the tool inventory (14_kg_panels.md — knowledge-service
// app/tools/{project_tools,build_tools,graph_schema_tools}.py): project_create, build_graph/
// build_wiki/run_benchmark (job triggers), propose_fact/propose_edge (triage inbox writes),
// view_upsert/view_delete, triage_resolve/triage_place_edge/triage_schema_write, schema_edit,
// adopt_template, sync_apply. Reads (project_list, graph_query, world_query, multi_query,
// entity_edge_timeline, schema_read, list_templates, sync_available, view_read, triage_list)
// are excluded so a chatty read loop doesn't thrash the query cache.
export const KNOWLEDGE_WRITE_PATTERN =
  /^kg_(?!project_list|graph_query|world_query|multi_query|entity_edge_timeline|schema_read|list_templates|sync_available|view_read|triage_list)/;

let registered = false;

export function knowledgeEffect(ctx: EffectContext): void {
  const { queryClient } = ctx;
  // Hub panel (Phase A) + project browsing.
  queryClient.invalidateQueries({ queryKey: ['knowledge-projects'] });
  // Phase-B panel surfaces — the hooks/classic routes already exist; the dock panels are new.
  queryClient.invalidateQueries({ queryKey: ['knowledge-entities'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-entity-detail'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-entity-facts'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-timeline'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-gaps'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-jobs'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-subgraph'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-proposals-inbox'] });
  // S-05 — the kg-triage panel: an agent triage_resolve/schema write clears the
  // queue, so the panel must refetch. Folded into THIS /^kg_/ handler (the one
  // home) — a second kg_*-matching handler would double-fire (effectCoverage <=1).
  queryClient.invalidateQueries({ queryKey: ['kg-triage'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-summaries'] });
  queryClient.invalidateQueries({ queryKey: ['knowledge-summary-versions'] });
  // KG schema/ontology family (kg-schema panel, Phase B).
  queryClient.invalidateQueries({ queryKey: ['kg-views'] });
  queryClient.invalidateQueries({ queryKey: ['kg-sync-available'] });
  queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] });
  queryClient.invalidateQueries({ queryKey: ['kg-graph-schema'] });
  queryClient.invalidateQueries({ queryKey: ['kg-resolved-schema'] });
  queryClient.invalidateQueries({ queryKey: ['kg-schema-usage'] });
  queryClient.invalidateQueries({ queryKey: ['kg-schema-observed'] });
  queryClient.invalidateQueries({ queryKey: ['kg-adopt-preview'] });
  // s7-4 — the Cast codex + Character-arc panels read the composition namespace
  // (`['composition','cast',…]` / `['composition','arc',…]`, useCast.ts /
  // useCharacterArc.ts), NOT the knowledge-* keys above. Without these two an
  // agent `kg_create_node` refreshes kg-entities but leaves an open cast codex
  // STALE — and the user's next rename then 412s against a version they were
  // never shown. Extend the EXISTING /^kg_/ handler (KG writes are already its
  // domain) rather than register a second one — matchEffectHandlers awaits every
  // match, so a second /^kg_/ registration would double-invalidate ("one home"
  // rule). The two keys ride the same write-only gate (KNOWLEDGE_WRITE_PATTERN
  // already excludes reads), so a chatty read loop does not thrash them.
  queryClient.invalidateQueries({ queryKey: ['composition', 'cast'] });
  queryClient.invalidateQueries({ queryKey: ['composition', 'arc'] });
  // S7-C (spec 38) — the Place-Graph panel's operable World/KG surface (PlaceGraphPanel →
  // <WorldMap>/useWorldMap) authors places/links via kg_* writes (createEntity/createRelation),
  // and reads `['composition','worldmap','places',…]` + `['composition','worldmap','detail',…]`.
  // Those are the SAME kg_* domain, so they are folded into THIS handler rather than a second
  // kg_*-matching worldEffects handler — a second match on kg_create_node would RED
  // effectCoverage's `<=1` no-double-fire assertion (integrator resolution-(a)). Disjoint from
  // the world_map_* raster keys, which worldEffects owns.
  queryClient.invalidateQueries({ queryKey: ['composition', 'worldmap', 'places'] });
  queryClient.invalidateQueries({ queryKey: ['composition', 'worldmap', 'detail'] });
}

/** Idempotent — register the knowledge effect handler once. */
export function registerKnowledgeEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(KNOWLEDGE_WRITE_PATTERN, knowledgeEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetKnowledgeEffectHandlers(): void {
  registered = false;
}
