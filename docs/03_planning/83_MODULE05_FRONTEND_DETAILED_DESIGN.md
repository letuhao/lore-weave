# LoreWeave Module 05 Frontend Detailed Design

## Document Metadata

- Document ID: LW-M05-83
- Version: 0.1.0
- Status: Approved
- Owner: Frontend Lead
- Last Updated: 2026-03-23
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Summary: Component design, state management, API layer, TypeScript types, and routing integration for Module 05 glossary and lore management frontend.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 frontend detailed design | Assistant |

---

## 1) Routes

### New Route

Add to `App.tsx`:

```tsx
<Route
  path="/books/:bookId/glossary"
  element={
    <RequireAuth>
      <GlossaryPage />
    </RequireAuth>
  }
/>
```

### Navigation

`BookDetailPage.tsx` — add tab link alongside Translation/Sharing:
```tsx
<Link to={`/books/${bookId}/glossary`}>Glossary</Link>
```

---

## 2) TypeScript Types (`features/glossary/types.ts`)

```typescript
export type FieldType = 'text' | 'textarea' | 'select' | 'number' | 'date' | 'tags' | 'url' | 'boolean';

export interface AttributeDefinition {
  attr_def_id: string;
  kind_id: string;
  code: string;
  name: string;
  description?: string;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options?: string[];
}

export interface EntityKind {
  kind_id: string;
  code: string;
  name: string;
  description?: string;
  icon: string;
  color: string;
  is_default: boolean;
  is_hidden: boolean;
  sort_order: number;
  default_attributes: AttributeDefinition[];
}

export type Confidence = 'verified' | 'draft' | 'machine';
export type EntityStatus = 'active' | 'inactive' | 'draft';
export type Relevance = 'major' | 'appears' | 'mentioned';
export type EvidenceType = 'quote' | 'summary' | 'reference';

export interface Translation {
  translation_id: string;
  attr_value_id: string;
  language_code: string;
  value: string;
  confidence: Confidence;
  translator?: string;
  updated_at: string;
}

export interface EvidenceTranslation {
  id: string;
  evidence_id: string;
  language_code: string;
  value: string;
  confidence: Confidence;
}

export interface Evidence {
  evidence_id: string;
  attr_value_id: string;
  chapter_id?: string;
  chapter_title?: string;
  block_or_line: string;
  evidence_type: EvidenceType;
  original_language: string;
  original_text: string;
  note?: string;
  translations: EvidenceTranslation[];
  created_at: string;
}

export interface AttributeValue {
  attr_value_id: string;
  entity_id: string;
  attr_def_id: string;
  attribute_def: AttributeDefinition;
  original_language: string;
  original_value: string;
  translations: Translation[];
  evidences: Evidence[];
}

export interface ChapterLink {
  link_id: string;
  entity_id: string;
  chapter_id: string;
  chapter_title?: string;
  chapter_index?: number;
  relevance: Relevance;
  note?: string;
  added_at: string;
}

// List item (summary)
export interface GlossaryEntitySummary {
  entity_id: string;
  book_id: string;
  kind_id: string;
  kind: Pick<EntityKind, 'kind_id' | 'code' | 'name' | 'icon' | 'color'>;
  display_name: string;
  display_name_translation?: string;
  status: EntityStatus;
  tags: string[];
  chapter_link_count: number;
  translation_count: number;
  evidence_count: number;
  created_at: string;
  updated_at: string;
}

// Full detail
export interface GlossaryEntity extends GlossaryEntitySummary {
  chapter_links: ChapterLink[];
  attribute_values: AttributeValue[];
}

export interface GlossaryEntityListResponse {
  items: GlossaryEntitySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface GlossaryFilters {
  kindCodes: string[];
  status: 'all' | EntityStatus;
  chapterIds: string[] | 'all' | 'unlinked';
  searchQuery: string;
  tags: string[];
}
```

---

