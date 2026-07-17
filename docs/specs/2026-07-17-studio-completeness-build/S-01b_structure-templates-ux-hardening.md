# S-01b · `structure-templates` UX hardening — clear every dead-end, lift the GUI score

> **Origin:** the S-01 GUI/UX audit ([`../../plans/2026-07-18-S01-gui-uiux-audit.md`](../../plans/2026-07-18-S01-gui-uiux-audit.md)),
> which scored the shipped panel **≈ 6.3/10** with one CRITICAL dead-end, one HIGH unreachable verb, and a band of
> feedback/layout/i18n rough edges. **Goal of this spec:** clear all dead-ends and raise every scorecard metric —
> without shipping empty shells (every fix is operable + proven by effect, per the S-01 usability bar).
> **Size:** M (FE-only; the backend already supports every verb — `create`/`update(kind)`/`clone`/`archive`/
> `restore` all exist). **No new backend, no migration, no HTML draft** (this hardens an existing panel).
> **A1 (the decompose exit) is owned by [S-13](S-13_studio-decompose-surface.md)** and only referenced here.

---

## 1. What "done" means (the target scorecard)

| Metric | Now | Target | The fixes that move it |
|---|---|---|---|
| Usability | 6.0 | **8.5** | B1 (create on-ramp) · A1→S-13 (decompose exit) · C1 (no lost work) |
| Completeness (CRUD) | 6.5 | **9.0** | B1 (blank-create button) · A1→S-13 (use verb) · B2 (kind editable) |
| Ease of use | 6.5 | **8.0** | B1 discoverability · C2 success signal · E3 wording |
| Beauty | 7.0 | **8.5** | D1 (no crushed editor) · E2 (proper controls) |
| Consistency | 6.5 | **8.5** | C3 (styled error copy) · E1 (i18n) · E3 (one-name-one-concept) |
| Accessibility / multi-device | 5.5 | **8.0** | E2 (aria + tap targets) · D1 (`@container` responsive) · E1 |
| Feedback & safety | 5.0 | **8.5** | C1 unsaved guard · C2 success toast · C3 error copy · C4 archive confirm |
| Robustness | 7.5 | **8.5** | C1 (kills the silent-draft-loss path) |
| **Overall** | **≈6.3** | **≈8.4** | — |

The spec is DONE when a live browser smoke shows: create-blank → author → save (toast) → **use in decompose**
(via S-13) → archive (confirm) → restore, with no dead-end and no lost work, at both a wide and a **narrow** dock.

---

## 2. The dead-ends (must both be cleared)

### A1 — the decompose EXIT (owned by S-13, wired here)
The panel's whole purpose is decompose; today there is no way out to it. **S-13** builds the studio `decompose`
panel; **this spec adds the button** once that panel exists: on an own (or built-in) template, a
`data-testid="structtpl-use-in-decompose"` button → `openPanel('decompose', { params: { templateId } })`. Ordering:
S-13 lands the panel + enum, S-01b adds the button. **Interim (ship now, before S-13):** a one-line, honest hint
under the editor — *"Structures are used from a chapter's Decompose step"* — so a user isn't left thinking the
feature is broken. No fake button that no-ops (Frontend-Tool-Contract: never a silent no-op).

### B1 — the create ON-RAMP (owned fully here)
**Problem:** the only path to an own template is *clone a built-in*; the hook exposes no `create`, so a human
can't author from scratch though `createTemplate` + `POST /templates` + the `..._create` MCP tool all exist
(agent-only today). **Fix — draft-first create (no orphan rows):**
- Add a **"+ New structure"** button at the top of the *Mine* group (`data-testid="structtpl-new"`).
- It enters the editor in **create-mode**: a synthetic local draft `{ name:'', kind:'generic', beats:[one
  starter beat] }`, no id/version. Save routes to `createTemplate` (not `updateTemplate`); on success the hook
  selects the returned row (same "land on the fresh result" pattern clone uses). The blank-name guard already
  present makes create-mode's empty name un-saveable — so no untitled server rows are ever created.
- Hook gains `create(patch) → createTemplate` and a `draft` selection sentinel; `OwnEditor` takes an optional
  `mode: 'edit' | 'create'` deciding which mutation Save calls.

---

## 3. Feedback & safety layer (C1–C4)

- **C1 — unsaved-changes guard.** `OwnEditor` computes `dirty` (draft name/beats ≠ `tpl`). Show a `● Unsaved`
  marker by Save + a **Discard** button (resets the draft). The panel routes row-selection through a guard: if
  the editor is dirty, an in-app **AlertDialog** ("Discard unsaved changes to '<name>'?") gates the switch —
  never the OS `confirm`. Kills the silent-draft-loss path (Robustness + Feedback).
