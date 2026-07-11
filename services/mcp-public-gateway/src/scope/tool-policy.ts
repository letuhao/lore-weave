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
  | 'catalog'
  // `story` — the universal manuscript-search surface (story_search, knowledge-service).
  // Added 2026-07-08 (discovery-hardening plan item 8 / external audit #6): `story` was
  // already a real, live GROUP_DIRECTORY domain on BOTH federation surfaces
  // (chat-service's tool_discovery.py + this gateway's find-tools.ts) and `story_search`
  // was already reachable on the authenticated chat surface — it was simply never added
  // to this PUBLIC-key allowlist when the 2026-07-05 search-tool-unification plan
  // promoted it to its own `story_` prefix (this file predates that plan). Confirmed an
  // incomplete rollout, not intentional tier-gating: no key, however privileged short of
  // the wildcard dev key, could ever reach it, since the Domain union itself had no
  // member for it.
  | 'story'
  // `registry` (agent-registry-service) — the skills catalog surface (registry_list_skills,
  // registry_get_skill, registry_propose_skill, registry_update_skill,
  // registry_set_skill_enabled). Added 2026-07-08 (MED-1 review finding): `registry` was
  // already a real, live federated provider (infra/docker-compose.yml
  // AI_GATEWAY_PROVIDERS=...,registry=http://agent-registry-service:8099/mcp) with real
  // Tier-R/Tier-A tools registered in services/agent-registry-service/internal/api/mcp_server.go,
  // but had NO Domain member and NO TOOL_POLICY entries — the exact same incomplete-rollout
  // shape as the `story` gap above. Confirmed an omission, not intentional gating.
  | 'registry'
  // `research` — EXTERNAL web retrieval. Added 2026-07-09 (Track D CD5 / C1 change).
  // Deliberately NOT `knowledge` (that is the INTERNAL knowledge graph). Home of the
  // universal `web_search` tool, renamed out of the `glossary_` prefix. NOTE: existing
  // public keys keep working through the retained `glossary_web_search` legacy row
  // (domains: ['glossary']); reaching the NEW name requires a `domain:research` scope.
  | 'research';

export interface ToolPolicy {
  tier: Tier;
  /** Every domain this tool reads or writes (H-F). Key must hold `domain:<d>` for all. */
  domains: Domain[];
}

/** The wildcard scope (dev/smoke static key) bypasses all scope gating. */
export const WILDCARD_SCOPE = '*';

/**
 * The consumer-local lazy-discovery meta-tool. It is ALWAYS allowed (scope-independent):
 * searching the catalogue reveals nothing on its own — the find_tools RESULT is scope-filtered
 * at the edge, and any discovered tool is still gated by `isToolAllowed` when actually called.
 * So a key may always call find_tools and always sees it in `tools/list`, regardless of scope.
 */
