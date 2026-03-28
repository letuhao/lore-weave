# UI/UX Improvement Plan — LoreWeave Frontend

> **Author**: Claude (Frontend Lead Review)
> **Date**: 2026-03-28
> **Scope**: Full frontend UI/UX audit and improvement roadmap

---

## 1. Executive Summary

The current LoreWeave frontend is functional but suffers from several structural UX problems:

- **Scattered layout** — Forms, lists, filters, and actions are placed linearly without clear visual grouping by feature category
- **Inconsistent patterns** — Filters, pagination, and sorting are implemented differently across pages (glossary uses load-more + filter chips; books use offset pagination + raw text inputs; translation uses inline select)
- **Hardcoded-feeling UI for dynamic data** — Entities have flexible, user-defined attributes and kinds, but the UI doesn't adapt to this (e.g., no column customization, no dynamic sort fields, no saved filter presets)
- **No unified data-table component** — Each page reinvents list rendering, filtering, and pagination from scratch
- **Minimal affordances** — Raw `<input>`, `<select>`, and `<button>` elements with inconsistent styling; no empty-state illustrations; limited keyboard navigation

---

## 2. Current State Audit

### 2.1 Page-by-Page Issues

| Page | Problems |
|---|---|
| **BooksPage** | Create form and book list side-by-side with no clear hierarchy. Pagination is present but non-functional (limit = total). No search, no sort, no filters. |
| **BookDetailPage** | Two create forms (editor + upload) dominate the top, pushing the chapter list below the fold. Filters are raw text inputs ("Filter language", "Sort order") with no labels or validation. Filter/list/forms are not visually separated. |
| **GlossaryPage** | Best-designed page, but uses load-more instead of page-based pagination. Filter bar is 3 stacked rows that feel heavy. Entity cards use a 2-column grid that doesn't scale — no table/list view toggle. |
| **BookTranslationPage** | Language filter is a single `<select>` nested inside the matrix border. No chapter search or sort. Settings and jobs are buttons in the header with no visual grouping. |
| **UsageLogsPage** | Flat list with no filtering, sorting, or date-range picker. |
| **RecycleBinPage** | Tabs for books/glossary, but no search or bulk actions. |

### 2.2 Cross-Cutting Issues

1. **No shared DataTable / DataGrid component** — Every page builds its own list + filter + pagination from scratch
2. **Filter patterns diverge** — Glossary has filter chips + kind toggles + tag input; BookDetail has raw text inputs; Translation has a single select
3. **Pagination is inconsistent** — `PaginationBar` (offset-based prev/next) vs load-more button vs no pagination
4. **Sort is almost non-existent** — BookDetail has a "Sort order" text input (expects a number?); Glossary passes `sort` to API but has no UI for it; other pages have no sort
5. **No column customization** — Entities have dynamic attributes, but the card/list views show a fixed set of fields
6. **No saved views or filter presets** — Users can't save commonly-used filter combinations
7. **Create forms compete with content** — BooksPage and BookDetailPage place forms alongside lists, reducing space for the primary content
8. **No bulk operations** — Can't multi-select entities for batch status change, delete, or tag
9. **Responsive design is basic** — `sm:grid-cols-2` / `xl:grid-cols-2` but no mobile-optimized layouts
10. **Accessibility gaps** — No ARIA landmarks, no focus management in modals, no keyboard shortcuts

---

## 3. Improvement Plan

### Phase 1: Unified Data Infrastructure (Foundation)

**Goal**: Build shared, reusable components that all list pages can adopt.

#### 3.1 Generic `<DataTable>` Component
- **Columns are config-driven** — Accept a `columns` array where each column defines: key, label, render function, sortable flag, width
- **Dynamic columns for flexible entities** — Entity attribute definitions become columns automatically
- **Built-in sort** — Click column headers to sort; visual indicator for active sort direction
- **Row selection** — Checkbox column for bulk operations
- **View toggle** — Switch between table view and card/grid view
- **Density toggle** — Compact / comfortable / spacious row heights

```
Props:
  columns: ColumnDef[]
  data: T[]
  isLoading: boolean
  emptyState: ReactNode
  rowSelection?: { selected: Set<string>, onToggle, onSelectAll }
  sortState?: { field: string, direction: 'asc' | 'desc' }
  onSort?: (field: string) => void
  viewMode?: 'table' | 'grid'
```