- **C2 — save success signal.** On `saveMut`/`createMut` success, `toast.success(t('structTpl.saved'))` (sonner,
  the studio's toast). Optional transient inline "Saved ✓". The user learns the write landed.
- **C3 — human error copy.** Add a `structTplError(err)` mapper (mirrors `asPlannerError`): 412/428 → *"This
  structure changed elsewhere — reload and reapply."*; 409 → *"A structure named '<name>' already exists."*;
  422 → *"Name can't be empty."*; else a generic line. `saveError`/`createError` render the mapped copy, never
  the raw `Error.message`.
- **C4 — archive confirm.** The Archive button opens an in-app **AlertDialog** ("Archive '<name>'? You can
  restore it later.") before archiving. Low-stakes (recoverable) but removes the startling silent vanish.

## 4. Layout / responsive (D1–D3) — the narrow-dock crush

- **D1 — stop the overflow.** Add `min-w-0` to **both** grid columns (grid items default `min-width:auto`, which
  is what lets the detail overflow instead of shrinking). Give the beat-editor `<ol>` an `overflow-x-auto`
  fallback. Make the beat-row key input shrinkable (`w-24 min-w-0`) and let the row `flex-wrap` so key+controls
  wrap above the label when pinched.
- **D3 — reclaim width + go single-column when tiny.** Adopt the studio's existing **`@container`** idiom (used
  in 7 panels): set `container-type: inline-size` on the panel body; below a threshold (~360px) collapse the grid
  to **one column** (list over detail) and expose a **collapse-list** toggle so the editor can take the full
  width. No dockview resize hacks needed — it's pure CSS container queries.
- **D2 — truncation.** Add `min-w-0` to the list `Row` button (so the `flex-1 truncate` name actually
  truncates), and `truncate` to the built-in read-only beat label.

## 5. i18n · a11y · consistency (E1–E3, B2)

- **E1 — i18n the hardcoded strings.** Replace `placeholder="key"`, `title="up|down|remove"` with `t(...)` keys
  (`structTpl.beatKey`, `.moveUp`, `.moveDown`, `.removeBeat`); add to the `studio` ns and fill 17 locales via
  `scripts/i18n_translate.py --ns studio` (ML-7 gate).
- **E2 — a11y + touch targets.** Give ↑ ↓ ✕ real `aria-label`s (not `title`-only) and the key/label inputs
  `aria-label`s; bump the icon buttons to ≥ `h-8 min-w-8` (toward the 44px touch target on the stated touch
  platform); ensure visible focus rings.
- **E3 — one name for one concept.** The list/detail badge for built-ins reads **"built-in"** (matching the
  group header "Built-in (read-only)"), not "system". Localize the badge labels.
- **B2 — editable `kind`.** `StructureTemplateUpdate` already accepts `kind` (verified `canon.py:267`); add a
  small free-text `kind` input to `OwnEditor`'s head and include `kind` in the FE `save` patch type + the
  create patch. Free-text (CV-1), **not** registered in `CLOSED_SET_ARGS`.

---

## 6. Scope / sizing / ordering

- **FE-only.** The hook gains `create` + `kind` in the patch type; `api.ts` `updateTemplate`/`createTemplate`
  already exist (createTemplate is present; confirm it sends `kind`). No route/migration/MCP change.
- **Convergence-node touch:** only i18n (studio ns) — a shared file; register keys minimally, one atomic
  pathspec commit, no `git add -A` (concurrent sessions). No `catalog.ts`/enum/contract change (the panel is
  already registered; A1's button waits on S-13's enum).
- **Order:** ship §3–§5 (feedback, layout, i18n, B1 create, B2 kind) independently of S-13; add the A1 button in
  the same PR as S-13 or a fast follow. B1 + C1 + D1 are the biggest score-movers — do them first.

## 7. Tests (evidence gate)

- **panel unit** (extend `StructureTemplatesPanel.test.tsx`): "+ New structure" enters create-mode (empty draft,
  Save disabled on blank name, Save calls `create` not `update`); a dirty editor + row-switch opens the discard
  AlertDialog and only switches on confirm; save success fires `toast.success`; a mapped 412 renders the human
  string (not the raw message); the built-in badge reads "built-in"; `kind` input round-trips into the save patch.
- **layout** (`@container` unit or a jsdom width assertion): at a narrow container the grid is single-column and
  the beat-row wraps (no horizontal overflow); `min-w-0` present on both columns.
- **hook unit** (`useStructureTemplates`): `create` calls `createTemplate` and selects the returned id; error
  mapper covers 412/409/422/fallback.
- **i18n**: no hardcoded English remains in the panel (a grep-guard test or the ML-7 parity gate); 17-locale keys
  present.
- **live browser smoke** (isolated static build, own port — HMR-free): create-blank → author → **Save (toast
  appears)** → try to switch away dirty (**discard dialog**) → archive (**confirm dialog**) → restore → **at a
  narrow dock width the editor is fully usable (no clipped inputs)**. This is the finish-line proof; the target
  scorecard is re-scored against it.

## 8. Out of scope / by-design
- The decompose **panel** itself (S-13). This spec only wires the button into it.
- No sharing/book-shared tier (S-01 §10). No change to `beats` semantics or the decompose engine.
- Built-ins stay read-only (System tier; User-Boundaries law) — create/kind/edit apply to own templates only.
