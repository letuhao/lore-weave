/**
 * ai-gateway configuration (env-driven; no hardcoded secrets — fails fast if the
 * internal service token is missing, per the repo "No hardcoded secrets" rule).
 */
import { Logger } from '@nestjs/common';

// P2·A2b — the default warn sink is the NestJS Logger, not console.* (LG-1). The
// sink stays injectable (tests pass a capturing fn); only the DEFAULT changed.
const configLog = new Logger('ai-gateway/config');

export interface ProviderConfig {
  /** logical provider name (used in logs + tool namespacing) */
  name: string;
  /** the provider's MCP streamable-HTTP endpoint, e.g. http://knowledge-service:8092/mcp */
  mcpUrl: string;
  /**
   * required name prefix for this provider's tools (C-GW prefix enforcement).
   * Resolved from {@link DEFAULT_PREFIX_MAP} by provider name, or overridden inline
   * in the env entry (`name|prefix_=url`). When neither resolves, `parseProviders`
   * DERIVES a default `${name}_` so EVERY provider is policed — a provider with no
   * prefix would otherwise be unpoliced and could shadow another's namespace.
   * This is the provider's CANONICAL namespace — used for dedup + logs.
   */
  prefix?: string;
  /**
   * ADDITIONAL allowed tool-name prefixes beyond {@link prefix}. A provider that
   * legitimately serves more than one namespace from one MCP server lists the
   * extras here; the C-GW gate keeps a tool matching ANY of `[prefix, ...extraPrefixes]`.
   * Resolved from {@link EXTRA_PREFIX_MAP} by name, or inline via `name|canon_+extra_=url`.
   * (knowledge serves both `memory_` memory tools AND `kg_` graph/ontology tools.)
   * Dedup is on the canonical {@link prefix} only — extras are curated, not env-shadowable.
   */
  extraPrefixes?: string[];
}

export interface AppConfig {
  port: number;
  /** service-to-service token; consumers must present it, gateway forwards its own to providers (SO-1) */
  internalToken: string;
  providers: ProviderConfig[];
  /**
   * The admin MCP upstreams (`/mcp/admin`) — federated into a SEPARATE, admin-only
   * catalog (INV-T6, spec §4c/§6.2). Deliberately NOT members of `providers` so
   * their tool names can never blend into the user/book `/mcp` catalog. Each
   * domain that owns System-tier admin tools contributes one: glossary (`glossary_*`)
   * and knowledge (`kg_admin_*`, policed by the `kg_` prefix). Built from each
   * domain's MCP base (`/mcp` → `/mcp/admin`) so no new env is required; each is
   * overridable (GLOSSARY_ADMIN_MCP_URL / KNOWLEDGE_ADMIN_MCP_URL).
   */
  adminProviders: ProviderConfig[];
  /**
   * Back-compat alias = `adminProviders[0]` (glossary-admin). Retained so existing
   * callers/tests that reference a single admin upstream keep working.
   * @deprecated use {@link adminProviders}
   */
  adminProvider: ProviderConfig;
  /** how often the federated catalog is refreshed from providers (H10) */
  catalogRefreshMs: number;
  /**
   * REG-P2-03 — per-user federation overlay. When enabled, tools/list for a turn
   * merges the caller's registered MCP servers (from agent-registry
   * /internal/effective-mcp-servers) over the static System catalog, under a
   * mandatory u_/b_ prefix so a user tool can never shadow a System tool. Default
   * OFF ⇒ the catalog is byte-identical to today (feature-flag safety). Zero
   * registrations ⇒ the static fast path (no overlay cost).
   */
  overlayEnabled: boolean;
  /** agent-registry internal base for the overlay resolver + per-user MCP federation. */
  agentRegistryInternalUrl: string;
  /**
   * P6 grounding port: knowledge-service HTTP base for the grounding proxy
   * (`POST /internal/context/build`). Defaults to the knowledge provider's MCP
   * URL with `/mcp` stripped, so no new env is required; overridable.
   */
  groundingUrl: string;
}

