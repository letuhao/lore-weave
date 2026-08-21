import { defineConfig, devices } from '@playwright/test';

// Cross-browser smoke for AC-FG-16 (spec §18). Tests run against the
// dev server on :5176.
//
// ⚠ 5176, NOT 5174 — `vite.config.ts` moved frontend-game to 5176 with
// `strictPort: true` ("the original 5174 went stale: `frontend/` moved to
// 5174"). A config left on 5174 fails QUIETLY in both directions: in CI the
// webServer starts vite on 5176 and polls 5174 until it times out, and locally
// `reuseExistingServer: true` cheerfully hands the suite whatever is on 5174 —
// the OTHER application — so every test runs against the wrong app and the
// failures read like a rotten suite.
//
// This file carried 5174 **on `feat/game-logic` only**, and that is worth
// stating precisely, because the first version of this comment did not: `main`
// had already been repaired, and its `frontend-game-e2e` job has been green
// since 2026-08-09. The branch was ~115 commits behind and stale. What looked
// like an undiscovered defect was a fix that existed and had not been merged
// down — `git show origin/main:<file>` would have said so in one command.
//
// Backend services (tilemap-service, game-server)
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
