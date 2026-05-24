import { test, expect } from '@playwright/test';

// Cross-browser V0 smoke per spec AC-FG-16 (Chrome + Firefox + Safari).
// Run via Playwright config which spins up dev server automatically.

test.describe('V0 smoke — static routes (no backend)', () => {
  test('/login renders', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/login');
    await expect(page).toHaveTitle(/LoreWeave/);
    await expect(page.getByRole('heading', { name: /Login/ })).toBeVisible();

    expect(errors, 'no uncaught page errors').toEqual([]);
  });

  test('/world-select renders', async ({ page }) => {
    await page.goto('/world-select');
    await expect(page.getByRole('heading', { name: /Select World/ })).toBeVisible();
  });

  test('login → world-select → play navigation', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: /Continue as guest/ }).click();
    await expect(page).toHaveURL(/\/world-select/);

    await page.getByRole('button', { name: /Enter world/ }).click();
    await expect(page).toHaveURL(/\/play/);
  });
});

test.describe('V0 smoke — /play (Phaser + HUD)', () => {
  test('canvas mounts + HUD visible (AC-FG-5, AC-FG-6)', async ({ page }) => {
    await page.goto('/play');

    // Canvas exists — Phaser bridge mounted (AC-FG-5 needs backend assets;
    // here we just verify the bridge lifecycle runs).
    // .first() because React StrictMode double-mounts Phaser in dev,
    // briefly producing 2 canvas elements before cleanup.
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 10_000 });

    // HUD bars render — React DOM overlay on top of canvas (AC-FG-6).
    await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();
    await expect(page.getByText(/MP \d+ \/ \d+/)).toBeVisible();

    // Sidebar placeholder
    await expect(page.getByRole('button', { name: /Sidebar/ })).toBeVisible();
  });

  test('EchoPanel renders connecting state (AC-FG-9 partial)', async ({ page }) => {
    await page.goto('/play');
    // EchoPanel always renders; status is "connecting" without game-server,
    // "connected" with it. Either is acceptable for cross-browser smoke.
    await expect(page.getByText(/game-server:/)).toBeVisible({ timeout: 5_000 });
  });
});