export const FIND_TOOLS_NAME = 'find_tools';
// WS-1a (contracts.md C2) — the deterministic discovery pair: always-allowed meta-tools whose
// RESULTS are scope-filtered (a listed/loaded tool is re-checked here when actually called).
export const TOOL_LIST_NAME = 'tool_list';
export const TOOL_LOAD_NAME = 'tool_load';

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
  kg_project_list: { tier: 'read', domains: ['knowledge'] },
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
  // the cheap single-node read (Context Budget T1) — MUST be public-reachable or
  // constrained agents fall back to list_outline (the 146K full-dump this replaces).
  composition_get_outline_node: { tier: 'read', domains: ['composition'] },
  composition_get_prose: { tier: 'read', domains: ['composition'] },
  composition_list_canon_rules: { tier: 'read', domains: ['composition'] },
  composition_get_generation_job: { tier: 'read', domains: ['composition'] },
  // composition — narrative motif library (W4+) reads. All composition-local (the
  // motif/arc graph + retrieval live in composition's own DB).
  composition_motif_search: { tier: 'read', domains: ['composition'] },
  composition_motif_get: { tier: 'read', domains: ['composition'] },
  composition_motif_suggest_for_chapter: { tier: 'read', domains: ['composition'] },
  composition_arc_suggest: { tier: 'read', domains: ['composition'] },
  composition_motif_link_list: { tier: 'read', domains: ['composition'] },
  composition_motif_book_list: { tier: 'read', domains: ['composition'] },
  composition_get_mine_job: { tier: 'read', domains: ['composition'] },
  // plan-forge (composition-service PlanForge MCP — extra prefix plan_ via ai-gateway)
  plan_validate: { tier: 'read', domains: ['composition'] },
  plan_self_check: { tier: 'read', domains: ['composition'] },
  plan_interpret_feedback: { tier: 'paid_read', domains: ['composition'] },
  // jobs (own explicit domain — never implied; edge result-filtering is H-F/P-future)
  jobs_list: { tier: 'read', domains: ['jobs'] },
  jobs_summary: { tier: 'read', domains: ['jobs'] },
  jobs_get: { tier: 'read', domains: ['jobs'] },
  // catalog (P5 OD-7 — PUBLIC discovery; owner-agnostic, returns only public books)
  catalog_list_public_books: { tier: 'read', domains: ['catalog'] },
  catalog_get_book: { tier: 'read', domains: ['catalog'] },
  // story (knowledge-service) — the universal manuscript search. Read-only, owner-scoped
  // (project_id), no different from any other read tool; added here (2026-07-08) to close
  // the incomplete-rollout gap above.
  story_search: { tier: 'read', domains: ['story'] },
  // registry (agent-registry-service) — skills catalog reads. Owner-scoped (System ∪
  // caller's own skills), same privilege class as other read tools; Tier-R/ScopeUser in
  // services/agent-registry-service/internal/api/mcp_server.go lines 22-35.
  registry_list_skills: { tier: 'read', domains: ['registry'] },
  registry_get_skill: { tier: 'read', domains: ['registry'] },
  // settings (secrets redacted upstream)
  settings_get_profile: { tier: 'read', domains: ['settings'] },
  settings_list_providers: { tier: 'read', domains: ['settings'] },
  settings_list_models: { tier: 'read', domains: ['settings'] },
  settings_get_defaults: { tier: 'read', domains: ['settings'] },
  settings_provider_inventory: { tier: 'read', domains: ['settings'] },

  // ── paid_read (Tier-R but incurs cost — needs paid_read scope; P3 spend gate) ─
  // The universal web-research tool (Track D CD5). Lives on provider-registry.
  web_search: { tier: 'paid_read', domains: ['research'] },
  // LEGACY, retained: `glossary_web_search` is the same handler, demoted in place
  // (visibility: legacy, superseded_by: web_search). Its row MUST stay — existing public
  // keys are scoped to `domain:glossary`, and dropping it here would 403 them. A key
  // scoped only to `glossary` cannot reach `web_search` (domain `research`), which is
  // precisely why the old name keeps working instead of being renamed.
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
  // jobs control (P4 slice E / H-N): an agent stops its OWN runaway job. Tier-A —
  // cancel/pause are free + reversible (no spend, no confirm). Owner-scoped on the
  // jobs-service side (anti-oracle 404 on a non-owned job).
  jobs_cancel: { tier: 'write_auto', domains: ['jobs'] },
  jobs_pause: { tier: 'write_auto', domains: ['jobs'] },
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
  // composition — motif library (W4+) auto-writes. All composition-local: create/edit/
  // archive a motif, bind/unbind a chapter (motif_bind takes role→entity ids the agent
  // supplies — it stores them, it does NOT call glossary, so no glossary domain), and the
  // motif_link graph edits (own-tier or a book's shared tier, EDIT-gated server-side).
  composition_motif_create: { tier: 'write_auto', domains: ['composition'] },
  composition_motif_patch: { tier: 'write_auto', domains: ['composition'] },
  composition_motif_archive: { tier: 'write_auto', domains: ['composition'] },
  composition_motif_bind: { tier: 'write_auto', domains: ['composition'] },
  composition_motif_unbind: { tier: 'write_auto', domains: ['composition'] },
  composition_motif_link_create: { tier: 'write_auto', domains: ['composition'] },
  composition_motif_link_delete: { tier: 'write_auto', domains: ['composition'] },
  // settings
  settings_update_profile: { tier: 'write_auto', domains: ['settings'] },
  settings_model_register: { tier: 'write_auto', domains: ['settings'] },
  settings_model_update: { tier: 'write_auto', domains: ['settings'] },
  settings_model_set_favorite: { tier: 'write_auto', domains: ['settings'] },
  settings_model_set_active: { tier: 'write_auto', domains: ['settings'] },
  settings_model_set_default: { tier: 'write_auto', domains: ['settings'] },
  // registry (agent-registry-service) — skills catalog writes are all propose→human-approve
  // (never a direct write) or a reversible own-user toggle, matching Tier-A/ScopeUser in
  // mcp_server.go lines 37-59: registry_propose_skill/registry_update_skill mint a pending
  // proposal row (nothing applied until UI approval); registry_set_skill_enabled is a
  // reversible per-user enable/disable flag (never mutates the shared skill). No-cost, no
  // confirm-token minting — same shape as other write_auto tools in this table.
  registry_propose_skill: { tier: 'write_auto', domains: ['registry'] },
  registry_update_skill: { tier: 'write_auto', domains: ['registry'] },
  registry_set_skill_enabled: { tier: 'write_auto', domains: ['registry'] },

  // ── write_confirm (Tier-W → human-approve by default; priced ones also P3) ──
  // Non-priced W
  book_chapter_publish: { tier: 'write_confirm', domains: ['book'] },
  book_chapter_unpublish: { tier: 'write_confirm', domains: ['book'] },
  // WS-0.4 — publish-independent KG indexing. domains ['book','knowledge'] per the H-F
  // rule (classify by the domains TOUCHED, not the name prefix): they are book-prefixed,
  // but their whole purpose is to write/retract the knowledge graph, so a public key must
  // hold BOTH domains.
  //
  // review-impl: both are write_confirm at the PUBLIC edge, not write_auto.
  //   book_chapter_set_kg_exclude is strictly MORE destructive than book_chapter_unpublish
  //     (which is already confirm-gated): it retracts the chapter's ENTIRE graph evidence
  //     and deletes its passages. Auto-executing it for a public key while gating the
  //     lesser op was an inversion.
  //   book_index_chapter enqueues a real Pass-2 LLM extraction on the user's BYOK model —
  //     the same spend effect as book_chapter_publish, which is confirm-gated. Unattended
  //     spend at the public edge should be a human decision.
  // (The tools' own Tier-A meta is unchanged; this is the public-edge policy only.)
  book_index_chapter: { tier: 'write_confirm', domains: ['book', 'knowledge'] },
  book_chapter_set_kg_exclude: { tier: 'write_confirm', domains: ['book', 'knowledge'] },
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
  // composition — motif library (W4+) confirm-gated writes. adopt = a tenancy/quota cross-tier
  // clone (composition-local, no LLM spend); arc_import = an LLM deconstruct of the user's own
  // imported text (composition-local). Both mint a confirm token (human-approve at the edge).
  composition_motif_adopt: { tier: 'write_confirm', domains: ['composition'] },
  composition_arc_import_analyze: { tier: 'write_confirm', domains: ['composition'] },
  // settings_model_delete is Tier-W (mints a confirm token; destructive BYOK-model
  // removal) — omitted from the original scope-map §2 audit, surfaced by the edge
  // drift-log against the live registry.
  settings_model_delete: { tier: 'write_confirm', domains: ['settings'] },
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
  // composition — motif mining + conformance: priced LLM jobs that ALSO touch knowledge
  // (mine reads the :Event beat-sequences AND writes mined_motif_code tags; conformance reads
  // the thread/causal/realized-motif tags). H-F: list BOTH domains so the key needs knowledge too.
  composition_motif_mine: { tier: 'write_confirm', domains: ['composition', 'knowledge'] },
  composition_conformance_run: { tier: 'write_confirm', domains: ['composition', 'knowledge'] },
  // plan-forge — LLM-heavy / mutating spec paths (composition domain confirm_action)
  plan_propose_spec: { tier: 'write_confirm', domains: ['composition'] },
  plan_review_checkpoint: { tier: 'write_confirm', domains: ['composition'] },
  plan_apply_revision: { tier: 'write_confirm', domains: ['composition'] },
  plan_handoff_autofix: { tier: 'write_confirm', domains: ['composition'] },
  plan_compile: { tier: 'write_confirm', domains: ['composition'] },
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
  // The discovery meta-tools are always-allowed (their results are scope-filtered; a
  // discovered/loaded tool is re-checked here when called) — permitted for every key, any scope.
  if (name === FIND_TOOLS_NAME || name === TOOL_LIST_NAME || name === TOOL_LOAD_NAME) return true;
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

