/**
 * mcp-public-gateway configuration (env-driven; no hardcoded secrets).
 *
 * This is the PUBLIC security edge: it authenticates an external-agent credential,
 * then mints the INTERNAL envelope (X-Internal-Token + X-User-Id) toward ai-gateway.
 * The internal token is held here and NEVER exposed to external callers (PUB-2).
 */
export interface AppConfig {
  port: number;
  /** service-to-service token minted toward ai-gateway; never sent to external agents (PUB-2) */
  internalToken: string;
  /** the internal MCP federation gateway base URL (the edge always relays to `${aiGatewayUrl}/mcp`) */
  aiGatewayUrl: string;
  /** Q-GATE kill-switch — public MCP refuses all traffic unless explicitly enabled */
  featureEnabled: boolean;
  /** auth-service base URL; the edge resolves real keys via `${authServiceUrl}/internal/mcp-keys/resolve` (P1) */
  authServiceUrl: string;
  /** resolve-cache TTL (ms) so the hot path isn't a DB round-trip per call; bounds revocation lag */
  resolveCacheTtlMs: number;
  /**
   * DEV/SMOKE static test credential (kept from P0 as a convenience). When both are
   * set AND the feature is enabled, `Bearer <testKey>` resolves to `testUserId`
   * WITHOUT calling auth-service. Leave empty in real deployments — real keys go
   * through the auth-service credential store.
   */
  testKey: string;
  testUserId: string;
  /**
   * P5 OAuth 2.1 — the edge verifies OAuth access tokens LOCALLY (RS256 via the
   * auth-service JWKS) instead of a resolve round-trip. `oauthIssuer` is the pinned
   * `iss`; `mcpResourceUrl` is the canonical resource id pinned as the `aud` (RFC 8707
   * — MUST equal auth-service's OAUTH_RESOURCE) so an audience-confused token is
   * rejected (S9). `oauthJwksUrl` is where the public verify key lives (defaults to
   * `${authServiceUrl}/oauth/jwks`). OAuth verification is active iff oauthIssuer +
   * mcpResourceUrl are set.
   */
  oauthIssuer: string;
  mcpResourceUrl: string;
  oauthJwksUrl: string;
  /** default per-minute rate limit applied to an OAuth-token call (no per-grant rpm in v1) */
  oauthDefaultRpm: number;
}

let cached: AppConfig | undefined;

export function loadConfig(): AppConfig {
  if (cached) return cached;
  cached = {
    port: parseInt(process.env.MCP_PUBLIC_GATEWAY_PORT ?? '8211', 10),
    internalToken: process.env.INTERNAL_SERVICE_TOKEN ?? '',
    aiGatewayUrl: (process.env.AI_GATEWAY_URL ?? 'http://ai-gateway:8210').replace(/\/$/, ''),
    featureEnabled: (process.env.PUBLIC_MCP_ENABLED ?? 'false').toLowerCase() === 'true',
    authServiceUrl: (process.env.AUTH_SERVICE_URL ?? 'http://auth-service:8081').replace(/\/$/, ''),
    resolveCacheTtlMs: parseInt(process.env.MCP_RESOLVE_CACHE_TTL_MS ?? '45000', 10),
    testKey: process.env.MCP_PUBLIC_TEST_KEY ?? '',
    testUserId: process.env.MCP_PUBLIC_TEST_USER_ID ?? '',
    oauthIssuer: process.env.OAUTH_ISSUER ?? '',
    mcpResourceUrl: (process.env.MCP_RESOURCE_URL ?? '').replace(/\/$/, ''),
    oauthJwksUrl:
      process.env.OAUTH_JWKS_URL ??
      `${(process.env.AUTH_SERVICE_URL ?? 'http://auth-service:8081').replace(/\/$/, '')}/oauth/jwks`,
    oauthDefaultRpm: parseInt(process.env.OAUTH_DEFAULT_RPM ?? '60', 10),
  };
  return cached;
}

/** test seam — drop the memoized config so a test can re-load with fresh env. */
export function resetConfigForTest(): void {
  cached = undefined;
}
