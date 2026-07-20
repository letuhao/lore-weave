/**
 * find_tools — the canonical lazy-discovery meta-tool (shared source of truth).
 *
 * At ~200+ federated tools, advertising the full catalogue to an agent is context bloat +
 * degraded selection. Instead the agent SEARCHES with `find_tools` and only the matched tools
 * become callable. This is the gateway-side twin of chat-service's `tool_discovery.py` — the
 * SAME token-overlap + strong-fuzzy-rescue algorithm — so both surfaces rank identically.
 *
 * Operates on the MCP-native tool shape the federation catalogue holds
 * (`{ name, description, inputSchema, _meta? }`) — NOT the OpenAI function wrapper. `find_tools`
 * is consumer-local (OD-1): it reads only the catalogue, never a provider, so it carries no
 * user-data envelope and needs no ownership guard.
 */

export const FIND_TOOLS_NAME = 'find_tools';
export const FIND_TOOLS_DEFAULT_LIMIT = 8;

/** Below this best score the result is "low confidence" — the agent may search once more. */
const CONFIDENCE_THRESHOLD = 0.3;
/** A tool must score at least this to appear at all — keeps pure-noise near-misses out so a
 * true "no such tool" reads as empty (anti-false-suggestion), not a bogus match. */
const INCLUSION_FLOOR = 0.2;

// Part A (tool-catalog-simplification spec) — the tool-group directory. Mirrors chat-service's
// tool_discovery.py GROUP_DIRECTORY verbatim; keep the two in lockstep (same rule as the search
// algorithm itself). Injected as plain text alongside a surface's core tools, not as schemas.
export const GROUP_DIRECTORY: Readonly<Record<string, string>> = {
  glossary: 'Lore entities (characters/locations/items/kinds) — CRUD + wiki + standards ontology.',
  // `book_get_chapter` is prefix `book_`, not `story_` — it lives in "book" below; the group
  // filter is prefix-based (see `providerPrefix`), so this entry must only claim tools this
  // group's search can actually surface.
  story: 'Manuscript search (story_search).',
  composition: 'Outline/scene/canon planning — Story Grid rules, motif/arc library.',
  knowledge: 'Derived KG facts (Neo4j-backed), passage retrieval, memory_search.',
  translation: 'Job-based chapter/book translation pipeline.',
  book: 'Book/chapter CRUD, publishing, chapter body reads (incl. book_get_chapter).',
  // W10 worldbuilding — book-service's SECOND federated namespace (world_*, world_map_*).
  // A distinct group from `book` (prose): worlds are prose-less containers + reference
  // maps. `domainOf` maps the `world_` prefix straight here (no DOMAIN_ALIASES entry
  // needed — the prefix already equals the group name). Without this entry the tools
  // reach the raw catalog but are NOT enumerable by group and are excluded from
  // `book`. Keep in lockstep with chat-service tool_discovery.py GROUP_DIRECTORY.
  world: 'Worldbuilding containers + reference maps — world create/get/list/move, plus map/marker/region authoring (world_*, world_map_*).',
  jobs: 'Job status/cancel for any long-running operation.',
  catalog: 'Public catalog browsing (published books, discovery).',
  registry: 'Agent/tool registry administration.',
  settings: 'User/account settings and provider-model configuration.',
  // Track D CD5/C1: EXTERNAL retrieval (`web_search`, prefix `web_` → alias below).
  // Deliberately NOT folded into `knowledge`, which is the INTERNAL knowledge graph.
  research: 'External web research — search the open web for background facts (web_search). PAID.',
  // PlanForge tools federate under their own `plan_` prefix (composition-service's M4
  // federation contract), NOT `composition_` — mirrors chat-service's tool_discovery.py.
  plan: 'Novel planning workflow — PlanForge propose/refine/validate/compile (plan_propose_spec, plan_self_check, plan_interpret_feedback, plan_apply_revision, plan_review_checkpoint, plan_handoff_autofix, plan_validate, plan_compile).',
};

/** The MCP tool def for find_tools, advertised on every minimal surface.
 *
 * Design item 1 (2026-07-07 discovery-hardening plan) reworded this description twice over:
 * (1) it now tells the caller about the enumeration affordance (`group` + no `intent` lists
 * everything in a domain — external audit #5, "no list-all-tools-in-a-domain affordance"); (2) it
 * DROPS the old unconditional "if it returns nothing useful, try once more... before telling the
 * user you can't" invitation — that unbounded retry bias is exactly what let one real session hit
 * 40 `find_tools` iterations / 53.8s / a 0-length final answer (see the plan's Problem section).
 * The retry-cap machinery below (`FindToolsAttemptTracker`) is what actually bounds it; the
 * wording here just stops encouraging the failure mode in the first place. */
