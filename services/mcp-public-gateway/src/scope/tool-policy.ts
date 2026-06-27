/**
 * Authoritative public-MCP tool scope-map (edge enforcement of PUB-3 / H-E / H-F).
 *
 * Source of truth: docs/specs/2026-06-26-public-mcp/05-tool-scope-map.md §2.
 *
 * This table is an ALLOWLIST: a tool is reachable by a public key ONLY if it has an
 * entry here AND the key holds the entry's `tier` scope plus a `domain:<d>` scope for
 * EVERY domain the tool touches. Any tool NOT in this table is denied by absence
 * (H-E — default-deny unknown / fail-closed). Admin, secret-create, and owner-only
 * destructive tools (book_delete/purge) are intentionally ABSENT, never granted.
 *
 * Domains are classified by *tools-touched, not prefix* (H-F): a tool that writes
 * another domain (e.g. translation_start_extraction → glossary) lists BOTH domains,
 * so the key must hold both. `jobs`/`settings` are their own explicit domain and are
 * never implied by any other (H-F / H-S).
 */

export type Tier = 'read' | 'paid_read' | 'write_auto' | 'write_confirm';

export type Domain =
  | 'book'
  | 'glossary'
  | 'knowledge'
  | 'translation'
  | 'composition'
  | 'jobs'
  | 'settings'
  | 'lore_enrichment'
  | 'catalog';

export interface ToolPolicy {
  tier: Tier;
  /** Every domain this tool reads or writes (H-F). Key must hold `domain:<d>` for all. */
  domains: Domain[];
}

/** The wildcard scope (dev/smoke static key) bypasses all scope gating. */
export const WILDCARD_SCOPE = '*';

