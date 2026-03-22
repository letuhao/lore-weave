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
  icon: string;              // emoji or icon identifier
  color: string;             // tag/badge color
  defaultAttributes: AttributeDefinition[];
  isDefault: boolean;        // system-provided vs user-created
  sortOrder: number;
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
├── <KindManagerModal>                     ← CRUD for entity kinds
│   ├── <KindList>
│   │   └── <KindRow>[]
│   │       ├── <IconPicker>
│   │       ├── <ColorPicker>
│   │       ├── <NameEditor>
│   │       └── <DefaultAttributeEditor>
│   └── <AddKindButton>
└── <AttributeSchemaEditor>                ← manage attribute definitions per kind
    ├── <AttributeDefinitionRow>[]
    │   ├── <CodeInput>
    │   ├── <NameInput>
    │   ├── <DescriptionInput>
    │   ├── <FieldTypePicker>
    │   ├── <RequiredToggle>
    │   ├── <ActiveToggle>
    │   └── <DragHandle>                   ← reorder
    └── <AddAttributeDefinitionButton>
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
│   sortField: string
│   sortDirection: "asc" | "desc"
│ }
└── actions: {
    createEntity, updateEntity, deleteEntity,
    addAttribute, removeAttribute, reorderAttributes,
    setAttributeValue, addTranslation, removeTranslation,
    addEvidence, updateEvidence, removeEvidence,
    linkChapter, unlinkChapter, updateChapterLink,
    toggleEntityStatus, updateFilters, ...
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

### 4.9 KindManagerModal

**Purpose**: CRUD for entity kinds themselves.

```
┌────────────────────────────────────────────────────────────┐
│  Manage Entity Kinds                                       │
│                                                            │
│  👤  Character        12 attrs   34 entities   🔒 Default  │
│  📍  Location          7 attrs   18 entities   🔒 Default  │
│  ⚔️  Item              8 attrs    9 entities   🔒 Default  │
│  ✨  Power System      8 attrs   22 entities   🔒 Default  │
│  🏛  Organization      8 attrs    6 entities   🔒 Default  │
│  📅  Event             7 attrs   11 entities   🔒 Default  │
│  📖  Terminology       4 attrs   45 entities   🔒 Default  │
│  🧬  Species           7 attrs    3 entities   🔒 Default  │
│  ─────────────────────────────────────────────────────────  │
│  🎵  Music / Song      5 attrs    2 entities   ✕ Custom    │
│  🗺  Map Feature       3 attrs    7 entities   ✕ Custom    │
│                                                            │
│  [+ Add Custom Kind]                                       │
└────────────────────────────────────────────────────────────┘
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

### 5.7 Manage Attributes for a Kind

1. User opens KindManagerModal → clicks a kind → clicks "Edit Attributes".
2. AttributeSchemaEditor opens.
3. User can drag-reorder attributes, toggle active/inactive, add new custom attributes (with code, name, description, field type), or remove custom ones.
4. Changes apply to all future entities of that kind. Existing entities retain their data but hidden attributes won't display in the detail panel.

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