export const FIND_TOOLS_TOOL = {
  name: FIND_TOOLS_NAME,
  description:
    'OPTIONAL (legacy) intent search for tools — PREFER `tool_list`/`tool_load`, which are ' +
    "deterministic and complete. Use `find_tools` only when you don't know which category fits and " +
    'want to search by intent (e.g. editing a book, starting a translation, ' +
    'building a knowledge graph). Pass `group` (a tool domain) with `intent` omitted or empty to ' +
    'list EVERY tool in that domain, unranked — the fastest way to check whether a whole domain ' +
    'has what you need. With `intent` set, returns the best-matching tool names + descriptions; ' +
    'matched tools become callable next. If `group` is set and your query scores weak or empty ' +
    'against it, you automatically get the FULL domain list instead of a poor guess — no need to ' +
    'retry with different wording first. Without `group`, an empty/weak `intent` instead returns ' +
    'the tool-domain directory so you can pick one and search again scoped to it. If a second ' +
    "attempt on the same ask ALSO comes back empty or weak, stop searching and tell the user this " +
    "isn't supported rather than guessing again.",
  inputSchema: {
    type: 'object',
    properties: {
      intent: { type: 'string', description: 'What you want to do, in your own words.' },
      // MED-3 (review-impl, 2026-07-08): `limit` only applies to the ranked/fuzzy search path.
      // Enumeration mode (`group` set, `intent` empty) deliberately IGNORES it and returns the
      // full domain list — see `enumerateGroup`'s doc comment for why capping would defeat the
      // point of the affordance. Documented here so the caller (and the model reading this
      // schema) isn't surprised that a `limit` passed alongside a bare `group` has no effect.
      limit: {
        type: 'integer',
        description: 'Max tools to return (default 8). Applies only when `intent` is set — ignored during group-enumeration (bare `group`, no `intent`), which always returns the full domain list.',
        default: FIND_TOOLS_DEFAULT_LIMIT,
      },
      group: {
        type: 'string',
        enum: Object.keys(GROUP_DIRECTORY).sort(),
        description: 'Optional — scope the search to one tool domain from your tool-domain directory. Omit to search everything.',
      },
    },
    required: ['intent'],
    additionalProperties: false,
  },
  // C-TOOL — declared, not inferred. These three are pure disclosure over the catalog:
  // they execute nothing and take no scope key. Without an explicit tier they relied on
  // the consumer's silent "R" default (tool_tier()) — the exact hole the per-service wire
  // gates exist to close, and why a federated tools/list showed 3 untiered tools. They are
  // consumer-local, so no domain service's gate ever covered them.
  _meta: { tier: 'R', scope: 'none' },
} as const;

interface McpTool {
  name?: unknown;
  description?: unknown;
  _meta?: { synonyms?: unknown } | unknown;
}

export interface ToolMatch {
  name: string;
  description: string;
}

export function toolName(t: McpTool): string {
  return typeof t?.name === 'string' ? t.name : '';
}

function toolDescription(t: McpTool): string {
  return typeof t?.description === 'string' ? t.description : '';
}

function toolSynonyms(t: McpTool): string[] {
  const meta = t?._meta;
  const syn = meta && typeof meta === 'object' ? (meta as { synonyms?: unknown }).synonyms : undefined;
  return Array.isArray(syn) ? syn.filter((s): s is string => typeof s === 'string') : [];
}

const VISIBILITY_LEGACY = 'legacy';

/** CAT-4 (mcp-tool-io.md Part 4) — `_meta.visibility` ∈ discoverable|legacy. Defaults to
 * "discoverable" when absent, so every pre-CAT-4 tool is unaffected without a code change. */
function toolVisibility(t: McpTool): string {
  const meta = t?._meta;
  const vis = meta && typeof meta === 'object' ? (meta as { visibility?: unknown }).visibility : undefined;
  return vis === VISIBILITY_LEGACY ? VISIBILITY_LEGACY : 'discoverable';
}

function isLegacyTool(t: McpTool): boolean {
  return toolVisibility(t) === VISIBILITY_LEGACY;
}

// ── Track A / WS-0 · visible-set + deprecated-LABELING (contracts.md C2) ──────────────────────
//
// The discovery-drift class (feedback capstone): a tool tagged `_meta.visibility:"legacy"` is
// DROPPED from `find_tools` search + enumeration (above) yet still policy-allowed at raw
// `tools/call` — so it is invisible-but-callable, and an agent can never be redirected from it.
// The fix (WS-0): a deterministic visible-set that LABELS deprecated tools (`deprecated` +
// `superseded_by`) instead of hiding them, so `tool_list` can show + redirect rather than drop.
// This is additive — `searchCatalog`/`enumerateGroup` keep dropping legacy (you don't want a
// deprecated tool RANKED in fuzzy search); `visibleTools` is the new, separate consumer `tool_list`
// (WS-1a) reads. The policy-allowed ∩ of the C2 visible-set is applied at the public edge
// (mcp-public-gateway), which is the only layer that holds the key's scope.

