import { test, expect } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { loginViaUI } from '../helpers/auth';

// QC Track-B — the personal assistant's DESKTOP data-rights surface. This is the A2 fix (Memory + the
// forget/erase controls were mobile-only) + the fail-closed capture-consent (S9). Everything here is
// NON-DESTRUCTIVE: it asserts reachability + fail-closed defaults, and opens the erase/new-epoch confirms
// but CANCELS them (never executes) — safe to run repeatedly against the shared dev account.
test.describe('Assistant — data-rights reachability + fail-closed (S2/S4/S5/S9/S12)', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('S9 — capture consent is OFF by default (fail-closed) on desktop', async ({ page }) => {
    const a = new AssistantPage(page);
    await a.goto();
    await expect(a.consentToggle).toBeVisible();
    // The whole tenant-safety promise: nothing is captured until the user opts in.
    expect(await AssistantPage.isOn(a.consentToggle)).toBe(false);
  });

  test('S12/S2 — Memory + Journal are reachable on desktop, and recall search is present', async ({ page }) => {
    const a = new AssistantPage(page);
    await a.goto();
    // The A2 parity fix: these were mounted only in the mobile dock before.
    await expect(a.openJournal).toBeVisible();
    await expect(a.openMemory).toBeVisible();

    await a.openMemorySheet();
    await expect(a.memorySearch).toBeVisible(); // "ask your own memory" recall (S2)
    await expect(a.memoryList).toBeVisible();
  });

  test('S5 — Erase-everything is reachable on desktop and is a two-step confirm (cancel, no execute)', async ({ page }) => {
    const a = new AssistantPage(page);
    await a.goto();
    await a.openMemorySheet();

    // The data-rights control the first-run promises — now on desktop (A2).
    await expect(a.eraseAllZone).toBeVisible();
    // Step 1: the confirm is hidden until opened; nothing destructive yet.
    await expect(a.eraseAllConfirm).toBeHidden();
    await a.eraseAllOpen.click();
    await expect(a.eraseAllConfirm).toBeVisible();
    // Step 2 is worded + guarded — we CANCEL (this is a non-destructive reachability check).
    await a.eraseAllCancel.click();
    await expect(a.eraseAllConfirm).toBeHidden();
  });

  test('S8 — "changed jobs / new chapter" is reachable on desktop and confirm-gated (cancel)', async ({ page }) => {
    const a = new AssistantPage(page);
    await a.goto();
    await a.openMemorySheet();
    await expect(a.newEpochZone).toBeVisible();
    await a.newEpochOpen.click();
    await expect(page.getByTestId('memory-new-epoch-confirm')).toBeVisible();
    await a.newEpochCancel.click();
    await expect(page.getByTestId('memory-new-epoch-confirm')).toBeHidden();
  });

  test('S7 — Practice interview is reachable from the assistant (links to /roleplay)', async ({ page }) => {
    const a = new AssistantPage(page);
    await a.goto();
    await expect(a.practiceLink).toHaveAttribute('href', '/roleplay');
    await a.gotoPractice();
    await page.waitForURL('**/roleplay', { timeout: 15_000 });
  });
});
