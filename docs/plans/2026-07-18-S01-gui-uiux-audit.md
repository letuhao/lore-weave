# S-01 `structure-templates` — GUI / UX / business-flow audit (as a user)

> **Perspective:** a novelist using the Writing Studio for the first time — not a developer who knows the code.
> **Target:** the shipped `StructureTemplatesPanel` (studio dock panel, category *storyBible*) + `useStructureTemplates`.
> **Method:** full read of the rendered component + hook + tests; layout claims derived from the actual Tailwind
> classes (layout is deterministic from them). **Live browser confirmation of the layout items was NOT possible
> this run — both browser MCPs were held by concurrent sessions; those items are marked `code-derived`.**
> Date: 2026-07-18.

---

## The business flow, walked as a user

1. Open the panel (palette). I see **Built-in (read-only)** structures + a **Mine** group that says
   *"None yet — clone a built-in to start."* → clear entry, no void. ✅
2. I select **Save the Cat** → its beats render read-only with a note *"Clone it to customise."* → tenancy is
   legible. ✅
3. I click **Clone to my structures** → I land on an editable copy named *"Save the Cat (copy)"*. ✅
4. I rename it, edit beat labels/purposes, **↑↓ reorder**, ✕ remove, **+ Add beat**, **Save**. ✅ (real authoring)
5. **Archive** → it leaves the list; tick **archived** → it reappears → **Restore**. ✅ (no dead-end soft-delete)
6. **…now I want to actually decompose my book against the structure I just built.** → **There is no button.
   The flow ends here.** ⛔ ← the terminal dead-end.
7. **…actually, I wanted to write a structure from scratch, not derived from Save the Cat.** → **There is no
   button for that either.** I have to clone a built-in and gut it. ⛔

So the panel is a **real, operable authoring tool — not a hollow shell** — but the *business* flow has a terminal
dead-end (can't use what you built) and a missing on-ramp (can't create blank).

---

## Findings

