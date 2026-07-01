# Story 02 — Translation mode

> **Status:** ✅ decided · **Epic:** B · **Touches backend:** YES (small) ·
> **Evidence:** [`../00_INVESTIGATION.md` §6](../00_INVESTIGATION.md)

## PO recollection (accurate)
"We have a translation switch button but it's disabled — I can't switch to make a **manual**
translation, only call **LLM** translation."

## Current state (evidence)
- Editor toolbar has a one-off **LLM "Translate"** button (`handleTranslate` → `POST
  /v1/translation/translate-text`, replaces the doc; disabled only while running / no content,
  `ChapterEditorPage.tsx:880-891`) and a **"View translations"** button that **navigates away** to the
  separate `ChapterTranslationsPage` (`:897-905`). There is **no persistent translation mode** in the
  editor.
- `ChapterTranslationsPage` / `VersionSidebar` offer: language tabs, version list, **Re-translate
  (LLM)**, **Compare** — but **no "create manual translation" control** (`VersionSidebar.tsx`).
- Manual authoring exists ONLY as **edit an existing completed version** (`TranslationViewer` Pencil →
  `useEditTranslation` → save a human "gold" version; appears only when `status === 'completed'`).
- **The gap (backend):** both manual endpoints require an existing base version —
  `saveEditedVersion` needs `edited_from_version_id`; `patchBlock` seeds the human-version from
  `base_version_id` (`api.ts:191-229`). **No endpoint creates a human version seeded from the SOURCE
  alone.** ⇒ you must run the LLM first, then overwrite it. Pure-human translation from scratch is
  unreachable.

## Needs
- **B1–B3** — persistent in-editor Translate mode (coverage, version picker/activate, side-by-side,
  edit a block). **Pure FE** — extract `ChapterTranslationsPanel` from `ChapterTranslationsPage:133-209`.
- **B4 (new)** — **manual / human-first translation:** open a target language with no version and
  **write the translation by hand** (no LLM), saving as a human-authored version. **Needs a small
  translation-service addition** (create-version-seeded-from-source, or allow
  `saveEditedVersion`/`patchBlock` with a `null` base + `seed_from_source` flag, marked human_authored).

## Recommendation
Translate mode = the extracted panel, plus: when a language has **no version**, present a choice —
**"Translate with AI"** or **"Write it myself."** The manual path opens the **source side-by-side**,
seeds each target block from the source, and you overwrite block-by-block; Save creates the human
version (reusing `patchBlock` / `saveEditedVersion` once the BE can seed from source).

## Decisions locked (PO, 2026-06-30)

- **L1 — Persistent Translate mode (B1–B3).** Mount the extracted `ChapterTranslationsPanel` inside
  the editor under the Translate workmode; retire the one-off `handleTranslate` button + the
  navigate-away "View translations". Reuse `versionsApi`/`translationApi`/`VersionSidebar`/
  `TranslationViewer`/`SplitCompareView`/`TranslateModal`.
- **L2 — Manual / human-first translation (B4 = B-D1).** When a target language has no version, the
  manual path creates a human version **seeded from the source text**; the author overwrites each
  block side-by-side, Save → human-authored version. Requires a **small translation-service
  endpoint**: create/seed a human version from source (no LLM base) — extend the existing
  `patchBlock`/`saveEditedVersion` get-or-create to accept a `null` base + `seed_from_source`,
  marked `human_authored`.
- **L3 — AI stays a peer option (B-D2).** Entering a language with no version shows a choice —
  **"Translate with AI"** *or* **"Write it myself."** LLM is not the only door, but remains available.
- **L4 — Placement (B-D3).** Translate mode renders **center, side-by-side** (source | translation),
  using `SplitCompareView` as the base.

## Scope impact (locked)
- **M1 is no longer pure FE** — it now carries **one small BE task** (the seed-from-source endpoint in
  translation-service) in addition to the FE extract/mount. Still the recommended first-relief
  milestone. → reflected in [`../02_DESIGN.md`](../02_DESIGN.md).

## Open decisions
- [x] B-D1 → **L2 (seed from source).**
- [x] B-D2 → **L3 (AI peer option).**
- [x] B-D3 → **L4 (center side-by-side).**
