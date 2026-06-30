import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { loadConfig } from '../config/config.js';
import { verifyHs256 } from './jwt.js';
import { hasBookAccess } from './grants.js';

/**
 * Dual-auth for the KAL READ surface — two trusted caller classes:
 *
 *  1. SERVICE mode (service-to-service): a valid `X-Internal-Token`. The calling service has
 *     already done its own grant check, so the forwarded `X-User-Id` header is trusted as-is.
 *  2. USER mode (FE via the api-gateway-bff, which is a DUMB JWT-passthrough proxy): a valid
 *     platform HS256 Bearer JWT. Because the BFF does NO grant check, the KAL is the boundary —
 *     it (a) validates the JWT, (b) GRANT-CHECKS the route's book against book-service, and (c)
 *     pins the downstream `X-User-Id` to the JWT's `sub`. A user CANNOT spoof `X-User-Id` in user
 *     mode: it is taken from the validated token, not a client header.
 *
 * The WRITE surface stays internal-token-ONLY (InternalTokenGuard) — FE never writes facts
 * directly; those are the producer / service path.
 */
@Injectable()
export class KalAuthGuard implements CanActivate {
  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest<{
      headers: Record<string, string | undefined>;
      params?: Record<string, string | undefined>;
      kalUserId?: string;
    }>();
    const cfg = loadConfig();

    // 1. SERVICE mode — a valid internal token; trust the forwarded X-User-Id.
    const presented = req.headers['x-internal-token'];
    if (cfg.internalToken && presented === cfg.internalToken) return true;

    // 2. USER mode — a valid platform JWT + a grant on the route's book.
    const auth = req.headers['authorization'];
    const bearer = typeof auth === 'string' && auth.startsWith('Bearer ') ? auth.slice(7) : undefined;
    const userId = verifyHs256(bearer, cfg.jwtSecret);
    if (!userId) {
      throw new UnauthorizedException('valid X-Internal-Token or Bearer JWT required');
    }
    const bookId = req.params?.bookId;
    if (!bookId) {
      throw new UnauthorizedException('book scope required');
    }
    if (!(await hasBookAccess(bookId, userId))) {
      throw new ForbiddenException('no grant on this book');
    }
    // Pin the downstream identity to the JWT (anti-spoof). ctxFromReq prefers this.
    req.kalUserId = userId;
    return true;
  }
}
