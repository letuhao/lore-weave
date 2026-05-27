# @loreweave/api-types

TypeScript mirrors of backend service contracts (tilemap-service, future
character-service, etc.) consumed by `frontend-game`.

**Status:** skeleton — filled in Session D.

**Generation:** hand-typed for V0. If type count exceeds ~20, revisit
auto-gen from OpenAPI (spec §17) or `schemars` JSON Schema export from
Rust services.

**Consumption requirement** (/review-impl LOW #4): TypeScript source as
package entry — TS-aware bundler (Vite, etc.) required. Same caveat as
all `@loreweave/*` packages in this workspace.
