import { generateKeyPairSync, sign, type KeyObject } from 'node:crypto';
import { OAuthTokenVerifier, looksLikeJwt } from '../src/oauth/token-verifier.js';

const ISS = 'loreweave-mcp-oauth';
const RES = 'https://app.loreweave.dev/mcp';
const KID = 'test-kid-1';

const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });

function b64url(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj)).toString('base64url');
}

function jwkSet(pub: KeyObject, kid: string) {
  const j = pub.export({ format: 'jwk' }) as { n: string; e: string };
  return { keys: [{ kty: 'RSA', use: 'sig', alg: 'RS256', kid, n: j.n, e: j.e }] };
}

function mint(opts: {
  iss?: string;
  aud?: string | string[];
  sub?: string;
  scope?: string;
  grantId?: string;
  expSec?: number;
  alg?: string;
  kid?: string;
  key?: KeyObject;
  tamper?: boolean;
}): string {
  const header = b64url({ alg: opts.alg ?? 'RS256', typ: 'JWT', kid: opts.kid ?? KID });
  const payload = b64url({
    iss: opts.iss ?? ISS,
    aud: opts.aud ?? RES,
    sub: opts.sub ?? 'user-123',
    scope: opts.scope ?? 'read domain:book',
    grant_id: opts.grantId ?? 'grant-abc',
    client_id: 'client-1',
    exp: opts.expSec ?? Math.floor(Date.now() / 1000) + 600,
    iat: Math.floor(Date.now() / 1000),
  });
  const signingInput = `${header}.${payload}`;
  let sig = sign('RSA-SHA256', Buffer.from(signingInput), opts.key ?? privateKey).toString('base64url');
  if (opts.tamper) sig = sig.slice(0, -2) + (sig.endsWith('AA') ? 'BB' : 'AA');
  return `${signingInput}.${sig}`;
}

// A verifier whose JWKS fetch always returns our test key set.
function verifier(jwks: unknown = jwkSet(publicKey, KID)): OAuthTokenVerifier {
  const fakeFetch = (async () => ({ status: 200, json: async () => jwks })) as unknown as typeof fetch;
  return new OAuthTokenVerifier('http://auth/oauth/jwks', ISS, RES, undefined, fakeFetch);
}

describe('looksLikeJwt', () => {
  it('is true for a 3-segment non-key bearer, false for an lw_pk_ key or a non-JWT', () => {
    expect(looksLikeJwt('aaa.bbb.ccc')).toBe(true);
    expect(looksLikeJwt('lw_pk_abc.def.ghi')).toBe(false);
    expect(looksLikeJwt('lw_pk_plainkey')).toBe(false);
    expect(looksLikeJwt('aaa.bbb')).toBe(false);
    expect(looksLikeJwt('aaa..ccc')).toBe(false);
  });
});

describe('OAuthTokenVerifier', () => {
  it('accepts a valid token and returns identity + scopes', async () => {
    const v = await verifier().verify(mint({}));
    expect(v).not.toBeNull();
    expect(v!.userId).toBe('user-123');
    expect(v!.grantId).toBe('grant-abc');
    expect(v!.scopes).toEqual(['read', 'domain:book']);
  });

  it('rejects a wrong AUDIENCE (S9 confused-deputy)', async () => {
    expect(await verifier().verify(mint({ aud: 'https://evil.example/mcp' }))).toBeNull();
  });

  it('accepts an aud ARRAY that contains the resource, rejects one that does not', async () => {
    expect(await verifier().verify(mint({ aud: ['x', RES] }))).not.toBeNull();
    expect(await verifier().verify(mint({ aud: ['x', 'y'] }))).toBeNull();
  });

  it('rejects a wrong ISSUER', async () => {
    expect(await verifier().verify(mint({ iss: 'loreweave-auth' }))).toBeNull(); // the admin issuer
  });

  it('rejects an expired token', async () => {
    expect(await verifier().verify(mint({ expSec: Math.floor(Date.now() / 1000) - 10 }))).toBeNull();
  });

  it('rejects a tampered signature', async () => {
    expect(await verifier().verify(mint({ tamper: true }))).toBeNull();
  });

  it('rejects alg:none and a non-RS256 alg (downgrade / confusion)', async () => {
    expect(await verifier().verify(mint({ alg: 'none' }))).toBeNull();
    expect(await verifier().verify(mint({ alg: 'HS256' }))).toBeNull();
  });

  it('rejects a token signed by a DIFFERENT key (sig mismatch even with refresh)', async () => {
    const other = generateKeyPairSync('rsa', { modulusLength: 2048 }).privateKey;
    expect(await verifier().verify(mint({ key: other }))).toBeNull();
  });

  it('strips the * wildcard scope (never honored for OAuth)', async () => {
    const v = await verifier().verify(mint({ scope: 'read * domain:book' }));
    expect(v!.scopes).toEqual(['read', 'domain:book']);
  });

  it('falls back grant_id → sub when grant_id is absent', async () => {
    const header = b64url({ alg: 'RS256', typ: 'JWT', kid: KID });
    const payload = b64url({ iss: ISS, aud: RES, sub: 'u-9', scope: 'read', exp: Math.floor(Date.now() / 1000) + 600 });
    const si = `${header}.${payload}`;
    const tok = `${si}.${sign('RSA-SHA256', Buffer.from(si), privateKey).toString('base64url')}`;
    const v = await verifier().verify(tok);
    expect(v!.grantId).toBe('u-9');
  });

  it('isConfigured is false when issuer or resource is empty', () => {
    expect(new OAuthTokenVerifier('u', '', RES).isConfigured()).toBe(false);
    expect(new OAuthTokenVerifier('u', ISS, '').isConfigured()).toBe(false);
    expect(new OAuthTokenVerifier('u', ISS, RES).isConfigured()).toBe(true);
  });

  it('returns null on malformed input (not 3 segments / bad base64)', async () => {
    expect(await verifier().verify('not-a-jwt')).toBeNull();
    expect(await verifier().verify('a.b')).toBeNull();
    expect(await verifier().verify('@@@.@@@.@@@')).toBeNull();
  });
});
