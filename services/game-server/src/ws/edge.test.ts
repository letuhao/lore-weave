import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ConnectionCap, MessageRateLimiter, rateLimitsFromEnv, DEFAULT_RATE_LIMITS } from './rate-limit.js';
import { LogWsAuditSink, type WsAuditEvent } from './audit.js';

test('ConnectionCap: acquire up to max, then reject; release frees a slot', () => {
  const cap = new ConnectionCap(2);
  assert.equal(cap.acquire('u'), true);
  assert.equal(cap.acquire('u'), true);
  assert.equal(cap.acquire('u'), false); // at cap → caller rejects (4008)
  assert.equal(cap.active('u'), 2);
  cap.release('u');
  assert.equal(cap.acquire('u'), true);
  assert.equal(cap.acquire('other'), true); // independent per user
});

test('ConnectionCap.atCap: reflects the cap without mutating (MED-1 onAuth check)', () => {
  const cap = new ConnectionCap(2);
  assert.equal(cap.atCap('u'), false);
  cap.acquire('u');
  assert.equal(cap.atCap('u'), false);
  cap.acquire('u');
  assert.equal(cap.atCap('u'), true); // at cap → onAuth rejects (4008)
  assert.equal(cap.active('u'), 2); // atCap is a pure check (no mutation)
  cap.release('u');
  assert.equal(cap.atCap('u'), false);
});

test('ConnectionCap: release never goes negative; deletes at zero', () => {
  const cap = new ConnectionCap(3);
  cap.release('ghost'); // no-op, no throw
  assert.equal(cap.active('ghost'), 0);
  cap.acquire('u');
  cap.release('u');
  assert.equal(cap.active('u'), 0);
});

test('MessageRateLimiter: allows perWindow then blocks; resets next window', () => {
  const rl = new MessageRateLimiter(3, 1000);
  assert.equal(rl.allow(0), true);
  assert.equal(rl.allow(100), true);
  assert.equal(rl.allow(200), true);
  assert.equal(rl.allow(300), false); // 4th in the same window → blocked
  assert.equal(rl.allow(1000), true); // new window resets the count
});

test('rateLimitsFromEnv: defaults when unset', () => {
  delete process.env.LW_WS_MAX_CONN_PER_USER;
  delete process.env.LW_WS_MSG_PER_WINDOW;
  delete process.env.LW_WS_RATE_WINDOW_MS;
  assert.deepEqual(rateLimitsFromEnv(), DEFAULT_RATE_LIMITS);
});

test('LogWsAuditSink: emits structured JSON with audit+service keys', () => {
  const lines: string[] = [];
  const sink = new LogWsAuditSink((l) => lines.push(l));
  const ev: WsAuditEvent = { kind: 'ws.connection.opened', connectionId: 'c1', userRefId: 'u1', at: 123 };
  sink.emit(ev);
  const parsed = JSON.parse(lines[0]);
  assert.equal(parsed.audit, 'ws');
  assert.equal(parsed.service, 'game-server');
  assert.equal(parsed.kind, 'ws.connection.opened');
  assert.equal(parsed.connectionId, 'c1');
  assert.equal(parsed.userRefId, 'u1');
});

test('LogWsAuditSink: rejection event carries the close code', () => {
  const lines: string[] = [];
  new LogWsAuditSink((l) => lines.push(l)).emit({
    kind: 'ws.handshake.rejected',
    reason: 'ticket_origin_mismatch',
    closeCode: 4007,
    at: 1,
  });
  const parsed = JSON.parse(lines[0]);
  assert.equal(parsed.closeCode, 4007);
  assert.equal(parsed.reason, 'ticket_origin_mismatch');
});