#### 3.2 Unified `<FilterToolbar>` Component
- **Composable filter slots** — Search input, dropdown filters, toggle chips, date ranges
- **Active filter chips** with one-click removal (adopt glossary's existing chip pattern)
- **Clear all** button
- **Saved filter presets** — Save/load named filter combinations (stored in localStorage initially, API later)
- **Collapsible advanced filters** — Show basic filters by default, expand for advanced

#### 3.3 Unified `<Pagination>` Component
- Replace both `PaginationBar` and load-more with a single component
- **Modes**: page-based (prev/1/2/3/next), cursor-based, or infinite scroll
- **Page size selector** (10 / 25 / 50 / 100)
- **Jump to page** input for large datasets
- **Item count summary** — "Showing 1-25 of 342"

#### 3.4 `useDataQuery` Hook
- Unified hook that manages: filter state, sort state, pagination state, API fetching, loading/error states
- Replaces `useGlossaryEntities` pattern with a generic, reusable version
- URL search params sync — Filters/sort/page are reflected in the URL (shareable, back-button friendly)

---

### Phase 2: Page Redesigns

#### 3.5 BooksPage Redesign
- **Separate create from list** — Move "Create book" into a modal or collapsible panel, not side-by-side
- **Add search** — Filter books by title
- **Add sort** — Sort by title, date created, chapter count
- **Use `<DataTable>`** — Table view with columns: Title, Language, Chapters, Visibility, State, Created
- **Fix pagination** — Currently non-functional; wire up proper offset/limit

#### 3.6 BookDetailPage Redesign
- **Reorganize into sections with tabs or vertical nav**:
  - **Overview** tab: Book metadata, cover, description (editable inline)
  - **Chapters** tab: Chapter list with proper DataTable, filters, sort
  - **Add Chapter** action: Modal or drawer instead of two always-visible forms
- **Chapter filters** — Replace raw text inputs with proper `<FilterToolbar>`:
  - Language: dropdown picker (not raw text)
  - Status: dropdown (active/trashed/purge_pending)
  - Sort: dropdown (by order, by title, by language) + direction toggle
- **Chapter actions** — Hover-reveal action menu (edit, translate, download, trash) instead of always-visible underlined text links

#### 3.7 GlossaryPage Enhancements
- **Adopt `<DataTable>`** — Add table view option alongside existing card grid
- **Dynamic columns from entity attributes** — Show attribute values as columns in table view, configurable per-kind
- **Proper pagination** — Replace load-more with page-based pagination (keep infinite scroll as option)
- **Sort UI** — Add sort dropdown: by name, by status, by kind, by date modified
- **Bulk actions** — Multi-select entities for batch: set status, add tags, delete, link to chapter
- **Column customization** — Users choose which attribute columns to show/hide

#### 3.8 TranslationPage Enhancements
- **Move filter into `<FilterToolbar>`** — Language multi-select, chapter search, status filter (translated/untranslated/partial)
- **Sticky header** for the matrix so columns stay visible while scrolling

#### 3.9 UsageLogsPage
- **Add `<DataTable>`** with columns: date, model, tokens, cost, chapter
- **Add filters** — Date range picker, model filter
- **Add sort** — By date, by cost, by token count

---

### Phase 3: Adaptive UI for Dynamic Entities

**Goal**: The UI should feel like it was designed specifically for whatever entity kinds and attributes the user has configured.

#### 3.10 Dynamic Form Generator
- Read `AttributeDefinition[]` from entity kind and render form fields dynamically
- Map `field_type` to components: text -> Input, textarea -> Textarea, select -> Select, number -> NumberInput, date -> DatePicker, tags -> TagInput, url -> UrlInput, boolean -> Toggle
- Validation from `is_required` + `field_type` constraints
- Form layout adapts: 1-column for few fields, 2-column for many

#### 3.11 Configurable List Columns
- Users pick which attributes appear as columns in the glossary table view
- Column config saved per entity-kind (e.g., Characters show "age", "role"; Locations show "region", "climate")
- Stored in localStorage, synced to user preferences API later

#### 3.12 Smart Filter Generation
- Auto-generate filter options from entity kind attributes:
  - `select` fields become dropdown filters
  - `boolean` fields become toggle filters
  - `tags` fields become tag-chip filters
  - `text`/`textarea` fields are searchable
- Filter toolbar adapts when user switches kind filter

#### 3.13 Custom Sort Fields
- Sort by any attribute field (not just name/status)
- API must support `sort=attr:<attr_def_code>` parameter

---

### Phase 4: Polish and Delight

#### 3.14 Empty States
- Illustrated empty states for each page (no books, no chapters, no entities, no translations)
- Contextual CTAs ("Create your first book", "Upload a chapter to get started")

#### 3.15 Keyboard Navigation
- `j`/`k` to move through lists
- `Enter` to open detail
- `Escape` to close panels/modals
- `/` to focus search
- `?` to show keyboard shortcut help

#### 3.16 Responsive & Mobile
- Collapsible sidebar navigation on mobile
- Bottom sheet for detail panels on small screens
- Touch-friendly tap targets (min 44px)
- Swipe gestures for card actions

#### 3.17 Loading & Skeleton States
- Consistent skeleton patterns matching final layout shape
- Optimistic updates for status changes and deletes
- Progress indicators for long operations (translation jobs)

#### 3.18 Accessibility
- ARIA landmarks for page regions
- Focus trap in modals and drawers
- Screen reader announcements for dynamic content changes
- Color contrast compliance (WCAG AA)
- Reduced motion support

---

## 4. Component Architecture

```
src/components/
├── data/                          # NEW — Shared data display components
│   ├── DataTable.tsx              # Generic table with sort, select, view toggle
│   ├── DataGrid.tsx               # Card grid variant
│   ├── FilterToolbar.tsx          # Composable filter bar
│   ├── Pagination.tsx             # Unified pagination
│   ├── SortDropdown.tsx           # Sort field + direction
│   ├── ColumnCustomizer.tsx       # Column show/hide panel
│   ├── BulkActionBar.tsx          # Floating bar for selected items
│   ├── EmptyState.tsx             # Illustrated empty state
│   └── ViewToggle.tsx             # Table/grid/list switch
├── forms/                         # NEW — Dynamic form components
│   ├── DynamicFieldRenderer.tsx   # Renders field by FieldType
│   ├── DynamicForm.tsx            # Full form from AttributeDefinition[]
│   └── FilterFieldRenderer.tsx    # Renders filter by FieldType
├── ui/                            # Existing — Extend with missing primitives
│   ├── ... (existing)
│   ├── select.tsx                 # Proper Select component (replace raw <select>)
│   ├── dropdown-menu.tsx          # Action menus
│   ├── dialog.tsx                 # Modal with focus trap
│   ├── drawer.tsx                 # Slide-out panel
│   ├── tabs.tsx                   # Tab navigation
│   ├── badge.tsx                  # Unified badge
│   ├── date-picker.tsx            # Date input
│   └── toggle.tsx                 # Boolean toggle
└── hooks/
    └── useDataQuery.ts            # NEW — Generic data fetch + filter + sort + paginate
```

---

## 5. Migration Strategy

| Step | Scope | Risk | Effort |
|---|---|---|---|
| 1 | Build `DataTable`, `FilterToolbar`, `Pagination` | Low | Medium |
| 2 | Add missing UI primitives (Select, Dialog, Tabs, etc.) | Low | Low |
| 3 | Refactor `GlossaryPage` to use new components | Medium | Medium |
| 4 | Refactor `BookDetailPage` chapters section | Medium | Medium |
| 5 | Refactor `BooksPage` | Low | Low |
| 6 | Add dynamic form generation | Low | Medium |
| 7 | Add configurable columns | Low | Medium |
| 8 | Add smart filter generation | Low | High |
| 9 | Polish pass (empty states, keyboard nav, a11y) | Low | Medium |

**Recommended order**: Steps 1-2 first (foundation), then 3-5 (page migrations), then 6-8 (dynamic features), then 9 (polish).

---

## 6. Key Design Principles

1. **Config-driven, not hardcoded** — Columns, filters, sorts, and forms should derive from data definitions, not be manually coded per page
2. **Consistent patterns** — One pagination component, one filter pattern, one sort interaction across all pages
3. **Content first** — Primary content (lists, tables) gets the most space; create/edit forms are on-demand (modals, drawers)
4. **Progressive disclosure** — Basic filters visible by default; advanced options behind "More filters"; column customization in a settings panel
5. **URL-driven state** — Filter, sort, page, and view mode reflected in URL params for shareability and back-button support
6. **Graceful degradation** — Works without JS for basic reading; progressive enhancement for interactions
