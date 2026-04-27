import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';
import { TEST_USER } from '../helpers/auth';

test.describe('Smoke: auth pipeline', () => {
  test('test user can log in and reach /books', async ({ page }) => {
    const login = new LoginPage(page);

    await login.goto();
    await login.expectVisible();

    await login.login(TEST_USER.email, TEST_USER.password);

    await page.waitForURL('**/books', { timeout: 10_000 });
    expect(new URL(page.url()).pathname).toBe('/books');
  });
});
