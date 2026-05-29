/**
 * L6.E.1 — WS metrics tests (RAID cycle 28).
 *
 * Acceptance criteria per cycle brief:
 *   - All `lw_ws_*` metrics emitted under correct events
 *   - Cardinality bounded (no per-connection labels — the auditor focus)
 *   - Saturation ratio drives alerts (>80% cap)
 */

import { WsMetrics } from './metrics';

describe('WsMetrics', () => {
  it('exposes the 6 canonical lw_ws_* surfaces', () => {
    const m = new WsMetrics();
    expect(m.activeConnections.name).toBe('lw_ws_active_connections');
    expect(m.handshakeFailures.name).toBe('lw_ws_handshake_failures_total');
    expect(m.messages.name).toBe('lw_ws_messages_total');
    expect(m.authzRejections.name).toBe('lw_ws_authz_rejections_total');
    expect(m.ticketRedeemed.name).toBe('lw_ws_ticket_redeemed_total');
    expect(m.evictions.name).toBe('lw_ws_connection_evictions_total');
  });

  it('cardinality budget: snapshot count bounded after stress emit', () => {
    const m = new WsMetrics();
    // Simulate 10k connections coming and going — the snapshot count
    // must remain bounded by the LABEL space, not the connection count.
    for (let i = 0; i < 10_000; i += 1) {
      m.onConnectionOpen();
      m.onMessage('c2s', 'data');
      m.onMessage('s2c', 'data');
      m.onConnectionClose('normal_close');
    }
    const snap = m.snapshot();
    // 1 gauge + (msgs: dir2 × kind2 = 4 max) + (evictions: 3 reasons but
    // only 'normal_close' used = 1) + 0 unused families = 6 records.
    // We don't pin the exact count; we pin "well under 100" as a
    // cardinality regression guard.
    expect(snap.length).toBeLessThan(100);
  });

  it('rejects an unknown label (cardinality discipline)', () => {
    const m = new WsMetrics();
    expect(() => {
      m.messages.inc({ direction: 'c2s', kind: 'data', userId: 'evil' } as Record<string, string>);
    }).toThrow(/unknown label/);
  });

  it('rejects a missing required label', () => {
    const m = new WsMetrics();
    expect(() => {
      m.messages.inc({ kind: 'data' } as Record<string, string>);
    }).toThrow(/missing label/);
  });

  it('tracks active connections as gauge (up + down)', () => {
    const m = new WsMetrics();
    m.onConnectionOpen();
    m.onConnectionOpen();
    m.onConnectionOpen();
    expect(m.activeConnections.get()).toBe(3);
    m.onConnectionClose('normal_close');
    expect(m.activeConnections.get()).toBe(2);
    m.onConnectionClose('forced_disconnect');
    m.onConnectionClose('session_expired');
    expect(m.activeConnections.get()).toBe(0);
    // Floors at 0 even with extra close
    m.onConnectionClose('normal_close');
    expect(m.activeConnections.get()).toBe(0);
  });

  it('saturationRatio: drives 80% cap alert', () => {
    const m = new WsMetrics();
    for (let i = 0; i < 8_000; i += 1) m.onConnectionOpen();
    expect(m.saturationRatio(10_000)).toBeCloseTo(0.8);
    for (let i = 0; i < 1_000; i += 1) m.onConnectionOpen();
    expect(m.saturationRatio(10_000)).toBeCloseTo(0.9);
  });

  it('records ticket redeem outcomes (4 buckets)', () => {
    const m = new WsMetrics();
    m.onTicketRedeem('success');
    m.onTicketRedeem('success');
    m.onTicketRedeem('expired');
    m.onTicketRedeem('not_found');
    m.onTicketRedeem('origin_mismatch');
    m.onTicketRedeem('fingerprint_mismatch');
    expect(m.ticketRedeemed.read({ outcome: 'success' })).toBe(2);
    expect(m.ticketRedeemed.read({ outcome: 'expired' })).toBe(1);
    expect(m.ticketRedeemed.read({ outcome: 'not_found' })).toBe(1);
    expect(m.ticketRedeemed.read({ outcome: 'origin_mismatch' })).toBe(1);
    expect(m.ticketRedeemed.read({ outcome: 'fingerprint_mismatch' })).toBe(1);
  });
});
