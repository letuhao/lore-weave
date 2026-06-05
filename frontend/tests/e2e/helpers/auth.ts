import type { Page } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

export const TEST_USER = {
  email: process.env.PLAYWRIGHT_TEST_EMAIL ?? 'claude-test@loreweave.dev',
  password: process.env.PLAYWRIGHT_TEST_PASSWORD ?? 'Claude@Test2026',
} as const;

// A SECOND account for cross-user isolation tests (B9.1/B2.4/B6.3/B8.10). Created
// on demand via ensureUserB(); login has no email-verification gate in dev.
export const TEST_USER_B = {
  email: process.env.PLAYWRIGHT_TEST_EMAIL_B ?? 'claude-test2@loreweave.dev',
  password: process.env.PLAYWRIGHT_TEST_PASSWORD_B ?? 'Claude@Test2026',
} as const;

/** Log in through the UI and wait until the app lands on /books. */
export async function loginViaUI(page: Page): Promise<void> {
  const login = new LoginPage(page);
  await login.goto();
  await login.login(TEST_USER.email, TEST_USER.password);
  await page.waitForURL('**/books', { timeout: 15_000 });
}
