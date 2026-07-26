# 06a · Quick Open (⌘P / Ctrl+P)

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: 📐 specced 2026-07-01 (design only).
> Draft: [`design-drafts/screens/studio/screen-command-palette.html`](../../../design-drafts/screens/studio/screen-command-palette.html) (Quick Open state).
> Pair: [`06b_command_palette.md`](06b_command_palette.md) (⌘⇧P — tools + actions).

## What it is

A **modal Quick Open** — the VS Code `Go to File…` analogue for manuscript **locations**:
arc, chapter, scene. Opens from anywhere in the studio (sidebar collapsed, focus in a dock
panel, bottom panel open) via **⌘P** (Mac) / **Ctrl+P** (Windows/Linux) or the top-bar
affordance.

**Not in scope:** opening tool panels (Compose, Cast, …) — that is [`06b`](06b_command_palette.md).
**Not in scope (this plan):** React implementation — build after #02 jump layer + #03 dock panel.

## Locked decisions

| # | Decision |
|---|---|
| Q1 | One result type per selectable row — `arc` \| `chapter` \| `chapter_editor` \| `chapter_raw` \| `chapter_reader` \| `scene` |
| Q2 | Chapter can appear as **multiple rows** when dock panels exist: *"Ch 0042 · Edit"*, *"Ch 0042 · Raw"*, *"Ch 0042 · Read"* — same `chapterId`, different panel kind ([#04b](04b_raw_editor.md)) |
| Q3 | Arc selection **does not** open a dock tab — it switches to Manuscript activity view, expands the arc, scrolls the sidebar tree |
| Q4 | Chapter/scene selection **opens or focuses** a dock tab (same wiring as sidebar click — Debt #1 / navigator→dock) |
| Q5 | Shares the **same jump/search data layer** as the Manuscript navigator jump box ([#02](02_manuscript-navigator.md) §Jump contract) — never a second query implementation |

## UX

### Shell

- Centred modal overlay (`z-index` above dockview), dimmed backdrop (`~60%` black).
- Single text input, autofocus on open; fuzzy/substring filter on the result list below.
- Result list: virtualized when >50 rows (same discipline as #02 tree).
- Keyboard: **↑↓** move selection · **Enter** accept · **Esc** close without action · **Tab** does not leave the modal while open.
- Empty query: show **recent locations** (last 8 opened chapter/scene tabs for this book, from studio session state — per-device, optional v1 slice).

### Top-bar affordance

- Click opens the same modal as ⌘P.
- Placeholder copy: **"Go to chapter, scene, arc…"** (no "tool" — tools are ⌘⇧P).
- Currently disabled in skeleton ([#01](01_skeleton.md)); enabled when #06a is built.

### Result row format

| Field | Example |
|---|---|
| Kind icon | arc (accent) · chapter (bold) · scene (dot) · reader glyph for Read rows |
| Primary label | `Nghịch thiên` or `Cảnh 1 — Bị phản bội` |
| Breadcrumb | `Arc I › Ch 0001 › Scene 1` (muted, truncated) |
| Meta | `0001` chapter number · status badge `drafting` / `done` / `outline` |
| Highlight | match substring in label (accent underline) |

### On select

| Result kind | Action |
|---|---|
| `arc` | `setActiveView('manuscript')` · expand arc in tree · `scrollToNode(arcId)` · close modal |
| `chapter` / `chapter_editor` | open/focus **Manuscript editor** (`editor`) dock panel for `chapterId` · highlight tree row · close modal |
| `chapter_raw` | open/focus **Raw editor** (`raw`) dock panel for `chapterId` · load `ManuscriptUnitDocument` · close modal |
| `chapter_reader` | open/focus **Reader** dock panel for `chapterId` · close modal |
| `scene` | open/focus editor dock panel scoped to `sceneId` (or chapter + scene focus) · expand parent chapter in tree · close modal |

Until #03/#04 exist, v1 build may **only** scroll/highlight the sidebar tree (same as #02 pre-wiring).

## Jump contract (shared with #02)

The sidebar jump box and Quick Open **must** call one hook — `useManuscriptJump(bookId)` — and
one search/jump backend. Cross-ref: [`02_manuscript-navigator.md`](02_manuscript-navigator.md) §Jump contract.

### v1 (ships with #02)

| Capability | Mechanism |
|---|---|
| Jump to chapter **number** | `sort_order` seek — book-service keyset cursor until the target page is loaded |
| Jump by **title** (loaded pages only) | Client filter over pages already in the navigator store |
| Full-text over all 10k chapters | **Deferred** — book-service `GET …/jump?q=` (Debt on #02 stack) |

Quick Open **inherits v1 behaviour** from the shared hook — it does not wait for server jump.
When server jump lands, both sidebar jump box and ⌘P gain it automatically.

### Target API (when book-service adds server jump)

```
GET /v1/books/{bookId}/manuscript/jump?q={query}&limit=20
→ {
    items: Array<{
      kind: 'arc' | 'chapter' | 'scene';
      id: string;           // outline_node id or chapter_id as appropriate
      chapter_id?: string;  // book chapter UUID when kind=scene
      label: string;
      breadcrumb: string;
      sort_order?: number;
      status?: 'empty' | 'outline' | 'drafting' | 'done';
    }>;
  }
```

- Query matches chapter number (`42`, `0042`), title substring, scene title, arc title.
- Composition outline + book chapters merged server-side for has-Work books; chapters-only for imports.
- `useManuscriptJump.search(query)` debounces 200ms; `resolve(item)` performs tree scroll + dock open.

### Hook surface (implement later)

```ts
// features/studio/hooks/useManuscriptJump.ts — single owner
search(query: string): JumpResult[] | Promise<JumpResult[]>;
resolve(result: JumpResult, mode: 'tree' | 'tree_and_dock'): void;
recent(): JumpResult[];          // Quick Open empty state
pushRecent(result: JumpResult): void;
```

- Sidebar jump box: `search` on input · **Enter** → `resolve(r, 'tree')` then optionally `'tree_and_dock'` when wired.
- Quick Open modal: `search` on input · **Enter** → `resolve(r, 'tree_and_dock')`.

## Edge cases

| Case | Behaviour |
|---|---|
| Sidebar collapsed | ⌘P still works; arc/chapter/scene resolve may expand sidebar if needed for tree sync |
| Import book (flat chapters, no arcs/scenes) | Results are chapter rows only; adaptive depth per #02 |
| No composition Work | No arc/scene rows; chapter spine only |
| Duplicate chapter open in dock | Focus existing tab, do not add duplicate (`panelId` keyed by `chapterId` + panel kind) |
| Modal open while typing in editor | ⌘P steals focus to modal; Esc returns focus to prior element |
| Very long result list | Virtualize; cap server jump at 20 items per query |

## Dependencies

| Dep | Why |
|---|---|
| #02 Manuscript navigator | Tree scroll targets, jump box shares `useManuscriptJump` |
| #03+ dock panels | `tree_and_dock` resolve path |
| [`04b_raw_editor.md`](04b_raw_editor.md) | `chapter_raw` row opens `raw` panel |
| Debt #1 navigator→dock | E2E for "⌘P opens chapter in dock" |

## Done-criteria (build phase — not this design track)

1. ⌘P / Ctrl+P and top-bar click open the modal; Esc closes.
2. Typing filters results; Enter resolves; arc vs chapter/scene actions per table above.
3. Shares `useManuscriptJump` with sidebar jump box — one unit test suite for search/resolve logic.
4. Unit tests: empty/recent state, keyboard nav, resolve branches, no duplicate dock tabs.
5. E2E: ⌘P from collapsed sidebar → open chapter editor tab; `Ch N · Raw` → raw panel; arc → tree scroll.
6. tsc + eslint clean; `/review-impl` pass.

## Out of scope

- Beat-level jump (defer until beat rows exist in navigator).
- Bible entity jump (future `#05` / Search navigator).
- Tool panel open (→ `06b`).
- `>` prefix command mode in the same input (optional later; prefer separate ⌘⇧P).
