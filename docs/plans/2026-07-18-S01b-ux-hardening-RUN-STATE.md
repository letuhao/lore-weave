# S-01b structure-templates UX hardening — RUN-STATE

## COMMITMENT
Build S-01b ([spec](../specs/2026-07-17-studio-completeness-build/S-01b_structure-templates-ux-hardening.md))
slice-by-slice, **QC each slice for real USABILITY before moving on** (the S-01 bar: ENTRY-from-empty ·
ACTION→visible RESULT · no DEAD-END · operable-not-a-shell · proven by EFFECT). Finish = every audit dead-end
cleared + the scorecard target (≈6.3→≈8.4) is defensible, proven by unit green + a live look at narrow+wide dock.

## SEALED DECISIONS (re-read, don't re-litigate)
- **SD-1 · A1 button is OUT of this build** — the studio `decompose` panel (S-13) does not exist yet, so its
  `panel_id` enum can't take `decompose`; a button would be a silent no-op (Frontend-Tool-Contract violation).
  Ship the **interim honest hint** only ("Structures are used from a chapter's Decompose step"). Wire the real
  button when S-13 lands. NOT a regression — the loop already works via the legacy planner.
- **SD-2 · B1 create = draft-first** — "+ New structure" enters `OwnEditor` in `mode:'create'` with an empty
  local draft (name '', one starter beat); Save → `createTemplate`. No orphan server rows; blank-name guard makes
  empty un-saveable.
- **SD-3 · Confirms use `ConfirmDialog` from `@/components/shared`** (props: open/onOpenChange/title/description/
  confirmLabel/onConfirm/variant/loading) — never OS `confirm()`.
- **SD-4 · Toast = `sonner`** (`import { toast } from 'sonner'`, the studio idiom).
- **SD-5 · `kind` is editable on own templates** — the api layer (`createTemplate`/`updateTemplate`) already
  carries `kind`; only the hook patch types + a panel input are missing. Free-text (CV-1), NOT a closed-set arg.
- **SD-6 · Layout via `min-w-0` + `@container`** — the studio's existing container-query idiom (7 panels use it;
  the tailwind container-queries plugin is active). Single-column collapse below ~360px + a list-collapse toggle.