/** Build the `domain:<d>` scope string the key must carry to reach domain `d`. */
export function domainScope(d: Domain): string {
  return `domain:${d}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// The allowlist. Keep aligned with scope-map §2; a NEW federated tool absent here
// is denied + logged (drift signal) until classified.
// ─────────────────────────────────────────────────────────────────────────────
export const TOOL_POLICY: Record<string, ToolPolicy> = {
  // ── read (Tier-R, no cost) ────────────────────────────────────────────────
  // book
  book_list: { tier: 'read', domains: ['book'] },
  book_get: { tier: 'read', domains: ['book'] },
  book_list_chapters: { tier: 'read', domains: ['book'] },
  book_get_chapter: { tier: 'read', domains: ['book'] },
  book_list_revisions: { tier: 'read', domains: ['book'] },
  // glossary
  glossary_search: { tier: 'read', domains: ['glossary'] },
  glossary_get_entity: { tier: 'read', domains: ['glossary'] },
  glossary_list_system_standards: { tier: 'read', domains: ['glossary'] },
  glossary_book_ontology_read: { tier: 'read', domains: ['glossary'] },
  glossary_entity_get_genres: { tier: 'read', domains: ['glossary'] },
  glossary_list_merge_candidates: { tier: 'read', domains: ['glossary'] },
  glossary_list_chapter_links: { tier: 'read', domains: ['glossary'] },
  glossary_list_entity_revisions: { tier: 'read', domains: ['glossary'] },
  glossary_list_unknown_entities: { tier: 'read', domains: ['glossary'] },
  glossary_get_entity_evidence: { tier: 'read', domains: ['glossary'] },
  glossary_list_ai_suggestions: { tier: 'read', domains: ['glossary'] },
  glossary_book_sync_available: { tier: 'read', domains: ['glossary'] },
  glossary_user_standards_read: { tier: 'read', domains: ['glossary'] },
  // knowledge (memory_* now H-U-guarded; all owner-checked)
  kg_graph_query: { tier: 'read', domains: ['knowledge'] },
  kg_entity_edge_timeline: { tier: 'read', domains: ['knowledge'] },
  kg_schema_read: { tier: 'read', domains: ['knowledge'] },
  kg_list_templates: { tier: 'read', domains: ['knowledge'] },
  kg_sync_available: { tier: 'read', domains: ['knowledge'] },
  kg_view_read: { tier: 'read', domains: ['knowledge'] },
  kg_triage_list: { tier: 'read', domains: ['knowledge'] },
  memory_search: { tier: 'read', domains: ['knowledge'] },
  memory_recall_entity: { tier: 'read', domains: ['knowledge'] },
  memory_timeline: { tier: 'read', domains: ['knowledge'] },
  // translation
  translation_coverage: { tier: 'read', domains: ['translation'] },
  translation_segment_status: { tier: 'read', domains: ['translation'] },
  translation_list_versions: { tier: 'read', domains: ['translation'] },
  translation_job_status: { tier: 'read', domains: ['translation'] },
  // composition
  composition_get_work: { tier: 'read', domains: ['composition'] },
  composition_list_outline: { tier: 'read', domains: ['composition'] },
  composition_get_prose: { tier: 'read', domains: ['composition'] },
  composition_list_canon_rules: { tier: 'read', domains: ['composition'] },
  composition_get_generation_job: { tier: 'read', domains: ['composition'] },
  // jobs (own explicit domain — never implied; edge result-filtering is H-F/P-future)
  jobs_list: { tier: 'read', domains: ['jobs'] },
  jobs_summary: { tier: 'read', domains: ['jobs'] },
  jobs_get: { tier: 'read', domains: ['jobs'] },
  // settings (secrets redacted upstream)
  settings_get_profile: { tier: 'read', domains: ['settings'] },
  settings_list_providers: { tier: 'read', domains: ['settings'] },
  settings_list_models: { tier: 'read', domains: ['settings'] },
  settings_get_defaults: { tier: 'read', domains: ['settings'] },
  settings_provider_inventory: { tier: 'read', domains: ['settings'] },

  // ── paid_read (Tier-R but incurs cost — needs paid_read scope; P3 spend gate) ─
  glossary_web_search: { tier: 'paid_read', domains: ['glossary'] },

  // ── write_auto (Tier-A, no cost) ──────────────────────────────────────────
  // book
  book_create: { tier: 'write_auto', domains: ['book'] },
  book_update_meta: { tier: 'write_auto', domains: ['book'] },
  book_chapter_create: { tier: 'write_auto', domains: ['book'] },
  book_chapter_bulk_create: { tier: 'write_auto', domains: ['book'] },
  book_chapter_update_meta: { tier: 'write_auto', domains: ['book'] },
  book_chapter_restore_revision: { tier: 'write_auto', domains: ['book'] },
  book_chapter_save_draft: { tier: 'write_auto', domains: ['book'] },
  // glossary
  glossary_book_create: { tier: 'write_auto', domains: ['glossary'] },
  glossary_book_patch: { tier: 'write_auto', domains: ['glossary'] },
  glossary_book_set_active_genres: { tier: 'write_auto', domains: ['glossary'] },
  glossary_book_set_kind_genres: { tier: 'write_auto', domains: ['glossary'] },
  glossary_entity_set_genres: { tier: 'write_auto', domains: ['glossary'] },
  glossary_create_chapter_link: { tier: 'write_auto', domains: ['glossary'] },
  glossary_create_evidence: { tier: 'write_auto', domains: ['glossary'] },
  glossary_propose_new_entity: { tier: 'write_auto', domains: ['glossary'] },
  glossary_propose_translation: { tier: 'write_auto', domains: ['glossary'] },
  glossary_propose_aliases: { tier: 'write_auto', domains: ['glossary'] },
  glossary_user_create: { tier: 'write_auto', domains: ['glossary'] },
  glossary_user_patch: { tier: 'write_auto', domains: ['glossary'] },
  glossary_user_delete: { tier: 'write_auto', domains: ['glossary'] },
  glossary_user_restore: { tier: 'write_auto', domains: ['glossary'] },
  // knowledge
  kg_view_upsert: { tier: 'write_auto', domains: ['knowledge'] },
  kg_view_delete: { tier: 'write_auto', domains: ['knowledge'] },
  kg_triage_resolve: { tier: 'write_auto', domains: ['knowledge'] },
  kg_triage_place_edge: { tier: 'write_auto', domains: ['knowledge'] },
  kg_adopt_template: { tier: 'write_auto', domains: ['knowledge'] },
  kg_sync_apply: { tier: 'write_auto', domains: ['knowledge'] },
  memory_remember: { tier: 'write_auto', domains: ['knowledge'] },
  memory_forget: { tier: 'write_auto', domains: ['knowledge'] },
  // translation (job_control cancel/pause is Tier-A; resume/retry's cost is gated
  // by the P3 incurs_cost spend-check, not the tier scope)
  translation_set_active_version: { tier: 'write_auto', domains: ['translation'] },
  translation_save_edited_version: { tier: 'write_auto', domains: ['translation'] },
  translation_patch_block: { tier: 'write_auto', domains: ['translation'] },
  translation_update_settings: { tier: 'write_auto', domains: ['translation'] },
  translation_job_control: { tier: 'write_auto', domains: ['translation'] },
  // composition
  composition_create_work: { tier: 'write_auto', domains: ['composition'] },
  composition_outline_node_create: { tier: 'write_auto', domains: ['composition'] },
  composition_outline_node_update: { tier: 'write_auto', domains: ['composition'] },
  composition_outline_node_delete: { tier: 'write_auto', domains: ['composition'] },
  composition_outline_node_restore: { tier: 'write_auto', domains: ['composition'] },
  composition_scene_link_create: { tier: 'write_auto', domains: ['composition'] },
  composition_scene_link_delete: { tier: 'write_auto', domains: ['composition'] },
  composition_canon_rule_create: { tier: 'write_auto', domains: ['composition'] },
  composition_canon_rule_update: { tier: 'write_auto', domains: ['composition'] },
  composition_canon_rule_delete: { tier: 'write_auto', domains: ['composition'] },
  composition_write_prose: { tier: 'write_auto', domains: ['composition'] },
  // settings
  settings_update_profile: { tier: 'write_auto', domains: ['settings'] },
  settings_model_register: { tier: 'write_auto', domains: ['settings'] },
  settings_model_update: { tier: 'write_auto', domains: ['settings'] },
  settings_model_set_favorite: { tier: 'write_auto', domains: ['settings'] },
  settings_model_set_active: { tier: 'write_auto', domains: ['settings'] },
  settings_model_set_default: { tier: 'write_auto', domains: ['settings'] },

  // ── write_confirm (Tier-W → human-approve by default; priced ones also P3) ──
  // Non-priced W
  book_chapter_publish: { tier: 'write_confirm', domains: ['book'] },
  book_chapter_unpublish: { tier: 'write_confirm', domains: ['book'] },
  book_chapter_delete: { tier: 'write_confirm', domains: ['book'] },
  book_chapter_purge: { tier: 'write_confirm', domains: ['book'] },
  glossary_adopt_standards: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_book_delete: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_book_revert: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_status_change: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_restore_revision: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_reassign_kind: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_merge: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_new_kind: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_kinds: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_propose_new_attribute: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_book_sync_apply: { tier: 'write_confirm', domains: ['glossary'] },
  kg_propose_fact: { tier: 'write_confirm', domains: ['knowledge'] },
  kg_propose_edge: { tier: 'write_confirm', domains: ['knowledge'] },
  kg_schema_edit: { tier: 'write_confirm', domains: ['knowledge'] },
  kg_triage_schema_write: { tier: 'write_confirm', domains: ['knowledge'] },
  kg_project_create: { tier: 'write_confirm', domains: ['knowledge'] },
  composition_publish: { tier: 'write_confirm', domains: ['composition'] },
  // Priced W (BYOK + spend pre-check at P3; cross-domain by tools-touched — H-F)
  translation_start_job: { tier: 'write_confirm', domains: ['translation'] },
  translation_retranslate_dirty: { tier: 'write_confirm', domains: ['translation'] },
  translation_start_extraction: { tier: 'write_confirm', domains: ['translation', 'glossary'] },
  glossary_plan: { tier: 'write_confirm', domains: ['glossary'] },
  glossary_deep_research: { tier: 'write_confirm', domains: ['glossary'] },
  kg_build_graph: { tier: 'write_confirm', domains: ['knowledge'] },
  kg_build_wiki: { tier: 'write_confirm', domains: ['knowledge'] },
  kg_run_benchmark: { tier: 'write_confirm', domains: ['knowledge'] },
  composition_generate: { tier: 'write_confirm', domains: ['composition', 'glossary', 'knowledge'] },
  // lore-enrichment: reclassified priced+confirm for public (NOT write_auto — a paid
  // auto-tool violates the money model); cross-domain by tools-touched.
  lore_enrichment_auto_enrich: { tier: 'write_confirm', domains: ['lore_enrichment', 'glossary', 'knowledge'] },
};

/** True iff the tool has an explicit policy entry (i.e. is classified, not unknown). */
export function knownTool(name: string): boolean {
  return Object.prototype.hasOwnProperty.call(TOOL_POLICY, name);
}

/**
 * Default-deny scope check. Returns true ONLY when the key may call `name`:
 *   - `*` wildcard scope → always true (dev/smoke key)
 *   - tool must be in the allowlist (H-E: unknown → false)
 *   - key must hold the tool's tier scope
 *   - key must hold `domain:<d>` for EVERY domain the tool touches (H-F)
 * A key with no `domain:*` scope can reach nothing (fail-closed, by the loop below).
 */
export function isToolAllowed(name: string, scopes: readonly string[]): boolean {
  if (scopes.includes(WILDCARD_SCOPE)) return true;
  const pol = TOOL_POLICY[name];
  if (!pol) return false;
  if (!scopes.includes(pol.tier)) return false;
  for (const d of pol.domains) {
    if (!scopes.includes(domainScope(d))) return false;
  }
  return true;
}

/** Filter an advertised tool list down to what the key may call (default-deny). */
export function filterTools<T extends { name?: unknown }>(tools: T[], scopes: readonly string[]): T[] {
  if (scopes.includes(WILDCARD_SCOPE)) return tools;
  return tools.filter((t) => typeof t?.name === 'string' && isToolAllowed(t.name, scopes));
}