## 3) API Layer (`features/glossary/api.ts`)

```typescript
import { apiJson } from '@/api';

const base = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';
const v = '/v1/glossary';

// Kinds
export const getKinds = (token: string) =>
  apiJson<EntityKind[]>(`${v}/kinds`, { token });

// Entities
export const listEntities = (bookId: string, filters: GlossaryFilters & { limit: number; offset: number }, token: string) => {
  const params = buildFilterParams(filters);
  return apiJson<GlossaryEntityListResponse>(`${v}/books/${bookId}/entities?${params}`, { token });
};

export const getEntity = (bookId: string, entityId: string, token: string) =>
  apiJson<GlossaryEntity>(`${v}/books/${bookId}/entities/${entityId}`, { token });

export const createEntity = (bookId: string, kindId: string, token: string) =>
  apiJson<GlossaryEntity>(`${v}/books/${bookId}/entities`, {
    method: 'POST', body: { kind_id: kindId }, token,
  });

export const patchEntity = (bookId: string, entityId: string, changes: Partial<Pick<GlossaryEntity, 'status' | 'tags'>>, token: string) =>
  apiJson<GlossaryEntity>(`${v}/books/${bookId}/entities/${entityId}`, {
    method: 'PATCH', body: changes, token,
  });

export const deleteEntity = (bookId: string, entityId: string, token: string) =>
  apiJson<void>(`${v}/books/${bookId}/entities/${entityId}`, { method: 'DELETE', token });

// Chapter Links
export const createChapterLink = (bookId: string, entityId: string, body: { chapter_id: string; relevance: Relevance; note?: string }, token: string) =>
  apiJson<ChapterLink>(`${v}/books/${bookId}/entities/${entityId}/chapter-links`, { method: 'POST', body, token });

export const patchChapterLink = (bookId: string, entityId: string, linkId: string, changes: { relevance?: Relevance; note?: string }, token: string) =>
  apiJson<ChapterLink>(`${v}/books/${bookId}/entities/${entityId}/chapter-links/${linkId}`, { method: 'PATCH', body: changes, token });

export const deleteChapterLink = (bookId: string, entityId: string, linkId: string, token: string) =>
  apiJson<void>(`${v}/books/${bookId}/entities/${entityId}/chapter-links/${linkId}`, { method: 'DELETE', token });

// Attribute Values
export const patchAttributeValue = (bookId: string, entityId: string, attrValueId: string, changes: { original_language?: string; original_value?: string }, token: string) =>
  apiJson<AttributeValue>(`${v}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}`, { method: 'PATCH', body: changes, token });

// Translations
export const createTranslation = (bookId: string, entityId: string, attrValueId: string, body: { language_code: string; value: string; confidence: Confidence; translator?: string }, token: string) =>
  apiJson<Translation>(`${v}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations`, { method: 'POST', body, token });

export const deleteTranslation = (bookId: string, entityId: string, attrValueId: string, translationId: string, token: string) =>
  apiJson<void>(`${v}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations/${translationId}`, { method: 'DELETE', token });

// Evidences
export const createEvidence = (bookId: string, entityId: string, attrValueId: string, body: Omit<Evidence, 'evidence_id' | 'attr_value_id' | 'translations' | 'created_at'>, token: string) =>
  apiJson<Evidence>(`${v}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences`, { method: 'POST', body, token });

export const deleteEvidence = (bookId: string, entityId: string, attrValueId: string, evidenceId: string, token: string) =>
  apiJson<void>(`${v}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences/${evidenceId}`, { method: 'DELETE', token });

// Export
export const exportGlossary = (bookId: string, token: string, chapterId?: string) => {
  const params = chapterId ? `?chapter_id=${chapterId}` : '';
  return apiJson<object>(`${v}/books/${bookId}/export${params}`, { token });
};
```

---

## 4) State Management

Use **React local state + custom hooks** (no global store required for MVP — glossary data is scoped to a single page/book):

