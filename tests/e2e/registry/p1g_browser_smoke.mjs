// E2E-P1-G LIVE browser panel-open smoke (standalone Playwright — own browser
// instance, bypassing the MCP-held shared browser). Proves the agent-openable
// studio Extensions panel actually mounts + renders in a real browser when
// host.openPanel('extensions') fires (here via the Command Palette command that
// the same enum drives). Run: node tests/e2e/registry/p1g_browser_smoke.mjs
import { createRequire } from 'module';
// Resolve playwright from the frontend workspace (where it's installed), not from
// this file's dir. Override with FRONTEND_DIR if the repo lives elsewhere.
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
  // 1) real JWT via the auth API
  const res = await fetch(`${BFF}/v1/auth/login`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  const auth = await res.json();
  if (!auth.access_token) throw new Error('login failed: ' + JSON.stringify(auth).slice(0, 120));
  ok('logged in (real JWT)');

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('  [pageerror]', String(e).slice(0, 120)));

  try {
    // 2) seed auth into localStorage on the app origin, then load the studio
    await page.goto(APP, { waitUntil: 'domcontentloaded' });
    await page.evaluate((a) => {
      localStorage.setItem('lw_auth', JSON.stringify({ accessToken: a.access_token, refreshToken: a.refresh_token }));
    }, auth);

    await page.goto(`${APP}/books/${BOOK_ID}/studio`, { waitUntil: 'domcontentloaded' });
    // studio frame present?
    await page.waitForSelector('[data-testid="palette-input"], .dv-dockview, [class*="studio"]', { timeout: 20000 }).catch(() => {});
    ok('studio route loaded (not bounced to /login)');
    if (page.url().includes('/login')) { bad('bounced to /login — auth seed failed'); throw new Error('auth'); }

    // 3) open the Command Palette (Ctrl+Shift+P) and run "Open Extensions"
    await page.keyboard.press('Control+Shift+P');
    await page.waitForSelector('[data-testid="palette-input"]', { timeout: 8000 });
    ok('command palette opened');
    await page.fill('[data-testid="palette-input"]', 'Extensions');
    const entry = '[data-testid="palette-entry-studio.openPanel.extensions"]';
    await page.waitForSelector(entry, { timeout: 5000 });
    ok('palette lists "Open Extensions" (enum→command wired)');
    await page.click(entry);

    // 4) the dock actually built + rendered the Extensions panel (the host effect)
    await page.waitForSelector('[data-testid="studio-extensions-panel"]', { timeout: 8000 });
    ok('EXTENSIONS PANEL MOUNTED in the dock (host.openPanel effect)');
    // and its Skills tab content renders
    await page.waitForSelector('[data-testid="extensions-skills-view"]', { timeout: 5000 });
    ok('Skills view rendered inside the panel');
  } catch (e) {
    bad('panel-open flow: ' + String(e.message || e).slice(0, 140));
    await page.screenshot({ path: 'tests/e2e/registry/p1g_failure.png' }).catch(() => {});
  } finally {
    await browser.close();
  }

  console.log('');
  if (failed === 0) { console.log('E2E-P1-G LIVE BROWSER PASSED'); process.exit(0); }
  else { console.log(failed + ' CHECK(S) FAILED'); process.exit(1); }
}
main().catch((e) => { console.error(e); process.exit(1); });
