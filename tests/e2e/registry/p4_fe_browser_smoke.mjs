// E2E-P4 FE — live browser render of the Commands & Hooks builder + a real create
// through the backend. Standalone Playwright (own chromium). Proves the tab renders +
// the command form round-trips to agent-registry.
import { createRequire } from 'module';
const require = createRequire((process.env.FRONTEND_DIR || 'D:/Works/source/lore-weave-mvp/frontend') + '/package.json');
const { chromium } = require('playwright');

const APP = process.env.APP_URL || 'http://localhost:5174';
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

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('  [pageerror]', String(e).slice(0, 140)));
  try {
    await page.goto(APP, { waitUntil: 'domcontentloaded' });
    await page.evaluate((a) => localStorage.setItem('lw_auth', JSON.stringify({ accessToken: a.access_token, refreshToken: a.refresh_token })), auth);
    await page.goto(`${APP}/extensions`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="extensions-page"]', { timeout: 20000 });
    if (page.url().includes('/login')) { bad('bounced to /login'); throw new Error('auth'); }

    await page.click('[data-testid="ext-page-tab-commands"]');
    await page.waitForSelector('[data-testid="commands-hooks-view"]', { timeout: 8000 });
    ok('Commands & Hooks tab renders');
    await page.waitForSelector('[data-testid="commands-section"]');
    await page.waitForSelector('[data-testid="hooks-section"]');
    ok('both builder sections present');

    // create a command through the real backend
    const nonce = 'br' + Date.now().toString().slice(-6);
    await page.fill('[data-testid="cmd-name"]', nonce);
    await page.fill('[data-testid="cmd-template"]', 'Test template {{args}}');
    await page.click('[data-testid="cmd-create"]');
    await page.waitForFunction(
      (n) => Array.from(document.querySelectorAll('[data-testid="cmd-row"]')).some((r) => r.textContent.includes('/' + n)),
      nonce, { timeout: 8000 },
    );
    ok('created a command via the builder → appears in the list (real backend round-trip)');

    // clean it up via the row delete
    const rows = await page.$$('[data-testid="cmd-row"]');
    for (const r of rows) {
      const t = await r.textContent();
      if (t && t.includes('/' + nonce)) { await (await r.$('[data-testid="cmd-delete"]')).click(); break; }
    }
    ok('deleted the test command');
  } catch (e) {
    bad('flow: ' + String(e.message || e).slice(0, 140));
    await page.screenshot({ path: 'tests/e2e/registry/p4_fe_failure.png' }).catch(() => {});
  } finally {
    await browser.close();
  }
  console.log('');
  if (failed === 0) { console.log('E2E-P4 FE BROWSER PASSED'); process.exit(0); }
  else { console.log(failed + ' CHECK(S) FAILED'); process.exit(1); }
}
main().catch((e) => { console.error(e); process.exit(1); });
