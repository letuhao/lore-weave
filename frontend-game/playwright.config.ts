import { defineConfig, devices } from '@playwright/test';

// Cross-browser smoke for AC-FG-16 (spec §18). Tests run against the
// dev server on :5176.
//
// ⚠ 5176, NOT 5174, and this file said 5174 until 2026-08-21. `vite.config.ts`
// moved frontend-game to 5176 with `strictPort: true` — its own header explains
// why: *"the original 5174 went stale: `frontend/` moved to 5174"*. This config
// was left behind, and the failure is quiet in both directions. In CI the
// webServer starts vite (which binds 5176) and then polls 5174 until it times
// out. LOCALLY, with `reuseExistingServer: true` and the OTHER app's container
// on 5174, every test happily runs against the wrong application: seven
// failures that look like a rotten suite and are nothing of the kind. Backend services (tilemap-service, game-server)
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
    baseURL: 'http://localhost:5176',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5176',
    reuseExistingServer: true,
    timeout: 60_000,
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
