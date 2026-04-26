export const TEST_USER = {
  email: process.env.PLAYWRIGHT_TEST_EMAIL ?? 'claude-test@loreweave.dev',
  password: process.env.PLAYWRIGHT_TEST_PASSWORD ?? 'Claude@Test2026',
} as const;