/** `_meta.tier` ∈ R|A|W|S, defaulting to R (read/inert) when absent — mirrors chat-service's
 * tool_discovery tier default. A missing tier must NEVER read as a write. */
function toolTier(t: McpTool): 'R' | 'A' | 'W' | 'S' {
  const meta = t?._meta;
  const tier = meta && typeof meta === 'object' ? (meta as { tier?: unknown }).tier : undefined;
  return tier === 'A' || tier === 'W' || tier === 'S' ? tier : 'R';
}

/** `_meta.superseded_by` — the replacement a deprecated tool points at, so `tool_list` can name it. */
function toolSupersededBy(t: McpTool): string | undefined {
  const meta = t?._meta;
  const s = meta && typeof meta === 'object' ? (meta as { superseded_by?: unknown }).superseded_by : undefined;
  return typeof s === 'string' && s.length > 0 ? s : undefined;
}

export interface VisibleTool {
  name: string;
  description: string;
  tier: 'R' | 'A' | 'W' | 'S';
  deprecated?: boolean;
  superseded_by?: string;
}

/**
 * The deterministic, complete visible set for `tool_list` (contracts.md C2). Returns EVERY tool
 * (optionally scoped to one `group`), unranked, in catalog order — legacy tools LABELED
 * `deprecated:true` (+ `superseded_by`) rather than dropped. `includeDeprecated=false` filters
 * them out entirely. Does NOT apply the policy-allowed intersection — that is the public edge's
 * job (it holds the key scope); this layer contributes `catalog ∩ (non-legacy OR includeDeprecated)`.
 */
export function visibleTools(
  catalog: McpTool[],
  group?: string | null,
  includeDeprecated = true,
  exclude: ReadonlySet<string> = new Set(),
): VisibleTool[] {
  const out: VisibleTool[] = [];
  for (const t of catalog) {
    const name = toolName(t);
    if (!name || exclude.has(name)) continue;
    if (group != null && domainOf(name) !== group) continue;
    const deprecated = isLegacyTool(t);
    if (deprecated && !includeDeprecated) continue;
    const entry: VisibleTool = { name, description: toolDescription(t), tier: toolTier(t) };
    if (deprecated) {
      entry.deprecated = true;
      const sb = toolSupersededBy(t);
      if (sb) entry.superseded_by = sb;
    }
    out.push(entry);
  }
  return out;
}

/** Domain prefix of a tool name (`glossary_book_patch` → `glossary`), the same federation
 * naming convention chat-service's `_provider_prefix` reads. Used for Part A `group` scoping. */
function providerPrefix(name: string): string {
  const i = name.indexOf('_');
  return i > 0 ? name.slice(0, i) : '';
}

/** The "knowledge" GROUP_DIRECTORY entry covers two literal prefixes (`kg_*`, `memory_*`)
 * under one conceptual domain — mirrors chat-service's `_DOMAIN_ALIASES`/`_domain_of`
 * (tool_discovery.py), found + fixed together 2026-07-07: without this, `providerPrefix`
 * alone made `find_tools(group="knowledge")` match nothing, since neither literal prefix
 * equals the domain name "knowledge". Keep in lockstep with the Python side. */
// WS-0 (contracts.md C1): `lore_enrichment_auto_enrich` (prefix `lore`) — the one orphan tool with no
// GROUP_DIRECTORY home — folds into `glossary`. Keep in lockstep with tool_discovery.py `_DOMAIN_ALIASES`.
// Track D: `web_search` (prefix `web`) → the `research` group (EXTERNAL retrieval, not the internal KG).
const DOMAIN_ALIASES: Readonly<Record<string, string>> = {
  kg: 'knowledge',
  memory: 'knowledge',
  lore: 'glossary',
  web: 'research',
};

function domainOf(name: string): string {
  const prefix = providerPrefix(name);
  return DOMAIN_ALIASES[prefix] ?? prefix;
}

const TOKEN_RE = /[a-z0-9]+/g;

function tokens(text: string): Set<string> {
  return new Set((text || '').toLowerCase().match(TOKEN_RE) ?? []);
}

/** difflib SequenceMatcher.ratio() equivalent (Python's gestalt ratio): 2*M / T where M is the
 * total matched chars across the recursive longest-match decomposition and T is the combined
 * length. Used only as a STRONG (≥0.8) near-spelling rescue, so an exact port isn't required —
 * but matching the algorithm keeps the gateway + chat-service rankings identical. */
function ratio(a: string, b: string): number {
  if (!a.length && !b.length) return 1;
  const matches = matchedChars(a, b);
  return (2 * matches) / (a.length + b.length);
}

