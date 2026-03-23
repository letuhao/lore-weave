# LoreWeave Module 05 Frontend Flow Specification

## Document Metadata

- Document ID: LW-M05-77
- Version: 0.1.0
- Status: Approved
- Owner: Product Manager + Frontend Lead
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Frontend user journeys, page routes, state model, component map, and API mapping for Module 05 glossary and lore management.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 frontend flow spec      | Assistant |

---

## 1) New Routes

| Route | Component | Access | Purpose |
| --- | --- | --- | --- |
| `/books/:bookId/glossary` | `GlossaryPage` | Protected (RequireAuth) | Main glossary view: filter bar, entity list, slide-over detail panel |

---

## 2) Navigation Changes

`BookDetailPage.tsx` — add tab/link alongside "Translation" and "Sharing":
```
Glossary  →  /books/:bookId/glossary
```

---

## 3) User Journey: Glossary Page (`/books/:bookId/glossary`)

### 3.1 Entry State

- Page loads: calls in parallel:
  - `GET /v1/glossary/kinds` — load entity kinds for filter bar and create modal
  - `GET /v1/glossary/books/:bookId/entities?limit=50&offset=0` — load first page
  - `GET /v1/books/:bookId/chapters?lifecycle_state=active&limit=200` — load chapter list for filter and link editor
- Skeleton cards shown while loading.
- On load success: filter bar and entity list rendered.
- On book-not-found or 403: redirect to `/books`.

### 3.2 Section 1 — Filters Bar

State shape:
```
filters: {
  kindCodes: string[]     // selected kind codes, empty = all
  status: "all" | "active" | "inactive" | "draft"
  chapterIds: string[] | "all" | "unlinked"
  searchQuery: string     // debounced 300ms
  tags: string[]
}
```

Filter change → `GET /v1/glossary/books/:bookId/entities` with updated params → replace entity list.

Active filters shown as removable chips below the bar.

Stat line: "Showing N entities" + warning badge if unlinked entities exist.

### 3.3 Section 2 — Entity List

- Displays `GlossaryEntityCard` components.
- Infinite scroll or "Load more" button (offset-based pagination, limit=50).
- Cards show: kind badge, display name, chapter link chips, translation count, evidence count, status.
- Click card → open `EntityDetailPanel` (slide-over from right, ~600px).
- Card ⋯ menu → quick actions: Duplicate, Set Inactive, Delete (with confirmation).
- Empty state: "No entities yet. Create your first." with `+ New Entity` button.
- Unlinked empty state (filter=unlinked): "No unlinked entities."

### 3.4 Action: Create Entity

1. User clicks `+ New Entity` button in toolbar.
2. `CreateEntityModal` opens: grid of kind icons (8 default kinds).
3. User selects kind → POST `/v1/glossary/books/:bookId/entities` with `kind_id`.
4. On success: entity created in `draft` status; `EntityDetailPanel` opens immediately with the new entity.
5. Error: inline toast with error message.

### 3.5 Section 3 — Entity Detail Panel (slide-over)

Triggered by: clicking any entity card. Side panel slides from the right (~600px wide on desktop, full-screen on mobile).

Panel sections (scrollable):

1. **Header**: Kind badge, entity status toggle (draft/active/inactive), `⋯` menu (duplicate, delete), close button.
2. **Chapter Links Section**: List of linked chapters with relevance + note. `+ Link` action at bottom.
3. **Attributes Section**: Ordered list of `AttributeRow` components.
4. **Footer**: Tags editor, timestamps (created/updated), Save button.

Panel opens in **view mode** by default. Fields become editable on click.

Auto-save on blur for individual field edits: `PATCH /v1/glossary/books/:bookId/entities/:entityId/attributes/:attrValueId`.

Explicit Save button for tag changes and status changes.

State transitions:
```
closed → open (click card)
open/view → open/edit (click field)
open/edit → saving → open/view (blur or save)
open/edit → saving → open/edit/error (API error)
open → closed (close button or ESC or click outside on desktop overlay)
```

### 3.6 Sub-Journey: Chapter Link Editor

Within `EntityDetailPanel` — Chapter Links section.

**View mode**: List of linked chapters with relevance badge and note. Unlink button (✕) per row.

**Link action**:
1. Click `+ Link` button.
2. Inline form expands: chapter dropdown (shows chapters NOT yet linked), relevance picker, optional note input.
3. Click "Link" → POST `/v1/glossary/books/:bookId/entities/:entityId/chapter-links`.
4. On success: new chapter row appears in list. Auto-sort by chapter index.
5. Auto-suggest toast: when evidence is added citing a chapter not yet linked → "Link to Ch.X? [Yes] [Dismiss]".

**Unlink action**:
- Click ✕ → if entity has evidences referencing that chapter → confirmation: "This entity has evidences in Ch.X. Unlink anyway?"
- DELETE `/v1/glossary/books/:bookId/entities/:entityId/chapter-links/:linkId`.

**Update relevance/note**:
- Click relevance badge → cycles major → appears → mentioned → major.
- Click note → inline text input.
- Auto-saves on blur: PATCH `/v1/glossary/books/:bookId/entities/:entityId/chapter-links/:linkId`.

### 3.7 Sub-Journey: Attribute Row

Each `AttributeRow` is collapsible. Collapsed state shows attribute name, original value preview, and translation/evidence count badges.

