# 11 · Dockable Migration — Wave 1 (foundation seams + user-scoped panels)

> **Status:** 🔨 EXECUTING · 2026-07-02 · branch `feat/studio-agent-raid`
> **Type:** FE (+1 BE touch: `ui_open_studio_panel` enum + contract regen)

## Why

The studio goal is Cursor-for-novels: every tool opens **inside** the studio as a dock
panel — never a route hop. The foundation (dock host, palette, bus, agent bridge,
frontend-tool contract) is built; most tools are still traditional route-based pages.
This track is the **exploitation layer**: migrate them to dockable panels, one wave at
a time, discovering + patching foundation gaps as they surface.

Wave 1 = the four "outside the writing loop but too convenient to leave outside" pages
(**usage, notifications, settings, trash**) + the three foundation seams they exposed.

## The migration standard (checklist — applies to every wave)

A panel is "studio-standard" when ([`EditorPanel.tsx`](../../../frontend/src/features/studio/panels/EditorPanel.tsx) is the reference):

1. **Catalog entry** in [`catalog.ts`](../../../frontend/src/features/studio/panels/catalog.ts) — `id` = dockview component id; i18n `titleKey`/`descKey` in the `studio` namespace.
2. **Thin view, no forks** — reuse the existing feature components/hooks AS-IS; the panel owns no domain state (D3/D4).
3. **`useRegisterStudioTool`** — palette command + agent rack visibility (D8).
4. **Bus, not props** — cross-panel talk via `StudioContextBus` (D9/D19).
5. **Self-title** via `props.api.setTitle` (agent opens precede mount).
6. **Agent-openable ⇒ contract dance** — add to the `ui_open_studio_panel` enum, keep enum ⊆ catalog (`panelCatalogContract.test.ts`), regen `contracts/frontend-tools.contract.json`.
7. **Route-decoupling** *(new, this wave)* — the dominant migration cost is always
   `useParams`/`useNavigate`/`Link`. Replace with: panel `params` (F1) for input,
   internal state for tabs/filters, and the **studio link resolver** (F3) for outbound
   navigation. A panel that calls `navigate()` is a defect.
8. Per-track testing discipline (00_OVERVIEW): unit tests + E2E per panel, `/review-impl` per milestone.

## Foundation seams (W1 — build first, each with tests)

### F1 · `openPanel` params

`StudioHost.openPanel(panelId, opts)` gains `params?: Record<string, unknown>`:

- not open → `api.addPanel({ id, component, title, params })`
- already open → `panel.api.updateParameters(params)` then focus (unless `focus:false`)

Additive; existing callers unchanged. First consumers: settings (`{ tab: 'providers' }`),
notifications link targets, palette deep-commands. Panels read via
`props.params` / `props.api.onDidParametersChange`.

### F2 · Status-bar contribution API

Mirror of `registerStudioTool`, for the status bar:

```ts
registerStatusBarItem({ id, side: 'left'|'right', order?, render, onClick? })
```

