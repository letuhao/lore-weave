# @loreweave/auth-client

Shared auth API client for `frontend-game` (and any future workspace package
that needs to talk to `auth-service` through `api-gateway-bff`).

**Status:** skeleton — filled in Session E.

**Scope:** consumed by `frontend-game/` only. The novel-workflow `frontend/`
is outside the pnpm workspace (spec §1 #5) and keeps its own auth code.

**Consumption requirement** (/review-impl LOW #4): this package exports
TypeScript source directly (`main: ./src/index.ts`) — no compiled build
step yet. Consumers MUST use a TS-aware bundler (Vite, esbuild, swc, tsx).
Plain `require('@loreweave/auth-client')` from Node will fail with
`Unknown file extension ".ts"`. If a non-Vite consumer is ever needed,
add a `tsup` build step in Session C+ scaffolding.
