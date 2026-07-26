# 04 · Manuscript Editors (Rich + Raw)

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: 📐 specced 2026-07-01 (design only).
> Children: **04a** Rich (Tiptap) · **04b** [`Raw`](04b_raw_editor.md).
> State tier: **Tier 4** domain hoist in [`08_studio_state_architecture.md`](08_studio_state_architecture.md).
> Draft: [`screen-studio-raw-editor.html`](../../../design-drafts/screens/studio/screen-studio-raw-editor.html).

## What it is

The **manuscript editing pair** for a single chapter — two dock panels over one hoisted
**manuscript unit**:

| Panel | Id | View |
|-------|-----|------|
| **04a Rich** | `editor` | WYSIWYG [`TiptapEditor`](../../../frontend/src/components/editor/TiptapEditor.tsx) |
| **04b Raw** | `raw` | Editable JSON — [`04b_raw_editor.md`](04b_raw_editor.md) |

VS Code analogue: open the same file as **Preview** (rich) or **Source** (raw). Split tab
groups supported via dockview.

**Not in scope (this plan):** React implementation.

## Locked decisions (umbrella)

| # | Decision |
|---|---|
| M1 | **`ManuscriptUnitProvider`** wraps `StudioFrame` (above dockview, D4) — owns `useManuscriptUnit(bookId, chapterId)` |
| M2 | Only **one active chapter unit** loaded at a time per provider; switching chapter prompts save-or-discard if dirty |
| M3 | Rich and Raw are **thin views** — they read/write the same unit state, never separate fetch caches |
| M4 | **Save** orchestrates book-service (draft body) + composition-service (scene rows) in one user action (⌘S) |
| M5 | **04a** reuses existing Tiptap stack; **04b** is new (code editor). Legacy `ChapterEditorPage` unchanged |

## State: `useManuscriptUnit`

```ts
// features/studio/manuscript/types.ts — design contract

type ManuscriptSceneRow = {
  id: string;
  title: string;
  synopsis: string;
  status: 'empty' | 'outline' | 'drafting' | 'done';
  beat_role: string | null;
  story_order: number | null;
  version: number;
};

type ManuscriptUnit = {
  bookId: string;
  chapterId: string;
  title: string;
  sortOrder: number;
  draftVersion: number;
  body: JSONContent;              // Tiptap doc
  scenes: ManuscriptSceneRow[];  // outline scenes for this chapter_id
  dirty: boolean;
  rawParseError: string | null;   // set when Raw buffer invalid
  syncState: 'synced' | 'raw_out_of_sync';
};

// API (hook)
load(chapterId: string): Promise<void>;
setBody(doc: JSONContent): void;           // from Rich
applyRawDocument(doc: ManuscriptUnitDocument): void;  // from Raw after parse
revert(): void;
save(): Promise<void>;
toRawDocument(): ManuscriptUnitDocument;
```

### Load path

1. `booksApi.getChapterDraft` → `body`, `draft_version`, title, sort_order.
2. If book has composition Work: fetch scenes for `chapter_id` via outline children API ([#02](02_manuscript-navigator.md) Phase 2) or filtered outline slice.
3. Import-only book: `scenes = []`.

### Save path

1. `addTextSnapshots(body)` before PATCH ([`tiptap-utils`](../../../frontend/src/lib/tiptap-utils.ts)).
2. `PATCH /v1/books/{bookId}/chapters/{chapterId}/draft` with `expected_draft_version`.
3. For each dirty scene row: `compositionApi.patchNode(id, patch, version)`.
4. On 409 draft version: reload unit, toast conflict.

### Save FSM (Tier 4 — #08)

`Clean → Dirty → Saving → Saved | Conflict → Reloading → Clean`. Owned by `useManuscriptUnit.save()`;
Raw parse invalid blocks transition to `Saving` ([#04b](04b_raw_editor.md)).

### Agent write-back (Lane C — #09)

`propose_edit` Apply in studio calls `applyProposedEdit(diff)` on the hoist — not
[`editorBridge`](../../../frontend/src/features/chat/context/editorBridge.ts). MCP saves from
the agent trigger `StudioEffectReconciler` → `reload()` — agent never passes draft JSON via
`ui_*` tools.

## 04a Rich editor (build notes)

- Dock component: `StudioRichEditorPanel` — renders `TiptapEditor` with `content={unit.body}`, `onUpdate` → `setBody`.
- Registers [`editorBridge`](../../../frontend/src/features/chat/context/editorBridge.ts) for chat write-back (until fully on Bus).
- `registerStudioTool({ panelId: 'editor', mcpToolPrefixes: ['book_'], … })` per [#07c](07c_studio_tool_registry.md).
- Toolbar: reuse `FormatToolbar`, grammar, glossary — parity with `ChapterEditorPage` subset (no left-rail tabs).
- Tab title: `Ch {sortOrder:04d} · {title}` or scene-scoped when opened from scene row.

## 04b Raw editor

Full spec: [`04b_raw_editor.md`](04b_raw_editor.md).

## Navigator + palette wiring

- [#02](02_manuscript-navigator.md) chapter/scene click → `openManuscriptUnit(chapterId)` + default panel (`editor` or user pref `lw_studio_default_editor`).
- [#06a](06a_quick_open.md): `Ch N · Edit` → Rich; `Ch N · Raw` → Raw.
- [#06b](06b_command_palette.md): `Studio: Open Editor` / `Studio: Open Raw`.

## Dependencies

| Dep | Why |
|---|---|
| [#09](09_agent_gui_reconciliation.md) | `applyProposedEdit`, reconciler reload after MCP save |
| #02 navigator | Opens chapter/scene into unit |
| Debt #1 navigator→dock | E2E open-from-tree |
| #07c registry | Panel registration |
| composition Work (optional) | Scene rows in unit |

## Done-criteria (build phase — umbrella)

1. `ManuscriptUnitProvider` loads chapter; Rich and Raw show same content.
2. Edit in Rich → Raw buffer updates on next focus (or live if both visible in split).
3. Edit JSON in Raw → Rich reflects after valid parse + apply.
4. Save persists draft + scene patches; 409 handled.
5. Unit tests: hoist, save orchestration, sync flags.
6. E2E: navigator → Rich tab; split Rich|Raw; edit raw → rich text changes.
7. `/review-impl` pass.

## Out of scope

- Beat-level raw editing.
- Replacing `ChapterEditorPage` route (studio is parallel surface).
- Reader panel (separate future dock tab if needed).
