/**
 * ai-gateway configuration (env-driven; no hardcoded secrets — fails fast if the
 * internal service token is missing, per the repo "No hardcoded secrets" rule).
 */
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
   */
  prefix?: string;
}

export interface AppConfig {
  port: number;
  /** service-to-service token; consumers must present it, gateway forwards its own to providers (SO-1) */
  internalToken: string;
  providers: ProviderConfig[];
  /** how often the federated catalog is refreshed from providers (H10) */
  catalogRefreshMs: number;
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
};

/** Back-compat default registry: P0 knowledge + P1 glossary. */
function defaultProviders(): ProviderConfig[] {
  return [
    {
      name: 'knowledge',
      mcpUrl: process.env.KNOWLEDGE_MCP_URL ?? 'http://knowledge-service:8092/mcp',
      prefix: DEFAULT_PREFIX_MAP.knowledge,
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
 * @param warn sink for skipped-entry warnings (defaults to `console.warn`)
 */
export function parseProviders(
  raw: string | undefined = process.env.AI_GATEWAY_PROVIDERS,
  warn: (msg: string) => void = (m) => console.warn(m),
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
    // optional inline prefix override: `name|prefix_`
    const pipe = keyPart.indexOf('|');
    const name = pipe >= 0 ? keyPart.slice(0, pipe).trim() : keyPart;
    const overridePrefix = pipe >= 0 ? keyPart.slice(pipe + 1).trim() : '';
    if (name === '') {
      warn(`AI_GATEWAY_PROVIDERS: skipping entry '${entry}' (empty provider name)`);
      continue;
    }
    if (seen.has(name)) {
      warn(`AI_GATEWAY_PROVIDERS: skipping duplicate provider '${name}'`);
      continue;
    }
    // Resolve prefix: inline override → DEFAULT_PREFIX_MAP → derived `${name}_`.
    // Never leave it undefined — an unpoliced provider could shadow another's
    // namespace through the C-GW gate.
    const prefix =
      overridePrefix !== '' ? overridePrefix : DEFAULT_PREFIX_MAP[name] ?? `${name}_`;
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
    providers.push({ name, mcpUrl, prefix });
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

  cached = {
    port: parseInt(process.env.AI_GATEWAY_PORT ?? '8210', 10),
    internalToken: process.env.INTERNAL_SERVICE_TOKEN ?? '',
    providers,
    catalogRefreshMs: parseInt(process.env.AI_GATEWAY_CATALOG_REFRESH_MS ?? '30000', 10),
    groundingUrl,
  };
  return cached;
}

/** test seam — drop the memoized config so a test can re-load with fresh env. */
export function resetConfigForTest(): void {
  cached = undefined;
}
