# 04b · Raw Editor

> Component of [Writing Studio (v2)](00_OVERVIEW.md) · parent [`04_manuscript_editor.md`](04_manuscript_editor.md).
> Status: 📐 specced 2026-07-01 (design only). **2026-07-02: build path GENERALIZED — ships as the
> `loreweave.manuscript-unit.v1` provider of the generic json-editor panel, per
> [`12_json_document_standard.md`](12_json_document_standard.md) (cycle 1). The document shape,
> UX rules (format/validate/⌘S) and D13–D17 in this file remain the authoritative design.**
> Draft: [`design-drafts/screens/studio/screen-studio-raw-editor.html`](../../../design-drafts/screens/studio/screen-studio-raw-editor.html).

## What it is

A **dock panel** for editing the manuscript as **structured JSON** — VS Code “open as text”.
One buffer per chapter: Tiptap `chapter.body` **plus** composition **scene metadata** (synopsis,
status, `beat_role`, …). Not plain prose.

Distinct from legacy [`SourceView`](../../../frontend/src/components/editor/SourceView.tsx):
read-only, body-only, toggle inside Tiptap — **not** a studio dock tab.

**Not in scope (this plan):** React/Monaco implementation.

## Locked decisions

| # | Decision |
|---|---|
| B1 | Panel id `raw`; tab label `Ch 0042 · Raw` |
| B2 | Buffer format id: `loreweave.manuscript-unit.v1` |
| B3 | Invalid JSON **blocks save**; Rich tab shows `out of sync` badge |
| B4 | `_text` snapshots **included** in displayed/saved body (required by book-service / `chapter_blocks`) |
| B5 | Code editor: **CodeMirror 6** or **Monaco** (pick at build — mockup uses static HTML) |
| B6 | Import-only books: `scenes: []` — buffer still valid |

## `ManuscriptUnitDocument` schema

```json
{
  "format": "loreweave.manuscript-unit.v1",
  "chapter": {
    "id": "019d…",
    "title": "Nghịch thiên",
    "sort_order": 1,
    "draft_version": 7,
    "body": {
      "type": "doc",
      "content": [
        {
          "type": "paragraph",
          "_text": "Đoạn văn…",
          "content": [{ "type": "text", "text": "Đoạn văn…" }]
        }
      ]
    }
  },
  "scenes": [
    {
      "id": "019e…",
      "title": "Cảnh 1 — Bị phản bội",
      "synopsis": "Tiểu Yên phản bội tại đỉnh núi…",
      "status": "drafting",
      "beat_role": "inciting",
      "story_order": 1,
      "version": 3
    }
  ]
}
```

### Field rules

| Path | Editable in raw | Notes |
|------|-----------------|-------|
| `format` | No (constant) | Mismatch → validation error |
| `chapter.id` | No | Must match loaded unit |
| `chapter.title` | Yes | Also PATCH chapter meta on save |
| `chapter.sort_order` | No | Display only |
| `chapter.draft_version` | No | Updated after successful save |
| `chapter.body` | Yes | Full Tiptap doc; run `addTextSnapshots` on apply |
| `scenes[].id` | No | Cannot add/remove scenes in v1 raw (use planner/navigator) |
| `scenes[].title` | Yes | |
| `scenes[].synopsis` | Yes | |
| `scenes[].status` | Yes | Enum: empty/outline/drafting/done |
| `scenes[].beat_role` | Yes | Nullable string |
| `scenes[].story_order` | Yes | Nullable number |
| `scenes[].version` | No | Optimistic lock; server returns new version |

Scene **prose** is not a separate field — it lives in `chapter.body` paragraphs.

## UX

### Layout

```
┌─ Toolbar: Format · Validate · Copy · Revert · Open Rich · Save ─┐
├─ gutter │  { "format": "loreweave.manuscript-unit.v1",          │
│   1     │    "chapter": { …                                     │
│   2     │  …                                                    │
├─ Status: draft v7 · 3 scenes · JSON valid · ● unsaved ──────────┤
└─────────────────────────────────────────────────────────────────┘
```

