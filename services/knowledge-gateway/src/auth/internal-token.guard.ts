import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

/**
 * Inbound auth for the KAL (HIGH-1). The KAL forwards downstream with its TRUSTED
 * X-Internal-Token + the caller's X-User-Id, so it MUST authenticate its own callers — or
 * any reachable peer could act unauthenticated and impersonate any user via a spoofed
 * X-User-Id. This is the platform's service-to-service posture (mirrors glossary's
 * requireInternalToken): a valid X-Internal-Token is required; only then is X-User-Id
 * trusted as the tenancy identity. The KAL sits behind api-gateway-bff (the edge does JWT
 * + grant checks and presents the internal token); direct internal callers must hold it too.
 *
 * Applied to the KAL read/write controllers, NOT to /health.
 */
@Injectable()
export class InternalTokenGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<{ headers: Record<string, string | undefined> }>();
    const presented = req.headers['x-internal-token'];
    const expected = loadConfig().internalToken;
    // expected is guaranteed non-empty (main.ts refuses to start without it), but check
    // anyway so a misconfig fails closed rather than open.
    if (!expected || presented !== expected) {
      throw new UnauthorizedException('valid X-Internal-Token required');
    }
    return true;
  }
}
