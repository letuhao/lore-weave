// S7 F4 — open-loop HTTP load on game-server /livez (pure-transport ceiling).
//
// constant-arrival-rate is k6's OPEN model: it dispatches a FIXED request rate
// regardless of how fast the server replies, so the latency histogram is
// coordinated-omission-correct (a slow server does NOT throttle the offered
// load — the spec §8 requirement). k6 records p50/p99/p99.9 natively.
//
// NO threshold is asserted (S7 §0 "no pass/fail numbers until baselined"): the
// summary JSON is the baseline artifact. The run is valid iff the server stayed
// up (the boot script curls /livez before invoking k6).
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.TARGET || 'http://127.0.0.1:2567';

export const options = {
  scenarios: {
    livez: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 500),
      timeUnit: '1s',
      duration: __ENV.DURATION || '20s',
      preAllocatedVUs: Number(__ENV.PRE_VUS || 50),
      maxVUs: Number(__ENV.MAX_VUS || 800),
    },
  },
};

export default function () {
  const res = http.get(`${BASE}/livez`);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  const out = __ENV.SUMMARY_OUT || 'k6-livez-summary.json';
  return { [out]: JSON.stringify(data, null, 2) };
}