function matchedChars(a: string, b: string): number {
  if (!a.length || !b.length) return 0;
  // Longest common contiguous block, then recurse on the left + right remainders (gestalt).
  let bestI = 0;
  let bestJ = 0;
  let bestLen = 0;
  const j2len = new Array<number>(b.length + 1).fill(0);
  for (let i = 0; i < a.length; i++) {
    const newj2len = new Array<number>(b.length + 1).fill(0);
    for (let j = 0; j < b.length; j++) {
      if (a[i] === b[j]) {
        const k = (j > 0 ? j2len[j] : 0) + 1;
        newj2len[j + 1] = k;
        if (k > bestLen) {
          bestI = i - k + 1;
          bestJ = j - k + 1;
          bestLen = k;
        }
      }
    }
    for (let j = 0; j <= b.length; j++) j2len[j] = newj2len[j];
  }
  if (bestLen === 0) return 0;
  return (
    bestLen +
    matchedChars(a.slice(0, bestI), b.slice(0, bestJ)) +
    matchedChars(a.slice(bestI + bestLen), b.slice(bestJ + bestLen))
  );
}

/** Heuristic relevance score in [0,1] of a tool for an intent: token overlap (dominant) over
 * name + description + synonyms, with a strong-fuzzy rescue on the name/synonym tokens. */
function score(intentTokens: Set<string>, t: McpTool): number {
  if (intentTokens.size === 0) return 0;
  const name = toolName(t);
  const desc = toolDescription(t);
  const syn = toolSynonyms(t);
  const synText = syn.join(' ');
  // The name often encodes the verb (book_create, translation_start_job) — split snake_case.
  const hayTokens = tokens(`${name.replace(/_/g, ' ')} ${desc} ${synText}`);
  let overlap = 0;
  for (const it of intentTokens) if (hayTokens.has(it)) overlap++;
  const tokenScore = overlap / intentTokens.size;

  // difflib near-miss rescue, per token, against the name + synonym tokens only (more
  // discriminating than the whole raw string). Only a STRONG hit (≥0.8) rescues a no-overlap tool.
  const targetTokens = tokens(`${name} ${synText}`);
  let best = 0;
  for (const it of intentTokens) {
    for (const tt of targetTokens) {
      const r = ratio(it, tt);
      if (r > best) best = r;
    }
  }
  // review-impl live-verification fix (2026-07-06, mirrors tool_discovery.py) — the
  // "rescues a no-overlap tool" precondition was documented but never enforced: an
  // EXACT single-token overlap (ratio=1.0 for identical strings) always qualified as
  // a "strong fuzzy hit," so one incidental shared word (e.g. "book") could override
  // tokenScore to a perfect 1.0 for an otherwise-unrelated tool. Live-verified at the
  // real ~190-tool federated catalog scale (invisible in the small offline eval).
  const fuzzy = overlap === 0 && best >= 0.8 ? best : 0;
  return Math.max(tokenScore, fuzzy);
}

/**
 * Fuzzy-search the catalogue for tools matching `intent`. Returns `{matches, confident}`:
 * `matches` are up to `limit` `{name, description}` (names + descriptions only — the full
 * schemas are advertised once the names are activated); `confident` is false when empty or the
 * best score is below the confidence threshold (the agent may search once more).
 * `exclude` — names already advertised (the core), so a search never re-suggests them.
 */
export function searchCatalog(
  catalog: McpTool[],
  intent: string,
  limit: number = FIND_TOOLS_DEFAULT_LIMIT,
  exclude: ReadonlySet<string> = new Set(),
  group?: string | null,
): { matches: ToolMatch[]; confident: boolean } {
  const intentTokens = tokens(intent);
  const scored: Array<{ s: number; t: McpTool }> = [];
  for (const t of catalog) {
    const name = toolName(t);
    if (!name || exclude.has(name) || isLegacyTool(t)) continue;
    if (group != null && domainOf(name) !== group) continue;
    const s = score(intentTokens, t);
    if (s >= INCLUSION_FLOOR) scored.push({ s, t });
  }
  scored.sort((a, b) => b.s - a.s);
  const top = scored.slice(0, Math.max(1, limit));
  const matches = top.map(({ t }) => ({ name: toolName(t), description: toolDescription(t) }));
  const confident = scored.length > 0 && scored[0].s >= CONFIDENCE_THRESHOLD;
  return { matches: scored.length ? matches : [], confident };
}

