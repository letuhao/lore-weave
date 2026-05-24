import { defineConfig, devices } from '@playwright/test';

// Cross-browser smoke for AC-FG-16 (spec §18). Tests run against the
// dev server on :5174. Backend services (tilemap-service, game-server)
// are optional — only tested when env LOREWEAVE_E2E_FULL=1.
//
// Run:
//   pnpm --filter frontend-game e2e               # chromium only (fast CI)
//   pnpm --filter frontend-game e2e:all-browsers  # + firefox + webkit
//   LOREWEAVE_E2E_FULL=1 pnpm --filter frontend-game e2e  # with backend asserts

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: 'http://localhost:5174',
    trace: 'on-first-retry',
  },

  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5174',
    reuseExistingServer: true,
    timeout: 60_000,
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
