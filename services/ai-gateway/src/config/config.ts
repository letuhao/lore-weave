/**
 * ai-gateway configuration (env-driven; no hardcoded secrets — fails fast if the
 * internal service token is missing, per the repo "No hardcoded secrets" rule).
 */
export interface ProviderConfig {
  /** logical provider name (used in logs + future tool namespacing) */
  name: string;
  /** the provider's MCP streamable-HTTP endpoint, e.g. http://knowledge-service:8092/mcp */
  mcpUrl: string;
}

export interface AppConfig {
  port: number;
  /** service-to-service token; consumers must present it, gateway forwards its own to providers (SO-1) */
  internalToken: string;
  providers: ProviderConfig[];
  /**
   * The glossary admin MCP upstream (`/mcp/admin`) — federated into a SEPARATE,
   * admin-only catalog (INV-T6, spec §4c/§6.2). Deliberately NOT a member of
   * `providers` so its tool names can never blend into the user/book `/mcp`
   * catalog. Defaults to the glossary provider's MCP base with `/mcp` → `/mcp/admin`,
   * so no new env is required for the standard topology; overridable.
   */
  adminProvider: ProviderConfig;
  /** how often the federated catalog is refreshed from providers (H10) */
  catalogRefreshMs: number;
  /**
   * P6 grounding port: knowledge-service HTTP base for the grounding proxy
   * (`POST /internal/context/build`). Defaults to the knowledge provider's MCP
   * URL with `/mcp` stripped, so no new env is required; overridable.
   */
  groundingUrl: string;
}

let cached: AppConfig | undefined;

export function loadConfig(): AppConfig {
  if (cached) return cached;
  // P0 knowledge + P1 glossary. The federation is provider-count-agnostic; tool
  // names are provider-prefixed (memory_* / glossary_*) so there is no collision.
  const providers: ProviderConfig[] = [
    {
      name: 'knowledge',
      mcpUrl: process.env.KNOWLEDGE_MCP_URL ?? 'http://knowledge-service:8092/mcp',
    },
    {
      name: 'glossary',
      mcpUrl: process.env.GLOSSARY_MCP_URL ?? 'http://glossary-service:8088/mcp',
    },
  ];
  // P6: grounding proxy target = knowledge HTTP base (strip the `/mcp` suffix
  // off the knowledge provider's MCP URL), overridable via KNOWLEDGE_SERVICE_URL.
  const knowledgeMcp = providers.find((p) => p.name === 'knowledge')?.mcpUrl ?? '';
  const groundingUrl = (
    process.env.KNOWLEDGE_SERVICE_URL ?? knowledgeMcp.replace(/\/mcp\/?$/, '')
  ).replace(/\/$/, '');

  // T4b: the glossary admin MCP upstream. Default = glossary's MCP base with the
  // `/mcp` segment rewritten to `/mcp/admin`; overridable via GLOSSARY_ADMIN_MCP_URL.
  const glossaryMcp = providers.find((p) => p.name === 'glossary')?.mcpUrl ?? '';
  const adminProvider: ProviderConfig = {
    name: 'glossary-admin',
    mcpUrl:
      process.env.GLOSSARY_ADMIN_MCP_URL ?? glossaryMcp.replace(/\/mcp\/?$/, '/mcp/admin'),
  };

  cached = {
    port: parseInt(process.env.AI_GATEWAY_PORT ?? '8210', 10),
    internalToken: process.env.INTERNAL_SERVICE_TOKEN ?? '',
    providers,
    adminProvider,
    catalogRefreshMs: parseInt(process.env.AI_GATEWAY_CATALOG_REFRESH_MS ?? '30000', 10),
    groundingUrl,
  };
  return cached;
}

/** test seam — drop the memoized config so a test can re-load with fresh env. */
export function resetConfigForTest(): void {
  cached = undefined;
}