/**
 * True per-domain enumeration (design item 1, external audit #1/#5 — "find_tools under-returns
 * on generic queries" / "no list-all-tools-in-a-domain affordance"). `searchCatalog` degrades to a
 * zero-token, zero-result search on an empty `intent` (`score()` returns 0 for an empty token
 * set) — the caller can never tell "this domain truly has nothing" from "my wording didn't
 * overlap enough tokens". This is the true fix: when the caller already knows the domain
 * (`group`), return EVERY non-legacy tool in it, UNRANKED (catalog order — no score, no sort; a
 * sort would itself be an implicit rank) and UNFILTERED by `INCLUSION_FLOOR`/`CONFIDENCE_THRESHOLD`
 * — mirrors what `GROUP_DIRECTORY` already does one level up (domain-level enumeration).
 *
 * MED-3 (review-impl, 2026-07-08) — deliberately takes NO `limit` param and applies none. The
 * whole point of this affordance (per the design plan's Layer A section) is "give the model a
 * COMPLETE list, unranked, unfiltered by score floor" so it can reliably tell "this domain truly
 * has nothing" from "my wording didn't overlap enough tokens." Capping the result here would
 * silently reintroduce exactly that ambiguity for any domain past the cap (composition ~37+,
 * glossary ~41+ tools measured at real catalog scale) — the opposite of what this mode exists to
 * fix. `FIND_TOOLS_TOOL.inputSchema.properties.limit`'s description says as much for the caller.
 * Mirrors chat-service's `enumerate_group` (`tool_discovery.py`), which likewise takes no `limit`.
 */
export function enumerateGroup(
  catalog: McpTool[],
  group: string,
  exclude: ReadonlySet<string> = new Set(),
): ToolMatch[] {
  const out: ToolMatch[] = [];
  for (const t of catalog) {
    const name = toolName(t);
    if (!name || exclude.has(name) || isLegacyTool(t)) continue;
    if (domainOf(name) !== group) continue;
    out.push({ name, description: toolDescription(t) });
  }
  return out;
}

// ── Track A / WS-1a · tool_list + tool_load (contracts.md C2) ────────────────────────────────
//
// The deterministic discovery pair that replaces mandatory `find_tools` semantic search. `tool_list`
// enumerates a category COMPLETELY (no ranking, no similarity floor) so an agent — including a
// mid-tier model — can reliably see what it can do instead of guessing query wording. `tool_load`
// pulls the exact input schema(s) by name/category (progressive disclosure) and, on the public edge,
// marks them activated so a raw `tools/call` is permitted. `find_tools` stays as an OPTIONAL
// convenience (OQ1) — never the sole gate.

/** `all` sentinel + the C1 category enum, single-sourced from GROUP_DIRECTORY. */
export const CATEGORY_ENUM: readonly string[] = [...Object.keys(GROUP_DIRECTORY).sort(), 'all'];

function toolInputSchema(t: McpTool): unknown {
  const s = (t as { inputSchema?: unknown }).inputSchema;
  return s ?? { type: 'object', properties: {} };
}

export const TOOL_LIST_NAME = 'tool_list';
export const TOOL_LOAD_NAME = 'tool_load';

export const TOOL_LIST_TOOL = {
  name: TOOL_LIST_NAME,
  description:
    'List EVERY tool in a category (or "all"), complete and deterministic — the reliable way to see ' +
    'what you can do here. Prefer this over find_tools when you know the rough area. Returns ' +
    '{name, description, tier} per tool; deprecated tools are labeled with their replacement. Then ' +
    'call tool_load(name) to get a tool’s exact arguments before using it.',
  inputSchema: {
    type: 'object',
    properties: {
      category: {
        type: 'string',
        enum: CATEGORY_ENUM,
        description: 'A tool domain, or "all" for the whole catalog. Omit = all.',
      },
      include_deprecated: {
        type: 'boolean',
        description: 'Include deprecated tools (shown labeled). Default true.',
        default: true,
      },
    },
    additionalProperties: false,
  },
  // C-TOOL — declared, not inferred. These three are pure disclosure over the catalog:
  // they execute nothing and take no scope key. Without an explicit tier they relied on
  // the consumer's silent "R" default (tool_tier()) — the exact hole the per-service wire
  // gates exist to close, and why a federated tools/list showed 3 untiered tools. They are
  // consumer-local, so no domain service's gate ever covered them.
  _meta: { tier: 'R', scope: 'none' },
} as const;

export const TOOL_LOAD_TOOL = {
  name: TOOL_LOAD_NAME,
  description:
    'Load the exact input schema(s) for one or more tools — by `name`, a list of `names`, or every ' +
    'tool in a `category` — so you can call them correctly. Loading makes them callable; it does ' +
    'NOT run anything. Use it after tool_list to pick tools by name.',
  inputSchema: {
    type: 'object',
    properties: {
      name: { type: 'string', description: 'A single tool name.' },
      names: { type: 'array', items: { type: 'string' }, description: 'Several tool names.' },
      category: { type: 'string', enum: CATEGORY_ENUM, description: 'Load every tool in this category.' },
    },
    additionalProperties: false,
  },
  // C-TOOL — declared, not inferred. These three are pure disclosure over the catalog:
  // they execute nothing and take no scope key. Without an explicit tier they relied on
  // the consumer's silent "R" default (tool_tier()) — the exact hole the per-service wire
  // gates exist to close, and why a federated tools/list showed 3 untiered tools. They are
  // consumer-local, so no domain service's gate ever covered them.
  _meta: { tier: 'R', scope: 'none' },
} as const;