/**
 * C-GW prefix map — `<provider> → required tool-name prefix`. Adding a provider's
 * prefix here (or overriding inline in `AI_GATEWAY_PROVIDERS`) lets `computeCatalog`
 * drop+warn any tool that doesn't carry the provider's namespace, killing silent
 * first-provider-wins collisions across the fan-out.
 */
export const DEFAULT_PREFIX_MAP: Record<string, string> = {
  knowledge: 'memory_',
  glossary: 'glossary_',
  book: 'book_',
  composition: 'composition_',
  translation: 'translation_',
  settings: 'settings_',
  jobs: 'jobs_',
  catalog: 'catalog_',
  registry: 'registry_',
};

/**
 * Additional allowed prefixes per provider (beyond the canonical {@link DEFAULT_PREFIX_MAP}).
 * A provider serving more than one namespace from one MCP server lists the extras here.
 * knowledge's `/mcp` server serves BOTH `memory_*` (chat memory) AND `kg_*` (graph +
 * ontology + views + triage, the KG ontology epic) — without `kg_` here the C-GW gate
 * would silently drop every kg_ tool, hiding the whole agentic KG surface from the
 * federated catalog. `kg_admin_*` (the future /mcp/admin provider) is covered by `kg_`.
 * `story_` is knowledge's THIRD namespace: `story_search` (the universal manuscript
 * find — exact/lexical + semantic + block snippets). Without it the C-GW gate silently
 * dropped `story_search` (proven: ai-gateway logged "dropping tool 'story_search' …
 * does not match any allowed prefix [memory_, kg_]"), leaving the agent with no
 * keyword/full-text search over the manuscript — so it punted on "where is X at chapter
 * N" even though the raw text was reachable. Any future `story_*` tool is covered here.
 */
export const EXTRA_PREFIX_MAP: Record<string, string[]> = {
  // `lore_` is knowledge's FOURTH namespace: the W11-M2 reader "ask the lore" tools
  // (lore_ask / lore_browse_entities / lore_entity / lore_timeline — spoiler-windowed
  // reader reads). Without it the C-GW gate silently drops all four, exactly as it once
  // dropped `story_search`, leaving a reader's chat agent with no way to explore lore.
  knowledge: ['kg_', 'story_', 'lore_'],
  // PlanForge MCP tools (composition-service) — federated alongside composition_*
  composition: ['plan_'],
  // `web_` is provider-registry's ("settings") SECOND namespace: the universal `web_search`
  // tool (Track D CD5). provider-registry OWNS the outward web-search call
  // (`/internal/web-search`, provider-gateway invariant), so it hosts the tool — but the
  // tool is universal and therefore carries NO service prefix. Without `web_` here the C-GW
  // gate would silently drop it, exactly as it once dropped `story_search` (see above).
  settings: ['web_'],
  // `world_` is book-service's SECOND namespace: the W10-M1 world-container tools
  // (world_create / world_get / world_list / world_move_book). A world groups books but
  // isn't itself a `book_`, so without this the C-GW gate silently drops the whole
  // agent-native worldbuilding surface (same drop class as story_search / kg_).
  book: ['world_'],
};

/** Back-compat default registry: P0 knowledge + P1 glossary. */
function defaultProviders(): ProviderConfig[] {
  return [
    {
      name: 'knowledge',
      mcpUrl: process.env.KNOWLEDGE_MCP_URL ?? 'http://knowledge-service:8092/mcp',
      prefix: DEFAULT_PREFIX_MAP.knowledge,
      extraPrefixes: EXTRA_PREFIX_MAP.knowledge,
    },
    {
      name: 'glossary',
      mcpUrl: process.env.GLOSSARY_MCP_URL ?? 'http://glossary-service:8088/mcp',
      prefix: DEFAULT_PREFIX_MAP.glossary,
    },
  ];
}

