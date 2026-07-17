// S2 — BLACKBOX USER JOURNEY. Not a per-panel check: a real web-novel author's end-to-end path
// through Plan & Structure, asserting the thing S2 exists to fix — that a GUI-only author can plan
// and structure a book entirely in the Studio, never dropping to the agent or a raw BE call.
//
// The evaluation question (the PO's "is it genuinely usable?"): with only clicks, can the author
// inspect a deep arc, EDIT the plan that steers generation, create + browse arc templates, and start
// a deconstruction — from a near-fresh book? Each step is a human action against the real
// login/gateway/composition stack.
//
// Run against the S2 build:  PLAYWRIGHT_BASE_URL=http://localhost:5199 npm run e2e -- s2-blackbox
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, createCompositionWork, trashBook } from '../helpers/api';
import { seedArc } from '../helpers/arc';
import { PlanStructurePage } from '../pages/PlanStructurePage';

test.describe('S2 · blackbox author journey (plan & structure, Studio-only)', () => {
  let bookId = '';
  let token = '';
  let arcId = '';

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    // A near-fresh book: a chapter + a co-writer Work + ONE arc — the "I've begun structuring in the
    // Plan Hub" state a real author reaches before they want to inspect/refine an arc.
    bookId = await createBook(request, token, `S2 blackbox — author journey ${Date.now()}`);
    await createChapter(request, token, bookId, 'Opening');
    await createCompositionWork(request, token, bookId);
    arcId = (await seedArc(request, token, bookId, 'Act I — The Fall')).id;
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test('a GUI-only author inspects an arc, refines the plan, and works templates — all in the Studio', async ({ page }) => {
    await loginViaUI(page);
    const s2 = new PlanStructurePage(page);

    // 1 · The author opens the Arc Inspector and picks their arc — the deep view the PlanDrawer used to
    //     only stub. It is fully operable (identity + the cascade + chapters + provenance + danger).
    await s2.openInspector(bookId);
    await s2.selectArc(arcId);
    await expect(s2.fTitle).toHaveValue('Act I — The Fall');

    // 2 · They refine the GOAL — the field that actually reaches the generation prompt — and it STICKS
    //     across a reload (the read↔write closure a GUI author needs; no agent, no /edit page).
    await s2.editField(s2.fGoal, 'The hero loses everything and learns the cost of pride.');
    await expect(s2.writeError).toHaveCount(0);
    await page.reload();
    await s2.openInspector(bookId);
    await s2.selectArc(arcId);
    await expect(s2.fGoal).toHaveValue('The hero loses everything and learns the cost of pride.');

    // 3 · They add a plot track to the arc (the CREATE verb the cascade was missing) — steering the
    //     arc's threads without touching the agent.
    const add = s2.addTrackForm();
    await add.open.click();
    await add.key.fill('pride');
    await add.submit.click();
    await expect(s2.trackRow('pride')).toBeVisible();

    // 4 · They move to Arc Templates and create a reusable template from scratch — it lands in "Mine".
    //     Templates are user-scoped + persist on the shared dev DB → a UNIQUE name keeps the selector
    //     exact across reruns. [[shared-dev-db-not-clean-fixture-e2e]]
    await s2.openTemplates(bookId);
    const stamp = Date.now();
    const tmplName = `My Reusable Act Structure ${stamp}`;
    await s2.createTemplate(`journey-${stamp}`, tmplName);
    await expect(page.getByText(tmplName)).toBeVisible({ timeout: 15_000 });

    // 5 · They open Import & Deconstruct to turn a reference story into a template — the priced 拆文
    //     flow is present, states its privacy contract, and gates on a chosen model (no silent payer).
    await s2.tab('deconstruct').click();
    await expect(s2.deconstructSection).toBeVisible();
    await expect(s2.deconstructCopyright).toBeVisible();

    // Verdict: from a near-fresh book, a GUI-only author inspected an arc, refined the plan that steers
    // generation, added a track, created a template, and reached the deconstruction flow — entirely in
    // the Studio. S2's reason to exist: Plan & Structure is operable without the agent or a raw BE call.
  });
});
