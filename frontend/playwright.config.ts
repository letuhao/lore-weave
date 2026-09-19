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
  // Allure is OPT-IN and must stay that way. The PO asked for it by name for the ship-proof run
  // (`allure-playwright` emits results; `allure-commandline` renders them, and that CLI needs
  // JAVA -- which this box has at 24 and **CI does not**). Making it a default reporter would put
  // a Java dependency on every CI run of a suite that does not need one.
  //
  //     PLAYWRIGHT_ALLURE=1 npx playwright test
  //     npx allure generate tests/e2e/allure-results --clean -o tests/e2e/allure-report
  //
  // The html reporter stays unconditional: it already embeds video, trace and screenshots inline
  // and needs nothing installed, so a run is never left with no readable output if Allure breaks.
  reporter: [
    ['list'],
    ['html', { outputFolder: 'tests/e2e/playwright-report', open: 'never' }],
    // ⚠️ `resultsDir`, NOT `outputFolder`. The html reporter above takes `outputFolder`, and
    // allure-playwright silently IGNORES an unknown key and falls back to `./allure-results` at
    // the package root. Measured 2026-09-13: a full run reported `PLAYWRIGHT_ALLURE=1`, wrote 676
    // result files somewhere else, and `allure generate` against the CONFIGURED path then exited
    // **0** having produced a 2 MB report from nothing. A report generated from an empty directory
    // is worse than no report -- it looks like evidence.
    ...(process.env.PLAYWRIGHT_ALLURE === '1'
      ? [['allure-playwright', {
          resultsDir: 'tests/e2e/allure-results',
          detail: true,
          suiteTitle: true,
        }] as const]
      : []),
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
