import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { IncomingHttpHeaders } from 'node:http';

import { parseUpgrade, extractTicketId, ipToPrivacyPrefix, UpgradeError } from './upgrade.js';
import {
  authenticateTicket,
  authCloseCode,
  wsTrustedProxy,
  assertWsAuthConfig,
  CLOSE_ORIGIN_MISMATCH,
  CLOSE_FINGERPRINT_MISMATCH,
  CLOSE_TOKEN_EXPIRED,
  CLOSE_SCHEMA_INVALID,
  type TicketRedeemer,
} from './auth.js';
import { TicketError, TICKET_TTL_MS, hashFingerprint, type Ticket } from './ticket-store.js';

function headers(over: Partial<IncomingHttpHeaders> = {}): IncomingHttpHeaders {
  return {
    'sec-websocket-protocol': 'lw.v1, ticket.wst_abc',
    origin: 'https://app.loreweave.dev',
    'user-agent': 'UA/1.0',
    ...over,
  };
}

test('ipToPrivacyPrefix: v4 strips last octet, v6 keeps /48', () => {
  assert.equal(ipToPrivacyPrefix('203.0.113.77'), '203.0.113.0');
  assert.equal(ipToPrivacyPrefix('2001:db8:abcd:1234::1'), '2001:db8:abcd::');
});

test('extractTicketId parses "lw.v1, ticket.<id>"; rejects malformed', () => {
  assert.equal(extractTicketId('lw.v1, ticket.wst_xyz'), 'wst_xyz');
  assert.equal(extractTicketId('lw.v1,ticket.wst_xyz'), 'wst_xyz'); // whitespace optional
  assert.throws(() => extractTicketId('lw.v1'), (e: unknown) => e instanceof UpgradeError);
  assert.throws(() => extractTicketId(undefined), (e: unknown) => e instanceof UpgradeError);
  assert.throws(() => extractTicketId('lw.v2, ticket.x'), (e: unknown) => e instanceof UpgradeError);
});

test('parseUpgrade requires origin + user-agent', () => {
  assert.throws(
    () => parseUpgrade(headers({ origin: undefined }), '203.0.113.1'),
    (e: unknown) => e instanceof UpgradeError && e.tag === 'missing_origin',
  );
  assert.throws(
    () => parseUpgrade(headers({ 'user-agent': undefined }), '203.0.113.1'),
    (e: unknown) => e instanceof UpgradeError && e.tag === 'missing_user_agent',
  );
});

test('parseUpgrade: trustedProxy uses the first X-Forwarded-For token', () => {
  const up = parseUpgrade(headers({ 'x-forwarded-for': '198.51.100.5, 10.0.0.1' }), '10.0.0.1', {
    trustedProxy: true,
  });
  assert.equal(up.clientIpSlash24, '198.51.100.0');
  // Without trustedProxy, the connection IP is used (XFF ignored).
  const up2 = parseUpgrade(headers({ 'x-forwarded-for': '198.51.100.5' }), '10.0.0.1');
  assert.equal(up2.clientIpSlash24, '10.0.0.0');
});

/** Build a ticket whose hashes BIND to the given headers/ip (issuer parity). */
function boundTicket(h: IncomingHttpHeaders, ip: string, now: number, over: Partial<Ticket> = {}): Ticket {
  const up = parseUpgrade(h, ip);
  return {
    ticketId: 'wst_abc',
    userRefId: 'u-1',
    allowedRealities: ['r-1'],
    allowedScopes: ['chat'],
    originHash: up.originHash,
    clientFingerprintHash: up.fingerprintHash,
    issuedAt: now,
    expiresAt: now + TICKET_TTL_MS,
    ...over,
  };
}

test('authenticateTicket: succeeds when the ticket binds to the upgrade', async () => {
  const now = Date.now();
  const h = headers();
  const ip = '203.0.113.1';
  const redeemer: TicketRedeemer = { async redeem() { return boundTicket(h, ip, now); } };
  const authed = await authenticateTicket(redeemer, h, ip, now);
  assert.equal(authed.userId, 'u-1');
  assert.equal(authed.userRefId, 'u-1');
  assert.deepEqual(authed.allowedScopes, ['chat']);
});

