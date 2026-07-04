# 19 · Studio Onboarding Fork + Catalog-Driven User Guide

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: 📐 specced 2026-07-05.
> Size: **L→XL** (new dependency, 2 new server-synced prefs, new panel, new overlay flow,
> i18n content across 4 locales for ~46 panels). Built in two waves — **infra first, content
> fanout second** — so the biggest wave (per-panel guide copy) is scoped and reviewable on its own.

## Why

The workspace's default features have moved into Studio ([#18](18_book_open_and_palette_grouping.md)
makes it the default landing surface), but there is **no user guide anywhere in the frontend**
(confirmed — only the unrelated global `/onboarding` intent fork exists) and the current
`WelcomePanel.tsx` is static prose with no actions. Research on 2026 onboarding patterns for
comparably complex tools (Notion/Figma/Linear/VSCode) converges on **progressive disclosure +
role-based routing questions**, not a wall of text, and command palettes are now a baseline
expectation once a tool crosses ~10 features (this one has ~46 panels).

The user's explicit constraint: **don't build a static docs site that needs hand-editing every
time a component changes.** The fix is to **not create a second source of truth** — drive the
guide from the `StudioPanelDef` catalog metadata that already exists and already feeds both the
dock and the palette, and use a tour library that points at **live rendered DOM** (real panels,
real `data-testid`s) rather than screenshots, so it can't go visually stale.

## Locked decisions

