// E2E-P5 FE — live browser bundle import (headline P5-M4 UX). Standalone Playwright.
// Opens /extensions → Plugins tab → uploads a real bundle file → the plugin appears
// (real backend import round-trip) → export button present → cleanup.
import { createRequire } from 'module';
import { writeFileSync, mkdtempSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
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

  const ns = 'br' + Date.now().toString().slice(-6);
  const bundle = {
    manifest: { name: `io.browser/${ns}`, version: '1.0.0', description: 'browser import test' },
    skills: [{ slug: `${ns}-skill`, description: 's', body_md: '# body', surfaces: ['chat'] }],
    commands: [{ name: `${ns}-cmd`, description: 'c', template_md: 'Do {{args}}', expand_side: 'server' }],
    hooks: [],
  };
  const dir = mkdtempSync(join(tmpdir(), 'lw-bundle-'));
  const bundlePath = join(dir, 'test.loreweave-bundle.json');
  writeFileSync(bundlePath, JSON.stringify(bundle));

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('  [pageerror]', String(e).slice(0, 140)));
  try {
    await page.goto(APP, { waitUntil: 'domcontentloaded' });
    await page.evaluate((a) => localStorage.setItem('lw_auth', JSON.stringify({ accessToken: a.access_token, refreshToken: a.refresh_token })), auth);
    await page.goto(`${APP}/extensions`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="extensions-page"]', { timeout: 20000 });
    if (page.url().includes('/login')) { bad('bounced to /login'); throw new Error('auth'); }

    await page.click('[data-testid="ext-page-tab-plugins"]');
    await page.waitForSelector('[data-testid="plugins-view"]', { timeout: 8000 });
    ok('Plugins tab renders');

    // upload the bundle file to the hidden input → import
    await page.setInputFiles('[data-testid="plugin-import-file"]', bundlePath);
    await page.waitForFunction(
      (n) => Array.from(document.querySelectorAll('[data-testid="plugin-row"]')).some((r) => r.textContent.includes(n)),
      `io.browser/${ns}`, { timeout: 10000 },
    );
    ok('imported the bundle via the file picker → plugin appears (real backend round-trip)');
    await page.waitForSelector('[data-testid="plugin-export"]');
    ok('exported-bundle affordance present on the row');

    // cleanup via the row delete
    const rows = await page.$$('[data-testid="plugin-row"]');
    for (const r of rows) {
      const t = await r.textContent();
      if (t && t.includes(`io.browser/${ns}`)) { await (await r.$('[data-testid="plugin-delete"]')).click(); break; }
    }
    ok('deleted the imported plugin');
  } catch (e) {
    bad('flow: ' + String(e.message || e).slice(0, 160));
    await page.screenshot({ path: 'tests/e2e/registry/p5_fe_failure.png' }).catch(() => {});
  } finally {
    await browser.close();
  }
  console.log('');
  if (failed === 0) { console.log('E2E-P5 FE BROWSER PASSED'); process.exit(0); }
  else { console.log(failed + ' CHECK(S) FAILED'); process.exit(1); }
}
main().catch((e) => { console.error(e); process.exit(1); });
