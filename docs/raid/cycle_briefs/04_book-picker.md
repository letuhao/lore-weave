# Cycle 4: Book picker (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
Replace the raw-UUID `book_id` text field in `ProjectFormModal` (and the campaign-setup step) with a reusable **`BookPicker`** that searches the user's books by title via `booksApi.listBooks` and stores the selected `book_id`. No user should ever paste a UUID to create a knowledge project or a campaign — they pick a book by name; an empty selection stays valid (book is optional).
- **Scope:** FE-only. A reusable picker component + two call-site swaps.
- **Acceptance gate:** `scripts/raid/verify-cycle-4.sh` exits 0 (this cycle's runner creates that script).
- **Top 3 LOCKED decisions consumed:** G6 (book-workspace IA — book is the workspace anchor; pick it by identity, not UUID), Scope-LOCKED (creation-unblock — remove the raw-UUID friction wall), G4 (Playwright screenshot smoke).
- **DPS count:** 2
- **Estimated wall time:** ~2 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist: `ProjectFormModal` (knowledge project create); the campaign-setup step component; `booksApi.listBooks` in the books API layer.

## Scope (IN)
- Reusable **`BookPicker`** component — searches `booksApi.listBooks` by title (debounced), shows matches, and emits the selected `book_id`. Empty selection is a valid state (book optional).
- Swap the raw-UUID `book_id` field in `ProjectFormModal` for `BookPicker`.
- Swap the raw-UUID field in the **campaign-setup step** for `BookPicker`.
- `scripts/raid/verify-cycle-4.sh` (acceptance gate) + a Playwright screenshot: search by title → select → stored `book_id`; empty stays valid.

## Scope (OUT — explicitly)
- NO BE changes; reuse the existing `booksApi.listBooks` endpoint as-is (no new search endpoint).
- NO world-container / `world_id` grouping (C20/C21) — `BookPicker` selects a book, not a world.
- NO build-graph gating (C5), NO knowledge IA restructure (C6/C7).
- NO change to how `book_id` is stored/validated downstream — only the input control changes.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `frontend` unit tests for `BookPicker` (title search → emits `book_id`; empty = valid) + both call-site integrations.
- Lints pass: `frontend` eslint/tsc clean on touched files.
- Integration smoke (FE-only, Playwright screenshot per G4): in `ProjectFormModal`, search a book by title → select → the stored value is the `book_id` (UUID), not free text; clearing it leaves the form valid. Screenshot filed with this brief.

## DPS parallelism plan
- DPS 1: `BookPicker` component — debounced `booksApi.listBooks` search, match list, selection emit, empty-valid state (return budget: 1500 tokens summary).
- DPS 2: call-site swaps in `ProjectFormModal` + the campaign step (seam-stub `BookPicker`'s props first, integrate once DPS 1 lands).
- Serial tail: `verify-cycle-4.sh` + Playwright screenshot once both DPS land.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- A picker that emits the title (or the whole book object) instead of the `book_id` — downstream still expects the UUID.
- Empty selection treated as invalid → regresses the "book optional" contract (knowledge project / campaign can be bookless).
- Unbounded/non-debounced `listBooks` calls on every keystroke — perf + rate-limit risk; confirm debounce.
- A residual raw-UUID field left in one of the two call sites (campaign step easy to miss).
- Conditional-unmount of the picker inside the modal (CLAUDE.md FE rule) — use internal branching/CSS `hidden`.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (`BookPicker` + both call-site swaps).
- No OUT items touched (no BE, no world grouping, no build-graph gating, no IA restructure).
- All acceptance criteria met; `verify-cycle-4.sh` exits 0 with a filed Playwright screenshot.
- Cross-cycle invariant: `book_id` storage/validation unchanged; only the input control is replaced.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) C4.
- LOCKED: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) §G6 (book-workspace IA), §Scope, §G4.
- Source spec: [knowledge-service-standalone-ux-review](../../specs/2026-06-13-knowledge-service-standalone-ux-review.md). BL-3 origin per the decomposition Sources list (knowledge-fe-ux-qol-gaps).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **G6 LOCKED:** the book is the workspace anchor — users pick it by title via `booksApi.listBooks`; a raw-UUID field is the friction wall this cycle removes.
- 🔴 **Contract:** `BookPicker` must emit the **`book_id` (UUID)**, and an **empty selection must stay valid** (book optional for knowledge project + campaign).
- 🔴 **G4 LOCKED:** FE VERIFY = a real Playwright screenshot (test account `claude-test@loreweave.dev`).
- 🔴 **Acceptance MUST include:** the campaign-setup step swap too — not just `ProjectFormModal`; the second call site is the easy miss.
- 🔴 **Do NOT touch:** any BE, the `world_id` grouping (C20/C21), build-graph gating (C5), or `book_id` downstream validation.
- 🔴 **Fresh session reminder:** new `/raid 4` invocation; no carry-over. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