### A · Dead-ends / dead-loops
- **A1 — CRITICAL · "Use in decompose" is absent.** The sole purpose of a story structure is to decompose a
  book against it, yet the panel offers no way to do so — no button, no deep-link. You author a structure and
  hit a wall. (The panel's own header comment even lists "use-in-decompose" as intended.) *Home:* specced this
  run as **[S-13 / G-STORY-STRUCTURE](../specs/2026-07-17-studio-completeness-build/S-13_studio-decompose-surface.md)**
  — an M FE port. *Mitigation today:* the structure IS usable via the legacy chapter-editor planner, but nothing
  in this panel tells the user that or takes them there.

### B · Verb built at the backend, no button in the GUI
- **B1 — HIGH · Create-from-scratch is unreachable.** The only path to an own template is *clone a built-in*.
  The hook (`useStructureTemplates`) exposes **no `create`**; the panel has no "New structure" button — even
  though `compositionApi.createTemplate`, the `POST /templates` route, AND the
  `composition_structure_template_create` MCP tool all exist (the panel even *registers* that MCP tool for the
  agent). So an **agent** can create a blank structure but a **human** cannot. Classic "verb shipped, no button."
- **B2 — LOW · `kind` is shown but never editable.** `DetailHead` renders `<code>{kind}</code>`, but an own
  template has no input to change it — every clone is frozen at the built-in's kind (e.g. `save_the_cat`) or
  `generic`. Low impact (kind is display-only, deliberately not a closed-set arg), but it's a visible field you
  can't touch.

### C · Feedback & safety
- **C1 — MEDIUM · No unsaved-changes guard.** The editor is a local draft; selecting another row remounts it
  (`key={selected.id}`) and **silently discards** unsaved beat edits. A user can lose work by clicking away —
  no "unsaved changes" prompt.
- **C2 — MEDIUM · Save gives no success signal.** After Save the button returns from "Saving…" to "Save" with
  no toast/checkmark. The list refetches, but there's no confirmation the write landed — the user is left
  guessing.
- **C3 — MEDIUM · Errors are raw exception strings.** `saveError` renders `(error as Error).message` verbatim,
  so an OCC conflict surfaces as e.g. *"Request failed with status 412"* rather than *"Someone edited this
  structure — reload and reapply."* Technical leak, and it's the one case (concurrent edit) most likely to hit.
- **C4 — LOW · Archive has no confirm.** One click removes the template from the list. Mitigated (recoverable
  via Restore), but the sudden disappearance can startle.

### D · Layout / display *(code-derived — not live-confirmed this run)*
- **D1 — MEDIUM · The editor is crushed at narrow dock widths.** The panel body is a
  `grid-template-columns: 240px 1fr` with **no `min-width: 0`** on either column and **no `overflow-x`** on the
  detail. The beat-editor row is a flex line of a **fixed `w-28` (112px) key input** + a flex label + three
  `px-1` buttons (~60px). Below a panel width of ~**410px** (240 list + ~170 min editor) the detail can't fit a
  beat row, and because grid items default to `min-width:auto`, the track **overflows rather than clips** →
  horizontal spill / the whole panel scrolls sideways. Dock panels are routinely dragged narrow, so this is
  reachable in normal use.
- **D2 — LOW · Truncation not fully wired.** The list row name is `flex-1 truncate` but the button lacks
  `min-w-0`, so a long template name may not truncate and can shove the badge. The built-in read-only beat `<li>`
  label has no `truncate`, so a long label pushes the key column.
- **D3 — LOW · No way to reclaim editor width.** The 240px list can't be collapsed and there's no resizer
  between it and the editor, so on a medium-width dock the editor stays pinched with the list eating a third.

### E · i18n / consistency / a11y / touch
- **E1 — LOW · Hardcoded English bypasses i18n.** `placeholder="key"`, `title="up"`, `title="down"`,
  `title="remove"` are literal English — untranslated in all 17 locales (everything else in the panel routes
  through `t(...)`).
- **E2 — LOW · Icon-only controls, weak labels, small targets.** ↑ ↓ ✕ carry only `title` (no `aria-label`;
  weakly announced by AT, invisible on touch) and are ~20px tap targets — under the 44px touch guideline on a
  stated touch platform.
- **E3 — LOW · Wording drift.** The group header says *"Built-in (read-only)"* but the row/detail badge says
  *"system"* — a dev-ish term for a novelist, and two names for one concept.

### ✓ What's genuinely good (to be fair — and better than the S-02 sample)
- **No OS `prompt()`/`confirm()`** anywhere — inline rename input + auto-named clone. S-01 *avoids* the exact
  "raw OS box breaks the spell" defect the S-02 scorecard flagged.
- **Reorder HAS a button** (↑↓) and it persists — the verb the S-02 sample marked unreachable is reachable here.
- **Button-based reorder, not HTML5 drag** → touch-friendlier than S-02's drag-to-file.
- Empty-state hint, clone lands you on the fresh copy (immediate visible result), archived items recoverable,
  blank-name Save guard (disabled + title), OCC version sent, unique beat-key generation.

---

## 🎯 GUI Scorecard — S-01 `structure-templates`

| Metric | Score | Why |
|---|---|---|
| **Usability** (can I do the job?) | **6.0/10** | The author loop (clone → edit → reorder → save → archive/restore) genuinely works. But the *job's endpoint* — decomposing with your structure — has **no button** (A1), and you **can't create from scratch** (B1). You can author, not finish. |
| **Completeness** (CRUD coverage) | **6.5/10** | Create ⚠️ (clone-only; blank-create has route+API+MCP but **no button**) · Read ✅ · Update ✅ (name+beats+**reorder**) · Delete ✅ (archive) · Restore ✅ · **Use/decompose ❌**. Reorder *is* reachable (beats the S-02 sample); two verbs unreachable: blank-create + use-in-decompose. |
| **Ease of use / learnability** | **6.5/10** | Clone-to-start is guided and inline editing is obvious; but "how do I make a *new* one" and "how do I *use* it" are both undiscoverable because both are missing. |
| **Beauty / aesthetics** | **7.0/10** | Consistent tokens, badges, card beat-rows, styled read-only note; **no OS-dialog spell-break**. Docked by the pinched editor at narrow widths (D1) and tiny icon buttons. |
| **Consistency** | **6.5/10** | Matches studio panel styling well; dinged by "system" vs "Built-in" wording (E3), hardcoded English amid i18n (E1), and raw error strings vs the app's styled copy (C3). |
| **Accessibility / multi-device** | **5.5/10** | Buttons are in the a11y tree and the blank-name guard has a title; but icon-only title-only controls (E2), sub-44px tap targets, hardcoded English, and the narrow-dock editor overflow (D1) are hostile to AT + touch. |
| **Feedback & safety** *(added)* | **5.0/10** | No save-success signal (C2), raw error copy (C3), **no unsaved-draft guard → silent data loss** (C1), no archive confirm (C4). |
| **Robustness** | **7.5/10** | Blank-name guard, OCC version sent, clone auto-disambiguates the name, archive clears the selection, unique beat-key generation. Held back only by the silent-draft-loss path. |
| **🎯 Overall** | **≈ 6.3/10** | A real, operable authoring tool — **not a hollow shell** — and cleaner than the S-02 sample on dialogs, reorder, and touch. It ships with **one critical terminal dead-end** (can't use what you built — A1), **one unreachable create path** (B1), a **narrow-width layout crush** (D1), and **feedback/safety rough edges** (C1–C3). |

---

## Fix-now vs defer (recommendation)

- **Cheap, in-scope, fix-now:** C3 (map 412/blank errors to human copy) · E1 (route the 4 hardcoded strings
  through `t`) · E2 (`aria-label` on ↑↓✕) · B2 (a `kind` input) · D2 (`min-w-0` + truncate). Each is a one-file
  edit; per the repo's FIX-NOW-default they don't earn a defer row.
- **Small but design-touching:** C2 (success toast) · C1 (unsaved-changes guard) · C4 (archive confirm) · D1/D3
  (`min-w-0` on the detail column + a collapse/resizer) · B1 (a "New structure" button → `createTemplate`).
- **Already specced:** A1 → **S-13 / G-STORY-STRUCTURE** (the studio decompose surface + the "Use in decompose"
  deep-link). Closing A1 is the single biggest usability lift.

> **Full fix set specced 2026-07-18 →** [`../specs/2026-07-17-studio-completeness-build/S-01b_structure-templates-ux-hardening.md`](../specs/2026-07-17-studio-completeness-build/S-01b_structure-templates-ux-hardening.md)
> — every finding above mapped to a concrete FE fix + the scorecard metric it lifts, with a target of **≈6.3 → ≈8.4**.
> All verbs are already backend-supported (FE-only, M). A1's button is wired through S-13.