test('authenticateTicket: origin mismatch (ticket bound to a different origin)', async () => {
  const now = Date.now();
  const h = headers();
  const ip = '203.0.113.1';
  const otherOrigin = boundTicket(headers({ origin: 'https://evil.example' }), ip, now);
  const redeemer: TicketRedeemer = { async redeem() { return otherOrigin; } };
  await assert.rejects(
    authenticateTicket(redeemer, h, ip, now),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_origin_mismatch',
  );
});

test('authenticateTicket: fingerprint mismatch (different IP/24)', async () => {
  const now = Date.now();
  const h = headers();
  const ticket = boundTicket(h, '203.0.113.1', now); // bound to 203.0.113.0
  const redeemer: TicketRedeemer = { async redeem() { return ticket; } };
  await assert.rejects(
    authenticateTicket(redeemer, h, '198.51.100.9', now), // → 198.51.100.0
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_fingerprint_mismatch',
  );
});

test('authenticateTicket: propagates a redeemer not_found', async () => {
  const redeemer: TicketRedeemer = {
    async redeem() { throw new TicketError('ticket_not_found', 'gone'); },
  };
  await assert.rejects(
    authenticateTicket(redeemer, headers(), '203.0.113.1', Date.now()),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_not_found',
  );
});

test('authCloseCode maps tags to §12AB.9 close codes', () => {
  assert.equal(authCloseCode(new TicketError('ticket_origin_mismatch', 'x')), CLOSE_ORIGIN_MISMATCH);
  assert.equal(authCloseCode(new TicketError('ticket_fingerprint_mismatch', 'x')), CLOSE_FINGERPRINT_MISMATCH);
  assert.equal(authCloseCode(new TicketError('ticket_expired', 'x')), CLOSE_TOKEN_EXPIRED);
  assert.equal(authCloseCode(new TicketError('ticket_not_found', 'x')), CLOSE_TOKEN_EXPIRED);
  assert.equal(authCloseCode(new UpgradeError('missing_origin', 'x')), CLOSE_SCHEMA_INVALID);
});

test('wsTrustedProxy defaults TRUE (mirrors the issuer); opt-out with =0 (HIGH-1)', () => {
  delete process.env.LW_WS_TRUSTED_PROXY;
  assert.equal(wsTrustedProxy(), true);
  process.env.LW_WS_TRUSTED_PROXY = '0';
  assert.equal(wsTrustedProxy(), false);
  process.env.LW_WS_TRUSTED_PROXY = '1';
  assert.equal(wsTrustedProxy(), true);
  delete process.env.LW_WS_TRUSTED_PROXY;
});

test('issuer↔redeemer IP parity: same XFF → same fingerprint (HIGH-1)', () => {
  // The gateway issuer hashes the FIRST X-Forwarded-For token unconditionally;
  // with trustedProxy default-true the redeemer derives the same /24, so the
  // fingerprints MUST match (else every prod handshake would 4009).
  const h = headers({ 'x-forwarded-for': '198.51.100.42, 10.0.0.1' });
  const up = parseUpgrade(h, '10.0.0.1', { trustedProxy: wsTrustedProxy() });
  const issuerFp = hashFingerprint('UA/1.0', ipToPrivacyPrefix('198.51.100.42'), '');
  assert.ok(up.fingerprintHash.equals(issuerFp), 'redeemer fingerprint must match the issuer for the same XFF');
});

test('assertWsAuthConfig: prod + no Redis + no dev-allow → throws; otherwise ok (HIGH-2)', () => {
  assert.throws(() => assertWsAuthConfig({ NODE_ENV: 'production' } as NodeJS.ProcessEnv));
  // configured store, explicit dev-allow, or non-prod are all fine:
  assertWsAuthConfig({ NODE_ENV: 'production', LW_WS_REDIS_URL: 'redis://x' } as NodeJS.ProcessEnv);
  assertWsAuthConfig({ NODE_ENV: 'production', LW_WS_ALLOW_DEV_AUTH: '1' } as NodeJS.ProcessEnv);
  assertWsAuthConfig({ NODE_ENV: 'development' } as NodeJS.ProcessEnv);
});