### `useGlossaryEntities` hook

```typescript
// Returns paginated entity list, filter state, and mutations
function useGlossaryEntities(bookId: string) {
  const [filters, setFilters] = useState<GlossaryFilters>({ ... });
  const [entities, setEntities] = useState<GlossaryEntitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  // Debounced fetch on filter change
  // Returns: { entities, total, filters, setFilters, loadMore, isLoading, isLoadingMore }
}
```

### `useEntityDetail` hook

```typescript
// Returns full entity detail and mutation helpers
function useEntityDetail(bookId: string, entityId: string | null) {
  const [entity, setEntity] = useState<GlossaryEntity | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Returns: { entity, isLoading, refetch, patchEntity, createChapterLink, ... }
}
```

---

## 5) Component Specifications

### `GlossaryPage`

- Layout: two-column on desktop (≥768px): entity list (left, ~55%) + detail panel overlay (right, ~45%).
- On mobile: full-width list; detail panel as full-screen modal.
- Toolbar: `+ New Entity` button (top right).
- Manages: `kinds`, `chapters`, `filters`, `selectedEntityId`, `isDetailOpen`, `isCreateModalOpen`.

### `GlossaryFiltersBar`

- Renders: chapter multi-select, kind multi-select (colored chips), status segmented control, search input, tag filter.
- Active filter chips shown below bar with ✕ to remove.
- `searchQuery` debounced 300ms before triggering fetch.

### `GlossaryEntityCard`

- Left color bar using `kind.color`.
- Displays: `kind.icon` + kind name badge, `display_name`, chapter link chips (max 3 + "+N more"), translation count, evidence count, status badge.
- Hover: subtle elevation + border highlight.
- ⋯ menu: Duplicate (future), Set Inactive, Delete.

### `EntityDetailPanel`

- `Sheet` component from shadcn/ui (slide from right).
- Sections: Header → ChapterLinkEditor → AttributeList → Footer.
- Close on: close button, ESC key, click outside.
- Refetches entity detail on open.

### `AttributeRow`

- Controlled by: `expandedAttrId` state in parent.
- Collapsed: attribute name, original value preview (truncated), translation count badge, evidence count badge.
- Expanded: `AttributeValueInput` + `TranslationList` + `EvidenceList`.
- Edit original value: inline input → blur → `patchAttributeValue`.

### `AttributeValueInput`

- Renders according to `attribute_def.field_type`:
  - `text` → `<Input>`
  - `textarea` → `<Textarea>`
  - `select` → `<Select>` with `attribute_def.options`
  - `tags` → comma-separated tag input with badge rendering
  - Other types → `<Input>` fallback in MVP

### `AddTranslationModal`

- Language `<Select>` filtered to exclude already-present language_codes.
- Value `<Input>`.
- Confidence `<Select>`: draft / machine / verified.
- Uses shadcn `Dialog` component.

### `AddEvidenceModal`

- Chapter `<Select>` from book's chapter list.
- Block/Line `<Input>`.
- Evidence type radio: quote / summary / reference.
- Original language `<Select>`.
- Text `<Textarea>`.
- Optional note `<Input>`.
- Uses shadcn `Dialog` component.

---

## 6) Error Handling

| Error code | User-facing message |
| --- | --- |
| `GLOSS_FORBIDDEN` | "You don't have permission to access this book's glossary." |
| `GLOSS_NOT_FOUND` | "Item not found. It may have been deleted." |
| `GLOSS_DUPLICATE_CHAPTER_LINK` | "This entity is already linked to that chapter." |
| `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE` | "A translation in this language already exists." |
| `GLOSS_CHAPTER_NOT_IN_BOOK` | "The selected chapter doesn't belong to this book." |
| Network / 5xx | "Something went wrong. Please try again." |

All errors shown as toast notifications (using existing `useToast` or inline error messages within modals).
