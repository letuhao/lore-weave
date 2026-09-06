import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { loadConfig } from '../config/config.js';
import { verifyHs256 } from './jwt.js';
import { hasBookAccess, hasProjectAccess } from './grants.js';

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
    // T55/h — the route's SCOPE, which is a book for most reads and a project for the ones
    // whose callers hold no book id (spec §8.6/§8.7). ONE guard rather than a second one that
    // re-derives the JWT check and the anti-spoof pin: the identity half is identical and only
    // the authority differs, so duplicating it would be two readers of one concept.
    //
    // ⚠️ A route with NEITHER param still fails CLOSED. That is the whole reason this reads
    // params instead of taking a constructor flag: a new controller cannot accidentally
    // inherit a guard that then has nothing to check and waves it through.
    const bookId = req.params?.bookId;
    const projectId = req.params?.projectId;
    if (bookId) {
      if (!(await hasBookAccess(bookId, userId))) {
        throw new ForbiddenException('no grant on this book');
      }
    } else if (projectId) {
      if (!(await hasProjectAccess(projectId, userId))) {
        throw new ForbiddenException('no grant on this project');
      }
    } else {
      throw new UnauthorizedException('book or project scope required');
    }
    // Pin the downstream identity to the JWT (anti-spoof). ctxFromReq prefers this.
    req.kalUserId = userId;
    return true;
  }
}
