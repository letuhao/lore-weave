/**
 * P5 OAuth discovery — PURE helpers (unit-tested) shared by the PRM controller and
 * the WWW-Authenticate header on the edge 401.
 */

/** The advertised scope vocabulary (tier + domain), mirroring the edge TOOL_POLICY tiers
 *  and FE MCP_SCOPES/MCP_DOMAINS. Advisory for discovery; the edge is the authoritative gate. */
export const OAUTH_SCOPES_SUPPORTED: readonly string[] = [
  'read',
  'paid_read',
  'write_auto',
  'write_confirm',
  'domain:book',
  'domain:glossary',
  'domain:knowledge',
  'domain:translation',
  'domain:composition',
  'domain:lore_enrichment',
  'domain:jobs',
  'domain:settings',
  'domain:catalog',
];

/** The app/AS base origin derived from the canonical MCP resource URL (`<base>/mcp` → `<base>`). */
export function authServerBaseFromResource(resourceUrl: string): string {
  const trimmed = resourceUrl.replace(/\/+$/, '');
  return trimmed.replace(/\/mcp$/, '');
}

/** The absolute URL of THIS resource's RFC 9728 metadata doc (for the WWW-Authenticate hint). */
export function resourceMetadataUrl(resourceUrl: string): string {
  return `${authServerBaseFromResource(resourceUrl)}/.well-known/oauth-protected-resource`;
}

/**
 * RFC 9728 Protected Resource Metadata. `authorization_servers` points at the AS base
 * (where `/.well-known/oauth-authorization-server` is reachable) so a client can chain
 * PRM → AS-metadata → auth-code. Empty resource → an empty-but-valid doc (OAuth not configured).
 */
export function protectedResourceMetadata(resourceUrl: string): Record<string, unknown> {
  const base = authServerBaseFromResource(resourceUrl);
  return {
    resource: resourceUrl,
    authorization_servers: base ? [base] : [],
    bearer_methods_supported: ['header'],
    scopes_supported: OAUTH_SCOPES_SUPPORTED,
  };
}

/** The RFC 9728 `WWW-Authenticate` challenge value pointing a 401'd client at the PRM doc. */
export function wwwAuthenticateChallenge(resourceUrl: string): string {
  return `Bearer resource_metadata="${resourceMetadataUrl(resourceUrl)}"`;
}