/**
 * Scope-size-adaptive exposure (2026-07-07 spec, §3.3/§6/§8b.7): below this many resolved
 * TOOL_POLICY entries, `tools/list` skips the lazy-hide collapse and advertises the full
 * scope-filtered set directly — for a narrow key (e.g. 5 book-read tools) the two-hop
 * find_tools→invoke_tool dance saves nothing (the list was already small) and only adds
 * round-trips. At/above this count, today's collapse+invoke_tool path is unchanged. Picked
 * from real measured key-scope data (§3.3): 5 real keys are bimodal — 3 resolve to 5 tools,
 * 2 resolve to the full 161-tool allowlist — so any threshold in ~6–160 classifies today's
 * keys identically; 20 is a deliberately round, conservative pick pending more data.
 */
export const DIRECT_LIST_TOOL_THRESHOLD = 20;

/**
 * Count how many `TOOL_POLICY` entries `scopes` would satisfy — the input to the
 * scope-size-adaptive `tools/list` branch (spec §6). Pure, cheap (one pass over the
 * allowlist). NOT meaningful for the wildcard scope (`*` would trivially "count" every
 * entry, 161 today) — callers MUST keep the wildcard check as its own distinct, earlier
 * branch (8b.7) and never route `*` through this function's result into the size decision.
 */
export function scopeToolCount(scopes: readonly string[]): number {
  let n = 0;
  for (const name of Object.keys(TOOL_POLICY)) {
    if (isToolAllowed(name, scopes)) n++;
  }
  return n;
}