**Expanded state** sections:
1. Original Language picker (BCP-47 select) + Value input (renders according to `field_type`).
2. Translations list + `+ Add` button.
3. Evidences list + `+ Add` button.

**Edit original value**: click value → inline edit → blur → PATCH attribute.

### 3.8 Sub-Journey: Add Translation

1. User clicks `+ Add` in an attribute's Translations section.
2. `AddTranslationModal` opens:
   - Language select (filtered to exclude already-added languages).
   - Translation value input.
   - Confidence select: draft / machine / verified.
3. Confirm → POST `.../translations`.
4. Success: new translation row added inline.

### 3.9 Sub-Journey: Add Evidence

1. User clicks `+ Add` in an attribute's Evidences section.
2. `AddEvidenceModal` opens:
   - Chapter select (full chapter list of the book).
   - Block/Line text input ("Line 34", "Paragraph 12").
   - Evidence type: quote / summary / reference.
   - Original language select.
   - Text textarea.
   - Optional note.
3. Confirm → POST `.../evidences`.
4. Success: new evidence card appears.
5. **Auto-link check**: if the selected chapter is not yet linked to the entity → toast: "Link this entity to Ch.X? [Yes] [Dismiss]".

### 3.10 Sub-Journey: Delete Entity

1. User clicks ⋯ → Delete on card or detail panel header.
2. Confirmation dialog: "Delete [entity name]? This cannot be undone. All attributes, translations, and evidences will be deleted."
3. Confirm → DELETE `/v1/glossary/books/:bookId/entities/:entityId`.
4. Detail panel closes. Entity removed from list with fade animation.

---

## 4) State Model (component-level)

```
GlossaryPage
  kinds: EntityKind[]                  ← from GET /kinds
  chapters: Chapter[]                  ← from GET /books/:id/chapters
  filters: FilterState
  entities: GlossaryEntitySummary[]    ← paginated list
  total: number
  isLoading: boolean
  isLoadingMore: boolean
  selectedEntityId: string | null
  isDetailOpen: boolean
  isCreateModalOpen: boolean

EntityDetailPanel
  entity: GlossaryEntity | null        ← full detail from GET single
  isLoading: boolean
  isSaving: boolean
  editingAttrId: string | null         ← which attribute row is expanded
  addTranslationFor: string | null     ← attrValueId for modal
  addEvidenceFor: string | null        ← attrValueId for modal
  pendingChapterLinkSuggest: string | null  ← chapter_id for auto-suggest toast
```

---

## 5) API Mapping Table

| User Action | HTTP Call | Success Behavior |
| --- | --- | --- |
| Page load | GET /kinds + GET /entities + GET /chapters (parallel) | Render filter bar + entity list |
| Change filter | GET /entities with new params | Replace entity list |
| Load more | GET /entities with offset += 50 | Append to entity list |
| Click entity card | GET /entities/:id | Open detail panel |
| Create entity | POST /entities | Open detail panel with new entity |
| Delete entity | DELETE /entities/:id | Close panel, remove from list |
| Edit attribute value | PATCH /attributes/:attrValueId | Update inline |
| Link chapter | POST /chapter-links | Add to chapter links list |
| Unlink chapter | DELETE /chapter-links/:linkId | Remove from list |
| Update chapter relevance/note | PATCH /chapter-links/:linkId | Update row inline |
| Add translation | POST /translations | Add row to translation list |
| Delete translation | DELETE /translations/:translId | Remove row |
| Add evidence | POST /evidences | Add card to evidence list |
| Delete evidence | DELETE /evidences/:evidenceId | Remove card |
| Toggle entity status | PATCH /entities/:id `{ status }` | Update status badge |
| Save tags | PATCH /entities/:id `{ tags }` | Update tags display |

---

## 6) Component Inventory

| Component | Location | Description |
| --- | --- | --- |
| `GlossaryPage` | `pages/GlossaryPage.tsx` | Top-level page, layout host |
| `GlossaryFiltersBar` | `features/glossary/components/` | Filter controls: chapter, kind, status, search, tags |
| `GlossaryEntityCard` | `features/glossary/components/` | Summary card with kind badge, name, chips |
| `CreateEntityModal` | `features/glossary/components/` | Kind picker grid, triggers POST |
| `EntityDetailPanel` | `features/glossary/components/` | Slide-over with full CRUD |
| `ChapterLinkEditor` | `features/glossary/components/` | Chapter M:N link management within detail panel |
| `AttributeRow` | `features/glossary/components/` | Collapsible attribute row with value, translations, evidences |
| `AttributeValueInput` | `features/glossary/components/` | Field-type-aware input (text/textarea/select/tags) |
| `TranslationList` | `features/glossary/components/` | Translation rows + add button |
| `AddTranslationModal` | `features/glossary/components/` | Language + value + confidence form |
| `EvidenceList` | `features/glossary/components/` | Evidence cards + add button |
| `AddEvidenceModal` | `features/glossary/components/` | Chapter + location + type + text form |
| `KindBadge` | `features/glossary/components/` | Colored badge with kind icon |
| `ConfidenceBadge` | `features/glossary/components/` | verified / draft / machine indicator |
| `glossary/api.ts` | `features/glossary/api.ts` | All API calls for this feature |
| `glossary/types.ts` | `features/glossary/types.ts` | TypeScript types mirroring contract schemas |
