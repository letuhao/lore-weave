# LoreWeave Module 05 UI/UX Wireframe Specification

## Document Metadata

- Document ID: LW-M05-84
- Version: 0.1.0
- Status: Draft
- Owner: Product Manager + Frontend Lead
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Low-fidelity wireframe and UI state behavior specification for Module 05 glossary page, entity detail panel, and associated modals.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 wireframe spec          | Assistant |

---

## 1) `/books/:bookId/glossary` — Glossary Page (desktop)

### 1.1 Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ AppNav                                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ [← Back to Book]  [Book Title]  [Chapters] [Glossary] [Translation]     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Glossary                                           [+ New Entity]      │
│                                                                         │
│  ┌── Filters ────────────────────────────────────────────────────────┐  │
│  │ 📖 Chapter: [All ▾]  🏷 Kind: [All ▾]  ◉All ○Active ○Draft      │  │
│  │ 🔍 Search glossary...                   🏷 Tags: [+]             │  │
│  │ ── Active filters ─────────────────────────────────────────────  │  │
│  │ Ch.1 ✕  Character ✕           Showing 47 entities  ⚠ 3 unlinked │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌── Entity Card ────────────────────────────────────────────────────┐  │
│  │▌  林默 (Lin Mo)                                       ● Active   │  │
│  │▌  👤 Character    📖 Ch.1  Ch.3  Ch.7  +2 more                   │  │
│  │▌  🌐 4 translations  📎 2 evidences  🏷 protagonist              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │▌  云山派 (Cloud Mountain Sect)                       ● Active     │  │
│  │▌  🏛 Organization  📖 Ch.1  Ch.3                                  │  │
│  │▌  🌐 1 translation  📎 0 evidences  🏷 sect  ally                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │▌  气 (Qi)                                             ○ Draft     │  │
│  │▌  📖 Terminology  📖 No chapters linked ⚠                        │  │
│  │▌  🌐 1 translation  📎 0 evidences                               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  [Load more]                                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Page States

| State | Visual |
| --- | --- |
| Initial loading | Skeleton cards (3–4 placeholder rows) |
| Empty (no entities) | Empty state illustration + "No entities yet. Add your first." + `+ New Entity` button |
| Empty (filtered, no results) | "No entities match your filters." + "Clear filters" link |
| Unlinked warning | Warning chip "N unlinked entities" in filter bar stat line (clickable → applies `chapterIds=unlinked` filter) |
| Load more in progress | Spinner below last card |

---

## 2) Create Entity Modal

```
┌─────────────────────────────────────────────────────┐
│  ✚ New Glossary Entity                       [✕]    │
│                                                     │
│  Select entity kind:                                │
│                                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────┐ │
│  │    👤   │  │    📍   │  │    ⚔️   │  │   ✨  │ │
│  │Character│  │Location │  │  Item   │  │ Power │ │
│  └─────────┘  └─────────┘  └─────────┘  └───────┘ │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────┐ │
│  │    🏛   │  │    📅   │  │    📖   │  │   🧬  │ │
│  │  Org.   │  │  Event  │  │  Term.  │  │Species│ │
│  └─────────┘  └─────────┘  └─────────┘  └───────┘ │
│                                                     │
│           [Cancel]         [Create]                 │
└─────────────────────────────────────────────────────┘
```

States:
- Default: all 8 kind tiles shown. No kind selected (Create button disabled).
- Hover kind tile: highlighted border.
- Selected: tile has colored border + checkmark.
- Creating: Create button shows spinner, disabled.

---

## 3) Entity Detail Panel (slide-over, ~600px wide)

