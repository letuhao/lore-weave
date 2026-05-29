/**
 * L6.A.3 — Session router tests (RAID cycle 28).
 *
 * The router dispatches inbound envelopes to control replies, data
 * forwards, or rejections. Control fast-path bypasses authz (cycle-29
 * L6.C re-auth applies to data only).
 */

import { routeInbound, validateEnvelope, ENVELOPE_VERSION } from './session-router';
import { WsMetrics } from './metrics';

function dataEnv(extra: Record<string, unknown> = {}) {
  return {
    v: ENVELOPE_VERSION,
    kind: 'data',
    type: 'chat.message',
    dir: 'c2s',
    seq: 1,
    nonce: 'n1',
    payload: { body: 'hi' },
    ...extra,
  };
}

describe('session-router', () => {
  describe('validateEnvelope', () => {
    it('passes a valid data envelope', () => {
      expect(() => validateEnvelope(dataEnv())).not.toThrow();
    });

    it('rejects version mismatch', () => {
      expect(() => validateEnvelope({ ...dataEnv(), v: 99 })).toThrow(/v=99/);
    });

    it('rejects bad kind', () => {
      expect(() => validateEnvelope({ ...dataEnv(), kind: 'bogus' })).toThrow(/bad kind/);
    });

    it('rejects bad direction', () => {
      expect(() => validateEnvelope({ ...dataEnv(), dir: 'b2b' })).toThrow(/bad direction/);
    });

    it('rejects data envelope without nonce', () => {
      expect(() => validateEnvelope({ ...dataEnv(), nonce: undefined })).toThrow(/nonce/);
    });

    it('rejects non-object inputs', () => {
      expect(() => validateEnvelope(null)).toThrow();
      expect(() => validateEnvelope('not-json')).toThrow();
    });
  });

  describe('routeInbound', () => {
    let metrics: WsMetrics;

    beforeEach(() => {
      metrics = new WsMetrics();
    });

    it('routes ws.ping → ws.pong (control ack)', () => {
      const env = { v: ENVELOPE_VERSION, kind: 'control', type: 'ws.ping', dir: 'c2s' };
      const out = routeInbound(env, metrics);
      expect(out.tag).toBe('control_ack');
      if (out.tag !== 'control_ack') return;
      expect(out.reply.type).toBe('ws.pong');
      expect(out.reply.dir).toBe('s2c');
      expect(metrics.messages.read({ direction: 'c2s', kind: 'control' })).toBe(1);
    });

    it('routes ws.refresh → refresh_requested + invokes hook', () => {
      const env = { v: ENVELOPE_VERSION, kind: 'control', type: 'ws.refresh', dir: 'c2s' };
      const hook = jest.fn();
      const out = routeInbound(env, metrics, { onRefreshRequested: hook });
      expect(out.tag).toBe('refresh_requested');
      expect(hook).toHaveBeenCalledTimes(1);
    });

    it('routes ws.close → control ack', () => {
      const env = { v: ENVELOPE_VERSION, kind: 'control', type: 'ws.close', dir: 'c2s' };
      const out = routeInbound(env, metrics);
      expect(out.tag).toBe('control_ack');
    });

    it('rejects unknown control type', () => {
      const env = { v: ENVELOPE_VERSION, kind: 'control', type: 'ws.mystery', dir: 'c2s' };
      const out = routeInbound(env, metrics);
      expect(out).toEqual({ tag: 'rejected', reason: 'unknown_type' });
    });

    it('forwards data envelopes downstream', () => {
      const out = routeInbound(dataEnv(), metrics);
      expect(out.tag).toBe('data_forward');
      if (out.tag !== 'data_forward') return;
      expect(out.type).toBe('chat.message');
      expect(out.payload).toEqual({ body: 'hi' });
      expect(metrics.messages.read({ direction: 'c2s', kind: 'data' })).toBe(1);
    });

    it('rejects s2c envelopes from client', () => {
      const out = routeInbound(dataEnv({ dir: 's2c' }), metrics);
      expect(out).toEqual({ tag: 'rejected', reason: 'direction_invalid' });
    });

    it('rejects schema-invalid input gracefully', () => {
      const out = routeInbound({ junk: true }, metrics);
      expect(out.tag).toBe('rejected');
    });
  });
});