/** Build the `tool_list` payload (contracts.md C2). `category` omitted or "all" → the whole visible
 * catalog grouped by category; a specific category → its flat `tools` list (+ a `reason` when empty
 * so a caller can tell "no tools" from a bad guess — the public edge upgrades this to
 * "gated: requires <scope>" when policy is what emptied it). Deterministic, unranked. */
export function toolListResult(
  catalog: McpTool[],
  category?: string | null,
  includeDeprecated = true,
  exclude: ReadonlySet<string> = new Set(),
): { payload: Record<string, unknown> } {
  if (category == null || category === 'all') {
    const tools = visibleTools(catalog, null, includeDeprecated, exclude);
    const categories: Record<string, VisibleTool[]> = {};
    for (const t of tools) (categories[domainOf(t.name)] ??= []).push(t);
    return { payload: { categories, count: tools.length } };
  }
  const tools = visibleTools(catalog, category, includeDeprecated, exclude);
  const payload: Record<string, unknown> = { category, count: tools.length, tools };
  if (tools.length === 0) payload.reason = 'no tools currently available in this category';
  return { payload };
}

interface LoadedTool extends VisibleTool {
  input_schema: unknown;
}

/** Build the `tool_load` payload + the names to activate (contracts.md C2). Pure disclosure —
 * returns full `inputSchema`(s); executes nothing. Unknown requested names come back under
 * `not_found` (a deterministic answer, never a silent drop). */
export function toolLoadResult(
  catalog: McpTool[],
  opts: { name?: string | null; names?: string[] | null; category?: string | null },
): { payload: Record<string, unknown>; loadedNames: string[] } {
  const want = new Set<string>();
  if (opts.name) want.add(opts.name);
  for (const n of opts.names ?? []) if (n) want.add(n);
  const wholeCatalog = opts.category === 'all';
  const byCategory = opts.category && opts.category !== 'all' ? opts.category : null;

  const loaded: LoadedTool[] = [];
  const seen = new Set<string>();
  for (const t of catalog) {
    const name = toolName(t);
    if (!name || seen.has(name)) continue;
    const match = want.has(name) || wholeCatalog || (byCategory != null && domainOf(name) === byCategory);
    if (!match) continue;
    seen.add(name);
    const entry: LoadedTool = {
      name,
      description: toolDescription(t),
      tier: toolTier(t),
      input_schema: toolInputSchema(t),
    };
    if (isLegacyTool(t)) {
      entry.deprecated = true;
      const sb = toolSupersededBy(t);
      if (sb) entry.superseded_by = sb;
    }
    loaded.push(entry);
  }
  const payload: Record<string, unknown> = { tools: loaded };
  const missing = [...want].filter((n) => !seen.has(n));
  if (missing.length) payload.not_found = missing.sort();
  return { payload, loadedNames: loaded.map((t) => t.name) };
}

// ── Retry-cap (design item 1) — bounds the unbounded-retry bias ─────────────────────────
//
// `mcp.controller.ts` is deliberately stateless per HTTP request ("one request == one call" — a
// fresh proxy Server + transport every time), so there is no per-connection object to hang a
// per-turn counter off. The closest stable key across the several `find_tools` calls one logical
// exchange makes is the caller-supplied `X-Session-Id` envelope header (the same header
// `federation.service.ts` forwards to providers as the tenancy/session identity) — tracked here
// as an in-PROCESS, TTL-bounded map, the same shape as `overlay.ts`'s `PerUserOverlay` cache /
// `egress.ts`'s `CircuitBreaker` state (the house pattern for "bounded in-memory state keyed by an
// envelope field"). A caller with no session id is never tracked (fail-open, same discipline as
// the overlay cache — a caller we can't key can't be safely capped without risking cross-talk).
const RETRY_WINDOW_MS = 10 * 60 * 1000; // bounds one exchange's worth of guessing, not a whole day
const RETRY_REPEAT_AT = 2; // the 2nd attempt at the same (group, intent) this window is a "repeat"

interface AttemptEntry {
  count: number;
  exp: number;
}

