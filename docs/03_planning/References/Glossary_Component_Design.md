# Novel Glossary & Lore Management — Component Design Specification

> **Platform**: React Web Application (Novel Creation, Translation & Lore Collection)
> **Purpose**: CRUD management for novel glossary entities with multilingual support, evidence tracking, and RAG-ready data structure
> **Version**: 1.0

---

## 1. Domain Model Overview

### 1.1 Core Concepts

The glossary system treats **Entities** (glossary entries) as **independent, book-level objects** — they are not owned by any chapter. Instead, entities are **linked** to one or more chapters via a many-to-many join (`ChapterLink`). This means a character, location, or item exists once in the glossary and can appear across any number of chapters.

```
Book
 ├── Chapters[]
 │    └── (no direct children — linked via ChapterLink)
 │
 └── Glossary Entities[]            ← independent, book-level
      ├── kind: EntityKind (character, location, item, ...)
      ├── chapterLinks[]            ← many-to-many join
      │    ├── chapterId
      │    ├── relevance: "appears" | "mentioned" | "major"
      │    └── note?: string
      ├── attributes[]
      │    ├── definition (code, name, description)
      │    ├── value (original language + translations[])
      │    └── evidences[]
      │         ├── location (chapter, block/line)
      │         ├── quote / summary
      │         └── translations[]
      └── status: active | inactive

Relationship: Entity ←—M:N—→ Chapter (via ChapterLink)
```

### 1.2 Data Type Definitions

```typescript
// ─── Language & Translation ────────────────────────────

type LanguageCode = string; // ISO 639-1: "en", "zh", "ja", "ko", etc.

interface Translation {
  id: string;
  languageCode: LanguageCode;
  value: string;
  translator?: string;       // who translated
  confidence?: "verified" | "draft" | "machine";
  updatedAt: string;
}

// ─── Evidence ──────────────────────────────────────────

interface EvidenceLocation {
  chapterIndex: number;      // which chapter (0-based or ID ref)
  chapterId?: string;
  chapterTitle?: string;
  blockOrLine: string;       // e.g. "paragraph 12", "line 34", "section 2.3"
}

interface Evidence {
  id: string;
  location: EvidenceLocation;
  type: "quote" | "summary" | "reference";
  originalLanguage: LanguageCode;
  originalText: string;
  translations: Translation[];
  note?: string;             // user's annotation
  createdAt: string;
}

// ─── Attribute ─────────────────────────────────────────

interface AttributeDefinition {
  id: string;
  code: string;              // machine key: "name", "title", "gender", etc.
  name: string;              // display label (English default)
  description: string;       // what this attribute represents
  fieldType: "text" | "textarea" | "select" | "number" | "date" | "tags" | "url" | "boolean";
  isDefault: boolean;        // system-provided vs user-added
  isRequired: boolean;
  sortOrder: number;
  isActive: boolean;
  options?: string[];        // for select type
  translations: Translation[];  // translations of the attribute NAME itself
}

interface AttributeValue {
  id: string;
  attributeDefinitionId: string;
  originalLanguage: LanguageCode;
  originalValue: string;
  translations: Translation[];
  evidences: Evidence[];
}

// ─── Entity Kind ───────────────────────────────────────

interface EntityKind {
  id: string;
  code: string;              // "character", "location", "item", etc.
  name: string;
  description?: string;      // what this kind represents
  icon: string;              // emoji or icon identifier
  color: string;             // tag/badge color
  defaultAttributes: AttributeDefinition[];
  isDefault: boolean;        // system-provided vs user-created
  isHidden: boolean;         // hidden kinds don't appear in pickers/filters
  sortOrder: number;
  clonedFromKindId?: string; // if created by cloning another kind
  createdAt: string;
  updatedAt: string;
}

// ─── Chapter Link (many-to-many join) ─────────────────

interface ChapterLink {
  id: string;
  chapterId: string;
  chapterTitle?: string;         // denormalized for display
  chapterIndex?: number;         // for ordering
  relevance: "major" | "appears" | "mentioned";
  note?: string;                 // e.g. "introduced here", "flashback only"
  addedAt: string;
}

// ─── Glossary Entity ───────────────────────────────────

interface GlossaryEntity {
  id: string;
  bookId: string;                // belongs to one book
  kindId: string;
  kind: EntityKind;
  chapterLinks: ChapterLink[];   // linked to 0..N chapters
  attributeValues: AttributeValue[];
  status: "active" | "inactive" | "draft";
  tags: string[];
  createdAt: string;
  updatedAt: string;
}
```

---

## 2. Default Entity Kinds & Their Attributes

Below is the recommended set of default entity kinds for a novel glossary system. Users can add/remove/customize these.

### 2.1 Character (`character`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Character's primary name |
| 2 | `aliases` | Aliases / Other Names | tags | | Alternative names, nicknames, titles |
| 3 | `gender` | Gender | select | | Male / Female / Non-binary / Other / Unknown |
| 4 | `age` | Age | text | | Age or age range at introduction |
| 5 | `role` | Role | select | | Protagonist / Antagonist / Supporting / Minor / Mentioned |
| 6 | `affiliation` | Affiliation / Faction | text | | Group, sect, family, organization |
| 7 | `cultivation_level` | Power Level / Rank | text | | For xianxia/fantasy: cultivation stage, magic rank, etc. |
| 8 | `appearance` | Appearance | textarea | | Physical description |
| 9 | `personality` | Personality | textarea | | Traits, temperament, motivations |
| 10 | `relationships` | Key Relationships | textarea | | Connections to other characters |
| 11 | `first_appearance` | First Appearance | text | | Chapter/scene of introduction |
| 12 | `description` | Description | textarea | | General notes |

### 2.2 Location / Place (`location`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Place name |
| 2 | `aliases` | Aliases | tags | | Other names for this place |
| 3 | `type` | Location Type | select | | City / Region / Building / Realm / Dimension / Landmark / Other |
| 4 | `parent_location` | Parent Location | text | | Containing region or realm |
| 5 | `description` | Description | textarea | | What this place looks/feels like |
| 6 | `significance` | Significance | textarea | | Why it matters to the plot |
| 7 | `first_appearance` | First Appearance | text | | Chapter/scene of introduction |

