# Plan — Session B: pnpm workspace (game subtree) + packages/ skeletons

> **Spec:** `docs/specs/2026-05-24-frontend-game-architecture.md` (§1 #5, §16 Session B, §18 AC-FG-1/2 — all revised 2026-05-24)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Size:** XL (11 files, mostly skeletons; gate-classified XL on file count, but logic surface is minimal)
> **PO pushback resolved:** original spec pulled `frontend/` into the pnpm workspace; PO rejected. Revised scope: `frontend/` is fully untouched, workspace is scoped to game subtree only.

## Goal

Lay down the monorepo plumbing for `frontend-game/` (built in Sessions C-F) without disturbing the live novel-workflow `frontend/`. After Session B:

- `pnpm install` from repo root resolves the game subtree workspace (no-op for now — packages have no deps, `frontend-game/` doesn't exist yet)
- 4 shared packages exist as skeletons ready to be filled in Sessions C-D
- `frontend/` is bit-for-bit unchanged (`git diff frontend/` empty)

## Out of scope (Session B)

- `frontend-game/` itself — Session C
- Phaser, React, or any runtime code in packages — Session D fills `packages/api-types` with tilemap-service types; auth-client gets real code in Session E; design-tokens consumed in Session C; i18n consumed in Session D
- TypeScript build (`tsc`) — skeletons re-export `{}` only; nothing to build yet
- Tests — skeletons have nothing to test yet

## Files to create (11)

| # | File | Purpose |
|---|---|---|
| 1 | `pnpm-workspace.yaml` | Lists `frontend-game`, `packages/*`. Explicitly NOT `frontend`. |
| 2 | `package.json` (root) | pnpm workspace root, `"private": true`, no runtime deps, scripts forward to `pnpm --filter ...` |
| 3 | `.npmrc` | `node-linker=isolated`, `strict-peer-dependencies=false` (Phaser 4 peer warnings are noisy; deferred to Session C) |
| 4 | `packages/auth-client/package.json` | `@loreweave/auth-client`, private, MIT, 0.0.0, exports `./src/index.ts` |
| 5 | `packages/auth-client/src/index.ts` | `export {};` stub |
| 6 | `packages/api-types/package.json` | `@loreweave/api-types`, private, MIT, 0.0.0 |
| 7 | `packages/api-types/src/index.ts` | `export {};` stub |
| 8 | `packages/design-tokens/package.json` | `@loreweave/design-tokens`, private, MIT, 0.0.0 |
| 9 | `packages/design-tokens/src/index.ts` | `export {};` stub |
| 10 | `packages/i18n/package.json` | `@loreweave/i18n`, private, MIT, 0.0.0, includes `locales/**/*.json` in `files` |
| 11 | `packages/i18n/src/index.ts` | `export {};` stub |

Plus locale data (not counted as code files — verbatim copy):
- `packages/i18n/locales/{en,ja,vi,zh-TW}/common.json` — one-time copy of `frontend/src/i18n/locales/<lang>/common.json` (game-relevant subset will be added in Session D; for now we seed full file so dropping novel-workflow-specific keys is a later cleanup, not lost data)

Plus README for each package (optional, but standard practice):
- `packages/auth-client/README.md`
- `packages/api-types/README.md`
- `packages/design-tokens/README.md`
- `packages/i18n/README.md`

## Files NOT to touch

- `frontend/**` — bit-for-bit unchanged. Verification: `git diff frontend/` empty
- `services/**` — no compose changes; tilemap-service stays at port 8220
- `infra/docker-compose.yml` — frontend-game compose entry added in Session F
- `.github/workflows/**` — no CI changes (workspace will run via existing CI when frontend-game has tests in Session C+)

## Naming convention

Package scope `@loreweave/*` chosen because:
- Matches existing project name (`loreweave-frontend`)
- Scoped names prevent collision with any public npm package
- Workspace `pnpm` resolves `@loreweave/foo` to local `packages/foo` automatically

## Verification (Phase 6 evidence)

1. `pnpm install` from repo root → exit 0, no errors. (May warn about lockfile creation — expected.)
2. `git diff frontend/` → empty output
3. `git status` → only new files (no modifications to existing files except spec + plan)
4. Each `packages/*/package.json` parses (jq or `node -e "JSON.parse(require('fs').readFileSync(...))"`)
5. `pnpm-workspace.yaml` valid YAML (parse via Python or pnpm itself)

## Risk register

| Risk | Mitigation |
|---|---|
| pnpm not installed on CI runner | Defer to Session F when CI is wired; for local dev, document `npm install -g pnpm` in repo README (not in scope here) |
| Root `package.json` accidentally hoists deps that `frontend/` was relying on at a transitive level | Impossible — `frontend/` is OUTSIDE the workspace; pnpm `node_modules/.pnpm/` is isolated to subtree packages |
| Locale JSON keys diverge between `frontend/` and `packages/i18n/` over time | Accepted (per §1 decision #11). Future refactor: if convergence becomes needed, migrate `frontend/` into workspace then. |
| `.npmrc` settings break Session C Phaser install | `strict-peer-dependencies=false` mitigates; revisit in Session C if Phaser 4 has hard peer-dep requirements |
| Workflow gate's "XL" classification overhead | Accepted — extra rigor for skeleton-heavy change is cheap. Plan doc IS the artifact XL requires. |

## Sequence

1. Write `pnpm-workspace.yaml`
2. Write root `package.json`
3. Write `.npmrc`
4. For each of 4 packages: `package.json` + `src/index.ts` + `README.md`
5. Copy 4 locale `common.json` files into `packages/i18n/locales/<lang>/`
6. Install pnpm globally if missing: `npm install -g pnpm` (developer tooling, not CI)
7. Run `pnpm install` from repo root → confirm clean exit
8. `git diff frontend/` → confirm empty
9. Self-review (Phase 7): walk file list, check each `package.json` parses, scope name is correct, no accidental `dependencies`/`devDependencies` block on skeleton packages
