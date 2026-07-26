import { Controller, Get, Header } from '@nestjs/common';
import { loadConfig } from '../config/config.js';
import { protectedResourceMetadata } from './discovery.js';

/**
 * P5 OAuth 2.1 — RFC 9728 Protected Resource Metadata. A spec-compliant MCP client
 * that gets a 401 from the edge reads `WWW-Authenticate: Bearer resource_metadata="…"`
 * (set in public-mcp.controller), fetches THIS doc, and discovers the authorization
 * server(s) to run the auth-code flow against. Served by the RESOURCE (the edge), per
 * RFC 9728 — the AS metadata (RFC 8414) is served by auth-service.
 *
 * Routed here via the BFF (`/.well-known/oauth-protected-resource` → mcp-public-gateway).
 * Public + unauthenticated by design (it's discovery).
 */
@Controller()
export class OAuthDiscoveryController {
  private readonly cfg = loadConfig();

  @Get('.well-known/oauth-protected-resource')
  @Header('Cache-Control', 'public, max-age=3600')
  protectedResource() {
    return protectedResourceMetadata(this.cfg.mcpResourceUrl);
  }
}
