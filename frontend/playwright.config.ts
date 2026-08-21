import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5174';
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH;
const devtoolsPort = process.env.PLAYWRIGHT_DEVTOOLS_PORT;
const video = process.env.PLAYWRIGHT_VIDEO === 'off' ? 'off' as const : 'retain-on-failure' as const;

export default defineConfig({
  testDir: './tests/e2e/specs',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'tests/e2e/playwright-report', open: 'never' }],
  ],
  outputDir: 'tests/e2e/test-results',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video,
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    launchOptions: {
      ...(executablePath ? { executablePath } : {}),
      ...(devtoolsPort ? { args: [`--remote-debugging-port=${devtoolsPort}`] } : {}),
    },
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