/** Per-session tracker of prior `(group, normalized-intent)` `find_tools` attempts. A repeated or
 * near-duplicate call — SAME group + a token-set-equal intent (order/casing/punctuation-
 * insensitive, the same `tokens()` splitter `searchCatalog` scores with, so "search the web" and
 * "web search" collide) — reports `isRepeat: true`, the signal `findToolsResult` uses to stop
 * inviting further guessing and instead permit "tell the user this isn't supported".
 *
 * MULTI-REPLICA LIMITATION (review-impl HIGH-1/MED-2, 2026-07-08): this is a process-wide
 * in-memory singleton (see `findToolsAttempts` below). `mcp.controller.ts` documents this service
 * as deliberately stateless per-request specifically so it scales horizontally — but this tracker
 * is NOT stateless: if ai-gateway ever runs >1 replica, each replica holds its own independent,
 * always-reset counter, so a client whose calls round-robin across replicas silently never hits
 * the repeat threshold. Effective per-process only. A shared store (e.g. Redis) would be needed
 * for this cap to hold under >1 replica — currently NOT implemented, tracked as a known
 * limitation, not a bug to silently work around. */
export class FindToolsAttemptTracker {
  private readonly sessions = new Map<string, Map<string, AttemptEntry>>();
  constructor(
    private readonly ttlMs: number = RETRY_WINDOW_MS,
    private readonly now: () => number = Date.now,
  ) {}

  private static key(group: string | null | undefined, intent: string): string {
    const toks = Array.from(tokens(intent)).sort().join(' ');
    return `${group ?? ''}\x00${toks}`;
  }

  /** Record this attempt for `sessionId` and report whether it is a REPEAT. Blank/enumeration
   * calls (no intent to guess with) are never tracked — there is no "wording" to repeat. Also
   * opportunistically evicts expired entries so the map never grows unbounded across a
   * long-lived MCP client (amortized on ANY incoming call, no global sweep timer needed).
   *
   * HIGH-1 fix (review-impl, 2026-07-08): the sweep used to prune only the CURRENT session's own
   * bucket — the top-level `sessions` map itself never shrank, so every distinct session id ever
   * seen leaked a bucket for the life of the process, unbounded by however many session ids the
   * caller of `/mcp` produces (not guaranteed to be a small finite set). A narrower fix that only
   * swept the current caller's own bucket turns out to be observably inert: a call that finds its
   * own bucket newly-empty always re-populates it before returning (this method never returns
   * without recording something once past the guard above), so the top-level key for THAT session
   * is back immediately — no net shrinkage. The actual fix has to be a SWEEP OF EVERY tracked
   * session, piggybacked on each incoming call: for every session's bucket, drop expired entries,
   * then drop the top-level session key if that leaves it empty. This is O(sessions currently
   * tracked) per call, but that count is itself bounded by "distinct sessions active within the
   * last TTL window" — the busier the tracker gets, the more aggressively each new call prunes it,
   * so it can never grow without bound the way the un-swept version could. Cost is negligible at
   * the cardinalities this tracker sees (session ids scoped to one exchange, TTL = 10 minutes).
   *
   * MUST stay synchronous — no `await` anywhere in this method, including during the sweep — the
   * whole thing runs to completion on Node's single thread before any other call can interleave.
   * If this ever moves to a shared store (Redis, see the multi-replica note above), a
   * check-then-act race becomes possible and needs its own guard (e.g. an atomic INCR or a Lua
   * script), and a full per-call sweep would also need to become a lazy/TTL-native expiry instead
   * (e.g. Redis `EXPIRE`), not a scan over every key on every call. */
  record(sessionId: string | null | undefined, group: string | null | undefined, intent: string): boolean {
    if (!sessionId || !intent.trim()) return false;
    const now = this.now();
    for (const [sid, sessionBucket] of this.sessions) {
      for (const [k, v] of sessionBucket) {
        if (v.exp <= now) sessionBucket.delete(k);
      }
      if (sessionBucket.size === 0) {
        this.sessions.delete(sid);
      }
    }
    let bucket = this.sessions.get(sessionId);
    if (!bucket) {
      bucket = new Map();
      this.sessions.set(sessionId, bucket);
    }
    const key = FindToolsAttemptTracker.key(group, intent);
    const existing = bucket.get(key);
    if (existing) {
      existing.count += 1;
      existing.exp = now + this.ttlMs;
      return existing.count >= RETRY_REPEAT_AT;
    }
    bucket.set(key, { count: 1, exp: now + this.ttlMs });
    return false;
  }

  /** Test-only accessor — mirrors the pattern other bounded in-memory state classes in this
   * codebase would expose for inspection (`CircuitBreaker`/`PerUserOverlay`'s internal maps). NOT
   * used by production code; lets tests assert the top-level map actually shrinks back down after
   * entries expire, not just that lookups still behave correctly. */
  get sessionCount(): number {
    return this.sessions.size;
  }
}

/** Process-wide singleton shared across all MCP requests — the per-HTTP-request statelessness is
 * at the transport/Server layer (`mcp.controller.ts`), not this tracker. See the MULTI-REPLICA
 * LIMITATION note on the class above: this cap only holds within a single ai-gateway process. */
export const findToolsAttempts = new FindToolsAttemptTracker();

