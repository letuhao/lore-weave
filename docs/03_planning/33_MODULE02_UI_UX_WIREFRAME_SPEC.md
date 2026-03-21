# LoreWeave Module 02 UI/UX Wireframe Specification

## Document Metadata

- Document ID: LW-M02-33
- Version: 1.4.0
- Status: Approved
- Owner: Product Manager
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Wireframes for book tabs, **`original_language`**, **recycle bin**, **chapter editor**, **revision history**, raw vs draft.

## Change History

| Version | Date       | Change                                                         | Author    |
| ------- | ---------- | -------------------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial M02 wireframes                                         | Assistant |
| 1.1.0   | 2026-03-21 | Book tabs, chapter list/upload, cover, AI-disabled placeholder | Assistant |
| 1.2.0   | 2026-03-21 | Editor + History blocks; **`original_language`** on forms/list | Assistant |
| 1.3.0   | 2026-03-21 | Chapters tab: optional **filter by language** (backed by list query `original_language`) | Assistant |
| 1.4.0   | 2026-03-21 | **Recycle bin** screen; two-step delete copy; **Restore** / **Delete permanently** | Assistant |

## 1) Design Principles

- Clear distinction: **“Original file”** download vs **“Working draft”** in editor.
- Upload feedback + quota errors; revision list scannable (time, message, author).

## 2) Screen Blocks

### My books

- List: title, **`original_language`**, chapter count, cover thumb optional; nav link **Recycle bin**.

### Recycle bin

- Table of **trashed** books (`trashed_at`); actions **Restore**, **Delete permanently** (second confirm explains data kept until system cleanup / GC).
- Drill-in trashed book: chapter list (all **trashed** with book); per-chapter **Restore** / **Delete permanently** if product allows chapter-only trash while book active.

### Create book

- Title, description, **`original_language`** (BCP-47 input or select), summary.

### Book detail (owner)

- **Summary tab:** same as create.
- **Chapters tab:** table with **Lang** column; optional **“Show language”** filter (all / one BCP-47 tag); actions **Edit**, **Original ↓**, **Move to trash**, reorder. Destructive labels must not imply **instant** physical wipe.
- **Add chapter:** file drop + **required language** + optional title.

### Chapter editor

- Full-width **textarea** (plain MVP); top bar: **Save**, optional **Commit message** field; indicator “Saved at …”.
- Side panel or sub-tab **History:** chronological revisions; click → read-only diff view (MVP: two text blocks or simple “before/after” later); **Restore** button with confirm.

### Future AI assist

- Ghosted: Generate summary/cover/**translate** — “Coming later”.

### Sharing / catalog / unlisted / public detail

- Show **`original_language`** where API provides it.

## 3) Accessibility

- Label **original language** selects; editor has accessible name; restore confirm in `Dialog`.

## 4) References

- `20_MODULE01_UI_UX_WIREFRAME_SPEC.md`
- `32_MODULE02_FRONTEND_DETAILED_DESIGN.md`
