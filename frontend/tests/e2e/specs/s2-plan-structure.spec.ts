// S2 — PLAN & STRUCTURE coverage. Per-panel operability against the §2 production-ready bar:
// arc-inspector (32), arc-templates (34), the 拆文 Import & Deconstruct section (34 §4.3) and the
// 34a book-shared tier. Every step is a real click/fill against the live login/gateway/composition
// stack — no mocks. Seeds a deterministic arc surface via the REAL arc routes S2 owns.
//
// Run against the S2 build:  PLAYWRIGHT_BASE_URL=http://localhost:5199 npm run e2e -- s2-plan-structure
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, createCompositionWork, trashBook } from '../helpers/api';
import { seedArc, seedBookSharedTemplate } from '../helpers/arc';
import { PlanStructurePage } from '../pages/PlanStructurePage';

test.describe('S2 · Plan & Structure panels (operable to the §2 bar)', () => {
  let bookId = '';
  let token = '';
  let arcId = '';

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `S2 E2E — plan & structure ${Date.now()}`);
    await createChapter(request, token, bookId, 'Chapter 1');
    await createCompositionWork(request, token, bookId); // a Work → apply-preview has a projectId
    const arc = await seedArc(request, token, bookId, 'The Betrayal Arc');
    arcId = arc.id;
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test('arc-inspector: pick → inspect → edit identity → add a track → archive → restore', async ({ page }) => {
    await loginViaUI(page);
    const s2 = new PlanStructurePage(page);
    await s2.openInspector(bookId);

    // 1 · Pick the seeded arc → the body renders (identity/tracks/roster/chapters/provenance/danger).
    await s2.selectArc(arcId);
    await expect(s2.fTitle).toHaveValue('The Betrayal Arc');
    await expect(page.getByTestId('arc-provenance-none')).toBeVisible(); // authored, no template

    // 2 · Edit the goal (blur → OCC PATCH) → reload the panel → the change PERSISTED (read↔write closure).
    await s2.editField(s2.fGoal, 'She must choose between vengeance and the child.');
    await expect(s2.writeError).toHaveCount(0);
    await page.reload();
    await s2.openInspector(bookId);
    await s2.selectArc(arcId);
    await expect(s2.fGoal).toHaveValue('She must choose between vengeance and the child.');

    // 3 · D-ARC-NO-ADD-CASCADE-ENTRY — the CREATE verb: add a brand-new own track with a fresh key.
    const add = s2.addTrackForm();
    await add.open.click();
    await add.key.fill('revenge');
    await add.label.fill('The revenge line');
    await add.submit.click();
    await expect(s2.trackRow('revenge')).toBeVisible();

    // 4 · Archive → the danger action returns chapters to the tray; the panel offers Restore (not a dead
    //     end). Even when this is the last arc (the shell empties), the archived detail stays visible so
    //     Restore is reachable — the bug this spec caught live (ArcInspectorPanel emptyBook gate).
    await s2.archive.click();
    await expect(s2.archivedBanner).toBeVisible();
    await expect(s2.restore).toBeVisible();
    // 5 · Restore → editable again (the archived banner clears).
    await s2.restore.click();
    await expect(s2.archivedBanner).toHaveCount(0);
  });

  test('arc-templates: library CRUD (create → appears → open detail → archive)', async ({ page }) => {
    await loginViaUI(page);
    const s2 = new PlanStructurePage(page);
    await s2.openTemplates(bookId);

    // Create a template through the UI (the CRUD the library was missing) → it appears in the list.
    const code = `e2e-${Date.now()}`;
    await s2.createTemplate(code, 'E2E Hero Journey');
    const rowByName = page.getByText('E2E Hero Journey').first();
    await expect(rowByName).toBeVisible({ timeout: 15_000 });

    // Open its detail → the timeline + apply-preview + drift section render (reused motif surface).
    await rowByName.click();
    await expect(s2.detail).toBeVisible();
    await expect(s2.driftSection).toBeVisible();
    // Drift with no materialized arc yet → the honest "not applied" empty (not a blank / not an error).
    await expect(page.getByTestId('arc-drift-unapplied')).toBeVisible();
    await s2.back.click();
  });

  test('arc-templates: the three tabs are reachable (Library / Catalog / Import & Deconstruct)', async ({ page }) => {
    await loginViaUI(page);
    const s2 = new PlanStructurePage(page);
    await s2.openTemplates(bookId);

    await s2.tab('catalog').click();
    // Catalog is a paged public projection — either rows or the honest empty, never a crash.
    await expect(page.getByTestId('arc-catalog').or(page.getByTestId('arc-catalog-empty'))).toBeVisible({ timeout: 15_000 });

    await s2.tab('deconstruct').click();
    await expect(s2.deconstructSection).toBeVisible();
    await expect(s2.deconstructCopyright).toBeVisible(); // B-3 privacy stated up front, not buried

    await s2.tab('library').click();
    await expect(s2.newButton).toBeVisible();
  });

  test('拆文: a source can be added, and Deconstruct is BLOCKED until a model is picked (AT-8 no silent payer)', async ({ page }) => {
    await loginViaUI(page);
    const s2 = new PlanStructurePage(page);
    await s2.openTemplates(bookId);
    await s2.tab('deconstruct').click();
    await expect(s2.deconstructSection).toBeVisible();

    // Add a reference source through the UI → it appears in the source list.
    await s2.pasteTitle.fill('Reference: a betrayal beat');
    await s2.pasteContent.fill('A loyal captain is betrayed by the prince he served, and swears revenge across three cities.');
    await s2.pasteSubmit.click();
    await expect(page.getByText('Reference: a betrayal beat')).toBeVisible({ timeout: 15_000 });

    // AT-8: with a source selected but NO model chosen, the priced Deconstruct button stays disabled —
    // there is no silent platform-fallback payer. (A real run needs a BYOK model + confirm; covered at
    // the priced-flow level, not billed here.)
    await expect(s2.deconstructRun).toBeDisabled();
  });

  test('34a book tier: a book-shared template is visible in the Book tier', async ({ page, request }) => {
    // Seed a book-shared template via the real EDIT-gated route, then prove the Book tab surfaces it.
    const code = `e2e-shared-${Date.now()}`;
    const shared = await seedBookSharedTemplate(request, token, bookId, code, 'E2E Shared Arc');
    expect(shared.book_shared).toBe(true);

    await loginViaUI(page);
    const s2 = new PlanStructurePage(page);
    await s2.openTemplates(bookId);
    await s2.tier('book').click();
    await expect(s2.row(shared.id)).toBeVisible({ timeout: 15_000 });
  });
});
