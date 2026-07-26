# S5 (What-If & Divergence) — E2E test plan

> Goal driver: "lên plan viết playwright testscripts + kịch bản test để coverage toàn bộ S5 …
> ngoài ra cần thêm kịch bản test với vai trò blackbox user … đứng dưới vai trò người dùng để test".
> Two deliverables: (A) per-capability Playwright coverage of the whole S5 surface, and (B) a
> blackbox author journey that evaluates whether the surface is genuinely usable click-only.

## What S5 shipped (the surface under test)

| Capability | Where | Key testids |
|---|---|---|
| Divergence MANAGE panel | `divergence` dock panel → `DivergenceManagerView` | `divergence-panel`, `divergence-canon-row`, `divergence-row-<pid>`, `divergence-empty`, `divergence-new` |
| Create a dị bản (wizard) | `DivergenceWizard` (from the panel + from compose) | `divergence-new`, `divergence-launch`, `divergence-next`, `divergence-step-3` |
| Switch active Work | per-user-per-book pref (`lw_active_work.<book>`) | `divergence-switch-<pid>`, `divergence-active-badge` |
| Archive a dị bản | soft-delete + If-Match | `divergence-archive-<pid>` |
| Branch spec (read-only) | Spec tab | `divergence-tab-spec`, `divergence-spec-taxonomy`, `divergence-spec-error` |
| Branch prose-diff | Diff tab → `BranchDiffView` | `divergence-tab-diff`, `branchdiff`, `branchdiff-noprose`, `branchdiff-nosource`, `branchdiff-error` |
| Canon-at-chapter home | `canonview` dock panel | `canonview-panel`, `canonview-loading`, `canonview-not-analyzed`, `canonview-empty` |
| What-if canvas | `whatif-canvas` dock panel | `whatif-canvas`, `whatif-canvas-nowork` |
| Derivative edit-guard | `EditorPanel` on a derivative | `studio-editor-derivative-guard` |
| Agent parity (MCP) | `composition_list_derivatives` / `composition_archive_derivative` | covered by BE MCP suite (`test_mcp_server.py`) |

## A · Per-capability coverage — `studio-divergence.spec.ts`

Seed once (beforeAll, real gateway): a fresh book + chapters + a canon Work + ONE derivative via
`createDerivative` (the real `/derive` route). If derive 503s (knowledge partition can't be minted),
`test.skip` the whole describe — an infra outage, not a product failure.

1. **Panel opens; canon + empty derivatives.** Open `divergence` → `divergence-panel` visible, the
   canon row present, and (before the seed is listed) the `divergence-empty` derivatives state.
2. **Seeded derivative LISTs by NAME** (not a raw UUID — the BE-13a fix): `divergence-row-<pid>`
   shows the name passed at derive.
3. **Select → Spec tab** shows `divergence-spec-taxonomy`, never `divergence-spec-error`.
4. **Diff tab renders** without error: the `branchdiff` container or a legitimate empty state
   (`branchdiff-noprose`/`branchdiff-nosource`), and `branchdiff-error` is absent (a freshly-derived
   branch has no promoted prose yet — the correct non-error empty state).
5. **Switch-to** moves `divergence-active-badge` onto the derivative; switching back to canon
   removes it.
6. **Archive** removes `divergence-row-<pid>` from the list (soft-delete; a toast confirms).
7. **Canonview panel** opens and renders a valid state (canon state or `canonview-not-analyzed`/
   `canonview-empty`), never a crash.
8. **Editor derivative-guard**: with the derivative active, the manuscript editor shows
   `studio-editor-derivative-guard`.

## B · Blackbox author journey — `s5-blackbox-journey.spec.ts`

One real author path on a fresh book, click-only, mirroring `s6-blackbox-journey`: lay the plan
(seed a Work + chapters via API = the "already planned" precondition), then **in the Studio only**:
open Divergence → create/seed a what-if → see it listed → open its Spec + Diff → Switch onto it →
confirm the editor guard → open Canon-view → Archive it. The verdict asserts the loop closes without
dropping to the legacy `/edit` page or the agent — the S5 reason to exist.

## Running

```
# against the isolated S5 static build on :5399 (does NOT collide with other sessions)
PLAYWRIGHT_BASE_URL=http://localhost:5399 npx playwright test studio-divergence s5-blackbox
```

The specs seed through the real gateway (`/v1` relative), so a live composition + knowledge +
book stack must be up. Each test trashes its book in `afterAll`; the per-user active-work pref is
scoped to the throwaway book, so nothing leaks to the shared account's real books.
