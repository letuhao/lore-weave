// E2E — Subagents + Activity-log FE (D-REG-P5-SUBAGENTS-FE / D-REG-P5-ACTIVITY-FE).
// Live browser round-trip through the REAL backend: /extensions → Subagents tab →
// create a persona via the form → it appears (real POST /subagents) → the create
// shows up in the Activity log → cleanup (delete). Proves the wiring the unit tests
// can't (route mounts the tab; real API round-trip), against vite dev (live code).
import { createRequire } from 'module';
const require = createRequire((process.env.FRONTEND_DIR || 'D:/Works/source/lore-weave-mvp/frontend') + '/package.json');
const { chromium } = require('playwright');

const APP = process.env.APP_URL || 'http://localhost:5199';
const BFF = process.env.BFF_URL || 'http://localhost:3123';
const EMAIL = 'claude-test@loreweave.dev';
const PASSWORD = 'Claude@Test2026';

let failed = 0;
const ok = (m) => console.log('  PASS  ' + m);
const bad = (m) => { failed++; console.log('  FAIL  ' + m); };

async function main() {
  const res = await fetch(`${BFF}/v1/auth/login`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  const auth = await res.json();
  if (!auth.access_token) throw new Error('login failed');
  ok('logged in');

  const name = 'br-scout-' + Date.now().toString().slice(-6);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('  [pageerror]', String(e).slice(0, 140)));
  try {
    await page.goto(APP, { waitUntil: 'domcontentloaded' });
    await page.evaluate((a) => localStorage.setItem('lw_auth', JSON.stringify({ accessToken: a.access_token, refreshToken: a.refresh_token })), auth);
    await page.goto(`${APP}/extensions`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="extensions-page"]', { timeout: 20000 });
    if (page.url().includes('/login')) { bad('bounced to /login'); throw new Error('auth'); }

    // --- Subagents tab exists + creates a persona ---
    await page.click('[data-testid="ext-page-tab-subagents"]');
    await page.waitForSelector('[data-testid="subagents-view"]', { timeout: 8000 });
    ok('Subagents tab renders (was MISSING before)');

    await page.fill('[data-testid="sa-name"]', name);
    await page.fill('[data-testid="sa-scope"]', 'glossary_search, kg_*');
    await page.fill('[data-testid="sa-prompt"]', 'You are a browser-smoke lore scout.');
    await page.click('[data-testid="sa-create"]');
    await page.waitForFunction(
      (n) => Array.from(document.querySelectorAll('[data-testid="sa-row"]')).some((r) => r.textContent.includes(n)),
      name, { timeout: 10000 },
    );
    ok('created a subagent via the form → row appears (real POST /subagents round-trip)');

    const chips = await page.$$eval('[data-testid="sa-scope-chip"]', (els) => els.map((e) => e.textContent));
    if (chips.includes('glossary_search') && chips.includes('kg_*')) ok('scope chips rendered from the parsed globs');
    else bad('scope chips missing: ' + JSON.stringify(chips));

    // --- Activity log tab shows the create ---
    await page.click('[data-testid="ext-page-tab-activity"]');
    await page.waitForSelector('[data-testid="activity-view"]', { timeout: 8000 });
    ok('Activity log tab renders (was MISSING before)');
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll('[data-testid="activity-row"]')).some((r) => r.textContent.includes('subagent·create')),
      null, { timeout: 10000 },
    );
    ok('the subagent create appears in the Activity log (real /audit round-trip)');

    // --- cleanup: back to Subagents, delete the persona ---
    await page.click('[data-testid="ext-page-tab-subagents"]');
    await page.waitForSelector('[data-testid="subagents-view"]');
    const rows = await page.$$('[data-testid="sa-row"]');
    for (const r of rows) {
      const t = await r.textContent();
      if (t && t.includes(name)) { await (await r.$('[data-testid="sa-delete"]')).click(); break; }
    }
    await page.waitForFunction(
      (n) => !Array.from(document.querySelectorAll('[data-testid="sa-row"]')).some((r) => r.textContent.includes(n)),
      name, { timeout: 8000 },
    );
    ok('deleted the persona (cleanup)');
  } catch (e) {
    bad('flow: ' + String(e.message || e).slice(0, 160));
    await page.screenshot({ path: 'tests/e2e/registry/p5_subagents_fe_failure.png' }).catch(() => {});
  } finally {
    await browser.close();
  }
  console.log('');
  if (failed === 0) { console.log('SUBAGENTS+ACTIVITY FE BROWSER PASSED'); process.exit(0); }
  else { console.log(failed + ' CHECK(S) FAILED'); process.exit(1); }
}
main().catch((e) => { console.error(e); process.exit(1); });
