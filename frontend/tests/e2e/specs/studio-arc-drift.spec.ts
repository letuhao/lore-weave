// Wave-4 (D-ARC-TEMPLATE-DRIFT-VIEW) — the arc-templates DriftSection renders the STRUCTURED
// drift view (a derived verdict + coverage / pacing / succession / folded sections), not the old
// raw <pre> JSON dump. Seeds a template + an arc stamped with arc_template_id (so it IS a drift
// subject) via the REAL gateway; asserts by data-testid (i18n-agnostic), by presence not counts.
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { createWork } from '../helpers/motif';
import { seedArcTemplate, seedArc } from '../helpers/arc';
import { StudioPage } from '../pages/StudioPage';

test.describe('@s4 Studio · arc-template drift view', () => {
  let token: string;
  let bookId = '';
  let templateId = '';
  let arcId = '';
  const stamp = Date.now();

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E arc-drift ${stamp}`);
    await createChapter(request, token, bookId, 'Ch.1');
    await createWork(request, token, bookId); // the co-writer Work → the project_id the drift route needs
    templateId = await seedArcTemplate(request, token, `e2e.arc.${stamp}`, `E2E Arc ${stamp}`);
    // Stamp arc_template_id directly (materialize does this server-side) so the arc IS a drift subject.
    const arc = await seedArc(request, token, bookId, `Materialized ${stamp}`, { arc_template_id: templateId });
    arcId = arc.id;
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('a materialized arc renders the STRUCTURED drift view, not raw JSON', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('arc-templates', 'arc templ');

    // select the seeded template → its detail (with the DriftSection) mounts
    await page.getByTestId(`arc-row-${templateId}`).click();
    await expect(page.getByTestId('arc-template-detail')).toBeVisible();

    // the drift section lists the arc that used this template → open its drift
    await expect(page.getByTestId(`drift-arc-${arcId}`)).toBeVisible();
    await page.getByTestId(`drift-arc-${arcId}`).click();

    // the STRUCTURED view renders (a derived verdict + the pacing section) — and the old
    // raw <pre data-testid="arc-drift-report"> dump is GONE.
    await expect(page.getByTestId('arc-drift-view')).toBeVisible();
    await expect(page.getByTestId('arc-drift-pacing')).toBeVisible();
    await expect(page.getByTestId('arc-drift-report')).toHaveCount(0);
    // an all-empty template drifts to the honest "no drift / clean" verdict (never a blank).
    await expect(page.getByTestId('arc-drift-clean')).toBeVisible();
  });
});
