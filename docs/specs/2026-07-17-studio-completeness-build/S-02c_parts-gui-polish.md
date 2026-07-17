# S-02c · Manuscript parts — GUI polish (raise the scorecard)

> **Follow-up to S-02, driven by the live GUI audit** ([`S-02_GUI-AUDIT-2026-07-18.md`](S-02_GUI-AUDIT-2026-07-18.md)).
> The feature works, but the live scorecard flagged rough edges that pull it down: **Accessibility/touch 5,
> Beauty 6, Consistency 6.5**. This spec raises those without changing behavior — **pure FE, reusing
> primitives the app already has** (`sonner` toasts, the shared `ConfirmDialog`, inline-edit patterns).
> Sibling to S-02b (reachability); the two together bring S-02's GUI to a shippable finish.

## 1. Goal
Turn the operable-but-rough parts GUI into a polished, touch-safe, on-brand surface: correct terminology,
no jarring OS dialogs, affordances reachable on every device, and clear drag/drop feedback.

## 2. Current state (verified against the live app + code)
- **"arc" not "act":** footer shows *"1 arc · 4 ch"* for acts. `useManuscriptTree` sets
  `counts.arcs = partsMode ? parts.length : null`; the footer prints the `statArcs` "{{n}} arc" string.
- **Native dialogs:** create/rename/trash call `window.prompt` / `window.confirm` (seen live — grey OS box
  over the dark UI). Known pattern-debt: `ChapterBrowserTitleView.tsx:211` uses the same stopgap and notes
  "upgrading to the shared ConfirmDialog is a reasonable follow-up".
- **Hover-only affordances:** rename/trash use `opacity-0 group-hover/row:opacity-100` — no reveal on touch
  or keyboard focus.
- **No empty-act cue / no drag-over highlight:** an empty act is a bare header; nothing signals it's a drop
  target, and dragging a chapter over an act shows no target state.
- **Two "+"-like header buttons:** `FolderPlus` (New act) beside `Plus` (Plan) — both read "add".
- **Primitives available:** `sonner` `toast` (mounted in `App.tsx`), `ConfirmDialog`
  (`src/components/shared/ConfirmDialog.tsx`), Radix Dialog.

## 3. Design decisions (each maps to a finding + a scorecard metric)

### 3.1 Terminology: "act", never "arc" (finding #3 · Consistency)
In `partsMode`, count/label acts as **"act"** — a distinct `statActs` (`"{{n}} act"` / `"{{count}} acts"`)
rather than reusing `statArcs`. The `ACT` row tag already reads correctly; only the footer/count string is wrong.

### 3.2 Replace OS dialogs with in-app editing (finding #4 · Beauty + Consistency)
- **Create act → inline input row** at the top of the act list: an empty "New act…" field; Enter creates,
  Esc/blur cancels. No modal, no prompt.
- **Rename act → in-place inline edit:** the ✎ (or double-click on the title) turns the act title into an
  input seeded with the current name; Enter commits (`renameAct`), Esc reverts.
- **Trash act → instant + Undo toast** (coordinated with S-02b §4.2): drop `window.confirm` entirely; trash
  immediately and show a `sonner` toast *"Act trashed · Undo"*. Trash is reversible, so a blocking confirm is
  unnecessary and the toast is both the confirmation AND the recovery. (If a destructive-confirm feel is
  still wanted for a NON-empty act, use the shared `ConfirmDialog` — but the toast is preferred.)

### 3.3 Touch- + keyboard-reachable affordances (finding #5 · Accessibility)
Affordances (rename / trash / ↑↓ from S-02b) must be reachable without hover:
- reveal on **`focus-within`** (keyboard), not only `:hover`;
- **always visible on coarse pointers** via `@media (pointer: coarse)` (tablet/mobile — a stated platform);
- every button keeps an `aria-label` (already present) so AT users reach them regardless.

### 3.4 Empty-act drop cue + drag-over highlight (finding #6 · Ease-of-use + Beauty)
- An **empty act** renders a muted child hint row: *"Drop chapters here"* (dashed, non-interactive) so it
  reads as a target.
- While a chapter is dragging, the act header under the pointer gets a **drag-over ring/bg** (track a
  `dragOverPartId` state; clear on drop/leave) — the active-drop-target style from the HTML draft that the
  S-02 build omitted.

### 3.5 Disambiguate the two "+" buttons (finding #7 · Ease-of-use)
Make New-act unmistakably an **act** action: a compact **"＋ Act"** text-button (icon + short label) instead
of a bare `FolderPlus` beside the Plan `+`; keep tooltips. (Alternatively separate them with a divider +
distinct icon — the label is clearer.)

## 4. Frontend surface (files S-02 already owns; no registry edits)
- `useManuscriptTree.ts`: the `statActs` count in `partsMode`.
- `ManuscriptNavigator.tsx`: inline create/rename inputs, drop of `window.confirm` → toast, `focus-within` +
  `pointer: coarse` affordance visibility, empty-act hint, `dragOverPartId` highlight, the "＋ Act" button.
- Reuse `sonner` + `ConfirmDialog`; no new dependency. New strings use `defaultValue` (locale entries at
  convergence).

## 5. Tests (evidence gate)
- **Unit:** footer says "act(s)" in partsMode, never "arc". Inline create commits on Enter / cancels on Esc.
  Inline rename commits/reverts. Trash fires the toast (no `window.confirm` called — assert via a spy that
  `window.confirm` is untouched). `dragOverPartId` sets on dragover and clears on drop/leave.
- **A11y unit:** affordance buttons are in the a11y tree and reachable via focus (not hover-gated in JSDOM).
- **Live smoke (rebuilt stack, isolated port):** create via inline field, rename in place, trash → styled
  toast (no OS box), drag a chapter and see the target act highlight, verify on a **touch-emulated** viewport
  the rename/trash are visible without hover. Screenshot each; re-score the metrics.

## 6. Out of scope / by-design
- No behavior/data change — every fix is presentation/interaction only (the routes + semantics from S-02
  stand). Reorder + restore *wiring* is S-02b, not here (this spec only makes those affordances touch-reachable
  once they exist).
- No new design system components — reuse `sonner` / `ConfirmDialog` / inline inputs.

## 7. Expected scorecard delta (target)
Accessibility 5 → 8 (touch/keyboard) · Beauty 6 → 8 (no OS dialogs, drop cues) · Consistency 6.5 → 8
(act terminology, in-app dialogs) · Ease-of-use 7 → 8. With S-02b's reachability fixes, **Overall ~6.4 → ~8.3**.