### 2.3 Item / Object / Artifact (`item`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Item name |
| 2 | `aliases` | Aliases | tags | | Other names |
| 3 | `type` | Item Type | select | | Weapon / Armor / Tool / Consumable / Treasure / Document / Other |
| 4 | `rarity` | Rarity / Grade | select | | Common / Uncommon / Rare / Legendary / Unique |
| 5 | `owner` | Owner / Holder | text | | Who possesses it |
| 6 | `abilities` | Abilities / Effects | textarea | | What it does |
| 7 | `description` | Description | textarea | | Physical description, lore |
| 8 | `first_appearance` | First Appearance | text | | Chapter/scene of introduction |

### 2.4 Power System / Ability (`power_system`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Technique or system name |
| 2 | `aliases` | Aliases | tags | | Alternative names |
| 3 | `type` | Category | select | | Martial Art / Spell / Skill / Passive / Bloodline / Other |
| 4 | `rank` | Rank / Tier | text | | Power level within the system |
| 5 | `user` | Known Users | text | | Characters who use this |
| 6 | `effects` | Effects | textarea | | What it does |
| 7 | `requirements` | Requirements | textarea | | Prerequisites to learn/use |
| 8 | `description` | Description | textarea | | Detailed explanation |

### 2.5 Organization / Faction (`organization`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Organization name |
| 2 | `aliases` | Aliases | tags | | Other names |
| 3 | `type` | Type | select | | Sect / Kingdom / Company / Guild / Family / Military / Other |
| 4 | `leader` | Leader | text | | Who leads this group |
| 5 | `headquarters` | Headquarters | text | | Where they are based |
| 6 | `members` | Notable Members | textarea | | Key people in the organization |
| 7 | `purpose` | Purpose / Goal | textarea | | What they aim to achieve |
| 8 | `description` | Description | textarea | | General notes |

### 2.6 Event (`event`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Event name |
| 2 | `type` | Event Type | select | | Battle / Ceremony / Disaster / Discovery / Political / Other |
| 3 | `date_in_story` | Date (In-Story) | text | | When it happened in the story timeline |
| 4 | `location` | Location | text | | Where it happened |
| 5 | `participants` | Participants | textarea | | Who was involved |
| 6 | `outcome` | Outcome | textarea | | What resulted |
| 7 | `description` | Description | textarea | | Full description |

### 2.7 Terminology / Concept (`terminology`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `term` | Term | text | ✓ | The word or phrase |
| 2 | `category` | Category | select | | Cultural / Technical / Magical / Political / Religious / Other |
| 3 | `definition` | Definition | textarea | ✓ | What it means in the novel's world |
| 4 | `usage_note` | Usage Notes | textarea | | Context, nuance, common confusion |

### 2.8 Species / Race (`species`)

| # | Code | Name | Type | Required | Description |
|---|------|------|------|----------|-------------|
| 1 | `name` | Name | text | ✓ | Species or race name |
| 2 | `aliases` | Aliases | tags | | Other names |
| 3 | `traits` | Physical Traits | textarea | | Distinguishing features |
| 4 | `abilities` | Innate Abilities | textarea | | Natural powers |
| 5 | `habitat` | Habitat | text | | Where they live |
| 6 | `culture` | Culture | textarea | | Social norms, values |
| 7 | `description` | Description | textarea | | General overview |

---

## 3. Component Architecture

### 3.1 Component Tree

```
<GlossaryManager>                          ← top-level page/panel
├── <GlossaryToolbar>                      ← actions: add entity, manage kinds, import/export
│   ├── <AddEntityButton>
│   ├── <ManageKindsButton>
│   └── <ExportButton>
├── <GlossaryFilters>                      ← filter bar
│   ├── <ChapterFilter>                    ← select chapters to show linked entities
│   ├── <KindFilter>                       ← filter by entity kind
│   ├── <StatusFilter>                     ← active / inactive / draft
│   ├── <LanguageFilter>                   ← filter by available translations
│   ├── <TagFilter>                        ← filter by user tags
│   └── <SearchInput>                      ← full-text search across all values
├── <GlossaryList>                         ← main list/grid of entities
│   ├── <GlossaryEntityCard>[]             ← summary card per entity
│   │   ├── <KindBadge>                    ← colored label (Character, Item, etc.)
│   │   ├── <EntityName>                   ← primary name + original language flag
│   │   ├── <ChapterLinks>                ← linked chapter badges (Ch.1, Ch.3, Ch.7…)
│   │   ├── <TranslationCount>            ← "3 languages"
│   │   ├── <EvidenceCount>               ← "5 evidences"
│   │   └── <StatusToggle>                ← active/inactive switch
│   └── <Pagination / InfiniteScroll>
├── <EntityDetailPanel>                    ← slide-over or modal for CRUD
│   ├── <EntityHeader>
│   │   ├── <KindSelector>                ← change entity kind
│   │   ├── <ChapterLinkEditor>           ← link/unlink chapters (many-to-many)
│   │   ├── <StatusToggle>
│   │   └── <DeleteButton>
│   ├── <AttributeList>                   ← all attributes for this entity
│   │   ├── <AttributeRow>[]
│   │   │   ├── <AttributeLabel>          ← name + code + field type icon
│   │   │   ├── <AttributeValueEditor>    ← edit the original-language value
│   │   │   │   ├── <OriginalLanguagePicker>
│   │   │   │   └── <ValueInput>          ← text / textarea / select / tags / etc.
│   │   │   ├── <TranslationList>         ← translations of this value
│   │   │   │   ├── <TranslationRow>[]
│   │   │   │   │   ├── <LanguageFlag>
│   │   │   │   │   ├── <TranslatedValue>
│   │   │   │   │   ├── <ConfidenceBadge>
│   │   │   │   │   ├── <EditButton>
│   │   │   │   │   └── <RemoveButton>
│   │   │   │   └── <AddTranslationButton>
│   │   │   ├── <EvidenceList>            ← evidences for this attribute
│   │   │   │   ├── <EvidenceCard>[]
│   │   │   │   │   ├── <LocationRef>     ← chapter + block/line
│   │   │   │   │   ├── <QuoteOrSummary>  ← original text
│   │   │   │   │   ├── <EvidenceTranslations>
│   │   │   │   │   ├── <EditButton>
│   │   │   │   │   └── <RemoveButton>
│   │   │   │   └── <AddEvidenceButton>
│   │   │   └── <DragHandle>              ← for reordering
│   │   ├── <AddAttributeButton>          ← add custom attribute
│   │   └── <ManageAttributesButton>      ← show/hide, reorder, remove fields
│   └── <EntityFooter>
│       ├── <TagEditor>
│       ├── <CreatedAt / UpdatedAt>
│       └── <SaveButton>
├── <KindManager>                          ← full CRUD for entity kinds (modal or page)
│   ├── <KindListPanel>                    ← left: scrollable list of all kinds
│   │   ├── <KindSearchInput>
│   │   ├── <KindGroup label="Default">
│   │   │   └── <KindRow>[]               ← draggable, clickable rows
│   │   │       ├── <DragHandle>
│   │   │       ├── <KindIcon>             ← emoji icon
│   │   │       ├── <KindName>
│   │   │       ├── <AttrCount>
│   │   │       ├── <EntityCount>
│   │   │       └── <StatusDot>            ← active / hidden
│   │   ├── <KindGroup label="Custom">
│   │   │   └── <KindRow>[]
│   │   └── <AddCustomKindButton>
│   ├── <KindDetailPanel>                  ← right: edit selected kind
│   │   ├── <KindIdentitySection>
│   │   │   ├── <EmojiPicker>
│   │   │   ├── <ColorPicker>
│   │   │   ├── <NameInput>
│   │   │   ├── <CodeInput>                ← auto-slug, read-only after entities exist
│   │   │   ├── <DescriptionInput>
│   │   │   ├── <StatusToggle>             ← active / hidden
│   │   │   └── <ImpactWarning>            ← "34 entities use this kind"
│   │   ├── <AttributeSchemaSection>
│   │   │   ├── <AttributeDefinitionRow>[] ← draggable, inline-editable
│   │   │   │   ├── <DragHandle>
│   │   │   │   ├── <VisibilityCheckbox>   ← show/hide attribute
│   │   │   │   ├── <CodeLabel>
│   │   │   │   ├── <NameLabel>
│   │   │   │   ├── <FieldTypeBadge>
│   │   │   │   ├── <RequiredToggle>
│   │   │   │   ├── <OriginBadge>          ← 🔒 Default / ✏ Custom
│   │   │   │   └── <DeleteButton>         ← custom attrs only
│   │   │   ├── <AddCustomAttributeForm>   ← inline expandable form
│   │   │   │   ├── <CodeInput>            ← auto-slug from name
│   │   │   │   ├── <NameInput>
│   │   │   │   ├── <DescriptionInput>
│   │   │   │   ├── <FieldTypePicker>
│   │   │   │   ├── <RequiredToggle>
│   │   │   │   ├── <SelectOptionEditor>   ← shown only for select type
│   │   │   │   └── <TranslationList>      ← translate attribute name
│   │   │   └── <ResetToDefaultsButton>
│   │   └── <KindDetailFooter>
│   │       ├── <DeleteKindButton>         ← custom kinds only
│   │       └── <SaveChangesButton>
│   └── <CreateKindPanel>                  ← replaces detail panel during creation
│       ├── <KindIdentitySection>          ← same as above but empty
│       ├── <StartFromSelector>            ← blank / clone from existing
│       ├── <AttributeSchemaSection>       ← empty or cloned
│       └── <CreateKindButton>
└── <DeleteKindDialog>                     ← confirmation with reassign option
    ├── <ReassignKindPicker>
    └── <ConfirmDeleteButton>
```