```
┌─────────────────────────────────────────────────────────┐
│  👤 Character                       ○ Draft    [⋯] [✕]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CHAPTER LINKS                              [+ Link]    │
│  ┌─────────────────────────────────────────────────┐    │
│  │  📖 Chapter 1 — The Beginning   ★ major    [✕]  │    │
│  │     Note: "Character first introduced"           │    │
│  │  📖 Chapter 3 — Trials of the Sect  ○ appears [✕]│    │
│  │  📖 Chapter 7 — The Tournament  ○ mentioned  [✕] │    │
│  └─────────────────────────────────────────────────┘    │
│  ── Link to chapter ──────────────────────────────────  │
│  [Select chapter...  ▾]  Relevance: ◉appears ○major ○mentioned │
│  Note: [optional]                           [Link]      │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ATTRIBUTES                                             │
│                                                         │
│  ▼ Name (name)  *required              🇨🇳 zh           │
│     ┌────────────────────────────────────────────┐     │
│     │ 林默                                       │     │
│     └────────────────────────────────────────────┘     │
│     Translations                          [+ Add]      │
│     🇬🇧 Lin Mo               ✓ verified   [✏] [✕]      │
│     🇯🇵 リン・モー             ○ draft     [✏] [✕]      │
│     Evidences                             [+ Add]      │
│     📍 Ch.1, Line 34                                   │
│       "少年名叫林默..." → 🌐 en           [✏] [✕]      │
│                                                         │
│  ▶ Aliases (aliases)                   🌐 0  📎 0      │
│                                                         │
│  ▶ Gender (gender)         Male        🌐 0  📎 0      │
│                                                         │
│  ▶ Role (role)             Protagonist  🌐 0  📎 0     │
│                                                         │
│  ▶ Affiliation (affiliation)   云山派   🌐 1  📎 0     │
│                                                         │
│  ▶ Appearance (appearance)              🌐 0  📎 0     │
│  ▶ Personality (personality)            🌐 0  📎 0     │
│  ▶ Description (description)            🌐 0  📎 0     │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Tags: [protagonist ✕] [cultivator ✕]  [+ add tag]     │
│  Created: 2025-01-10   Updated: 2025-01-20              │
│                                                  [Save] │
└─────────────────────────────────────────────────────────┘
```

### Detail Panel States

| State | Visual |
| --- | --- |
| Loading | Skeleton sections for attributes |
| View mode | All fields non-editable, click to edit |
| Field editing | Input highlighted, blur auto-saves with subtle spinner |
| Auto-save success | Brief green flash on the saved field |
| Save error | Inline red message below field |
| Delete confirm | Destructive alert dialog overlay |
| Status toggle | Badge cycles: Draft → Active → Inactive → Draft |

---

## 4) Add Translation Modal

```
┌──────────────────────────────────────────┐
│  Add Translation                  [✕]    │
│                                          │
│  Attribute: Name (name)                  │
│  Original: 🇨🇳 林默                      │
│                                          │
│  Language                                │
│  [Select language...            ▾]       │
│  (only shows languages not yet added)    │
│                                          │
│  Translation                             │
│  ┌──────────────────────────────────┐    │
│  │                                  │    │
│  └──────────────────────────────────┘    │
│                                          │
│  Confidence                              │
│  ◉ Draft  ○ Machine  ○ Verified          │
│                                          │
│  Translator (optional)                   │
│  [                    ]                  │
│                                          │
│     [Cancel]         [Add Translation]   │
└──────────────────────────────────────────┘
```

States:
- Language not selected: Add button disabled.
- Value empty: Add button disabled.
- Adding: spinner, button disabled.
- `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE`: inline error "A translation in this language already exists."

---

## 5) Add Evidence Modal

```
┌────────────────────────────────────────────────────┐
│  Add Evidence                               [✕]    │
│                                                    │
│  Attribute: Name (name)                            │
│                                                    │
│  Location                                          │
│  Chapter:  [Select chapter...              ▾]      │
│  Block / Line:  [e.g. "Line 34", "Para 12"]        │
│                                                    │
│  Evidence type                                     │
│  ◉ Quote   ○ Summary   ○ Reference                 │
│                                                    │
│  Original Language:  [🇨🇳 Chinese (zh) ▾]          │
│                                                    │
│  Text                                              │
│  ┌──────────────────────────────────────────────┐  │
│  │ 少年名叫林默，是云山派的外门弟子。           │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  Note (optional)                                   │
│  [                                        ]        │
│                                                    │
│         [Cancel]           [Save Evidence]         │
└────────────────────────────────────────────────────┘
```

**Auto-link toast** (shown after save if chapter not yet linked):
```
┌──────────────────────────────────────────────────────────┐
│  ℹ Chapter 1 is not linked to this entity.  [Link now]   │
└──────────────────────────────────────────────────────────┘
```

---

## 6) Responsive Behavior

| Breakpoint | Behavior |
| --- | --- |
| Desktop (≥1024px) | Entity list fills page; detail panel slides over from right (~600px overlay) |
| Tablet (768–1023px) | Same as desktop but detail panel takes 60% of width |
| Mobile (<768px) | Entity list full-width; detail panel opens as full-screen modal; filter bar collapses to "Filters" button opening a bottom sheet |

---

## 7) Design System Integration

- All components use shadcn/ui: `Card`, `Button`, `Input`, `Textarea`, `Select`, `Dialog`, `Sheet`, `Badge`, `Skeleton`, `Alert`.
- Kind color bars and kind badges use inline `style={{ borderColor: kind.color, color: kind.color }}`.
- Status badges: `active` → green, `draft` → amber, `inactive` → gray (using Tailwind classes).
- Confidence badges: `verified` → green dot, `draft` → amber dot, `machine` → gray dot.
- Entity card left color bar: 3px solid border-left using `kind.color`.
