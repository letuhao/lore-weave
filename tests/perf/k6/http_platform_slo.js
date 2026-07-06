// D-D-PERF-NIGHTLY — platform user-HTTP latency driver, keyed to contracts/slo/latency.yaml.
//
// Measures the p95 request duration of each platform SLO endpoint AT THE GATEWAY EDGE
// (all external traffic goes through api-gateway-bff — I1). Each endpoint records into a
// Trend metric named `slo_<id>` matching its latency.yaml row, so scripts/perf/slo_assert.py
// can map the summary back to the contracted p95 target.
//
// SAFETY — this is a nightly perf smoke, NOT a load test of side-effecting work:
//   * By default it drives ONLY idempotent GET reads (list/browse surfaces).
//   * The mutating / cost-bearing POSTs (search = embed+rerank, chat send, compose/translate
//     ENQUEUE) are gated behind PERF_DRIVE_MUTATING=1 and only fire when their resource ids
//     are supplied — so a stray nightly can never spam job queues or paid LLM calls.
//   ⚠ DANGER: PERF_DRIVE_MUTATING=1 with a REAL BOOK_ID enqueues REAL translation/composition
//     jobs and runs REAL embed/rerank — i.e. SPENDS MONEY and creates real work. NEVER set it
//     against production or a stack with a real user's book. Use a THROWAWAY stack + a scratch
//     book id only. Left off, the 4 mutating endpoints are SKIPPED (measured as no-data).
// An endpoint whose required id/flag is absent is SKIPPED (logged); slo_assert.py treats an
// unmeasured row as SKIPPED (or a failure under --require-all on a fully-seeded stack).
//
// Env:
//   TARGET      gateway base URL (default http://127.0.0.1:3123 — dev host-mapped BFF)
//   TOKEN       platform JWT (Bearer) for authed endpoints
//   BOOK_ID / SESSION_ID   resource ids for path-param endpoints
//   PERF_DRIVE_MUTATING=1  also drive the cost/mutating POSTs (throwaway stack only)
//   RATE, DURATION, PRE_VUS, MAX_VUS   k6 open-model knobs (defaults below)
//   SUMMARY_OUT k6 summary path (default k6-platform-slo-summary.json)
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = (__ENV.TARGET || 'http://127.0.0.1:3123').replace(/\/$/, '');
const TOKEN = __ENV.TOKEN || '';
const BOOK_ID = __ENV.BOOK_ID || '';
const SESSION_ID = __ENV.SESSION_ID || '';
const DRIVE_MUTATING = __ENV.PERF_DRIVE_MUTATING === '1';

const authHeaders = () => {
  const h = { 'Content-Type': 'application/json' };
  if (TOKEN) h['Authorization'] = `Bearer ${TOKEN}`;
  return h;
};

// One entry per contracts/slo/latency.yaml row. `requires` gates the endpoint on env;
// `mutating` marks the cost/side-effecting POSTs that only fire under PERF_DRIVE_MUTATING.
const ENDPOINTS = [
  // ── idempotent reads (driven by default) ──
  { id: 'catalog_list_books', method: 'GET', path: '/v1/catalog/books' },
  { id: 'notifications_list', method: 'GET', path: '/v1/notifications', requires: ['TOKEN'] },
  { id: 'glossary_list_entities', method: 'GET', path: '/v1/glossary/entities', requires: ['TOKEN'] },
  { id: 'book_list_chapters', method: 'GET', path: `/v1/books/${BOOK_ID}/chapters`, requires: ['TOKEN', 'BOOK_ID'] },
  // ── cost / mutating (gated behind PERF_DRIVE_MUTATING) ──
  {
    id: 'knowledge_search', method: 'POST', path: '/v1/knowledge/search', mutating: true,
    requires: ['TOKEN', 'BOOK_ID'], body: () => JSON.stringify({ query: 'perf smoke', book_id: BOOK_ID, limit: 5 }),
  },
  {
    id: 'chat_send_message', method: 'POST', path: `/v1/chat/sessions/${SESSION_ID}/messages`, mutating: true,
    requires: ['TOKEN', 'SESSION_ID'], body: () => JSON.stringify({ content: 'perf smoke', stream: false }),
  },
  {
    id: 'composition_enqueue', method: 'POST', path: '/v1/composition/compose', mutating: true,
    requires: ['TOKEN', 'BOOK_ID'], body: () => JSON.stringify({ book_id: BOOK_ID, mode: 'smoke' }),
  },
  {
    id: 'translation_enqueue', method: 'POST', path: '/v1/translation/jobs', mutating: true,
    requires: ['TOKEN', 'BOOK_ID'], body: () => JSON.stringify({ book_id: BOOK_ID, target_language: 'vi' }),
  },
];

const ENV = { TOKEN, BOOK_ID, SESSION_ID };
const eligible = (ep) => {
  if (ep.mutating && !DRIVE_MUTATING) return false;
  for (const req of ep.requires || []) if (!ENV[req]) return false;
  return true;
};

// A Trend per eligible endpoint → the summary carries slo_<id>.p(95).
const trends = {};
const DRIVEN = ENDPOINTS.filter(eligible);
for (const ep of DRIVEN) trends[ep.id] = new Trend(`slo_${ep.id}`, true);

export const options = {
  scenarios: {
    slo: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 20),
      timeUnit: '1s',
      duration: __ENV.DURATION || '30s',
      preAllocatedVUs: Number(__ENV.PRE_VUS || 10),
      maxVUs: Number(__ENV.MAX_VUS || 100),
    },
  },
};

export function setup() {
  const skipped = ENDPOINTS.filter((ep) => !eligible(ep)).map((ep) => ep.id);
  if (skipped.length) console.log(`[platform-slo] SKIPPED (missing id/flag): ${skipped.join(', ')}`);
  if (!DRIVEN.length) console.log('[platform-slo] WARNING: no endpoint eligible — set TOKEN/BOOK_ID or PERF_DRIVE_MUTATING');
  return {};
}

export default function () {
  // Round-robin one request per iteration across the eligible endpoints.
  if (!DRIVEN.length) return;
  const ep = DRIVEN[Math.floor(Math.random() * DRIVEN.length)];
  const url = `${BASE}${ep.path}`;
  const params = { headers: authHeaders(), tags: { slo: ep.id } };
  let res;
  if (ep.method === 'GET') {
    res = http.get(url, params);
  } else {
    res = http.post(url, ep.body ? ep.body() : null, params);
  }
  trends[ep.id].add(res.timings.duration);
  check(res, { [`${ep.id} not 5xx`]: (r) => r.status < 500 });
}

export function handleSummary(data) {
  const out = __ENV.SUMMARY_OUT || 'k6-platform-slo-summary.json';
  return { [out]: JSON.stringify(data, null, 2), stdout: '' };
}