### 3.2 State Management Approach

Recommended: **React Context + useReducer** for local state, or **Zustand / Jotai** for a more scalable store. Key slices:

```
glossaryStore
├── entities: GlossaryEntity[]
├── kinds: EntityKind[]
├── chapters: Chapter[]              ← book's chapter list (for link UI)
├── filters: {
│   chapterIds: string[] | "all" | "unlinked"
│   │                         ↑ "all" = every entity
│   │                           "unlinked" = entities with 0 chapter links
│   kindCodes: string[]
│   status: "all" | "active" | "inactive" | "draft"
│   searchQuery: string
│   languageCode: string | null
│   tags: string[]
│ }
├── ui: {
│   selectedEntityId: string | null
│   isDetailPanelOpen: boolean
│   isKindManagerOpen: boolean
│   selectedKindId: string | null        ← which kind is selected in KindManager
│   isCreatingKind: boolean              ← shows CreateKindPanel instead of detail
│   sortField: string
│   sortDirection: "asc" | "desc"
│ }
└── actions: {
    // Entity CRUD
    createEntity, updateEntity, deleteEntity,
    toggleEntityStatus, updateFilters,
    // Chapter linking
    linkChapter, unlinkChapter, updateChapterLink,
    // Attribute values (on entities)
    setAttributeValue, addTranslation, removeTranslation,
    addEvidence, updateEvidence, removeEvidence,
    // Kind CRUD
    createKind, updateKind, deleteKind,
    hideKind, showKind,
    reorderKinds,
    reassignEntitiesKind,
    // Attribute definitions (on kinds)
    addAttributeDef, updateAttributeDef, removeAttributeDef,
    reorderAttributeDefs, toggleAttributeDefVisibility,
    resetAttributeDefsToDefault,
    ...
  }
```

---

## 4. Component Specifications

### 4.1 GlossaryFilters

**Purpose**: Let user narrow the glossary view by linked chapters, kind, status, language, and free text.

**Layout**: Horizontal bar with inline controls. Collapsible to a single "Filters" chip on mobile.

**Behavior**:
- **Chapter Filter**: Multi-select dropdown listing all chapters + "All" (default) + "Unlinked". Selecting specific chapters shows entities that have a `ChapterLink` to any of those chapters. "Unlinked" shows entities with zero chapter links (newly created, not yet placed). "All" shows everything.
- **Kind Filter**: Multi-select with colored icons matching the entity kind badges.
- **Status Filter**: Segmented control — All / Active / Inactive / Draft.
- **Language Filter**: Single-select dropdown. When a language is chosen, only entities that have at least one translation in that language are shown.
- **Search**: Debounced text input (300ms). Searches across entity names, attribute values, translations, and evidence text.
- **Tag Filter**: Combobox with existing tags. Multi-select.
- Active filters shown as removable chips below the bar.