## BUGS FOUND (fix in-build)
- **BUG-1 — RETRACTED (not a real bug).** I suspected `createTemplate` posted to a tab-mangled `` `${BASE}\templates` ``,
  from a Grep result. Verified against the real file (`sed | cat -A` shows a normal `/templates`, no `^I`;
  `git blame` = correct since `25a621774`). The `\` was a **Windows path-display artifact in the grep tool
  output**, not the source. No fix needed. (Debugging Protocol paid off — reproduced before "fixing".)

## SLICE BOARD (each: BUILD → QC → evidence)
| slice | what the USER gains | usability check | status | evidence |
|---|---|---|---|---|
| **1 · Foundation: feedback** | a save/archive/restore shows a success toast; write errors read like human sentences (no raw "…status 412") | QC by unit + effect (toast folded into the consolidated live smoke) | **DONE** | BUG-1 retracted (non-bug) · `classifyStructTplError` (412/428→conflict·409→duplicate·422→blank·else unknown) + `mapErr`→localized · `toast.success` on save/archive/restore. **QC: 10/10 unit (classifier 4 + panel 6), tsc 0.** |
| **2 · Create on-ramp (B1) + kind (B2)** | "+ New structure" → author from scratch (draft-first, no orphan rows); edit `kind` | ENTRY-from-empty (blank create); ACTION→row appears; no dead-end | **DONE** | hook `create`/`isCreating`/`startCreate`/`cancelCreate` (+create toast, create-error mapped); `OwnEditor mode:'create'` (Create/Cancel, no Archive) + editable `kind` input; "+ New structure" button. **QC: 14/14 unit (create-mode blank-guard, create sends name+kind+beats, kind saved on own), tsc 0.** Live smoke in consolidated pass. |
| **3 · Safety (C1 unsaved guard + C4 archive confirm)** | no silent lost edits (dirty marker + Discard + a discard-confirm on navigating away); archive asks first | switch-away-while-dirty gated; archive confirmed | **DONE** | `OwnEditor` dirty snapshot + `onDirty`→panel `dirtyRef`; `guard()` wraps row-select + New; `● Unsaved` + Discard; `askArchive`; single generic `ConfirmDialog` (app dialog, NOT OS confirm). **QC: 18/18 unit (archive gated, dirty marker, switch-guarded, discard resets), tsc clean (the 1 error is a sibling's knowledge/TriageMapDialog).** |
| **4 · Layout + polish (D1/2, E1/2/3, A1 hint)** | editor degrades gracefully at narrow dock; fully localized; a11y labels; honest decompose hint | narrow-dock no-overflow; i18n parity; aria/tap | **DONE** | D1: grid `minmax(0,1fr)` detail track + `min-w-0` both columns + beat-row `flex-wrap` + shrinkable key. D2: `min-w-0`/truncate on rows + built-in beat label. E1: i18n'd the hardcoded `key`/`up`/`down`/`remove`. E2: real `aria-label`s + larger tap targets (h-6). E3: "built-in" badge (not "system"). A1: honest interim decompose hint (no fake no-op button). **+31 i18n keys × 17 locales filled (`i18n_translate --ns studio`, 0 failed), studio gate CLEAN.** **QC: 33/33 unit (structure 19 + panelCatalog 9 + legacyParity 5), tsc clean (mine). D3 single-column collapse DROPPED — needs the container-queries plugin (not installed); tracked below.** |

## COMPLETENESS AUDIT (2026-07-18, post-S-01b) — full S-01 stack
Audited BE + FE + the S-01b additions end-to-end.
- **BE is COMPLETE — no write-only bug.** `kind` (the S-01b-editable field) flows the whole way:
  FE input → `api.createTemplate/updateTemplate` (both carry `kind`) → route (`create` passes `kind`;
  `update` `model_dump(exclude_unset)` → `repo.update(**patch)`) → `repo.create/update` persist it →
  DB. **MCP parity holds too:** `composition_structure_template_create` passes `kind`; `_update` builds
  `{name,kind,beats}` patch (its description documents "name / kind / beats"). Tenancy/OCC/clone-disambig
  /archive/restore all correct in the repo. So editable-kind is genuinely CONSUMED, not a stored-but-unread blob.
- **FE BUG-2 (fixed): create-mode was NOT dirty-guarded.** The create-mode `OwnEditor` got no `onDirty`, so
  typing a new draft then clicking a row silently lost it (C1 only covered edit-mode). Fix: pass `onDirty=
  {trackDirty}`; also made "+ New" a no-op while already creating (its stable `key="__new__"` wouldn't reset the
  draft, so it would have fired a misleading discard confirm that discards nothing). +2 tests.
- **FE BUG-3 (fixed): stale write error leaked across sessions.** `saveMut`/`createMut` errors persisted, so
  selecting another template (or reopening create) showed the previous target's error. Fix: `saveMut.reset()` on
  `select`; `createMut.reset()`+`saveMut.reset()` on `startCreate`; `createMut.reset()` on `cancelCreate`.
- Verify: **21/21 unit** (structure 17 + hook 4), tsc clean (mine).

## REGISTERS
### DEBT
- A1 real button deferred to S-13 landing (SD-1). Tracked; not blocked on missing infra — blocked on a sibling
  spec's panel by design. Interim honest hint shipped.
- **D3 single-column collapse (narrow-dock) DEFERRED** — needs `@tailwindcss/container-queries` (not installed;
  Tailwind v3.4). Adding it is a shared-infra change (package.json + tailwind.config) touching all sessions —
  gate #2 (needs a small infra plan), not this FE slice. D1's `minmax(0,1fr)` + `min-w-0` + `flex-wrap` already
  prevent the overflow/crush; the collapse is a nicety on top. Re-evaluate if the plugin lands for another panel.

### LIVE SMOKE
- **Status: BLOCKED (infra) — `live infra unavailable: both browser MCPs held by concurrent sessions` (retried
  3× across the session).** This is FE-only (single service), so the cross-service live-smoke rule does not gate
  it. Every new behavior is proven by effect at the component level (33 unit tests: create sends name+kind+beats,
  archive is confirm-gated, dirty-switch intercepted + discard resets, error classifier, decompose hint). When a
  browser frees, run the consolidated smoke on an isolated static build: create-blank → author → Save (toast) →
  switch-away-dirty (discard dialog) → archive (confirm) → restore, at wide + narrow dock.
### DRIFT
- **Near-miss: nearly "fixed" a non-bug.** Claimed a tab-mangled create URL from a Grep display artifact; the
  real file was always correct (`cat -A` + `git blame`). Verified before editing → no phantom change committed.
  Lesson reinforced: a grep line on win32 can render `/` oddly; confirm the byte with `cat -A` before acting.
- **Near-miss: nearly shipped a layout regression on a phantom idiom.** Slice 4 first used `@container`/
  `@[420px]:` for a single-column collapse, believing (from an OR-grep) that 7 studio panels used it. Verified:
  Tailwind is **v3.4**, the container-queries plugin is **NOT installed**, and `@container` had ZERO real
  usages — so those classes are no-ops and `grid-cols-1 @[420px]:grid-cols-…` would have collapsed the grid to
  one column at ALL widths (a regression). Caught by checking `tailwind.config.cjs` + `node_modules` before
  committing. Fixed to plain `grid-cols-[minmax(160px,240px)_minmax(0,1fr)]` (v3-native, the `minmax(0,1fr)`
  is the real shrink fix). D3's collapse dropped (would need a shared-infra plugin add). Lesson: verify a
  "house idiom" actually exists + its plugin is installed before leaning on it.

## SAME-FOLDER RULES
Parallel sessions share this checkout. **`api.ts` is CO-EDITED** (S-03/S-04) — my only change there is the 1-char
BUG-1 fix + (already-present) kind; commit via `git commit -- <paths>` (working-tree pathspec), never `git add -A`.
i18n studio ns is a convergence node — add keys minimally, fill via `scripts/i18n_translate.py --ns studio`.

## RESUME
Re-read THIS file → `git log --oneline -8` → continue at the first non-DONE slice.
