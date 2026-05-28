# @loreweave/i18n

Cluster-language translations for `frontend-game`. Supports `en`, `ja`,
`vi`, `zh-TW` (matching the novel-workflow `frontend/` cluster).

**Status:** skeleton — filled in Session D.

**Origin:** locales seeded from `frontend/src/i18n/locales/` on
2026-05-24 (one-time copy via `git`), then pruned to the `common.*`
namespace only per /review-impl LOW #5. The novel-workflow-specific
namespaces (`nav.*`, `voice.*`, `placeholder.*`) were intentionally
dropped — game has different navigation, no voice/STT features, and
its own loading-state copy. Game-specific namespaces (`hud`, `world`,
`combat`, `inventory`) get added in Session D when the React HUD ships.
Evolves independently of `frontend/` thereafter per spec §1 #5 + #11.

**Phaser text rule:** game UI text is rendered as React DOM over the
canvas, never via Phaser `BitmapText`. CJK glyph baking is impractical
(spec §12).

**Consumption requirement** (/review-impl LOW #4): TypeScript source as
package entry (`main: ./src/index.ts`) — TS-aware bundler (Vite, etc.)
required. Locale JSONs under `locales/<lang>/*.json` are valid JSON and
work in any consumer that resolves the exports map.
