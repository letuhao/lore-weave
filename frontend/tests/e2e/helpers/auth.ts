import type { Page } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

export const TEST_USER = {
  email: process.env.PLAYWRIGHT_TEST_EMAIL ?? 'claude-test@loreweave.dev',
  password: process.env.PLAYWRIGHT_TEST_PASSWORD ?? 'Claude@Test2026',
} as const;

/** Log in through the UI and wait until the app lands on /books. */
export async function loginViaUI(page: Page): Promise<void> {
  const login = new LoginPage(page);
  await login.goto();
  await login.login(TEST_USER.email, TEST_USER.password);
  await page.waitForURL('**/books', { timeout: 15_000 });
}
