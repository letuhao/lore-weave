// S7 F4 — WebSocket echo ROUND-TRIP driver (Colyseus protocol).
//
// Speaking Colyseus's msgpack room protocol by hand in k6 is brittle (the seat
// reservation + JOIN_REQUEST handshake), so per the spec's documented choice
// (D-S7-WS-K6-PROTOCOL) the WS round-trip uses the REAL colyseus.js client,
// which speaks the protocol correctly. This is closed-loop (sequential
// round-trips → per-message latency), the tradeoff vs k6's open-loop HTTP — the
// HTTP generators (http_livez/http_matchmake.js) carry the coordinated-omission-
// correct throughput story; this carries the WS round-trip latency story.
//
// Dev auth: game-server booted without LW_WS_REDIS_URL → EchoRoom.onAuth uses
// the static-token path, so joinOrCreate('echo', { jwt: 'dev_token' }) succeeds.
//
// NO threshold asserted (S7 §0) — writes a percentile summary artifact.
import { Client } from 'colyseus.js';
import { writeFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

const wsEndpoint = process.env.TARGET_WS || 'ws://127.0.0.1:2567';
const N = Number(process.env.WS_ROUNDTRIPS || 500);
const token = process.env.LOREWEAVE_INTERNAL_TOKEN || 'dev_token';
const out = process.env.SUMMARY_OUT || 'k6-ws-echo-summary.json';

function pct(sorted, p) {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
}

async function main() {
  const client = new Client(wsEndpoint);
  const room = await client.joinOrCreate('echo', { jwt: token });

  // The room sends a 'welcome' on join — register a no-op so colyseus.js does
  // not warn "onMessage() not registered for type 'welcome'".
  room.onMessage('welcome', () => {});

  // Single handler resolves the in-flight round-trip.
  let pending = null;
  room.onMessage('echo', () => {
    const p = pending;
    pending = null;
    if (p) p();
  });

  const roundtrip = (seq) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending = null;
        reject(new Error(`echo round-trip ${seq} timed out`));
      }, 5000);
      pending = () => {
        clearTimeout(timer);
        resolve();
      };
      room.send('echo', { seq });
    });

  await new Promise((r) => setTimeout(r, 200)); // let 'welcome' settle

  const times = [];
  for (let i = 0; i < N; i++) {
    const t0 = performance.now();
    await roundtrip(i);
    times.push(performance.now() - t0);
  }

  await room.leave(true);

  times.sort((a, b) => a - b);
  const summary = {
    metric: 'ws_echo_roundtrip',
    model: 'closed-loop (colyseus.js client)',
    count: N,
    unit: 'ms',
    p50: pct(times, 50),
    p90: pct(times, 90),
    p99: pct(times, 99),
    p999: pct(times, 99.9),
    max: times[times.length - 1] ?? 0,
  };
  writeFileSync(out, JSON.stringify(summary, null, 2));
  // eslint-disable-next-line no-console
  console.log('[ws-echo]', JSON.stringify(summary));
}

main().then(
  () => process.exit(0),
  (err) => {
    // eslint-disable-next-line no-console
    console.error('[ws-echo] FAILED:', err.message);
    process.exit(3); // distinct from 0/2 so the run script can classify
  },
);