/**
 * Parse `AI_GATEWAY_PROVIDERS` into a provider registry.
 *
 * Format: comma-separated `name=url` entries, e.g.
 *   `knowledge=http://knowledge-service:8092/mcp,glossary=http://glossary-service:8088/mcp`
 * A provider's prefix is resolved from {@link DEFAULT_PREFIX_MAP} by name, or
 * overridden inline with a `|` between name and url:
 *   `myprov|my_=http://myprov:9000/mcp`
 * When neither resolves, a default `${name}_` is derived so the provider is still
 * policed by the C-GW prefix gate (no unpoliced namespace-shadowing hole).
 * Providers are de-duped by NAME *and* by PREFIX — a second provider claiming an
 * already-taken namespace is warned + skipped (it would otherwise both pass the
 * gate for that namespace and shadow the first).
 *
 * Adding a provider becomes an env entry — no code edit (the load-bearing
 * no-conflict guarantee). Falls back to {@link defaultProviders} when the env var
 * is unset/empty so existing deployments keep working. Malformed entries (no
 * `=`, empty name/url) are skipped with a warning rather than crashing the parse.
 *
 * @param raw the env value (defaults to `process.env.AI_GATEWAY_PROVIDERS`)
 * @param warn sink for skipped-entry warnings (defaults to the NestJS Logger)
 */
export function parseProviders(
  raw: string | undefined = process.env.AI_GATEWAY_PROVIDERS,
  warn: (msg: string) => void = (m) => configLog.warn(m),
): ProviderConfig[] {
  if (raw === undefined || raw.trim() === '') {
    return defaultProviders();
  }

  const providers: ProviderConfig[] = [];
  const seen = new Set<string>();
  const seenPrefix = new Set<string>();
  for (const rawEntry of raw.split(',')) {
    const entry = rawEntry.trim();
    if (entry === '') continue;
    const eq = entry.indexOf('=');
    if (eq <= 0) {
      warn(`AI_GATEWAY_PROVIDERS: skipping malformed entry '${entry}' (expected name=url)`);
      continue;
    }
    const keyPart = entry.slice(0, eq).trim();
    const mcpUrl = entry.slice(eq + 1).trim();
    if (keyPart === '' || mcpUrl === '') {
      warn(`AI_GATEWAY_PROVIDERS: skipping entry '${entry}' (empty name or url)`);
      continue;
    }
    // optional inline prefix override: `name|prefix_` (canonical) or
    // `name|canon_+extra_` (canonical + extra allowed namespaces).
    const pipe = keyPart.indexOf('|');
    const name = pipe >= 0 ? keyPart.slice(0, pipe).trim() : keyPart;
    const overrideRaw = pipe >= 0 ? keyPart.slice(pipe + 1).trim() : '';
    if (name === '') {
      warn(`AI_GATEWAY_PROVIDERS: skipping entry '${entry}' (empty provider name)`);
      continue;
    }
    if (seen.has(name)) {
      warn(`AI_GATEWAY_PROVIDERS: skipping duplicate provider '${name}'`);
      continue;
    }
    // Resolve canonical prefix + extra allowed prefixes:
    //   inline `canon_+extra_` → DEFAULT_PREFIX_MAP + EXTRA_PREFIX_MAP → derived `${name}_`.
    // Never leave the canonical prefix undefined — an unpoliced provider could shadow
    // another's namespace through the C-GW gate.
    let prefix: string;
    let extraPrefixes: string[] | undefined;
    if (overrideRaw !== '') {
      const parts = overrideRaw.split('+').map((s) => s.trim()).filter((s) => s !== '');
      prefix = parts[0];
      extraPrefixes = parts.length > 1 ? parts.slice(1) : undefined;
    } else {
      prefix = DEFAULT_PREFIX_MAP[name] ?? `${name}_`;
      extraPrefixes = EXTRA_PREFIX_MAP[name];
    }
    // De-dupe by PREFIX too: two providers can't both own the same namespace, or
    // both would pass the prefix gate and the first would silently shadow the
    // second on every collision. Warn + skip the later claimant (keep first).
    if (seenPrefix.has(prefix)) {
      warn(
        `AI_GATEWAY_PROVIDERS: skipping provider '${name}' — prefix '${prefix}' ` +
          `already claimed by an earlier provider`,
      );
      continue;
    }
    seen.add(name);
    seenPrefix.add(prefix);
    providers.push({ name, mcpUrl, prefix, ...(extraPrefixes ? { extraPrefixes } : {}) });
  }

  // An entirely-malformed list must not silently drop the gateway to zero
  // providers — fall back to defaults so the stack still federates.
  if (providers.length === 0) {
    warn('AI_GATEWAY_PROVIDERS: no valid entries parsed — falling back to defaults');
    return defaultProviders();
  }
  return providers;
}