```
┌─────────────────────────────────────────────────────────────────┐
│  📖 Chapters: [Ch.1, Ch.2 ▾]  │  🏷 Kind: [All ▾]            │
│  ◉ All ○ Active ○ Inactive    │  🌐 Language: [Any ▾]         │
│  🔍 Search glossary...         │  🏷 Tags: [+]                │
├─────────────────────────────────────────────────────────────────┤
│  Showing 47 entries  │  Filters: Ch.1 ✕  Ch.2 ✕  Character ✕  │
│                      │           ⚠ 3 unlinked entries          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 GlossaryEntityCard

**Purpose**: Compact summary of one glossary entity in the list view.

**Layout**: Card with left color bar (kind color), name, kind badge, linked chapter chips, stat counts.

```
┌──┬──────────────────────────────────────────────────┐
│▌ │  林默 (Lín Mò)                          ● Active │
│▌ │  👤 Character     📖 Ch.1  Ch.3  Ch.7  +4 more   │
│▌ │  🌐 3 languages  📎 5 evidences  🏷 protagonist  │
└──┴──────────────────────────────────────────────────┘
```

**No links state** (newly created entity):
```
┌──┬──────────────────────────────────────────────────┐
│▌ │  云山派                                  ○ Draft  │
│▌ │  🏛 Organization   📖 No chapters linked ⚠       │
│▌ │  🌐 1 language   📎 0 evidences                   │
└──┴──────────────────────────────────────────────────┘
```

**Interactions**:
- Click → opens EntityDetailPanel
- Right-click or ⋯ menu → quick actions: Duplicate, Set Inactive, Delete
- Hover → subtle elevation + border highlight

### 4.3 EntityDetailPanel

**Purpose**: Full CRUD interface for a single glossary entity.

**Layout**: Side panel (slide from right, ~600px wide on desktop) or full-screen modal on mobile.

**Sections** (scrollable):

1. **Header**: Kind selector, chapter link editor (link/unlink chapters), status toggle, actions (delete, duplicate)
2. **Chapter Links Section**: Shows all linked chapters with relevance tags and notes. Quick-add to link more chapters.
3. **Attributes Section**: Ordered list of attribute rows. Each row is collapsible.
4. **Footer**: Tags, timestamps, save/cancel

### 4.4 ChapterLinkEditor (within EntityDetailPanel)

**Purpose**: Manage the many-to-many relationship between a glossary entity and chapters. The entity is independent — this component lets users link/unlink it to chapters and annotate each link.

**Layout**: Sits between the header and attributes section. Shows linked chapters as editable rows, with a quick-add bar at the bottom.

```
┌─────────────────────────────────────────────────────────┐
│  Linked Chapters                            [+ Link]    │
│                                                         │
│  📖 Ch.1 — The Beginning       ★ major         ✕      │
│     Note: "Character first introduced"                  │
│  📖 Ch.3 — Trials of the Sect  ○ appears        ✕      │
│  📖 Ch.7 — The Tournament      ○ mentioned      ✕      │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ + Link to chapter... [Select chapter ▾]           │  │
│  │   Relevance: ◉ appears  ○ major  ○ mentioned      │  │
│  │   Note (optional): ___________       [Link]       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  💡 Tip: Adding evidence auto-suggests linking          │
│     to that evidence's chapter.                         │
└─────────────────────────────────────────────────────────┘
```

**Behavior**:
- **Link**: User selects a chapter from dropdown (filtered to exclude already-linked chapters), chooses relevance level, optionally adds a note. Clicking "Link" creates a `ChapterLink`.
- **Unlink**: Click ✕ on any linked chapter row. Confirmation required if there are evidences referencing that chapter.
- **Edit relevance/note**: Inline editing — click the relevance badge to cycle through options, click the note to edit.
- **Auto-suggest**: When user adds an Evidence that references a chapter not yet linked, show a toast: "This entity isn't linked to Ch.X yet. Link now?" with a one-click action.
- **Bulk link**: A "Link multiple…" option opens a chapter checklist for quickly linking several chapters at once.
- **Sort**: Linked chapters displayed in chapter order (by `chapterIndex`), not by link creation date.

### 4.5 AttributeRow (within EntityDetailPanel)

This is the most complex component. Each row represents one attribute and its value, translations, and evidences.

**Collapsed state**:
```
┌─────────────────────────────────────────────────────┐
│  ▶ Name (name)                        🇨🇳 zh        │
│    林默                               🌐 +3  📎 +2  │
└─────────────────────────────────────────────────────┘
```

**Expanded state**:
```
┌─────────────────────────────────────────────────────┐
│  ▼ Name (name)                     ≡ drag handle    │
│                                                     │
│  Original Language: [🇨🇳 Chinese (zh) ▾]            │
│  ┌───────────────────────────────────────────┐      │
│  │ 林默                                      │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  Translations                          [+ Add]      │
│  ┌─────────────────────────────────────────────┐    │
│  │ 🇬🇧 en │ Lin Mo           │ ✓ verified │ ✏ ✕ │    │
│  │ 🇯🇵 ja │ リン・モー        │ ○ draft    │ ✏ ✕ │    │
│  │ 🇰🇷 ko │ 린모             │ ○ draft    │ ✏ ✕ │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Evidences                             [+ Add]      │
│  ┌─────────────────────────────────────────────┐    │
│  │ 📍 Ch.1, Line 34                            │    │
│  │ "少年名叫林默，是云山派的外门弟子。"          │    │
│  │ 🌐 Translations: en, ja           ✏ ✕      │    │
│  ├─────────────────────────────────────────────┤    │
│  │ 📍 Ch.3, Paragraph 12                       │    │
│  │ Summary: MC formally introduced at the sect  │    │
│  │ 🌐 Translations: en               ✏ ✕      │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 4.6 AddTranslationPopover

**Triggered by**: clicking "+ Add" in any translation list.

```
┌──────────────────────────────────┐
│  Add Translation                 │
│                                  │
│  Language: [Select language ▾]   │
│  (only shows languages not yet   │
│   added to this value)           │
│                                  │
│  Translation:                    │
│  ┌────────────────────────────┐  │
│  │                            │  │
│  └────────────────────────────┘  │
│                                  │
│  Confidence: ○ Draft             │
│              ○ Machine           │
│              ○ Verified          │
│                                  │
│  Translator: ___________         │
│                                  │
│      [Cancel]   [Add]            │
└──────────────────────────────────┘
```

### 4.7 AddEvidenceModal

**Triggered by**: clicking "+ Add" in any evidence list.