- Host store + `useRegisterStatusBarItem` hook + `useStatusBarItems` (useSyncExternalStore, same pattern as the registry).
- `StudioStatusBar` renders registered items between its fixed chrome (bottom toggle stays hardcoded — it's chrome, not a contribution).
- **Items live independent of panels** — a badge must show while its panel is closed, so items are registered at `StudioFrame` level (a `StudioStatusContributions` component mounting feature hooks), not inside panels.
- Wave-1 items: **notifications unread badge** (click → open notifications panel), **usage cost meter** (click → open usage panel). Meter shows period spend from the existing summary endpoint; a live "session spend" stream is out of scope this wave.

### F3 · Studio link resolver

New seam `resolveStudioLink(url: string): ((host: StudioHost) => void) | null`:

- Maps known in-app URL patterns → studio actions (`/books/:id/chapters/:cid` → `focusManuscriptUnit`; more patterns added per wave).
- **Fallback (LOCKED): unmapped or external link → `window.open(link)`** — the studio never unmounts itself. `navigate()` away from the studio is forbidden inside panels.
- Keeps NotificationsPage's existing safety rule: only `http(s)` or `/`-prefixed strings are followed at all.
- Pure + unit-tested like `studioUiNav.ts`; consumed first by the notifications panel, later by any cross-panel navigation.

## Panels (W2 — after F1–F3)

| Panel id | Source | Migration notes |
|---|---|---|
| `usage` | [`UsagePage`](../../../frontend/src/pages/UsagePage.tsx) | No route coupling; wrap feature components (StatCards/BudgetPanel/DailyChart/RequestLogTable) as-is. Easiest — do first as the F-seam smoke. |
| `trash` | [`TrashPage`](../../../frontend/src/pages/TrashPage.tsx) | Self-contained hook; replace `Link`s via F3. After restoring a chapter, offer "open in editor" → `focusManuscriptUnit`. |
| `notifications` | [`NotificationsPage`](../../../frontend/src/pages/NotificationsPage.tsx) | `useNotificationList` as-is; item click → `markOne` + F3 resolve (never `navigate`). Pairs with the F2 unread badge. |
| `settings` | [`SettingsPage`](../../../frontend/src/pages/SettingsPage.tsx) | Tab state moves from route (`/settings/:tab`) to internal state seeded by F1 `params.tab`; reuse the six tab components as-is. Keep the `public_mcp_enabled` gate. |

All four: catalog + i18n + register + self-title + unit tests + E2E, per the checklist.
**Agent enum (LOCKED): all four** join `ui_open_studio_panel` → BE enum + contract regen
(`WRITE_FRONTEND_CONTRACT=1 pytest …`) + `panelCatalogContract` stays green.

The existing pages/routes **stay** (multi-device + non-studio entry points); the panels are
additional mounts of the same feature layer, not replacements.

## Known tradeoff (recorded, accepted)

`StudioHost` is **per-book** (StudioFrame keyed by bookId) but all four panels are
**user-scoped**. Book switch ⇒ panel remount + refetch. Accepted for this wave (pure
refetch, no state worth preserving); revisit only if a user-scoped panel ever holds
in-flight work.

## Decisions locked this wave

| # | Decision | Why |
|---|---|---|
| W1-1 | Status bar gets a **contribution API**, not hardcoded slots | Third status item would force the refactor anyway; mirrors the proven registry pattern. |
| W1-2 | Link-resolver fallback = **new browser tab** | Studio never unmounts; VS Code behaviour. |
| W1-3 | **All 4** panels agent-openable | "Show me my usage" is a natural agent ask; cost is one contract regen. |
| W1-4 | **Foundation first, panels second** | Panels consume F1–F3; no rework. |
| W1-5 | **Conflict-first ordering** (parallel with the studio-agent RAID): F2 → F1/F3 → panels → enum+regen | The two RAID collision hotspots (`StudioStatusBar`, contract JSON) get done EARLY, while the RAID agent is parked on KG Track 4 (BE-only). Note the constraint: enum ⊆ catalog, so the contract step can only run once the 4 panels exist. |
| W1-6 | Build in **this checkout, this branch** (`feat/studio-agent-raid`), staging files explicitly | Wave 1 is FE-disjoint from the KG track's BE surface right now; repo already runs multiple tracks on this branch. `git diff --cached --name-only` before every commit (the index carries the other track's WIP). |
| W1-7 | Enum + contract regen **inside the current window**, not deferred to integration | Nobody else touches `frontend_tools.py`/contract JSON while RAID is on Track 4; later RAID waves (B2/C2/C4/C6) then regen on top of the 4-panel enum — no race. |
| W1-8 | Status-bar cost meter shows **last-24h spend** from the existing usage summary endpoint | No new BE; live "session spend" stays out of scope this wave. |

## RAID coordination (parallel-run contract)

- **A3 (RAID Wave A, FE context meter) must consume F2** — register via `registerStatusBarItem`,
  never hardcode into `StudioStatusBar.tsx`. Noted in the RAID plan §2 Wave A.
- Contract regen hotspot is cleared by W1-7 (this wave regens first, during the Track-4 window).
- No RAID item depends on Wave 1 and vice-versa; remaining textual-merge risk is i18n keys only.

## Later waves (inventory backlog — not this spec)

Strong candidates from the writing loop, to be specced per-wave: GlossaryTab,
KnowledgeOntologyTab, WikiTab/WikiEditorPage, TranslationTab/ChapterTranslationsPage/
TranslationReviewPage, ChapterComparePage, EnrichmentTab, ReaderPage, KnowledgePage,
RawSearchPage. Stay pages: auth, Browse/Home/PublicBookDetail, Profile, ReadingHistory.
