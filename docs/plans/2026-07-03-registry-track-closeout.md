# Plan — Agent Extensibility Registry: TRACK CLOSE-OUT

**Goal:** clear every remaining defer + tick `01_GUI_CHECKLIST.md` to 100%, so the track can be
e2e-live-tested and fully closed. **XL.** Governing principle (memory
`checklist-is-self-report-enforce-by-tests`): a checklist tick / "done" is valid ONLY when a test
asserts the EFFECT. Every milestone ships tests; ticks cite the test.

## Verified remaining defers (reconciled vs code + DECISION_LOG, 2026-07-03)
1. `D-REG-P5-INGEST-SCHEDULED-WORKER` (folds `D-REG-P3-SCHEDULED-RESCAN`) — M1
2. `D-REG-P5-INGEST-ADMIN-FE` — M2
3. `D-REG-P4-SLASH-AUTOCOMPLETE` — M3
4. `D-REG-BOOK-TIER-FE` — M4 *(was NOT in the user's list — surfaced by the reconcile)*
5. `D-REG-P5-SUBAGENT-WRITE-DELEGATION` — M6 (SPEC ONLY this round; build is a separate user-gated call)
Plus **screen-polish** (EVALUATION U5–U8) — M5, to tick the checklist 100%.

## Milestones

### M1 — Ingest scheduled worker [backend, clears 2 defers]
A Go goroutine ticker in agent-registry (off by default; interval from config). Each tick:
- **Re-pull** the official registry (reuse `pullOfficialRegistry`), min-interval guarded.
- **Denylist / retroactive-removal sync (§7b#1):** an already-`approved` `registry_id` now absent
  upstream → **suspend** the linked System server + mark the queue row `revoked_upstream`, audited.
- **Rug-pull rescan (§7b#2):** re-run `runScan` on each System-tier ingested (`is_external`) server;
  a newly-HIGH finding → auto-`suspended`. This is also the on-demand `D-REG-P3-SCHEDULED-RESCAN`.
- Config: `AGENT_REGISTRY_INGEST_WORKER=1` + `AGENT_REGISTRY_INGEST_INTERVAL` (default 1h). Off → no-op.
- Tests: the denylist-suspend predicate + the rescan-selects-external predicate (pure, pgxmock);
  a `revoked_upstream` status added to the queue CHECK.

### M2 — Ingest admin FE [FE]
The curation table the backend already serves (`/admin/ingest/*`). Rather than a new CMS app, add an
**admin-only** surface: an `AdminIngestView` gated on the JWT `role==='admin'` (decode client-side for
show/hide; the API is the real gate). Mount as a role-gated tab in `ExtensionsPage` ("Registry sources"
— hidden for non-admins) + a route. Pull button, pending/approved/rejected queue with the scan verdict,
approve/reject. Tests: renders queue, approve calls the API, hidden when non-admin.

### M3 — Slash autocomplete [FE, chat-input]
An in-chat `/` autocomplete: on a leading `/token`, show a dropdown of the user's commands (from the
commands list / a lightweight fetch), arrow-select + Enter/Tab to complete. Verify the concurrent-track
collision on the chat-input is gone at build. Tests: typing `/pl` filters to `plan-*`; Enter completes;
Esc/space dismisses; non-leading `/` ignored.

### M4 — Book-tier FE [FE]
A book-context selector in the Extensions surface so tier=`book` skills/commands/hooks/subagents/servers
are listed + created for a chosen book (backend is grant-gated + complete). A book picker (the user's
grantable books) → the create forms gain a "scope: user/book" toggle that sets `tier:'book', book_id`.
Tests: selecting a book + book scope sends `tier:'book'`+`book_id` on create; list filters to the book.

### M5 — Screen-polish sweep → tick `01_GUI_CHECKLIST.md` 100% [FE, the big grind]
Per screen, close the element-level `[ ]`: **Pager/search/sort** on every list (reuse the shared
`useServerPagedList`/`Pager` if present, else a minimal shared one — no hand-roll drift); **states**
(empty CTA · skeleton · cached+Retry error banner); **cascade-delete dialog** (typed-confirm listing
N members); **shadow-warning** in the skill editor; **bulk actions** on the plugins list; **quota strip**
(already partly there); **i18n** (react-i18next vi/en keys on all new strings); **a11y** (`role="switch"`,
focus-trap dialogs, Esc, `data-testid`). Tick a checklist line ONLY with a passing test. Un-testable-cheap
lines (pure visual) get a browser-smoke assertion or stay `[ ]` with a note — never a self-report tick.

### M6 — Subagent write-delegation SPEC (design only)
Full spec: lift the read-only clamp so a subagent can perform an **approved** write. The crux: a nested
`run_subagent` sub-run that hits the Tier-A approval gate must **bubble the suspend up** through the
parent turn's suspend/resume (today the nested suspend is swallowed). Design the suspend-envelope
threading, the resume re-entry into the correct nesting depth, the audit of the delegated write, and the
E2E. **No build this round** — user decides after M1–M5 land.

### M7 — Full E2E live + closure
A live stack run exercising the whole track end-to-end (register → scan → federate → command-expand →
hook → subagent-delegate → admin-ingest-approve → activity-log), rebuild touched images first, real
lm_studio. Then the FINAL GATE: re-walk `01_GUI_CHECKLIST.md` against the running app; close the track in
SESSION only when every non-deferred line is test-or-smoke-backed.

## Execution order & commit boundaries
M1 (Go, self-contained) → M2 → M3 → M4 (FE, mostly disjoint; commit each) → M5 (per-screen commits) →
M6 (spec commit) → M7 (live + SESSION). `/review-impl` after M1, after the M2–M4 FE batch, after M5.
