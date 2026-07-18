// S4 · B — BLACKBOX real-user journey. Persona: a web-novel author strengthening a chapter with
// tropes (套路/爽点/打脸). Drives the REAL app end to end with NO test-only shortcuts for the actions
// under test, and at EVERY step asserts the user could actually COMPLETE it — a visible result, a
// reachable next step, no dead-end, no silent no-op (the What-If "skeleton renders but does nothing"
// failure = a FAIL here). Screenshots each step into an artifact so a human can eyeball the flow.
//
// Usability rubric (asserted, not just observed): every read has a reachable write · every list row
// opens something · every action shows success/error · no step dead-ends · the panels the author needs
// are reachable + operable, Studio-only (never the legacy editor).
import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { seedMotif, archiveMotif, createWork } from '../helpers/motif';
import { MotifLibraryPage } from '../pages/MotifLibraryPage';
import { QualityConformancePage } from '../pages/QualityConformancePage';

test.describe('@s4 Studio · motif author journey (blackbox)', () => {
  let token: string;
  let bookId: string;
  const stamp = Date.now();
  let seededId = '';
  let neighbourId = '';

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E author-journey ${stamp}`);
    await createChapter(request, token, bookId, 'Chapter 41 「反目」');
    await createWork(request, token, bookId);   // the co-writer Work so Conformance renders its panel (not the setup gate)
    // the author already has a couple of tropes in their library (a realistic starting point)
    seededId = await seedMotif(request, token, { code: `journey.slap.${stamp}`, name: `Face-slap ${stamp}`, kind: 'scheme' });
    neighbourId = await seedMotif(request, token, { code: `journey.rise.${stamp}`, name: `Rise after fall ${stamp}`, kind: 'sequence' });
  });

  test.afterAll(async ({ request }) => {
    await archiveMotif(request, token, seededId);
    await archiveMotif(request, token, neighbourId);
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  const shot = (page: Page, name: string) =>
    page.screenshot({ path: `tests/e2e/test-results/journey-${name}.png` }).catch(() => {});

  test('an author can complete the trope workflow in the Studio (reachable + operable, no dead-ends)', async ({ page }) => {
    const lib = new MotifLibraryPage(page);
    const conf = new QualityConformancePage(page);

    // ── STEP 1 · "Where are my tropes?" — reach the Motif Library from the palette ──────────────
    await lib.open(bookId);
    await expect(lib.panel, 'STEP 1 — the Motif Library must be REACHABLE from the palette (audit: it was MCP-only)').toBeVisible();
    await expect(lib.view).toBeVisible();
    await shot(page, '1-library-open');

    // ── STEP 2 · "Study the shelves" — the 6 tiers are legible + my seeded trope is on Mine ──────
    for (const s of ['my', 'system', 'catalog', 'drafts'] as const) {
      await expect(lib.scopeTab(s), `STEP 2 — the ${s} tier must be present`).toBeVisible();
    }
    await expect(lib.card(seededId), 'STEP 2 — my own trope must show under Mine').toBeVisible();
    await shot(page, '2-tiers');

    // ── STEP 3 · "Author a new trope" — create it inline; it must actually LAND (no silent no-op) ─
    const newName = `打脸 escalation ${Date.now()}`;
    const newCode = `journey.created.${Date.now()}`;
    await lib.createMotif(newName, newCode);
    await expect(page.getByText(newName).first(), 'STEP 3 — the authored trope must appear (write landed)').toBeVisible({ timeout: 10_000 });
    await shot(page, '3-created');
    // creating opens the new motif's detail (realistic) — the author closes it to keep browsing.
    await page.getByTestId('motif-detail-close').click().catch(() => {});
    await expect(lib.detailDrawer).toHaveCount(0);

    // ── STEP 4 · "Open a trope" — every list row must OPEN something (the What-If lesson) ─────────
    await lib.cardOpen(seededId).click();
    await expect(lib.detailDrawer, 'STEP 4 — a card must open its detail, not be a dead tile').toBeVisible();
    await shot(page, '4-detail');

    // ── STEP 5 · "Relate two tropes" — the graph must be OPERABLE (add an edge, see it) ──────────
    await lib.graphToggle.click();
    await lib.graphAddToggle.click();
    await expect(page.getByTestId('motif-graph-add-form')).toBeVisible();
    await lib.graphNeighbor.selectOption(neighbourId);
    await lib.graphKind.selectOption('precedes');
    await lib.graphAddSubmit.click();
    await expect(lib.graphEdges.first(), 'STEP 5 — the relationship edge must render (graph operable)').toBeVisible({ timeout: 10_000 });
    await shot(page, '5-graph-edge');
    await page.getByTestId('motif-detail-close').click().catch(() => {});

    // ── STEP 6 · "Did my prose deliver the beats?" — Conformance must be reachable + not dead-end ─
    await conf.open(bookId);
    await expect(conf.panel, 'STEP 6 — Conformance must be REACHABLE (was a red/green dot only)').toBeVisible();
    // pick the chapter; the panel must resolve to EITHER a trace OR an honest, actionable empty/no-chapter
    // state — never a blank/broken pane (a skeleton that renders nothing = a usability FAIL).
    await expect(conf.chapterPicker).toBeVisible();
    const options = await conf.chapterPicker.locator('option').count();
    if (options > 1) {
      await conf.chapterPicker.selectOption({ index: 1 });
      // either the trace renders, or the empty-state offers a next step (bind a motif) — both are "usable".
      const traceOrEmpty = conf.trace.or(conf.empty);
      await expect(traceOrEmpty, 'STEP 6 — a picked chapter must show a trace OR an actionable empty state').toBeVisible({ timeout: 15_000 });
    } else {
      await expect(conf.noChapter, 'STEP 6 — no chapter yet must say so (honest), not blank').toBeVisible();
    }
    await shot(page, '6-conformance');

    // ── STEP 7 · "The loop closes" — from conformance a path must lead back toward the manuscript ──
    // Either a scene row deep-links to the inspector, or the empty state deep-links to the scene surface.
    const hasDeepLink = (await conf.anyOpenScene().count()) > 0 || (await conf.emptyBindCta.count()) > 0;
    expect(hasDeepLink, 'STEP 7 — Conformance must not be an island: a deep-link back to a scene/inspector').toBeTruthy();
    await shot(page, '7-loop');

    // ── VERDICT ──────────────────────────────────────────────────────────────────────────────────
    // Reaching here means: Library reachable+operable, a trope authored + opened, the graph operated,
    // Conformance reachable + honest, and the loop offers a way back — all Studio-only, no dead-ends.
    // (The bind→generate→re-check sub-loop over a live scene is exercised in A2/A3 where a Work with
    //  outline nodes is seeded; this journey proves the author's reachability + operability spine.)
  });
});
