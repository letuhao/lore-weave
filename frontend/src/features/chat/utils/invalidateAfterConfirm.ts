import type { QueryClient } from '@tanstack/react-query';

// bug #41 — after the agent commits a class-C action through a chat confirm card, the
// open viewing pages (KG ontology/graph, glossary browser) keep serving STALE react-query
// caches until a full browser refresh (F5). The GUI's own mutation hooks invalidate, but
// the chat/MCP confirm path (ConfirmActionCard / ConfirmCard / BatchConfirmCard) commits
// straight through actionsApi/glossaryApi and bypasses them. We close the gap by mapping
// the committed DOMAIN to the query-key roots it can affect and invalidating them, so the
// page refetches immediately — no F5.
//
// react-query matches a queryKey by its FIRST array element (prefix match on the array),
// and the knowledge keys are DISTINCT roots ('knowledge-subgraph' is not under
// 'knowledge'), so we invalidate via a `predicate` that string-prefixes the first key
// element — one rule covers every kg-*/knowledge-* / glossary-* variant.
const DOMAIN_KEY_PREFIXES: Record<string, string[]> = {
  // kg_schema_edit / kg_adopt / kg_sync_apply / kg_triage_* → the schema, resolved
  // schema, views, sync/adopt previews, and every knowledge-graph read.
  kg: ['kg-', 'knowledge'],
  // glossary kinds/attributes/entities/merge/summarize → the glossary browser + ontology,
  // and the KG-anchored-glossary read that mirrors a glossary entry into the graph view.
  glossary: ['glossary-', 'kg-anchored'],
  book: ['book'],
  composition: ['composition'],
  translation: ['translation'],
  settings: ['me-preferences', 'preferences'],
};

/** Invalidate the react-query caches a committed confirm-card action can have changed.
 *  Accepts one domain or the union of domains a batch committed. Safe no-op for an
 *  unknown domain (nothing to invalidate). */
export function invalidateAfterConfirm(
  queryClient: QueryClient,
  domains: string | string[],
): void {
  const list = Array.isArray(domains) ? domains : [domains];
  const prefixes = new Set<string>();
  for (const d of list) for (const p of DOMAIN_KEY_PREFIXES[d] ?? []) prefixes.add(p);
  if (prefixes.size === 0) return;
  const roots = [...prefixes];
  void queryClient.invalidateQueries({
    predicate: (query) => {
      const head = String(query.queryKey?.[0] ?? '');
      return roots.some((pre) => head.startsWith(pre));
    },
  });
}