```
┌──────────────────────────────────────────────────┐
│  Add Evidence                                    │
│                                                  │
│  Location                                        │
│  Chapter: [Select chapter ▾]                     │
│  Block / Line: [e.g. "Line 34", "Para 12" ]     │
│                                                  │
│  Type: ◉ Quote  ○ Summary  ○ Reference           │
│                                                  │
│  Original Language: [🇨🇳 zh ▾]                    │
│  ┌──────────────────────────────────────────┐    │
│  │ 少年名叫林默，是云山派的外门弟子。        │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  Note (optional):                                │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  Translations (optional, add after saving)       │
│                                                  │
│          [Cancel]          [Save Evidence]        │
└──────────────────────────────────────────────────┘
```

### 4.8 ManageAttributes Panel

**Purpose**: Let user configure which attributes appear for a given entity kind — add custom fields, reorder, toggle visibility, remove user-added fields.

```
┌──────────────────────────────────────────────────────────────┐
│  Manage Attributes — 👤 Character                            │
│                                                              │
│  Drag to reorder. Default attributes cannot be deleted       │
│  but can be hidden.                                          │
│                                                              │
│  ≡  ☑ name           Name              text      🔒 Default │
│  ≡  ☑ aliases        Aliases           tags      🔒 Default │
│  ≡  ☑ gender         Gender            select    🔒 Default │
│  ≡  ☐ age            Age               text      🔒 Default │
│  ≡  ☑ role           Role              select    🔒 Default │
│  ≡  ☑ blood_type     Blood Type        select    ✕ Custom   │
│  ≡  ☑ zodiac_sign    Zodiac Sign       select    ✕ Custom   │
│                                                              │
│  [+ Add Custom Attribute]                                    │
│                                                              │
│          [Reset to Defaults]        [Save Layout]            │
└──────────────────────────────────────────────────────────────┘
```

### 4.9 KindManager (Full CRUD)

**Purpose**: Let users view, create, edit, reorder, and delete entity kinds. Each kind has its own identity (icon, color, name, code) and a configurable attribute schema. Default kinds cannot be deleted but can be hidden; custom kinds are fully editable.

**Layout**: Full-width modal (or dedicated settings page) with a **two-panel layout**: kind list on the left, kind detail/editor on the right. This mirrors the entity list ↔ detail panel pattern from the main glossary view, giving users a consistent mental model.

#### 4.9.1 Kind List Panel (left side)

Shows all kinds in two groups: Default (system-provided) and Custom (user-created), separated by a visual divider. Each kind row is clickable to open its detail editor.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  ⚙ Manage Entity Kinds                                                    [✕ Close]│
│─────────────────────────────────────────────────────────────────────────────────────│
│                                    │                                               │
│  🔍 Search kinds…                  │  (Kind Detail — see 4.9.2)                    │
│                                    │                                               │
│  DEFAULT KINDS                     │                                               │
│  ┌──────────────────────────────┐  │                                               │
│  │ ≡ 👤 Character    12 attrs  │◀─│─── selected                                   │
│  │      34 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ 📍 Location      7 attrs  │  │                                               │
│  │      18 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ ⚔️ Item           8 attrs  │  │                                               │
│  │       9 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ ✨ Power System   8 attrs  │  │                                               │
│  │      22 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ 🏛 Organization   8 attrs  │  │                                               │
│  │       6 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ 📅 Event          7 attrs  │  │                                               │
│  │      11 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ 📖 Terminology    4 attrs  │  │                                               │
│  │      45 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ 🧬 Species        7 attrs  │  │                                               │
│  │       3 entities  ● active  │  │                                               │
│  └──────────────────────────────┘  │                                               │
│                                    │                                               │
│  CUSTOM KINDS                      │                                               │
│  ┌──────────────────────────────┐  │                                               │
│  │ ≡ 🎵 Music / Song   5 attrs  │  │                                               │
│  │       2 entities  ● active  │  │                                               │
│  ├──────────────────────────────┤  │                                               │
│  │ ≡ 🗺 Map Feature    3 attrs  │  │                                               │
│  │       7 entities  ○ hidden  │  │                                               │
│  └──────────────────────────────┘  │                                               │
│                                    │                                               │
│  [+ Add Custom Kind]               │                                               │
│                                    │                                               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Kind row elements**:
- **Drag handle** (≡): Reorder within its group (default kinds reorder among defaults; custom among customs). Default kinds always appear above custom kinds.
- **Icon**: The kind's emoji icon (editable on the detail panel).
- **Name**: Display name.
- **Attr count**: Number of active attributes.
- **Entity count**: How many glossary entities use this kind. Shown to help user understand impact of changes.
- **Status dot**: ● active / ○ hidden. Hidden kinds don't appear in the "New Entity" kind picker or the filter bar, but existing entities of that kind remain accessible.

**Kind row interactions**:
- Click → loads the kind in the detail panel on the right.
- Drag → reorder within group.
- The selected kind has a highlighted border (like entity card selection).

#### 4.9.2 Kind Detail Panel (right side)

When a kind is selected from the list, the right panel shows its full editable configuration. This has two sections: **Kind Identity** and **Attribute Schema**.

```
┌─────────────────────────────────────────────────────────────────┐
│  👤 Character                                  🔒 Default Kind  │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│  KIND IDENTITY                                                  │
│                                                                 │
│  Icon          [👤]  ← click to open emoji picker               │
│  Color         [■ #6366f1]  ← click to open color picker        │
│  Name          [Character          ]                            │
│  Code          [character          ]  ← auto-generated from     │
│                                        name, editable for       │
│                                        custom kinds only        │
│  Description   [People and beings in the story    ]             │
│  Status        ◉ Active  ○ Hidden                               │
│                                                                 │
│  ⚠ 34 entities use this kind. Changes to identity affect        │
│    all of them.                                                 │
│                                                                 │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│  ATTRIBUTE SCHEMA                                               │
│                                                                 │
│  Define which fields appear when creating or editing entities   │
│  of this kind. Drag to reorder. Default attributes can be       │
│  hidden but not deleted.                                        │
│                                                                 │
│  ≡  ☑ name         Name              text     ✱ req  🔒 Default│
│  ≡  ☑ aliases      Aliases           tags            🔒 Default│
│  ≡  ☑ gender       Gender            select          🔒 Default│
│  ≡  ☐ age          Age               text            🔒 Default│
│  ≡  ☑ role         Role              select          🔒 Default│
│  ≡  ☑ affiliation  Affiliation       text            🔒 Default│
│  ≡  ☐ cultivation  Power Level       text            🔒 Default│
│  ≡  ☑ appearance   Appearance        textarea        🔒 Default│
│  ≡  ☑ personality  Personality       textarea        🔒 Default│
│  ≡  ☐ relationships Relationships    textarea        🔒 Default│
│  ≡  ☑ description  Description       textarea        🔒 Default│
│  ──────────────────────────────────────────────────────────────  │
│  ≡  ☑ blood_type   Blood Type        select          ✏ ✕      │
│  ≡  ☑ zodiac       Zodiac Sign       select          ✏ ✕      │
│                                                                 │
│  [+ Add Custom Attribute]                                       │
│                                                                 │
│          [Reset to Defaults]              [Save Changes]        │
└─────────────────────────────────────────────────────────────────┘
```