/**
 * Build the find_tools RESULT payload + the matched names. Distinguishes (H10) a genuinely
 * empty result from one whose only plausible providers are temporarily unavailable — so the
 * agent says "try again", never a false "I can't".
 *
 * `group` + a blank/missing `intent` switches to enumeration mode (see `enumerateGroup` above)
 * instead of falling through to a zero-token fuzzy search. `isRepeatAttempt` (from
 * `FindToolsAttemptTracker`) reshapes the empty/weak-match note so a 2nd+ near-duplicate call
 * explicitly permits concluding "not supported" instead of inviting yet another guess.
 *
 * 2026-07-08 re-verification pass (external audit #1/#5) — two further gaps closed, mirroring
 * chat-service's `tool_discovery.py` (kept in lockstep, same discipline as GROUP_DIRECTORY/domainOf):
 * (1) NO `group` + blank `intent` used to fall straight through to `searchCatalog('')` (0 matches,
 * generic "No tool matched" note) — chat-service's Python side already had a dedicated directive
 * here that TS never mirrored; now returns the `GROUP_DIRECTORY` listing so the caller has a
 * concrete next step instead of a bare scold. (2) `group` set + a NON-blank but low-signal/generic
 * `intent` (e.g. "list everything you can do in this domain") scores below `CONFIDENCE_THRESHOLD`
 * and silently under-returned (measured: `book` → 1/~15 tools, 7% recall, for exactly this shape —
 * the ORIGINAL enumeration-mode fix never fired since the caller's intent wasn't literally blank).
 * Now falls back to full enumeration just like a literal blank intent would.
 */
export function findToolsResult(
  catalog: McpTool[],
  intent: string,
  limit: number,
  exclude: ReadonlySet<string>,
  unavailableProviders: string[],
  group?: string | null,
  isRepeatAttempt = false,
): { payload: Record<string, unknown>; matchedNames: string[] } {
  const hasGroup = typeof group === 'string' && group.length > 0;
  const blankIntent = !intent.trim();

  if (!hasGroup && blankIntent) {
    return {
      payload: {
        tools: [],
        domains: { ...GROUP_DIRECTORY },
        note:
          '`intent` was missing/empty and no `group` was given either — pick a domain from ' +
          '`domains` above and call find_tools again with that `group` (leave `intent` empty to ' +
          'list everything in it, unranked), or describe what you want to do in your own words as ' +
          'a non-empty `intent`.',
      },
      matchedNames: [],
    };
  }

  const enumerationMode = hasGroup && blankIntent;
  const { matches, confident } = enumerationMode
    ? { matches: enumerateGroup(catalog, group as string, exclude), confident: true }
    : searchCatalog(catalog, intent, limit, exclude, group);

  if (hasGroup && !blankIntent && !confident) {
    const fullList = enumerateGroup(catalog, group as string, exclude);
    const payload: Record<string, unknown> = { tools: fullList, enumerated: true };
    payload.note =
      fullList.length === 0
        ? `The "${group}" domain genuinely has no tools right now — this capability isn't supported; no need to keep searching.`
        : `Your query didn't score well against anything specific in the "${group}" domain — ` +
          'showing the FULL domain list instead of a weak/empty guess. Pick whichever tool(s) actually fit.';
    return { payload, matchedNames: fullList.map((m) => m.name) };
  }

  const payload: Record<string, unknown> = { tools: matches };
  if (enumerationMode) {
    // Signals to the caller (and to tests) that this list is the full, unranked domain
    // enumeration, not a scored search result.
    payload.enumerated = true;
  }
  if (matches.length === 0) {
    if (unavailableProviders.length > 0) {
      payload.unavailable_providers = [...unavailableProviders].sort();
      payload.note =
        'No matching tool is currently available. One or more services are temporarily ' +
        'unavailable — tell the user the capability exists but to try again shortly; do NOT say ' +
        "you can't do it.";
    } else if (enumerationMode) {
      payload.note = `The "${group}" domain genuinely has no tools right now — this capability isn't supported; no need to keep searching.`;
    } else if (isRepeatAttempt) {
      payload.note =
        'No tool matched, and this is a repeat of a search you already tried. Stop searching — ' +
        'tell the user this capability is not supported.';
    } else {
      payload.note =
        'No tool matched. You may try once more with different wording (or list a `group` ' +
        "instead), but if that also comes back empty, tell the user this isn't supported rather " +
        'than continuing to retry.';
    }
  } else if (!confident) {
    payload.low_confidence = true;
    if (isRepeatAttempt) {
      payload.note =
        'These are still only weak matches on a repeated search. Pick the closest one if it ' +
        "genuinely fits, or tell the user this isn't well supported — don't search again.";
    } else {
      payload.note = 'These are weak matches. If none fit, you may search once more with different wording.';
    }
  }
  return { payload, matchedNames: matches.map((m) => m.name) };
}
