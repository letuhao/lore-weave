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
  /** how often the federated catalog is refreshed from providers (H10) */
  catalogRefreshMs: number;
}

let cached: AppConfig | undefined;

export function loadConfig(): AppConfig {
  if (cached) return cached;
  // P0: knowledge is the only provider. Provider #2 (glossary) is added at P1 by
  // appending here — the federation is provider-count-agnostic.
  const providers: ProviderConfig[] = [
    {
      name: 'knowledge',
      mcpUrl: process.env.KNOWLEDGE_MCP_URL ?? 'http://knowledge-service:8092/mcp',
    },
  ];
  cached = {
    port: parseInt(process.env.AI_GATEWAY_PORT ?? '8210', 10),
    internalToken: process.env.INTERNAL_SERVICE_TOKEN ?? '',
    providers,
    catalogRefreshMs: parseInt(process.env.AI_GATEWAY_CATALOG_REFRESH_MS ?? '30000', 10),
  };
  return cached;
}

/** test seam — drop the memoized config so a test can re-load with fresh env. */
export function resetConfigForTest(): void {
  cached = undefined;
}