**Kind Identity section — field rules**:

| Field | Default Kind | Custom Kind |
|---|---|---|
| Icon | Editable | Editable |
| Color | Editable | Editable |
| Name | Editable (display only, code stays) | Editable |
| Code | Read-only (system-defined) | Auto-generated from name on creation, editable before first save, read-only after entities exist |
| Description | Editable | Editable |
| Status | Active / Hidden (cannot delete) | Active / Hidden / **Delete** (only if 0 entities) |

**Attribute Schema section** — follows the same pattern as §4.8 ManageAttributes but is embedded directly in the kind detail panel:

Each attribute row shows:
- **Drag handle** (≡): Reorder via drag or keyboard (↑↓ buttons on focus).
- **Visibility checkbox** (☑/☐): Toggle whether this attribute is shown in the entity detail panel. Unchecked = hidden (data preserved, just not displayed).
- **Code**: Machine key (read-only for defaults, editable for custom).
- **Name**: Display label (always editable).
- **Field type**: text / textarea / select / number / date / tags / url / boolean. For default attributes, type is read-only. For custom, editable until entities have data in this field.
- **Required marker** (✱ req): Whether this attribute must have a value. Togglable for custom attributes; some defaults are locked as required (e.g., `name`).
- **Origin badge**: 🔒 Default (cannot delete, can hide) or ✏ ✕ Custom (can edit and delete).

#### 4.9.3 Add Custom Attribute (inline form)

Clicking **"+ Add Custom Attribute"** expands an inline form below the attribute list:

```
┌──────────────────────────────────────────────────────────────┐
│  New Attribute                                               │
│                                                              │
│  Code     [             ]  ← auto-slugified from name        │
│  Name     [             ]  ← display label                   │
│  Description [                                      ]        │
│                                                              │
│  Field Type   [▾ text       ]    Required  ☐                 │
│                                                              │
│  ┌─ If field type = "select" ──────────────────────────────┐ │
│  │  Options (one per line):                                │ │
│  │  ┌──────────────────────────────────────────────────┐   │ │
│  │  │ Option A                                         │   │ │
│  │  │ Option B                                         │   │ │
│  │  │ Option C                                         │   │ │
│  │  └──────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Translations (for the attribute name itself):               │
│  🌐 No translations yet  [+ Add]                            │
│                                                              │
│          [Cancel]                    [Add Attribute]          │
└──────────────────────────────────────────────────────────────┘
```

**Code auto-generation**: As the user types the Name, the Code field auto-fills with a slugified version (lowercase, underscores, no special chars). User can override before saving. Once saved with entities using it, the code becomes read-only.

**Field type determines input behavior**:
| Type | UI in entity editor | Notes |
|---|---|---|
| text | Single-line input | General purpose |
| textarea | Multi-line expandable | For descriptions, notes |
| select | Dropdown with predefined options | Options defined here |
| number | Number input with optional min/max | For ages, quantities |
| date | Date picker | For in-story or real dates |
| tags | Comma-separated tag input | Renders as badges |
| url | URL input with link preview | For references, images |
| boolean | Toggle switch | Yes/no fields |

#### 4.9.4 Add Custom Kind (creation flow)

Clicking **"+ Add Custom Kind"** at the bottom of the kind list opens the right panel with an empty kind creation form:

```
┌─────────────────────────────────────────────────────────────────┐
│  ✚ New Custom Kind                                              │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│  KIND IDENTITY                                                  │
│                                                                 │
│  Icon          [😀]  ← click to open emoji picker               │
│  Color         [■ #6366f1]  ← click to open color picker        │
│  Name          [                    ]  ← required               │
│  Code          [                    ]  ← auto-generated from    │
│                                         name, editable          │
│  Description   [                                        ]       │
│                                                                 │
│  ───────── Start from ─────────                                 │
│                                                                 │
│  ◉ Blank (no default attributes)                                │
│  ○ Clone from existing kind: [Select kind ▾]                    │
│                                                                 │
│  If "Clone" is selected, all attributes from the source kind    │
│  are copied as defaults for the new kind. User can then         │
│  modify, add, or remove them.                                   │
│                                                                 │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│  ATTRIBUTE SCHEMA                                               │
│                                                                 │
│  (empty — or cloned from source kind)                           │
│                                                                 │
│  The "name" attribute (text, required) is auto-added as the     │
│  first attribute. Every kind needs at least one identifier.     │
│                                                                 │
│  ≡  ☑ name         Name              text     ✱ req   🔒 Auto  │
│                                                                 │
│  [+ Add Custom Attribute]                                       │
│                                                                 │
│                                                                 │
│          [Cancel]                     [Create Kind]             │
└─────────────────────────────────────────────────────────────────┘
```

**Creation rules**:
- **Name** is required. Code auto-generates. Icon defaults to a generic emoji (😀) until user picks one.
- **"name" attribute is auto-added**: Every kind must have at least one identifier field. The system auto-creates a `name` attribute (text, required) that cannot be removed. User can rename its display label (e.g., "Term" for Terminology) but the code stays `name`.
- **Clone from existing**: Copies all attribute definitions (both default and custom) from the source kind. Cloned attributes become "default" for the new kind. User can then add, hide, reorder, or add more custom fields on top.
- **Blank start**: Only the auto-added `name` attribute. User builds the schema from scratch.

#### 4.9.5 Delete / Hide Kind

**Hiding** (available for all kinds):
- Sets the kind to "hidden" status. Hidden kinds don't appear in the "New Entity" kind picker or the filter bar.
- Existing entities of that kind remain intact and accessible. They show a subtle "hidden kind" indicator in the entity list.
- User can un-hide at any time.

**Deleting** (custom kinds only):
- Only available when 0 entities use this kind.
- If entities exist, the delete button is disabled with a tooltip: "Cannot delete: 5 entities use this kind. Reassign or delete them first."
- Alternatively, offer a **"Delete & Reassign"** flow: user picks another kind to reassign all entities to before deleting. Attributes that don't exist in the target kind are preserved as custom attributes on each entity.
- Confirmation dialog: "Delete 'Music / Song' kind? This cannot be undone."

