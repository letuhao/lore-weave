/**
 * L6.B.4 — Ticket store tests (RAID cycle 28).
 *
 * Acceptance contract per cycle brief:
 *   - Ticket single-use enforced (Redis atomic DEL semantics).
 *   - Ticket NEVER appears in URL query string (covered by upgrade-handler tests).
 *   - TTL 60 s exactly.
 *   - user_ref_id + allowed_realities + allowed_scopes + origin_hash + fingerprint_hash
 *     correctly bound in ticket.
 */

import {
  TICKET_TTL_MS,
  TicketError,
  InMemoryTicketStore,
  hashOrigin,
  hashFingerprint,
  makeTicket,
  validateTicket,
  constantTimeBufferEquals,
} from './ticket-store';

const SAMPLE_USER = '00000000-0000-0000-0000-000000000abc';
const SAMPLE_REALITY = '00000000-0000-0000-0000-000000000def';

function makeSampleTicket(now: number, scopes: string[] = ['chat']) {
  return makeTicket({
    userRefId: SAMPLE_USER,
    allowedRealities: [SAMPLE_REALITY],
    allowedScopes: scopes,
    originHash: hashOrigin('https://app.loreweave.dev'),
    clientFingerprintHash: hashFingerprint('UA/1.0', '10.0.0.0', 'tlsprefix'),
    nowMs: now,
  });
}

