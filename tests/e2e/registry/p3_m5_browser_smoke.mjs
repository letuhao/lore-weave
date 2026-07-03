// E2E-P3-M5 LIVE browser smoke (standalone Playwright — own browser instance).
// Proves the external-MCP FE renders + drives in a real browser: open the studio
// Extensions panel → MCP Servers tab → Add server → the 4-step wizard mounts and
// advances step 1→2. Run: node tests/e2e/registry/p3_m5_browser_smoke.mjs
import { createRequire } from 'module';
const require = createRequire((process.env.FRONTEND_DIR || 'D:/Works/source/lore-weave-mvp/frontend') + '/package.json');
const { chromium } = require('playwright');

const APP = process.env.APP_URL || 'http://localhost:5174';
const BFF = process.env.BFF_URL || 'http://localhost:3123';
const EMAIL = 'claude-test@loreweave.dev';
const PASSWORD = 'Claude@Test2026';
const BOOK_ID = process.env.BOOK_ID || '019d872f-f3a3-7076-88b8-6c902054860f';

let failed = 0;
const ok = (m) => console.log('  PASS  ' + m);
const bad = (m) => { failed++; console.log('  FAIL  ' + m); };

async function main() {
  const res = await fetch(`${BFF}/v1/auth/login`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  const auth = await res.json();
  if (!auth.access_token) throw new Error('login failed: ' + JSON.stringify(auth).slice(0, 120));
  ok('logged in (real JWT)');

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('  [pageerror]', String(e).slice(0, 160)));

  try {
    await page.goto(APP, { waitUntil: 'domcontentloaded' });
    await page.evaluate((a) => {
      localStorage.setItem('lw_auth', JSON.stringify({ accessToken: a.access_token, refreshToken: a.refresh_token }));
    }, auth);

    // Use the standalone /extensions route (simpler than the studio dock; same components).
    await page.goto(`${APP}/extensions`, { waitUntil: 'domcontentloaded' });
    if (page.url().includes('/login')) { bad('bounced to /login — auth seed failed'); throw new Error('auth'); }
    await page.waitForSelector('[data-testid="extensions-page"]', { timeout: 20000 });
    ok('/extensions page loaded');

    // MCP Servers tab
    await page.click('[data-testid="ext-page-tab-mcp"]');
    await page.waitForSelector('[data-testid="mcp-servers-view"]', { timeout: 8000 });
    ok('MCP Servers tab renders the servers view (real backend list)');

    // Add server → wizard
    await page.click('[data-testid="mcp-add-button"]');
    await page.waitForSelector('[data-testid="mcp-add-wizard"]', { timeout: 5000 });
    ok('Add server → 4-step wizard mounted');
    await page.waitForSelector('[data-testid="wiz-steps"]', { timeout: 3000 });

    // Fill step 1 + advance to step 2
    await page.fill('[data-testid="wiz-endpoint-url"]', 'https://mcp.example.com/mcp');
    await page.click('[data-testid="wiz-next"]');
    // step 2 (auth) — the none-auth hint or a Register & scan next button
    await page.waitForSelector('[data-testid="wiz-next"]', { timeout: 5000 });
    const stepText = await page.textContent('[data-testid="wiz-steps"]');
    if (stepText && stepText.includes('Auth')) ok('wizard advanced to the Auth step');
    else bad('wizard did not advance');
  } catch (e) {
    bad('mcp FE flow: ' + String(e.message || e).slice(0, 160));
    await page.screenshot({ path: 'tests/e2e/registry/p3_m5_failure.png' }).catch(() => {});
  } finally {
    await browser.close();
  }

  console.log('');
  if (failed === 0) { console.log('E2E-P3-M5 LIVE BROWSER PASSED'); process.exit(0); }
  else { console.log(failed + ' CHECK(S) FAILED'); process.exit(1); }
}
main().catch((e) => { console.error(e); process.exit(1); });
