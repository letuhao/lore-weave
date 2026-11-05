# E2E Tests (Playwright)

End-to-end tests for the LoreWeave demo pipeline. Test framework: [Playwright](https://playwright.dev).

## Prerequisites

1. Docker compose stack up:
   ```sh
   cd ../infra && docker compose up -d
   ```
2. Wait for `frontend` (port 5174) and `api-gateway-bff` (port 3123) healthy.
3. Test account `claude-test@loreweave.dev` / `Claude@Test2026` (per CLAUDE.md).

## Running

From `frontend/`:

| Command | Use |
|---|---|
| `npm run e2e` | Headless run, all specs (CI default) |
| `npm run e2e:ui` | Playwright UI mode (watch + debug) |
| `npm run e2e:headed` | Headed (browser visible) — useful for demo recording |
| `npm run e2e:report` | Open last HTML report |

## Model-gated tests (two-model specs are a resource commitment)

Some specs guard on the test account's model count and SKIP when it is too low — for example
`composition-generate.spec.ts` needs a chat-tagged drafter **plus a distinct active critic**
(`allModels.length < 2` → skip). Read the guard as what it really is before raising the count:

- **A second ACTIVE model is not additive — it arms a different code path.** These tests ask the
  backend for two models AT ONCE, which on a local BYOK backend means two model loads
  concurrently (the pair that motivated this note was a 35B beside a 27B — it exhausted the
  machine, and every later request failed with `Engine protocol startup was aborted`, an error
  that looks like a broken model but is a resource cap).
- **Both directions are silent.** 2 → 1 and a batch of tests quietly start SKIPPING (a skip reads
  as success in a summary line — coverage drops with no red anywhere). 1 → 2 and they start
  running, which is correct, but the resource cost is a step change nothing declares at the
  account screen.
- Treat the test account's active-model count as a **safety setting**: keep it at 1 unless you
  specifically want the two-model specs, and expect the concurrent-load requirement stated above
  when you do.

## Configuration

| Env var | Default | Use |
|---|---|---|
| `PLAYWRIGHT_BASE_URL` | `http://localhost:5174` | Override frontend URL |
| `PLAYWRIGHT_TEST_EMAIL` | `claude-test@loreweave.dev` | Test account email |
| `PLAYWRIGHT_TEST_PASSWORD` | `Claude@Test2026` | Test account password |
| `PLAYWRIGHT_EXECUTABLE_PATH` | unset | Use a system browser (for example `/usr/bin/google-chrome`) when Playwright browsers are not installed |
| `PLAYWRIGHT_DEVTOOLS_PORT` | unset | Pass a Chrome DevTools remote-debugging port to the launched browser |
| `PLAYWRIGHT_VIDEO` | `retain-on-failure` | Set to `off` when system ffmpeg is unavailable |

## When you change frontend source

The docker `frontend` container serves a static built bundle (Vite build → nginx). Source changes only take effect after:

```sh
cd infra && docker compose build frontend && docker compose up -d frontend
```

For faster dev iteration, stop the docker frontend and run vite dev:

```sh
docker compose stop frontend
cd ../frontend && npm run dev   # serves on :5174 with hot reload + proxy to gateway
```

Both modes serve on `:5174` (vite proxies `/v1` and `/ws` to gateway @ `:3123`), so `PLAYWRIGHT_BASE_URL` doesn't need changing.

## Layout

```
tests/e2e/
├── README.md           ← this file
├── pages/              ← Page Object Model (UI interaction layer)
├── helpers/            ← auth, fixtures, API setup
├── specs/              ← actual tests (*.spec.ts)
└── fixtures/           ← demo book content (Phase 3 — Dracula Ch.1)
```

## Phase context

- **Phase 2 (current)**: bootstrap config + page objects + smoke login test
- **Phase 3 (next)**: full demo pipeline — book create → Dracula Ch.1 chapter → glossary extract → wiki page → knowledge graph
- **Phase 4 (later)**: video devlog recording from headed test runs

## Conventions

- Page Object Model — UI selectors live in `pages/`, never inline in specs
- No `waitForTimeout` — only `expect().toBeVisible()` / `waitForURL()` etc.
- One worker, no retries — tests must be deterministic
- Fixtures are deterministic: same book content, same expected entity set
