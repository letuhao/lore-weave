// S7 F4 — open-loop HTTP load on the Colyseus matchmake endpoint
// (POST /matchmake/joinOrCreate/echo) — the SEAT-RESERVATION path. NOTE: Colyseus
// runs onAuth at the WS JOIN (seat consumption), not at this HTTP reservation, so
// the jwt in the body below is NOT validated at this stage — this script measures
// matchmake/seat-reservation HTTP throughput, not the auth gate (the WS auth gate
// is exercised by ws_echo.mjs + game-server's own edge tests).
//
// Same coordinated-omission-correct constant-arrival-rate model as livez, at a
// MODEST rate: each matchmake reserves a seat that expires after
// seatReservationTime (~30s) since this generator does NOT complete the WS join,
// so a high sustained rate would just accumulate short-lived reservations. This
// measures the matchmake HTTP path throughput, not sustained connections.
//
// NO threshold asserted (S7 §0); the summary JSON is the artifact.
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.TARGET || 'http://127.0.0.1:2567';

export const options = {
  scenarios: {
    matchmake: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 100),
      timeUnit: '1s',
      duration: __ENV.DURATION || '15s',
      preAllocatedVUs: Number(__ENV.PRE_VUS || 50),
      maxVUs: Number(__ENV.MAX_VUS || 400),
    },
  },
};

export default function () {
  const res = http.post(
    `${BASE}/matchmake/joinOrCreate/echo`,
    JSON.stringify({ jwt: __ENV.LOREWEAVE_INTERNAL_TOKEN || 'dev_token' }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  // 200 = seat reserved; the body carries the reservation. We don't redeem it.
  check(res, { 'reserved (200)': (r) => r.status === 200 });
}

export function handleSummary(data) {
  const out = __ENV.SUMMARY_OUT || 'k6-matchmake-summary.json';
  return { [out]: JSON.stringify(data, null, 2) };
}
