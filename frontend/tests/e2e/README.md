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

## Configuration

| Env var | Default | Use |
|---|---|---|
| `PLAYWRIGHT_BASE_URL` | `http://localhost:5174` | Override frontend URL |
| `PLAYWRIGHT_TEST_EMAIL` | `claude-test@loreweave.dev` | Test account email |
| `PLAYWRIGHT_TEST_PASSWORD` | `Claude@Test2026` | Test account password |

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