- Placed in dock tab `raw`; can split horizontally with Rich (`editor` | `raw`).
- **Toolbar actions:**
  - **Format** (⌘⇧F) — `JSON.stringify` pretty-print
  - **Validate** — parse + schema checks, focus first error
  - **Copy** — clipboard full buffer
  - **Revert** — confirm dialog → reload from `useManuscriptUnit`
  - **Open Rich** — focus `editor` panel in same group
  - **Save** (⌘S) — delegate to unit `save()`; disabled when parse invalid

### Validation layers

1. **JSON parse** — syntax error → line/column in status + red gutter marker
2. **Shape** — `format`, `chapter`, `chapter.body.type === 'doc'`
3. **Id guard** — `chapter.id` matches active unit
4. **Tiptap allowlist** — top-level block types known to editor extensions (paragraph, heading, codeBlock, callout, imageBlock, …) — warn on unknown, block save if critical
5. **Scene enum** — `status` in allowed set
6. **Version** — on save, 409 from book or composition → reload + toast

### Sync with Rich

| Event | Behaviour |
|-------|-----------|
| Rich `onUpdate` | Unit `setBody` → if Raw tab open, refresh buffer text (debounced 300ms) unless Raw has local unsaved parse edit |
| Raw edit (valid parse) | `applyRawDocument` → Rich `setContent` via unit |
| Raw parse fail | `syncState = raw_out_of_sync`; Rich keeps last good doc; badge on Rich tab |

### Keyboard

| Key | Action |
|-----|--------|
| ⌘S / Ctrl+S | Save (studio frame capture) |
| ⌘⇧F | Format document |
| Esc | If dirty, focus — Revert dialog optional v1 |

## Data APIs (existing)

| Operation | API |
|-----------|-----|
| Load draft | `GET` chapter draft / `booksApi` equivalent |
| Save draft | `PATCH` with `body`, `expected_draft_version`, `body_format: 'json'` |
| Load scenes | `GET /v1/composition/works/{id}/outline/children?parent_id=…` or chapter-filtered query |
| Save scene | `compositionApi.patchNode(nodeId, { title, synopsis, status, … }, version)` |

## Registry ([#07c](07c_studio_tool_registry.md))

```ts
registerStudioTool({
  panelId: 'raw',
  label: 'Raw Editor',
  paletteCommand: 'Studio: Open Raw',
  commandId: 'studio.openPanel.raw',
  mcpToolPrefixes: ['book_', 'composition_'],
  contributeContext: () => ({ activeChapterId: unit.chapterId }),
});
```

## vs legacy SourceView

| | SourceView | #04b Raw |
|--|------------|----------|
| Placement | Inside Tiptap toggle | Dock tab |
| Editable | No | Yes |
| Scope | `body` only, `_text` stripped in display | Full unit document |
| Studio | No | Yes |

## Dependencies

| Dep | Why |
|---|---|
| [`04_manuscript_editor.md`](04_manuscript_editor.md) | `useManuscriptUnit` hoist |
| #02 navigator | Open chapter into unit |
| #07c | Registration |
| #06a | `Ch N · Raw` quick open row |

## Done-criteria (build phase)

1. Raw dock tab renders code editor with `ManuscriptUnitDocument` for active chapter.
2. Format, Validate, Save, Revert work; invalid JSON disables Save.
3. Edit synopsis in raw → saves via `patchNode`; edit body → saves via draft PATCH.
4. Split with Rich: edit one side, valid apply updates the other.
5. Import book shows `scenes: []`.
6. Unit tests: parse/validate, applyRawDocument, sync flags.
7. E2E: open Raw from navigator → edit JSON → Rich shows change.
8. tsc + eslint clean; `/review-impl` pass.

## Out of scope

- Create/delete scenes in raw buffer (v2 — use planner).
- Beat nodes in buffer.
- JSON Schema LSP autocomplete (v2).
