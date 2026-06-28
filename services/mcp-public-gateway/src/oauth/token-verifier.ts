import { createPublicKey, verify as cryptoVerify, type KeyObject } from 'node:crypto';
import { Logger } from '@nestjs/common';

/**
 * P5 OAuth 2.1 — LOCAL access-token verification at the edge (no auth-service round
 * trip on the hot path). An OAuth access token is an RS256 JWT minted by auth-service
 * (`authjwt.OAuthAccessClaims`) with a DISTINCT issuer + a resource-bound audience
 * (RFC 8707). This verifier:
 *   - pins RS256 (rejects alg:none / HS-confusion),
 *   - verifies the signature against the auth-service JWKS (kid-keyed, cached, with a
 *     refresh-on-unknown-kid / sig-miss for key rotation),
 *   - asserts `iss == oauthIssuer`, `aud` CONTAINS `mcpResourceUrl` (S9 confused-deputy
 *     defense — a token minted for any other audience is rejected), and `exp` not past.
 *
 * Zero JWT deps — Node's built-in crypto verifies RS256 and imports the JWK directly.
 */

export interface VerifiedOAuth {
  userId: string; // the LoreWeave user the token acts on-behalf-of ("sub")
  grantId: string; // the grant id ("grant_id", else "sub") — rides x-mcp-key-id, a UUID
  scopes: string[]; // parsed from the space-delimited "scope" claim ('*' stripped)
}

interface Jwk {
  kid?: string;
  kty?: string;
  n?: string;
  e?: string;
}

/** Decode a base64url JWT segment into a JSON object, or null on any malformation. */
function decodeSegment(seg: string): Record<string, unknown> | null {
  try {
    const obj: unknown = JSON.parse(Buffer.from(seg, 'base64url').toString('utf8'));
    return obj && typeof obj === 'object' && !Array.isArray(obj) ? (obj as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * True iff the bearer is JWT-shaped (three non-empty dot-separated segments) and is
 * NOT an `lw_pk_` personal API key. Used to route a credential to local OAuth verify
 * vs the API-key resolve endpoint.
 */
export function looksLikeJwt(bearer: string): boolean {
  if (bearer.startsWith('lw_pk_')) return false;
  const parts = bearer.split('.');
  return parts.length === 3 && parts.every((p) => p.length > 0);
}

export class OAuthTokenVerifier {
  private keys = new Map<string, KeyObject>(); // kid → RSA public key ('' kid = first key)
  private fetchedAt = 0;
  private readonly jwksTtlMs = 3_600_000;

  constructor(
    private readonly jwksUrl: string,
    private readonly issuer: string,
    private readonly resource: string,
    private readonly log = new Logger(OAuthTokenVerifier.name),
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  /** OAuth verification is active only when both the issuer and the resource (aud) are configured. */
  isConfigured(): boolean {
    return this.issuer.length > 0 && this.resource.length > 0;
  }

  /**
   * Verify an OAuth access token. Returns the resolved identity + scopes, or null for
   * ANY failure (bad shape/alg/sig/iss/aud/exp) — the caller maps null to a uniform
   * 401 (anti-oracle). Never throws into the request path.
   */
  async verify(token: string, now: number = Date.now()): Promise<VerifiedOAuth | null> {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const header = decodeSegment(parts[0]);
    const payload = decodeSegment(parts[1]);
    if (!header || !payload) return null;
    if (header.alg !== 'RS256') return null; // pin RS256 — reject alg:none / HS confusion
    const kid = typeof header.kid === 'string' ? header.kid : '';

    const signingInput = `${parts[0]}.${parts[1]}`;
    let sig: Buffer;
    try {
      sig = Buffer.from(parts[2], 'base64url');
    } catch {
      return null;
    }

    // Verify against the cached key; on a miss (rotation / unknown kid) force one refresh.
    let key = await this.keyFor(kid, now, false);
    let ok = key ? this.verifySig(signingInput, sig, key) : false;
    if (!ok) {
      key = await this.keyFor(kid, now, true);
      ok = key ? this.verifySig(signingInput, sig, key) : false;
    }
    if (!ok) return null;

    // Claims: pinned issuer + audience (S9) + required, unexpired exp.
    if (payload.iss !== this.issuer) return null;
    if (!this.audienceMatches(payload.aud)) return null;
    if (typeof payload.exp !== 'number' || now >= payload.exp * 1000) return null;
    if (typeof payload.sub !== 'string' || payload.sub.length === 0) return null;

    const grantId =
      typeof payload.grant_id === 'string' && payload.grant_id.length > 0 ? payload.grant_id : payload.sub;
    const scopes =
      typeof payload.scope === 'string'
        ? payload.scope.split(/\s+/).filter((s) => s.length > 0 && s !== '*') // '*' is the dev wildcard — never honored for OAuth
        : [];
    return { userId: payload.sub, grantId, scopes };
  }

  /** RFC 8707: the token's aud (string or array) must contain our resource id. */
  private audienceMatches(aud: unknown): boolean {
    if (typeof aud === 'string') return aud === this.resource;
    if (Array.isArray(aud)) return aud.includes(this.resource);
    return false;
  }

  private verifySig(signingInput: string, sig: Buffer, key: KeyObject): boolean {
    try {
      return cryptoVerify('RSA-SHA256', Buffer.from(signingInput), key, sig);
    } catch {
      return false;
    }
  }

  private async keyFor(kid: string, now: number, force: boolean): Promise<KeyObject | null> {
    const fresh = this.keys.size > 0 && now - this.fetchedAt < this.jwksTtlMs;
    const have = kid ? this.keys.get(kid) : this.keys.values().next().value;
    if (!force && fresh && have) return have ?? null;
    await this.refresh(now);
    return (kid ? this.keys.get(kid) : this.keys.values().next().value) ?? null;
  }

  private async refresh(now: number): Promise<void> {
    try {
      const res = await this.fetchImpl(this.jwksUrl, { signal: AbortSignal.timeout(3000) });
      if (res.status < 200 || res.status >= 300) {
        this.log.warn(`jwks fetch non-OK: ${res.status}`);
        return;
      }
      const body = (await res.json()) as { keys?: Jwk[] };
      const next = new Map<string, KeyObject>();
      for (const jwk of body.keys ?? []) {
        if (jwk.kty !== 'RSA' || !jwk.n || !jwk.e) continue;
        try {
          next.set(jwk.kid ?? '', createPublicKey({ key: { kty: 'RSA', n: jwk.n, e: jwk.e }, format: 'jwk' }));
        } catch (e) {
          this.log.warn(`skip bad jwk: ${e}`);
        }
      }
      if (next.size > 0) {
        this.keys = next;
        this.fetchedAt = now;
      }
    } catch (e) {
      this.log.warn(`jwks fetch failed: ${e}`);
    }
  }
}
