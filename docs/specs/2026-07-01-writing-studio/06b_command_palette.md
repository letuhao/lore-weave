# 06b · Command Palette (⌘⇧P / Ctrl+Shift+P)

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: 📐 specced 2026-07-01 (design only).
> Draft: [`design-drafts/screens/studio/screen-command-palette.html`](../../../design-drafts/screens/studio/screen-command-palette.html) (Command Palette state).
> Pair: [`06a_quick_open.md`](06a_quick_open.md) (⌘P — manuscript locations).

## What it is

A **modal Command Palette** — the VS Code `Show All Commands` analogue. Runs **studio actions**:
open a dock tool panel, toggle chrome, switch activity view. Opens via **⌘⇧P** / **Ctrl+Shift+P**
or (optional) a status-bar click target.

**Not in scope:** jumping to chapter/scene/arc — that is [`06a`](06a_quick_open.md).
**Not in scope (this plan):** React implementation — build when enough dock panels exist to be useful.

## Locked decisions

| # | Decision |
|---|---|
| C1 | Commands are **static registry + dynamic panel list** — not free-text LLM |
| C2 | Dock tool open commands use prefix **`Studio: Open …`** (display); internal id = `studio.openPanel.<panelId>` |
| C3 | Chrome/layout commands use prefix **`View: …`** |
| C4 | Panel ids source of truth: [`StudioToolRegistry`](07c_studio_tool_registry.md) — `listRegisteredStudioTools()` at runtime; legacy [`WorkspacePanelId`](../../../frontend/src/features/composition/workspace/types.ts) is the id vocabulary only |
| C5 | Opening a panel = `dockviewApi.addPanel` or focus if already open — same idempotency rule as Quick Open (no duplicate tabs per panel kind) |
| C6 | **Build trigger:** ship #06b when **≥3 dock tool panels** are registered in studio (e.g. Compose, Editor, Quality). Chrome-only commands may ship as a thin first slice. |

## UX

### Shell

- Same modal chrome as Quick Open (shared `StudioPaletteShell` component when built) — user learns one overlay pattern.
- Input placeholder: **"Type a command…"**
- Keyboard: identical to 06a (↑↓ Enter Esc).
- Empty query: show **recent commands** (last 5) + **common** group (Toggle Bottom Panel, Open Compose).

### Result groups

Results are **grouped headers** (sticky or separated by divider):

| Group | Examples |
|---|---|
| **Recent** | Last 5 executed commands |
| **Panels** | `Studio: Open Compose` · `Studio: Open Cast` · … |
| **Layout** | `View: Toggle Bottom Panel` · `View: Toggle Side Bar` · `View: Focus Editor Group` |
| **Navigate** | `View: Show Manuscript` · `View: Show Story Bible` · `View: Show Search` · `View: Show Quality` |
| **Generate** *(deferred)* | `Studio: Generate` · `Studio: Save All` — Debt #2 on overview |

### Result row format

```
Studio: Open Cast          Cast & relationships
View: Toggle Bottom Panel  Jobs · Generation · Issues
```

- Left: command label (match highlighted).
- Right: muted description (i18n subtitle from panel registry).

### Command registry (v1 chrome-only slice)

These can ship before dock tools exist:

| Command id | Label | Action |
|---|---|---|
| `view.toggleBottom` | View: Toggle Bottom Panel | `toggleBottom()` from `useStudioChrome` |
| `view.toggleSidebar` | View: Toggle Side Bar | `toggleSidebar()` |
| `view.showManuscript` | View: Show Manuscript | `setActiveView('manuscript')` |
| `view.showBible` | View: Show Story Bible | `setActiveView('bible')` |
| `view.showSearch` | View: Show Search | `setActiveView('search')` |
| `view.showQuality` | View: Show Quality | `setActiveView('quality')` |
| `view.openQuickOpen` | View: Go to Chapter… | Close self · open Quick Open (06a) |

### Panel open commands (when dock panels registered)

**Source:** [`listRegisteredStudioTools()`](07c_studio_tool_registry.md) — one command per registration.
Unregistered panels do **not** appear (incremental port). Example rows when mounted:

| panelId | paletteCommand | Notes |
|---|---|---|
| `compose` | Studio: Open Compose | First stateful panel (#03); hosts [#07](07_studio_agent_chat.md) chat |
| `editor` | Studio: Open Editor | Manuscript editor |
| `cast` | Studio: Open Cast | |
| `quality` | Studio: Open Quality | Distinct from Quality *navigator* |
| `planner` | Studio: Open Planner | |

Legacy `PANEL_IDS` (25) are **not** auto-listed — each panel opts in via `registerStudioTool()` on mount.

### Deferred commands (Debt #2 / later)

| Command | Clears when |
|---|---|
| `Studio: Generate` | Top-bar Generate wired (#03+) |
| `Studio: Save All` | Save pipeline exists |
| `Studio: Select Model…` | Model picker in top bar |
| `Studio: Open Command Palette` | meta — optional |

## Shortcut map

| Platform | Quick Open | Command Palette |
|---|---|---|
| macOS | ⌘P | ⌘⇧P |
| Windows / Linux | Ctrl+P | Ctrl+Shift+P |

- Register at `StudioFrame` level (capture phase) so dock panels don't swallow shortcuts.
- Status bar shows both hints (design intent in overview).
- Top bar: click opens Quick Open only — no duplicate entry for Command Palette (status bar is enough).

## Relationship to activity bar

| Activity bar | Command Palette |
|---|---|
| 4 high-level **navigator views** | Opens **dock tool tabs** (25+ in legacy studio) |
| Always visible spatial switch | Keyboard fuzzy finder |
| Mutually exclusive sidebar content | Can open panel while any activity view is active |

No duplication: activity bar never lists Cast/Planner/Compose as icons.

## Optional: `>` prefix in Quick Open

VS Code allows typing `>` in Quick Open to switch to command mode. **Deferred** — two shortcuts
(⌘P / ⌘⇧P) are sufficient for v1; document here so we don't accidentally merge palettes later.

## Dependencies

| Dep | Why |
|---|---|
| `useStudioChrome` | Layout/navigate commands |
| `useStudioLayout` / `apiRef` | Panel open commands |
| [#07c StudioToolRegistry](07c_studio_tool_registry.md) | Dynamic Panels group |
| ≥3 registered dock components | Panel group is non-empty |
| i18n `studio.palette.*` | Command labels × en/vi/ja/zh-TW |

## Done-criteria (build phase — not this design track)

1. ⌘⇧P / Ctrl+Shift+P opens modal; chrome commands work without any dock tool panel.
2. Each registered panel has `Studio: Open …` command; focus-if-open else addPanel.
3. Unit tests: registry filter, command dispatch, recent list.
4. E2E: ⌘⇧P → Open Compose → dock tab visible; Toggle Bottom Panel.
5. tsc + eslint clean; `/review-impl` pass.

## Out of scope

- Custom user macros / keybinding editor.
- Natural-language command parsing.
- Chapter/scene search (→ `06a`).
- Running long-running jobs from palette (use bottom Jobs panel).