```
┌──────────────────────────────────────────────────────┐
│  Delete Kind                                         │
│                                                      │
│  ⚠ "Music / Song" has 2 entities.                    │
│                                                      │
│  ○ Delete kind only (entities become "untyped")      │
│  ◉ Reassign entities to: [Select kind ▾]             │
│    Attributes that don't match the new kind will     │
│    be kept as custom attributes on each entity.      │
│                                                      │
│          [Cancel]         [Delete Kind]               │
└──────────────────────────────────────────────────────┘
```

---

## 5. Interaction Flows

### 5.1 Create New Entity

1. User clicks **"+ New Entity"** in toolbar.
2. Popover or modal asks: **Select Kind** (grid of kind icons).
3. EntityDetailPanel opens with empty attribute rows for that kind's defaults. The entity is created as a **book-level** object with zero chapter links.
4. User fills in original language, values, optionally adds translations and evidences.
5. User links to chapters via ChapterLinkEditor (optional — can be done later).
6. User clicks **Save**. Entity appears in the list.
7. If no chapters are linked, the card shows a "No chapters linked" warning to encourage linking later.

### 5.2 Edit Entity

1. User clicks entity card in the list.
2. EntityDetailPanel slides open with all current data.
3. User edits inline. Changes are auto-saved or saved on explicit "Save" click (configurable).
4. Panel closes via close button or clicking outside.

### 5.3 Link / Unlink Chapters

1. In the EntityDetailPanel, user sees the **Chapter Links** section showing all currently linked chapters.
2. To **link**: user clicks "+ Link", selects a chapter from the dropdown (already-linked chapters are excluded), sets relevance (`major` / `appears` / `mentioned`), adds an optional note, clicks "Link".
3. To **unlink**: user clicks ✕ on a linked chapter row. If evidences reference that chapter, a confirmation dialog warns: "This entity has 3 evidences in Ch.5. Unlinking won't delete them, but the chapter relationship will be removed."
4. To **bulk link**: user clicks "Link multiple…" to open a chapter checklist and link several at once with a default relevance.
5. **Auto-suggest on evidence add**: When the user adds an evidence citing Ch.X and the entity isn't linked to Ch.X, a toast appears: "Link to Ch.X? [Yes] [Dismiss]". Clicking "Yes" creates a `ChapterLink` with relevance `appears`.

### 5.4 Add Translation to an Attribute Value

1. Within an expanded AttributeRow, user clicks **"+ Add"** in the Translations section.
2. AddTranslationPopover appears.
3. User selects language (filtered to exclude already-added languages).
4. User types translated value, sets confidence level.
5. Clicks **Add**. Translation row appears inline.

### 5.5 Add Evidence

1. Within an expanded AttributeRow, user clicks **"+ Add"** in the Evidences section.
2. AddEvidenceModal opens.
3. User selects chapter, enters block/line reference.
4. User chooses type (quote/summary/reference) and enters text in the original language.
5. User saves. Evidence card appears. User can then add translations to the evidence via the same TranslationList sub-component.
6. **Auto-link check**: If the selected chapter is not yet linked to this entity, the system prompts: "Link this entity to Ch.X?" — streamlining the chapter-linking workflow.

### 5.6 Filter by Chapter

1. User opens Chapter Filter dropdown.
2. Options: **All** (default), **Unlinked**, or specific chapters (multi-select).
3. Selecting specific chapters shows entities where `chapterLinks` contains any of the selected chapter IDs.
4. Selecting **Unlinked** shows entities with `chapterLinks.length === 0` — useful for finding orphaned entries that need placement.
5. List updates immediately. Active chapter filters appear as removable chips.
6. Filters combine with AND logic across different filter types (chapters AND kind AND status).

### 5.7 Manage Kinds — Overview

1. User clicks **"⚙ Manage Kinds"** from the toolbar (or settings gear).
2. KindManager opens as a full modal with two panels: kind list (left) and kind detail (right).
3. Default kinds appear first, then custom kinds below a separator.
4. User clicks a kind to select it and view/edit its configuration in the right panel.

### 5.8 Create Custom Kind

1. User clicks **"+ Add Custom Kind"** at the bottom of the kind list.
2. The right panel switches to the **CreateKindPanel** with an empty form.
3. User fills in identity: name (required), icon (emoji picker), color (color picker). Code auto-generates from name as a slug.
4. User chooses **"Start from"**: Blank (only auto-added `name` attribute) or Clone from existing kind (copies all attribute definitions).
5. If cloning, the attribute schema section populates with the source kind's attributes. User can immediately modify, add, hide, or remove them.
6. User adds custom attributes as needed via the inline form.
7. User clicks **"Create Kind"**. The new kind appears in the Custom section of the kind list and becomes available in the "New Entity" kind picker.

### 5.9 Edit Kind Identity

1. User selects a kind from the list.
2. Kind detail panel loads with current identity and attribute schema.
3. User edits name, icon, color, description. For custom kinds, code is also editable if no entities use this kind yet.
4. If entities exist, an impact warning shows: "34 entities use this kind."
5. User clicks **"Save Changes"**. All entities of this kind reflect the updated icon, color, and name immediately.

### 5.10 Add Custom Attribute to a Kind

1. In the kind detail panel's Attribute Schema section, user clicks **"+ Add Custom Attribute"**.
2. An inline form expands below the attribute list.
3. User enters name (required) — code auto-generates as a slug. User can override code before saving.
4. User selects field type. If "select" is chosen, an options editor appears (one option per line).
5. User optionally toggles "required" and adds translations for the attribute name.
6. User clicks **"Add Attribute"**. The new attribute appears at the bottom of the attribute list with a "Custom" badge.
7. **Effect on existing entities**: Existing entities of this kind gain a new empty attribute value for this field. It appears in their detail panel the next time they're opened.

### 5.11 Edit / Reorder / Hide Attributes in a Kind

