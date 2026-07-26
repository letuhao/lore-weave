// S4 · A3 — the quality-conformance dock panel: reachable via palette AND the QualityHub card,
// the chapter picker + trace/empty states, the loop-connect deep-link affordance, and the M-BUG-4
// regression (arc-scope conformance parses arc_id instead of 422-ing on arc_template_id).
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { createWork } from '../helpers/motif';
import { QualityConformancePage } from '../pages/QualityConformancePage';
import { StudioPage } from '../pages/StudioPage';

test.describe('@s4 Studio · quality-conformance', () => {
  let token: string;
  let bookId: string;
  let projectId = '';
  const stamp = Date.now();

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E conformance ${stamp}`);
    await createChapter(request, token, bookId, 'Ch.1');
    projectId = await createWork(request, token, bookId);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('reachable from the palette; the panel + chapter picker render (§2#3, #1)', async ({ page }) => {
    const conf = new QualityConformancePage(page);
    await conf.open(bookId);
    await expect(conf.panel).toBeVisible();
    await expect(conf.chapterPicker).toBeVisible();
    // no chapter picked yet → an honest hint, not a blank pane
    await expect(conf.noChapter).toBeVisible();
  });

  test('reachable from the QualityHub 5th-area card (DOCK-8 pattern)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('quality', 'quality');            // the hub
    // the hub lists a conformance card that opens the panel
    const card = page.getByTestId('quality-hub-card-quality-conformance')
      .or(page.getByRole('button', { name: /conformance/i }));
    await card.first().click();
    await expect(page.getByTestId('studio-quality-conformance-panel')).toBeVisible({ timeout: 10_000 });
  });

  test('picking a chapter resolves to a trace OR an actionable empty state (never blank)', async ({ page }) => {
    const conf = new QualityConformancePage(page);
    await conf.open(bookId);
    const options = await conf.chapterPicker.locator('option').count();
    test.skip(options <= 1, 'no chapter to pick in this book');
    await conf.chapterPicker.selectOption({ index: 1 });
    // trace, or the empty state that deep-links to the scene surface (loop-connect) — both usable
    await expect(conf.trace.or(conf.empty)).toBeVisible({ timeout: 15_000 });
    // §2#6 loop-connect — if empty, the CTA back to the scene surface must exist (no island)
    if (await conf.empty.isVisible()) {
      await expect(conf.emptyBindCta).toBeVisible();
    }
  });

  test('M-BUG-4 regression — arc-scope conformance parses arc_id (NOT 422 on arc_template_id)', async ({ request }) => {
    // network-level assertion (the arc UI needs a real structure node; the WIRE ARG is the bug).
    const node = '019f0000-0000-7000-8000-000000000000';   // any UUID: the point is the arg NAME, not the node
    const auth = { headers: { Authorization: `Bearer ${token}` } };
    const oldArg = await request.get(`/v1/composition/works/${projectId}/conformance?scope=arc&arc_template_id=${node}`, auth);
    const newArg = await request.get(`/v1/composition/works/${projectId}/conformance?scope=arc&arc_id=${node}`, auth);
    expect(oldArg.status(), 'the OLD arg (arc_template_id) is dropped → 422 ARC_ID_REQUIRED').toBe(422);
    expect(newArg.status(), 'the FIXED arg (arc_id) is PARSED → 404 on a non-arc node, never 422').not.toBe(422);
  });
});
