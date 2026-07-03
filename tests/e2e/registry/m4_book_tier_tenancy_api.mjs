// E2E — M4 book-tier tenancy (D-REG-BOOK-TIER-FE, security-critical backend).
// Proves the grant-gated, anti-oracle book-scoped listing through the REAL gateway →
// agent-registry round-trip (rebuilt image). No browser needed — this is the tenancy
// boundary the unit tests mock. Run: node tests/e2e/registry/m4_book_tier_tenancy_api.mjs
//
// Invariants proven:
//   1. create tier=book on an OWNED book → 200 (requireBookGrant passes for Owner)
//   2. list ?book_id=OWNED → the book-tier row appears
//   3. list with NO book_id → the book-tier row is NOT visible (system+user only)
//   4. list ?book_id=FOREIGN (a book you don't own) → 404 anti-oracle (not 403/empty-200)
//   5. create tier=book on a FOREIGN book → denied (not 200)
const BFF = process.env.BFF_URL || 'http://localhost:3123';
const EMAIL = 'claude-test@loreweave.dev';
const PASSWORD = 'Claude@Test2026';
const BASE = '/v1/agent-registry';
const OWNED = '019d872f-f3a3-7076-88b8-6c902054860f'; // a book owned by the test account
const FOREIGN = '00000000-0000-4000-8000-0000deadbeef'; // valid-shape UUID the user does NOT own

let failed = 0;
const ok = (m) => console.log('  PASS  ' + m);
const bad = (m) => { failed++; console.log('  FAIL  ' + m); };

async function main() {
  const login = await fetch(`${BFF}/v1/auth/login`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  const auth = await login.json();
  if (!auth.access_token) throw new Error('login failed');
  const H = { authorization: `Bearer ${auth.access_token}`, 'content-type': 'application/json' };
  ok('logged in');

  const name = 'm4-book-scout-' + Date.now().toString().slice(-6);
  let createdId = null;

  // (1) create tier=book on an OWNED book → grant passes
  const c = await fetch(`${BFF}${BASE}/subagents`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ name, system_prompt: 'book-tier tenancy smoke', tier: 'book', book_id: OWNED }),
  });
  if (c.status === 200 || c.status === 201) {
    const row = await c.json();
    createdId = row.subagent_id;
    if (row.tier === 'book') ok('create tier=book on OWNED book → 200, tier=book');
    else bad(`created but tier=${row.tier} (expected book)`);
  } else {
    bad(`create tier=book on OWNED book → ${c.status} (expected 200); ${(await c.text()).slice(0, 120)}`);
  }

  // (2) list ?book_id=OWNED → the row appears
  const lOwned = await (await fetch(`${BFF}${BASE}/subagents?book_id=${OWNED}`, { headers: H })).json();
  if ((lOwned.items || []).some((s) => s.subagent_id === createdId)) ok('list ?book_id=OWNED → book-tier row visible');
  else bad('list ?book_id=OWNED did NOT include the book-tier row');

  // (3) list with NO book_id → book-tier row NOT visible (system+user only)
  const lNone = await (await fetch(`${BFF}${BASE}/subagents`, { headers: H })).json();
  if (!(lNone.items || []).some((s) => s.subagent_id === createdId)) ok('list without book_id → book-tier row correctly hidden (tenant isolation)');
  else bad('SECURITY: book-tier row leaked into the unscoped (user) list');

  // (4) list ?book_id=FOREIGN → 404 anti-oracle (not 403, not empty-200)
  const lForeign = await fetch(`${BFF}${BASE}/subagents?book_id=${FOREIGN}`, { headers: H });
  if (lForeign.status === 404) ok('list ?book_id=FOREIGN → 404 anti-oracle (not-found ≡ not-authorized)');
  else bad(`list ?book_id=FOREIGN → ${lForeign.status} (expected 404 anti-oracle)`);

  // (5) create tier=book on a FOREIGN book → denied (grant fails)
  const cForeign = await fetch(`${BFF}${BASE}/subagents`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ name: name + '-x', system_prompt: 'should be denied', tier: 'book', book_id: FOREIGN }),
  });
  if (cForeign.status !== 200 && cForeign.status !== 201) ok(`create tier=book on FOREIGN book → denied (${cForeign.status})`);
  else bad('SECURITY: created a book-tier subagent on a book the user does not own');

  // cleanup
  if (createdId) {
    await fetch(`${BFF}${BASE}/subagents/${createdId}`, { method: 'DELETE', headers: H }).catch(() => {});
    ok('cleanup: deleted the book-tier persona');
  }

  // (6) M1/M2 ingest routes are live + admin-gated: the non-admin test account → 403
  // (proves the ingest curation endpoints are wired; the external registry PULL itself
  // needs admin role + the live public MCP registry = gate #4, unit-proven separately).
  const q = await fetch(`${BFF}${BASE}/admin/ingest/queue`, { headers: H });
  if (q.status === 403) ok('admin ingest queue → 403 for non-admin (route wired + admin-gated)');
  else bad(`admin ingest queue → ${q.status} (expected 403 for a non-admin)`);

  console.log('');
  if (failed === 0) { console.log('M4 BOOK-TIER TENANCY API PASSED'); process.exit(0); }
  else { console.log(failed + ' CHECK(S) FAILED'); process.exit(1); }
}
main().catch((e) => { console.error(e); process.exit(1); });