1. **Reorder**: User drags an attribute row via the handle (≡) or uses ↑↓ keyboard buttons. Order is saved and applies to all entity detail panels of this kind.
2. **Hide**: User unchecks the visibility checkbox (☑→☐) on an attribute row. The attribute is hidden from entity detail panels but data is preserved. User can re-show at any time.
3. **Edit custom attribute**: User clicks the edit (✏) icon on a custom attribute row. The row expands into an inline editor (same fields as the add form). User modifies and saves.
4. **Delete custom attribute**: User clicks ✕ on a custom attribute. If entities have data in this field, a confirmation dialog warns: "3 entities have values for this attribute. Deleting will remove their data." User confirms or cancels.
5. **Default attributes**: Cannot be deleted (🔒). Can be hidden, reordered, and have their display name edited. Code and field type are read-only.
6. User clicks **"Save Changes"** to persist all modifications. **"Reset to Defaults"** reverts the attribute schema to the kind's original default state (only affects order and visibility; does not delete custom attributes).

### 5.12 Hide / Delete Kind

**Hide a kind**:
1. In the kind detail panel, user sets Status to "Hidden".
2. The kind disappears from the "New Entity" kind picker and the filter bar.
3. Existing entities of this kind remain accessible and show a subtle "hidden kind" indicator.
4. User can un-hide at any time by setting status back to "Active".

**Delete a custom kind**:
1. User clicks **"Delete Kind"** in the kind detail footer (only available for custom kinds).
2. If 0 entities use this kind: confirmation dialog → kind is deleted.
3. If entities exist: the DeleteKindDialog opens with two options:
   - **"Delete kind only"**: Entities become "untyped" (their kind reference is cleared; they retain all attribute data and can be reassigned later).
   - **"Reassign entities to [kind]"**: User picks a target kind. Entities are moved to that kind. Attributes that exist in both kinds map automatically. Attributes unique to the deleted kind are preserved as custom attributes on each reassigned entity.
4. User confirms. Kind is removed from the list.

---

## 6. RAG Integration Notes

The glossary data structure is designed to be easily serializable for RAG pipelines.

### 6.1 Embedding Strategy

Each glossary entity should produce multiple embedding chunks:

```
Chunk 1 (Entity Summary):
"[Character] 林默 (Lin Mo): Male protagonist of the story.
 A young outer disciple of the Cloud Mountain Sect.
 First appears in Chapter 1."

Chunk 2 (Attribute Detail):
"Name: 林默 | Translations: Lin Mo (en), リン・モー (ja), 린모 (ko)"

Chunk 3 (Evidence):
"林默 — Ch.1 Line 34: 少年名叫林默，是云山派的外门弟子。
 (The young man was named Lin Mo, an outer disciple of the
  Cloud Mountain Sect.)"
```

### 6.2 Export Format

Provide a JSON export that RAG pipelines can ingest directly:

```json
{
  "glossary_version": "1.0",
  "book_id": "...",
  "entities": [
    {
      "id": "...",
      "kind": "character",
      "chapter_links": [
        { "chapter_id": "ch1", "relevance": "major" },
        { "chapter_id": "ch3", "relevance": "appears" },
        { "chapter_id": "ch7", "relevance": "mentioned" }
      ],
      "attributes": {
        "name": {
          "original": { "lang": "zh", "value": "林默" },
          "translations": [
            { "lang": "en", "value": "Lin Mo", "confidence": "verified" }
          ]
        }
      },
      "evidences": [
        {
          "attribute": "name",
          "location": { "chapter": "ch1", "block": "line 34" },
          "type": "quote",
          "original": { "lang": "zh", "text": "少年名叫林默..." },
          "translations": [
            { "lang": "en", "text": "The young man was named Lin Mo..." }
          ]
        }
      ],
      "tags": ["protagonist", "cultivator"],
      "status": "active"
    }
  ]
}
```

### 6.3 Retrieval Context Template

When a RAG query matches a glossary entity, inject this context:

```
--- GLOSSARY: {kind} ---
Name: {originalValue} ({translations joined by " / "})
Kind: {kind.name}
Chapters: {chapterLinks mapped to "Ch.N (relevance)" joined by ", "}
{for each active attribute with value:}
  {attribute.name}: {value} ({translations})
{for each evidence:}
  Evidence ({type}): {location} — "{text}"
---
```

### 6.4 Chapter-Scoped Retrieval

A major benefit of the independent-entity + chapter-link model is **chapter-aware RAG retrieval**. When a user is working on translating or reading a specific chapter, the system can:

1. **Pre-filter**: Only retrieve glossary entities linked to that chapter (via `chapterLinks`), reducing noise.
2. **Relevance-weighted**: Entities with `relevance: "major"` for the current chapter rank higher than `"mentioned"`.
3. **Cross-chapter context**: If the user is on Ch.7 and a character was introduced in Ch.1 (`relevance: "major"` on Ch.1, `"appears"` on Ch.7), the RAG context can include the Ch.1 introduction evidence alongside Ch.7-specific details.
4. **Unlinked detection**: Entities with zero chapter links can be flagged for review — they may be incomplete data or concepts that span the entire book and should be linked broadly.

---

## 7. Responsive Behavior

| Breakpoint | Layout |
|---|---|
| Desktop (≥1200px) | List on left (60%), detail panel on right (40%), side-by-side |
| Tablet (768–1199px) | Full-width list, detail panel as overlay (slide from right) |
| Mobile (<768px) | Full-width list, detail panel as full-screen modal. Filters collapse to a single "Filter" button opening a bottom sheet. |

---

## 8. Accessibility & UX Notes

- All drag-and-drop interactions (attribute reorder) must have keyboard alternatives (move up/down buttons).
- Language selectors should show both the language name and its native name (e.g., "Chinese — 中文").
- Evidence quotes should be visually distinct (left border, slightly muted background) to differentiate from user-authored summaries.
- Color-coded kind badges must also include an icon — do not rely on color alone.
- Translation confidence badges use both color and label: green "verified", amber "draft", gray "machine".
- All forms support keyboard navigation with Tab/Shift+Tab, Enter to submit.
- Entity status changes (active/inactive) should require confirmation if the entity has evidences linked from other entities.

---

## 9. Suggested Tech Stack

| Concern | Recommendation |
|---|---|
| State management | Zustand (lightweight, scales well) |
| Forms | React Hook Form + Zod validation |
| Drag & drop | @dnd-kit/core |
| UI primitives | Radix UI (unstyled) + Tailwind CSS |
| i18n for UI | react-i18next |
| Rich text (evidence quotes) | Tiptap (optional, for formatted quotes) |
| Search | Client-side: Fuse.js. Server-side: Meilisearch or Typesense |
| Icons | Lucide React |
| Storage | REST API or tRPC to your backend; local IndexedDB for offline draft |
