# @loreweave/design-tokens

Shared design tokens for `frontend-game`: Tailwind preset, CSS variables,
and a typed color palette consumed by both React (DOM HUD) and Phaser
(canvas tint constants).

**Status:** skeleton — filled in Session C.

**Why both DOM and canvas:** spec §1 #3 picks a hybrid React + Phaser UI.
A React HUD bar at `#ef4444` and a canvas damage flash at `0xef4444` must
read as the same red. This package is the SSOT preventing drift.

**Consumption requirement** (/review-impl LOW #4): TypeScript source as
package entry — TS-aware bundler (Vite, etc.) required. Same caveat as
all `@loreweave/*` packages in this workspace.
