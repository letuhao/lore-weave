import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5174';
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH;
const devtoolsPort = process.env.PLAYWRIGHT_DEVTOOLS_PORT;
const video = process.env.PLAYWRIGHT_VIDEO === 'off' ? 'off' as const : 'retain-on-failure' as const;

// 🔴 EVIDENCE MODE — capture on PASS, which the defaults deliberately do not.
//
// `retain-on-failure` / `only-on-failure` is the right shape for a suite whose job is red/green,
// and the wrong shape for the question the PO actually asked on 2026-09-13: *"i need to review
// what did you already test and cover by my eyes then i will sign off"*. Under the defaults, 225
// passing tests across 76 spec files leave NO artefact at all -- so the coverage is real and
// invisible, which from outside is indistinguishable from coverage that was never written.
//
// A SWITCH, not a new default. 225 tests x video is minutes and gigabytes; making every CI run pay
// that is how the switch gets turned back off by the next person in a hurry. `humanRun.ts` already
// does per-step snapshots for the persona journeys and keeps doing them either way -- this widens
// the same idea to whatever spec you point it at.
//
//     PLAYWRIGHT_EVIDENCE=1 npx playwright test tests/e2e/specs/persona-journeys.spec.ts
//
// PLAYWRIGHT_VIDEO=off still wins, so a box that cannot encode video can still capture the rest.
const evidence = process.env.PLAYWRIGHT_EVIDENCE === '1';

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
    trace: evidence ? 'on' : 'retain-on-failure',
    screenshot: evidence ? 'on' : 'only-on-failure',
    video: evidence && process.env.PLAYWRIGHT_VIDEO !== 'off' ? 'on' : video,
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
