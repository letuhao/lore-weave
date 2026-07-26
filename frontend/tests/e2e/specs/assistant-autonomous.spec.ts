import { test, expect } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { loginViaUI } from '../helpers/auth';

// QC Track-B — the autonomous layer's settings (A3 + the proactive debt-clear). Assert the control is
// present and every job toggle is FAIL-CLOSED OFF by default (arming spends background tokens, so it must
// never be on without an explicit opt-in). Read-only: this does NOT arm anything (the arm→fire scenario
// is a heavier stateful test — see the QC plan S10 — that needs the scheduler tick + cleanup).
test.describe('Assistant — autonomous settings fail-closed (S10)', () => {
  test('the autonomous panel renders with every job toggle OFF by default', async ({ page }) => {
    await loginViaUI(page);
    const a = new AssistantPage(page);
    await a.goto();

    await expect(a.autonomousSettings).toBeVisible();

    // The four schedule-driven jobs + the double-gated proactive row — all fail-closed OFF.
    for (const kind of ['eod_distill', 'weekly_reflection', 'weekly_rollup', 'nudge', 'proactive_nudge']) {
      const toggle = a.autonomousToggle(kind);
      await expect(toggle, `${kind} toggle present`).toBeVisible();
      expect(await AssistantPage.isOn(toggle), `${kind} fail-closed OFF`).toBe(false);
    }
  });
});