let cached: AppConfig | undefined;

export function loadConfig(): AppConfig {
  if (cached) return cached;
  const providers = parseProviders();
  // P6: grounding proxy target = knowledge HTTP base (strip the `/mcp` suffix
  // off the knowledge provider's MCP URL), overridable via KNOWLEDGE_SERVICE_URL.
  const knowledgeMcp = providers.find((p) => p.name === 'knowledge')?.mcpUrl ?? '';
  const groundingUrl = (
    process.env.KNOWLEDGE_SERVICE_URL ?? knowledgeMcp.replace(/\/mcp\/?$/, '')
  ).replace(/\/$/, '');

  // T4b / KM5-M4b: the admin MCP upstreams. Each domain's admin surface = its MCP
  // base with `/mcp` rewritten to `/mcp/admin`; included only when that domain has a
  // (user) provider configured OR its admin URL is set explicitly. knowledge-admin is
  // policed by `kg_` so its kg_admin_* tools survive the C-GW gate (a glossary tool
  // can never bleed into the knowledge admin namespace and vice-versa).
  const glossaryMcp = providers.find((p) => p.name === 'glossary')?.mcpUrl ?? '';
  const adminProviders: ProviderConfig[] = [];
  if (glossaryMcp || process.env.GLOSSARY_ADMIN_MCP_URL) {
    adminProviders.push({
      name: 'glossary-admin',
      mcpUrl:
        process.env.GLOSSARY_ADMIN_MCP_URL ?? glossaryMcp.replace(/\/mcp\/?$/, '/mcp/admin'),
      // Policed to glossary_ so the two admin upstreams sharing one catalog stay
      // namespace-disjoint: an unpoliced first provider could otherwise shadow
      // knowledge-admin's kg_ tools (every glossary admin tool is glossary_admin_*).
      prefix: 'glossary_',
    });
  }
  if (knowledgeMcp || process.env.KNOWLEDGE_ADMIN_MCP_URL) {
    adminProviders.push({
      name: 'knowledge-admin',
      mcpUrl:
        process.env.KNOWLEDGE_ADMIN_MCP_URL ?? knowledgeMcp.replace(/\/mcp\/?$/, '/mcp/admin'),
      prefix: 'kg_',
    });
  }
  // Back-compat alias (deprecated): the first admin upstream (glossary). Never
  // undefined — fall back to a glossary-admin shape even if no provider matched.
  const adminProvider: ProviderConfig =
    adminProviders[0] ?? {
      name: 'glossary-admin',
      mcpUrl: glossaryMcp.replace(/\/mcp\/?$/, '/mcp/admin'),
    };

  cached = {
    port: parseInt(process.env.AI_GATEWAY_PORT ?? '8210', 10),
    internalToken: process.env.INTERNAL_SERVICE_TOKEN ?? '',
    providers,
    adminProviders,
    adminProvider,
    catalogRefreshMs: parseInt(process.env.AI_GATEWAY_CATALOG_REFRESH_MS ?? '30000', 10),
    groundingUrl,
    overlayEnabled: process.env.REGISTRY_OVERLAY_ENABLED === 'true',
    agentRegistryInternalUrl: (
      process.env.AGENT_REGISTRY_INTERNAL_URL ?? 'http://agent-registry-service:8099'
    ).replace(/\/$/, ''),
  };
  return cached;
}

/** test seam — drop the memoized config so a test can re-load with fresh env. */
export function resetConfigForTest(): void {
  cached = undefined;
}
