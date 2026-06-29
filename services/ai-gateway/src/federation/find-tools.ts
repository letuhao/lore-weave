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

/** The MCP tool def for find_tools, advertised on every minimal surface. */
export const FIND_TOOLS_TOOL = {
  name: FIND_TOOLS_NAME,
  description:
    'Find tools that can perform an intent. Call this FIRST when you need a capability you ' +
    "don't already have a tool advertised for (e.g. editing a book, starting a translation, " +
    'building a knowledge graph). Returns matching tool names + descriptions; the matched tools ' +
    'become callable. If it returns nothing useful, try once more with broader wording.',
  inputSchema: {
    type: 'object',
    properties: {
      intent: { type: 'string', description: 'What you want to do, in your own words.' },
      limit: { type: 'integer', description: 'Max tools to return (default 8).', default: FIND_TOOLS_DEFAULT_LIMIT },
    },
    required: ['intent'],
    additionalProperties: false,
  },
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
  const fuzzy = best >= 0.8 ? best : 0;
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
): { matches: ToolMatch[]; confident: boolean } {
  const intentTokens = tokens(intent);
  const scored: Array<{ s: number; t: McpTool }> = [];
  for (const t of catalog) {
    const name = toolName(t);
    if (!name || exclude.has(name)) continue;
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
 * Build the find_tools RESULT payload + the matched names. Distinguishes (H10) a genuinely
 * empty result from one whose only plausible providers are temporarily unavailable — so the
 * agent says "try again", never a false "I can't".
 */
export function findToolsResult(
  catalog: McpTool[],
  intent: string,
  limit: number,
  exclude: ReadonlySet<string>,
  unavailableProviders: string[],
): { payload: Record<string, unknown>; matchedNames: string[] } {
  const { matches, confident } = searchCatalog(catalog, intent, limit, exclude);
  const payload: Record<string, unknown> = { tools: matches };
  if (matches.length === 0) {
    if (unavailableProviders.length > 0) {
      payload.unavailable_providers = [...unavailableProviders].sort();
      payload.note =
        'No matching tool is currently available. One or more services are temporarily ' +
        'unavailable — tell the user the capability exists but to try again shortly; do NOT say ' +
        "you can't do it.";
    } else {
      payload.note =
        'No tool matched. Reconsider the wording and search once more before telling the user ' +
        'this isn\'t supported.';
    }
  } else if (!confident) {
    payload.low_confidence = true;
    payload.note = 'These are weak matches. If none fit, you may search once more with different wording.';
  }
  return { payload, matchedNames: matches.map((m) => m.name) };
}
