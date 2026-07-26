// S3 (PlanForge) e2e coverage — the Pass Rail + Planner + checkpoint surfaces built this session.
// Two tiers:
//   • REACHABILITY + COPY (no model): the panel is palette-reachable, the propose-blind honesty copy
//     renders, the planner↔rail deep-links exist.
//   • FULL JOURNEY [model-gated]: a real gemma run — propose → compile → run the passes → review the
//     cast checkpoint (readable content + PF-7 seed gate) → apply seed → approve → the cursor
//     advances past cast; then archive/restore the run. Skips cleanly without a local chat model.
import { test, expect } from '@playwright/test';
import { StudioPassRailPage } from '../pages/StudioPassRailPage';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import {
  findGemma, createPlanRun, waitProposed, compileArc, getPasses, runPass,
} from '../helpers/planforge';

const PREMISE = `# STORY PLAN — e2e
## 1. Premise
A discarded fifth miss transmigrates, masters a corrupt technique, and takes revenge.
## 2. Arcs
- Arc I — The Discarded Miss: awakening, humiliation, first face-slap.
- Arc II — The Corrupt Path: the flawed technique, corruption debt.
- Arc III — Reckoning: confront the rival and the elders.
## 3. Cast
Diep Van Vu (protagonist), Bach Su (mentor), To Diep (rival).
## 4. Planner Variables
PA = Perfection_Addiction, HA = Humanity_Anchor, CD = Corruption_Debt.
`;

test.describe('PlanForge Pass Rail — reachability + honesty copy', () => {
  test('the Pass Rail is palette-reachable and the planner shows the propose-blind honesty + rail link', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `S3 reach ${Date.now()}`);
    try {
      await loginViaUI(page);
      const s = new StudioPassRailPage(page);
      await s.gotoStudio(bookId);

      // reachable via the command palette (§2.3)
      await s.openPassRail();
      await expect(s.railPanel).toBeVisible();
      // a book with no compiled run shows the honest empty state, never a blank panel (§2.4)
      await expect(page.getByTestId('plan-passes-no-run').or(page.getByTestId('plan-passes-not-compiled'))).toBeVisible();

      // planner: the propose-blind honesty copy + the loop-connect deep-link to the rail
      await s.planner.open();
      await s.planner.runTab().click();
      await expect(s.planner.proposeBlindNote()).toContainText('Existing chapters are not read');
      await expect(s.planner.passRailLink()).toBeVisible();
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});

test.describe('PlanForge Pass Rail — full journey [model-gated]', () => {
  test('propose → compile → run passes → approve cast checkpoint (seed gate) → cursor advances; archive/restore', async ({ page, request }) => {
    test.setTimeout(400_000);
    const token = await getAccessToken(request);
    const gemma = await findGemma(request, token);
    test.skip(!gemma, 'needs the local gemma-4-26B-A4B QAT model (LM Studio)');

    const bookId = await createBook(request, token, `S3 journey ${Date.now()}`);
    try {
      // 1 · propose (gemma) → real arcs
      const runId = await createPlanRun(request, token, bookId, {
        source_markdown: PREMISE, mode: 'llm', model_ref: gemma!, genre_tags: ['xianxia'],
      });
      const run = await waitProposed(request, token, bookId, runId);
      expect(run.arcs.length).toBeGreaterThanOrEqual(1);

      // 2 · compile the FIRST arc — F-5 guarantees every arc has events, so this materialises chapters
      const arcId = run.arcs[0].id;
      const comp = await compileArc(request, token, bookId, runId, arcId);
      expect(comp.status, `compile: ${JSON.stringify(comp.body)}`).toBe(200);

      // 3 · run motifs (advisory) then cast (blocking) via the API, then drive the GUI review
      const gm = gemma!;
      await runPass(request, token, bookId, runId, 'motifs', gm);
      const afterCast = await runPass(request, token, bookId, runId, 'cast', gm);
      expect(afterCast.blocked_at).toBe('cast'); // the compiler stops at the cast checkpoint

      // 4 · GUI: open the rail on THIS run, review cast, clear the seed gate, approve
      await loginViaUI(page);
      const s = new StudioPassRailPage(page);
      await s.gotoStudio(bookId);
      await s.openPassRail();
      // pick this run if a picker is present (H4), else the rail already binds the latest
      if (await s.runPicker.isVisible().catch(() => false)) {
        const opt = s.runPicker.locator('option', { hasText: runId.slice(0, 8) });
        await s.runPicker.selectOption(await opt.getAttribute('value') ?? '');
      }
      await expect(s.reviewButton('cast')).toBeVisible();
      await s.reviewButton('cast').click();

      // the review renders a READABLE cast list (F-1), not raw JSON
      await expect(s.review.content()).toBeVisible();
      await expect(s.review.rawJson()).toHaveCount(0);

      // the PF-7 seed gate: Approve is disabled until the seed is applied
      if (await s.review.seedGate().isVisible().catch(() => false)) {
        await expect(s.review.approve()).toBeDisabled();
        await s.review.applySeed().click();
        await expect(s.review.approve()).toBeEnabled({ timeout: 30_000 });
      }
      await s.review.approve().click();

      // the cursor advanced past cast (blocked_at cleared, world/beats unblocked)
      await expect(async () => {
        const l = await getPasses(request, token, bookId, runId);
        expect(l.pass_cursor).toBeGreaterThanOrEqual(2);
        expect(l.passes.find((p) => p.pass_id === 'cast')?.decision).toBe('accepted');
      }).toPass({ timeout: 15_000 });

      // 5 · archive the run then restore it (BE-4)
      await s.planner.open();
      await s.planner.runsTab().click();
      await page.getByTestId(`plan-run-archive-${runId.slice(0, 8)}`).click();
      await expect(page.getByTestId(`plan-run-archive-${runId.slice(0, 8)}`)).toHaveCount(0);
      await s.planner.showArchived().check();
      await page.getByTestId(`plan-run-restore-${runId.slice(0, 8)}`).click();
      await expect(page.getByTestId(`plan-run-archive-${runId.slice(0, 8)}`)).toBeVisible();
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