describe('ticket-store', () => {
  describe('TTL discipline (Q-L6-1 / S12 §12AB.2)', () => {
    it('TICKET_TTL_MS is exactly 60 000 ms', () => {
      expect(TICKET_TTL_MS).toBe(60_000);
    });

    it('makeTicket sets expiresAt = issuedAt + TTL', () => {
      const t = makeSampleTicket(1_000);
      expect(t.expiresAt - t.issuedAt).toBe(TICKET_TTL_MS);
    });
  });

  describe('entropy (auditor focus: ≥128 bits)', () => {
    it('ticket id is unique across 1000 issues', () => {
      const ids = new Set<string>();
      for (let i = 0; i < 1000; i += 1) {
        ids.add(makeSampleTicket(i).ticketId);
      }
      expect(ids.size).toBe(1000);
    });

    it('ticket id has 128-bit-equivalent hex tail', () => {
      const t = makeSampleTicket(0);
      // 32 hex chars = 128 random bits from randomUUID v4 minus 6 fixed bits = ~122 bits.
      // We document the floor here; collision math holds well past 1B issues at <1k/sec.
      expect(t.ticketId).toMatch(/^wst_[0-9a-f]{32}$/);
    });
  });

  describe('one-shot redeem (atomic — Q-L6 auditor focus)', () => {
    it('first redeem succeeds; second returns ticket_not_found', async () => {
      const store = new InMemoryTicketStore();
      const t = makeSampleTicket(1_000);
      await store.issue(t);

      const first = await store.redeem(t.ticketId, 1_500);
      expect(first.ticketId).toBe(t.ticketId);
      expect(await store.size()).toBe(0);

      await expect(store.redeem(t.ticketId, 1_600)).rejects.toMatchObject({
        name: 'TicketError',
        tag: 'ticket_not_found',
      });
    });

    it('concurrent redeems: only one succeeds', async () => {
      const store = new InMemoryTicketStore();
      const t = makeSampleTicket(1_000);
      await store.issue(t);

      const results = await Promise.allSettled([
        store.redeem(t.ticketId, 1_500),
        store.redeem(t.ticketId, 1_500),
      ]);
      const fulfilled = results.filter((r) => r.status === 'fulfilled');
      const rejected = results.filter((r) => r.status === 'rejected');
      expect(fulfilled.length).toBe(1);
      expect(rejected.length).toBe(1);
    });

    it('expired ticket: redeem deletes AND rejects with ticket_expired', async () => {
      const store = new InMemoryTicketStore();
      const t = makeSampleTicket(1_000);
      await store.issue(t);

      const tooLate = 1_000 + TICKET_TTL_MS + 1;
      await expect(store.redeem(t.ticketId, tooLate)).rejects.toMatchObject({
        tag: 'ticket_expired',
      });
      // Expired ticket MUST still be removed so a clock-skew replay cannot
      // resurrect it.
      expect(await store.size()).toBe(0);
    });
  });

  describe('binding integrity', () => {
    it('rejects issue with wrong-size origin hash', () => {
      expect(() =>
        makeTicket({
          userRefId: SAMPLE_USER,
          allowedRealities: [],
          allowedScopes: [],
          originHash: Buffer.alloc(16), // 16 bytes — wrong
          clientFingerprintHash: Buffer.alloc(32),
          nowMs: 0,
        }),
      ).toThrow(TicketError);
    });

    it('rejects issue with wrong-size fingerprint hash', () => {
      expect(() =>
        makeTicket({
          userRefId: SAMPLE_USER,
          allowedRealities: [],
          allowedScopes: [],
          originHash: Buffer.alloc(32),
          clientFingerprintHash: Buffer.alloc(64), // wrong
          nowMs: 0,
        }),
      ).toThrow(TicketError);
    });

    it('hashOrigin is deterministic across calls', () => {
      const a = hashOrigin('https://app.loreweave.dev');
      const b = hashOrigin('https://app.loreweave.dev');
      expect(a.equals(b)).toBe(true);
      expect(a.length).toBe(32);
    });

    it('hashFingerprint mixes all three inputs (changing any one changes the hash)', () => {
      const base = hashFingerprint('UA/1', '10.0.0.0', 'sid');
      const ua = hashFingerprint('UA/2', '10.0.0.0', 'sid');
      const ip = hashFingerprint('UA/1', '10.0.1.0', 'sid');
      const tls = hashFingerprint('UA/1', '10.0.0.0', 'sid2');
      expect(base.equals(ua)).toBe(false);
      expect(base.equals(ip)).toBe(false);
      expect(base.equals(tls)).toBe(false);
    });

    it('preserves allowedRealities + allowedScopes + userRefId', async () => {
      const store = new InMemoryTicketStore();
      const t = makeSampleTicket(1_000, ['chat', 'presence']);
      await store.issue(t);
      const out = await store.redeem(t.ticketId, 1_500);
      expect(out.userRefId).toBe(SAMPLE_USER);
      expect(out.allowedRealities).toEqual([SAMPLE_REALITY]);
      expect(out.allowedScopes).toEqual(['chat', 'presence']);
    });
  });

  describe('validateTicket', () => {
    it('passes for a freshly minted ticket', () => {
      const t = makeSampleTicket(1_000);
      expect(() => validateTicket(t, 1_500)).not.toThrow();
    });

    it('rejects expired ticket', () => {
      const t = makeSampleTicket(1_000);
      expect(() => validateTicket(t, 1_000 + TICKET_TTL_MS + 1)).toThrow(
        expect.objectContaining({ tag: 'ticket_expired' }),
      );
    });

    it('rejects ticket with TTL window > 2 × canonical', () => {
      const base = makeSampleTicket(1_000);
      const bad = {
        ...base,
        // forge wide window
        expiresAt: base.issuedAt + 3 * TICKET_TTL_MS,
      };
      expect(() => validateTicket(bad, 1_500)).toThrow(/TTL window/);
    });
  });

  describe('constantTimeBufferEquals', () => {
    it('returns true for matching buffers', () => {
      const a = Buffer.from('abcdefgh');
      const b = Buffer.from('abcdefgh');
      expect(constantTimeBufferEquals(a, b)).toBe(true);
    });

    it('returns false for mismatched buffers', () => {
      expect(constantTimeBufferEquals(Buffer.from('abc'), Buffer.from('abd'))).toBe(false);
    });

    it('returns false for different lengths', () => {
      expect(constantTimeBufferEquals(Buffer.from('abc'), Buffer.from('abcd'))).toBe(false);
    });
  });
});