| # | Decision | Why |
|---|---|---|
| G1 | **No new docs site / MDX / Docusaurus.** The guide is generated from `STUDIO_PANELS` catalog entries (title/description/category from [#18](18_book_open_and_palette_grouping.md)) — a new panel, not new content infrastructure. | A hand-authored doc set is the exact "modify twice" problem the human flagged; catalog is already the single source feeding dock + palette. |
| G2 | **react-joyride** for the guided tour, not Driver.js/Shepherd/Tour Kit. | Dominant React-native choice (~340k weekly installs), supports custom React step components (needed for i18n'd rich captions), acceptable bundle (~34KB gzip). Tour Kit's headless split is more future-proof but less battle-tested; not worth the extra integration risk for v1. |
| G3 | Tours target **live DOM** via existing `data-testid`s on dock tabs / activity bar / palette trigger — never screenshots. A step that references a closed panel opens it first (`onOpenPanel`), then waits for the target node before advancing. | Directly satisfies "shouldn't need to modify when components change" — the tour follows whatever is actually rendered. |
| G4 | `StudioPanelDef` gains two optional fields: `guideBodyKey?: string` (longer i18n paragraph for the Help panel + tour caption; falls back to `descKey` if absent) and `tourAnchor?: string` (a `data-testid` selector; panels not in any tour path omit it). | Reuses the exact mechanism [#18](18_book_open_and_palette_grouping.md) already introduces for `category` — one place to edit per panel, not two. |
| G5 | **Role-based onboarding is per-account (server-synced), not per-book.** Two new flat preference keys via the existing `@/lib/syncPrefs` (`loadPrefFromServer`/`savePrefToServer`/`syncPrefsToServer`) — the same mechanism + naming convention `features/onboarding/hooks/useOnboarding.ts` already uses (`ONBOARDING_SEEN_PREF_KEY = 'hasSeenOnboarding'`): `STUDIO_ONBOARDING_SEEN_PREF_KEY = 'hasSeenStudioOnboarding'` (bool) and `STUDIO_ROLE_PREF_KEY = 'studioRole'` (nullable enum: `writer` \| `worldbuilder` \| `translator` \| `enricher` \| `manager`). | Per-CLAUDE.md: preferences are server-synced, never localStorage-only. Asking "what are you here to do" on *every new book* (as the per-book Welcome seed does today) would be annoying and doesn't match how Notion/Linear ask once and reuse the answer. Prefixed key names avoid colliding in the flat `/v1/me/preferences` namespace the existing key already lives in. |
| G6 | The **Welcome dock panel** (`WelcomePanel.tsx`) stays seeded per-book exactly as today (`useStudioLayout.ts`'s un-persisted seed-when-no-saved-layout) — that mechanic is unchanged. It is *extended*, not replaced: it now reads the role pref and renders role-tailored quick links + "Start Guided Tour" + "Open User Guide" buttons. It gates its role-tailored content on the same loading state as G7's hook (see below) so it never flashes generic content then swaps — if the pref is still loading, it renders the current static copy (today's behavior) until resolved. | Keeps the existing, already-correct "shows on any book with no saved layout" behavior; only its content gets richer, without introducing a new flash-of-content bug. |
| G7 | The **role picker is a modal overlay above the mounted `StudioFrame`**, implemented with **raw `Dialog.*` from `@radix-ui/react-dialog`** (multi-step chrome — role cards, then confirm/skip — doesn't fit `FormDialog`'s title+body+footer template, so this is the "custom chrome" case, same precedent as `EntityDetailPanel`/`EntityEditorModal` in `docs/standards/dockable-gui.md` DOCK-9) — **never a hand-rolled `fixed inset-0` div**, and lives in a new `features/studio/onboarding/` folder, explicitly **outside** `frontend/src/features/studio/panels/**` (it is not a dockview tab, so DOCK-1..11 don't apply to it — but DOCK-9's underlying reason, no third hand-rolled overlay primitive, applies repo-wide on principle, not just where the mechanical gate scans). Not a new route, not a ternary unmount of the dock. A `useStudioOnboarding` hook mirrors `useOnboarding`'s shape exactly (`isLoading` / `shouldShow` / a `skip()` alongside `chooseRole()`) so there's no flash of the overlay (or of the dock) while the server round-trip resolves. **Skip is always available**, on the very first showing too — picking a role and skipping both persist `hasSeenStudioOnboarding = true` (skip leaves `studioRole = null`); this can never be a trap the user must complete. Re-triggerable via a palette command (`Studio: Choose Your Focus`) — re-triggering only overwrites `studioRole`, it never re-flips the seen flag. | Studio must stay a standalone mounted surface (D2/D5 in [00_OVERVIEW](00_OVERVIEW.md)); a hand-rolled overlay is the exact anti-pattern `dockablePanelHygiene.test.ts` (DOCK-9) already exists to kill — six Glossary modals were migrated away from it for the same z-index/SDK-1-duplication reasons, which apply here too even though this component sits outside the scanned `panels/**` tree. Mirroring `useOnboarding`'s loading gate avoids reintroducing the exact flash-of-content bug that hook was written to prevent. |
| G8 | This is a **distinct concept from the global `/onboarding` intent fork** (`features/onboarding/`) — different pref keys, different copy namespace (`studio.intro.*` vs `onboarding.json`), different purpose (page-level routing vs in-Studio panel/tour tailoring). No shared code beyond the `syncPrefs` utility. | Avoids conflating a whole-app first-run fork with a Studio-scoped preference; keeps both independently changeable. |
| G9 | **Two build waves.** Wave 1 (infra): overlay, prefs, `user-guide` panel, tour engine wired to a small **core tour** (4-6 panels: Manuscript Navigator entry, Compose, Editor, Command Palette hint) using existing `descKey` as the `guideBodyKey` fallback — no new per-panel copy required to ship. Wave 2 (content, agent-fanout candidate): write dedicated `guideBodyKey` copy + assign `tourAnchor`/role-specific tour membership for the remaining ~40 panels, × 4 locales, fanned out **per category** (the 9 groups from [#18](18_book_open_and_palette_grouping.md), ~5 panels/batch) rather than one 40-panel batch, so each PR stays reviewable. | Wave 1 is shippable and testable on its own; Wave 2 is a bounded, parallelizable content task that fits [`fanout-independent-slices-parallel-build-serial-integrate`] — many independent panels, one integration pass — not a reason to block Wave 1. Category-sized batches keep review tractable instead of one unreviewable mega-diff. |
| G10 | **Tour resilience.** (a) `onOpenPanel` is called before **every** step, not just once at tour start — it's already idempotent (open-or-focus, [06b](06b_command_palette.md) C5), so this self-heals if the user manually closes a panel mid-tour instead of the tour silently breaking. (b) If a step's target `tourAnchor` node doesn't appear within a fixed timeout (4s) after opening its panel, the tour **skips that step** (dev console warning, silent in prod) rather than hanging indefinitely — a stale/typo'd `tourAnchor` fails loud in dev, never traps a user in prod. (c) The tour's z-index is set explicitly above dockview's `--dv-overlay-z-index: 999` and the palette's `z-[60]` (documented conflict zone per DOCK-9 in `docs/standards/dockable-gui.md`); the Command Palette is suppressed (closed, hotkey briefly disabled) while a tour is active so the two overlays never stack. | A tour that can hang, silently break on a closed panel, or visually fight the palette/dockview drag-feedback layer is worse than no tour — these are the concrete failure modes a "points at live DOM" design must handle, not just the happy path. |
| G11 | **Accessibility is a Wave-1 requirement, not a follow-up.** react-joyride's default tooltip is not fully accessible out of the box (per 2026 tour-library benchmarks, only the newer headless "Tour Kit" scored zero axe-core violations). Wave 1 ships a **custom React step-component** (react-joyride supports this natively — the same reason G2 picked it over Driver.js) with: focus moved to the step panel on advance, `Esc` = skip whole tour, `aria-live="polite"` announcing step captions, and visible focus rings on Next/Back/Skip. | "Ship the tour, fix a11y later" is exactly the kind of finding CLAUDE.md's no-defer-drift rule says to fix now, not defer — it's cheap to build the custom step component correctly the first time versus retrofitting after Wave 2 content lands on top of it. |

## Role → tour / highlight mapping (Wave 1 scope: `core` only; Wave 2 fills the rest)

| Role | Tour id | Welcome dock highlights |
|---|---|---|
| (unset / skipped) | `core` | Compose, Editor, Command Palette |
| `writer` | `core` (Wave 1) → `writer` (Wave 2: + Planner, Steering, Chapter Browser) | Compose, Editor, Planner |
| `worldbuilder` | `core` (Wave 1) → `worldbuilder` (Wave 2: + Glossary, Wiki, Knowledge Graph) | Glossary, Wiki, Knowledge |
| `translator` | `core` (Wave 1) → `translator` (Wave 2: + Translation, Enrichment) | Translation, Enrichment Compose |
| `enricher` | `core` (Wave 1) → `enricher` (Wave 2: + Enrichment*, Knowledge Gap) | Enrichment Gaps, Enrichment Sources |
| `manager` | `core` (Wave 1) → `manager` (Wave 2: + Sharing, Book Settings, Usage) | Sharing, Book Settings |

`STUDIO_TOURS: Record<TourId, TourStepDef[]>` is a small hand-authored map (sequencing +
`tourAnchor` refs only — captions pull from the catalog's `guideBodyKey`, never duplicated).

## User Guide panel (`user-guide`)

- New catalog entry: `{ id: 'user-guide', component: UserGuidePanel, titleKey: 'panels.user-guide.title', descKey: 'panels.user-guide.desc', category: 'platform' }` — a **normal dock panel**, unlike the onboarding overlay (G7): it lives in `panels/**`, so it must satisfy the full DOCK-1..11 checklist in `docs/standards/dockable-gui.md` — thin view over catalog data (DOCK-2), registers via `useRegisterStudioTool` (DOCK-3), zero `useNavigate`/`<Link>` (DOCK-7, its "Open" buttons call `onOpenPanel` per the F3 link-resolver pattern, not a route hop), zero hand-rolled overlay (DOCK-9, N/A — it renders inline, no dialog). Palette + agent openable: joins the `ui_open_studio_panel` BE enum, `panelCatalogContract.test.ts` (DOCK-6, enum ⊆ catalog), and requires a `WRITE_FRONTEND_CONTRACT=1 pytest` regen of `contracts/frontend-tools.contract.json` — same lockstep every prior panel wave (11 through 17) already followed.
- Content: `OPENABLE_STUDIO_PANELS` grouped by `category` (reuses [#18](18_book_open_and_palette_grouping.md)'s grouping, same order), each row rendering `titleKey` + `guideBodyKey ?? descKey` + an "Open" button (`onOpenPanel`) +, if `tourAnchor` set and the panel belongs to a tour, a "Show me" button that launches that tour scoped to just this panel's step.
- **No hand-authored guide document** — editing a panel's catalog entry (or leaving it at the `descKey` fallback) is the only maintenance action, satisfying the "don't modify twice" requirement directly.

## Dependencies

| Dep | Why |
|---|---|
| `react-joyride` (new npm dep) | Tour engine |
| [#18](18_book_open_and_palette_grouping.md) `category` field | User Guide panel grouping reuses it |
| `@/lib/syncPrefs` | Role + seen-flag persistence (existing utility, no changes needed) |
| `useStudioLayout.ts` welcome seed | Unchanged; `WelcomePanel.tsx` extended in place |
| i18n `studio.json` × en/ja/vi/zh-TW | `intro.*` (role picker + tour trigger copy), `userGuide.*` (panel chrome), `panels.user-guide.*` |
| `panelCatalogContract` + `contracts/frontend-tools.contract.json` | New `user-guide` panel joins the agent-openable enum |

## Done-criteria

**Wave 1 (infra):**
1. First Studio visit with `hasSeenStudioOnboarding` unset shows the role-picker overlay (Radix `Dialog.*`) above the mounted dock, with no flash of either the overlay or default Welcome content while the pref loads; picking a role, or skipping, both persist `hasSeenStudioOnboarding = true` server-side and dismiss it.
2. `Studio: Choose Your Focus` palette command re-opens the overlay on demand; doing so never resets `hasSeenStudioOnboarding` to false.
3. Welcome dock panel reads the role pref and renders tailored quick-open buttons + Start Guided Tour + Open User Guide.
4. `core` tour runs via react-joyride against live DOM: opens closed panels before each step (idempotent, self-heals if the user closes one mid-tour), skips a step after a 4s anchor-wait timeout instead of hanging, renders above dockview's `999`/palette's `z-[60]`, and suppresses the palette while active — verified with a live browser smoke, not just a raw-stream/unit assertion (per this repo's agent-GUI-loop rule: a raw-stream smoke misses whether the browser could actually execute it).
5. Tour step UI is a custom component (not Joyride's default tooltip): focus management, `Esc`-to-skip, `aria-live` step announcements — checked with an axe/a11y pass, not assumed from the library.
6. `user-guide` panel renders all 46 catalog entries grouped by category with working "Open" buttons; passes the full DOCK-1..11 checklist; joins the palette + agent enum; `WRITE_FRONTEND_CONTRACT=1 pytest` regen of `contracts/frontend-tools.contract.json` committed alongside.
7. Unit tests: role-overlay show/skip/persist logic (including the never-traps-the-user skip path), tour-step anchor-wait-then-skip logic, idempotent re-open-per-step, User Guide panel grouping/fallback-to-descKey.
8. E2E: fresh-book Studio visit → overlay → pick role (and, separately, skip) → Welcome dock reflects role → open User Guide → start core tour → tour completes including a mid-tour manual panel-close recovery case.
9. i18n: en/ja/vi/zh-TW parity for all new `intro.*`/`userGuide.*`/`panels.user-guide.*` keys.
10. tsc + eslint clean; `/review-impl` pass; `panelCatalogContract` + `dockablePanelHygiene` + contract regen all green.

**Wave 2 (content fanout, separate PR):**
1. Every non-hidden catalog panel has a dedicated `guideBodyKey` (not falling back to `descKey`) and, where it belongs to a role tour, a `tourAnchor`.
2. Role-specific tours (`writer`/`worldbuilder`/`translator`/`enricher`/`manager`) extend beyond `core` per the mapping table above.
3. i18n parity maintained across all 4 locales for the new copy.
4. Live smoke re-run per extended tour to confirm anchors resolve.

## Out of scope

- A/B testing onboarding copy or role-detection heuristics beyond explicit user choice.
- Retiring the global `/onboarding` intent fork (unrelated, out of scope — see G8).
- Mobile onboarding (Studio remains desktop-first per [00_OVERVIEW](00_OVERVIEW.md) "Out of scope").
- A generic "docs site" for anything outside Studio panels (this spec covers only the Studio surface).
