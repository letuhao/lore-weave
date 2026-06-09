import * as jwt from 'jsonwebtoken';

export function requireStreamTicketEnforced(): boolean {
  return process.env.BFF_REQUIRE_STREAM_TICKET === 'true';
}

export function resolveUserIdFromToken(token: string, jwtSecret: string): string {
  const decoded = jwt.verify(token, jwtSecret) as jwt.JwtPayload & { typ?: string; sub?: string };
  if (!decoded.sub) {
    throw new Error('missing sub');
  }
  if (requireStreamTicketEnforced()) {
    if (decoded.typ !== 'stream') {
      throw new Error('invalid token type');
    }
  } else if (decoded.typ && decoded.typ !== 'stream') {
    throw new Error('invalid token type');
  }
  return decoded.sub;
}
