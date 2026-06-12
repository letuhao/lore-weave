import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';
import { EnrichmentTab } from '../pages/EnrichmentTab';
import { TEST_USER } from '../helpers/auth';

// The seeded demo Fengshen book (owned by the test user). Override via env.
const BOOK = process.env.E2E_BOOK_ID ?? '019e7850-a8d9-78dd-8b2a-f33ccc2396ad';

// GUI gap-closure browser sweep — exercises the NEW author controls through the
// REAL chain (login → gateway → FE → lore-enrichment) on the MERGED branch (main's
// ARCH MCP/AG-UI + this branch's enrichment together). It hits the two genuinely-new
// live endpoints (GET /dimensions + ?base=true) that jsdom unit tests mock, proving
// the gateway routes them + the controls render & wire. Generation-dependent journeys
// (compose run → proposal → promote) are NOT re-run here — they're API-smoke-proven
// (S1–S4 + the Step-2 live e2e); this sweep is render+wire only.
test.describe('Enrichment GUI gap-closure — browser sweep (merged branch)', () => {
  test.beforeEach(async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.expectVisible();
    await login.login(TEST_USER.email, TEST_USER.password);
    await page.waitForURL('**/books', { timeout: 15_000 });
  });

  test('the enrichment shell renders all 6 panels incl. the Compose tab (merge intact)', async ({ page }) => {
    const enr = new EnrichmentTab(page);
    await enr.goto(BOOK);
    for (const p of ['compose', 'proposals', 'gaps', 'sources', 'jobs', 'settings'] as const) {
      await expect(enr.tab(p)).toBeVisible();
    }
  });

  test('Compose author controls (Slice 1+4): technique selector + save-corpus + dimension picker (live /dimensions)', async ({ page }) => {
    const enr = new EnrichmentTab(page);
    await enr.goto(BOOK);
    await enr.openPanel('compose');

    // mode C (paste-context) → the grounded composer with the new config controls.
    await enr.composeMode('context').click();
    // a NEW target lets us pick the kind that drives the dimension fetch.
    await enr.targetNewToggle.click();
    await enr.targetKind.selectOption('character');
    await enr.targetName.fill('Sweep 真人');
    await enr.contextText.fill('崑崙修道之士，善觀星象。');

    // #2 technique selector (context/files only) + #7 save-to-corpus checkbox render.
    await expect(enr.techniqueSelect).toBeVisible();
    await expect(enr.persistCorpus).toBeVisible();

    // #1 dimension picker: the "auto" toggle appears once GET /dimensions?kind=character
    // resolves LIVE (through the gateway) — proving the new endpoint is routed + wired.
    await expect(enr.dimsAuto).toBeVisible({ timeout: 15_000 });
    await expect(enr.dimsAuto).toBeChecked(); // auto by default (server derives)
    await enr.dimsAuto.uncheck();
    await expect(enr.dimsPicker).toBeVisible();
    await expect(enr.dimsPicker.locator('button')).not.toHaveCount(0); // the kind's dim chips
  });

  test('Profile override editor (Slice 2): built-in dimension base rows from live /dimensions?base=true', async ({ page }) => {
    const enr = new EnrichmentTab(page);
    await enr.goto(BOOK);
    await enr.openPanel('settings');

    // ProfileForm loads (seeded profile), then the override editor fetches the BASE
    // dimension set per kind (?base=true) and renders relabel/reweight/hide rows.
    await expect(enr.worldview).toBeVisible();
    await expect(enr.overrideKind('character')).toBeVisible();
    await expect(enr.overrideBase('character')).toBeVisible({ timeout: 15_000 });
  });

  test('Jobs + Sources + Proposals panels mount against live data without crashing the shell', async ({ page }) => {
    const enr = new EnrichmentTab(page);
    await enr.goto(BOOK);
    // Each panel reaches its live list endpoint; we assert switching to it does NOT
    // crash the shell (the tab strip survives). The surfacing details (#4/#5/#8/#9)
    // are component-tested; this is a live mount smoke for the merged frontend.
    for (const p of ['jobs', 'sources', 'proposals'] as const) {
      await enr.openPanel(p);
      await expect(enr.tab(p)).toBeVisible();
      await expect(enr.tab('compose')).toBeVisible(); // shell intact after the switch
    }
  });
});
