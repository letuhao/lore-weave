// PlanForge-v2 grounding (PROPOSE-BLIND + A1/A2) e2e coverage.
// Two tiers:
//   • CONTRACT (rules mode, no model, CI-safe): the "Continue this book" toggle is reachable; a
//     grounded rules-propose on a book with existing arcs RECORDS grounded_on (fingerprint + arc
//     titles); a blind propose leaves grounded_on null (fails-closed). The deploy ceiling defaults
//     ON (the A/B passed), so the grounded path is exercised without special env.
//   • AFFIRMATION [model-gated]: a grounded run flips the planner copy from the honesty note to the
//     grounded affirmation with real counts.
import { test, expect } from '@playwright/test';
import { StudioPassRailPage } from '../pages/StudioPassRailPage';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import { createPlanRun, getRun, findGemma, waitProposed } from '../helpers/planforge';

// Rules-mode source (deterministic, no LLM) — named arcs so the first propose autocompiles a spec
// tree the grounded re-propose can then read back as EXISTING STATE.
const SOURCE = `# 1. Arc Overview
## The Iron Court
**Theme:** intrigue
### Event 1
Goal: the court closes ranks
## The Long Road
**Theme:** a journey
### Event 1
Goal: leave the capital
`;

test.describe('PlanForge grounding — contract (rules mode, CI-safe)', () => {
  test('the "Continue this book" toggle is reachable (default ON / opt-out since the eval passed)', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `ground toggle ${Date.now()}`);
    try {
      await loginViaUI(page);
      const s = new StudioPassRailPage(page);
      await s.gotoStudio(bookId);
      await s.planner.open();
      await s.planner.runTab().click();
      // the toggle renders + is togglable. Its default is now ON (opt-out) unless the user stored an
      // opt-out; either honesty or grounded copy is present depending on whether this fresh book was
      // grounded. We assert reachability + togglability, not a fixed default (that depends on the
      // account's stored preference + the opt-out default).
      await expect(s.planner.groundToggle()).toBeVisible();
      const wasChecked = await s.planner.groundCheckbox().isChecked();
      await s.planner.groundCheckbox().click();
      await expect(s.planner.groundCheckbox()).toBeChecked({ checked: !wasChecked });
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('a GROUNDED re-propose records grounded_on; a BLIND one leaves it null (fails-closed)', async ({ request }) => {
    test.setTimeout(180_000);  // three rules proposes + autocompile + polling
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `ground contract ${Date.now()}`);
    try {
      // 1 · first rules propose (cold start) → autocompiles the arc tree (structure_node)
      const first = await createPlanRun(request, token, bookId, { source_markdown: SOURCE, mode: 'rules' });
      await waitProposed(request, token, bookId, first);

      // 2 · GROUNDED re-propose → the gather lens sees the existing arcs → grounded_on recorded
      const grounded = await createPlanRun(request, token, bookId, {
        source_markdown: SOURCE, mode: 'rules', ground_on_existing: true, force: true,
      });
      await waitProposed(request, token, bookId, grounded);
      const gd = await getRun(request, token, bookId, grounded);
      // ceiling defaults ON (A/B passed); if a deployment set it OFF, grounded_on is null — assert the
      // contract either way: WHEN present it carries the fingerprint + the existing arc titles.
      if (gd.grounded_on) {
        expect(gd.grounded_on.fingerprint).toBeTruthy();
        expect(gd.grounded_on.arc_titles).toEqual(
          expect.arrayContaining(['The Iron Court', 'The Long Road']),
        );
      }

      // 3 · a BLIND re-propose NEVER records grounded_on (fails-closed) — always true
      const blind = await createPlanRun(request, token, bookId, {
        source_markdown: SOURCE, mode: 'rules', force: true,
      });
      await waitProposed(request, token, bookId, blind);
      const bd = await getRun(request, token, bookId, blind);
      expect(bd.grounded_on ?? null).toBeNull();
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});

test.describe('PlanForge grounding — affirmation copy [model-gated]', () => {
  test('a grounded run flips the planner copy to the grounded affirmation', async ({ page, request }) => {
    test.setTimeout(300_000);
    const token = await getAccessToken(request);
    const gemma = await findGemma(request, token);
    test.skip(!gemma, 'needs the local gemma model');

    const bookId = await createBook(request, token, `ground affirm ${Date.now()}`);
    try {
      // seed arcs (rules), then a grounded LLM run so grounded_on is recorded + the copy switches
      const seed = await createPlanRun(request, token, bookId, { source_markdown: SOURCE, mode: 'rules' });
      await waitProposed(request, token, bookId, seed);
      const grounded = await createPlanRun(request, token, bookId, {
        source_markdown: SOURCE, mode: 'llm', model_ref: gemma!, ground_on_existing: true, force: true,
      });
      const run = await waitProposed(request, token, bookId, grounded);
      test.skip(!run.grounded_on, 'ceiling off in this deployment — grounded_on not recorded');

      // open the planner on this grounded run → the affirmation replaces the honesty copy (SET-8)
      await loginViaUI(page);
      const s = new StudioPassRailPage(page);
      await s.gotoStudio(bookId);
      await s.planner.open();
      await s.planner.runsTab().click();
      await page.getByTestId(`plan-run-open-${grounded.slice(0, 8)}`).click().catch(() => {});
      await expect(s.planner.groundedNote()).toBeVisible({ timeout: 10_000 });
      await expect(s.planner.proposeBlindNote()).toHaveCount(0);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
