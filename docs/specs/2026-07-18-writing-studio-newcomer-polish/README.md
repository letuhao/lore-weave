# Writing Studio — Newcomer Polish & Bug-Fix Track

**Origin:** a real first-run dogfood session. We put on a brand-new-user hat, followed the
advertised promise ("draft chapters with an AI co-writer"), and tried to write our first book
end-to-end in the live app. It worked — but the path from *New Book* to *words on the page* was a
maze, and twice the app *looked broken when it wasn't*. The diary of that run is the primary source:

> **[docs/dogfood/2026-07-18-newcomer-first-book.md](../../dogfood/2026-07-18-newcomer-first-book.md)**

This folder turns those complaints into a fix spec. Every finding below is grounded in the actual
root cause in code (file:line), not the surface symptom — per the repo's anti-laziness rule.

## Documents
- **[spec.md](spec.md)** — the findings, root causes, brainstormed solution options, the recommended
  fix for each, acceptance criteria, and sizing/sequencing. Decisions **sealed** at the bottom.
- **[plan.md](plan.md)** — the sequenced implementation plan (M1–M6): files, changes, tests,
  acceptance, and per-milestone gates.
- **[round-2-feedback.md](round-2-feedback.md)** — a *second* dogfood pass on the build that already
  ships the M1–M6 fixes. Confirms F1–F7 resolved in live use, and captures three new findings one
  layer deeper (**F8–F10**: the Plan panel dead-end, the `Divergence (dị bản)` bilingual label leak,
  and the un-onboarded "Work" concept). Shipped.
- **[round-3-feedback.md](round-3-feedback.md)** — a *third* pass on the live stack after the Parts→Arcs
  merge. Confirms the merge works end-to-end, and captures **F11 (HIGH)**: creating a Work makes an
  un-decomposed book's chapters vanish from the Manuscript rail — and the onboarding door leads straight
  into it. Root cause + fix options; not yet built.
- **[round-4-feedback.md](round-4-feedback.md)** — a *fourth* pass on the **durable-gate-ACTIVATED** build
  (2026-07-20). Confirms the durable confirm gate is wired correctly (the agent describes propose→confirm-card
  accurately). Captures **F12–F16**: agent-registry crashed (Exited 255) → a 504 flood; a failing-tool-call
  LOOP (`composition_get_mine_job` with no `job_id`, 7×) the success-only breaker never stops; the agent
  refusing to drive `book_chapter_delete`/`book_list_chapters` (weak local model + maybe prompt); chapter-create
  stealing panel focus from the chat; and language-not-required on New Book. **Backlog — investigate one-by-one
  in ALPHABET order of each finding's slug.** Not yet built.

## The findings at a glance (priority-ordered)

| ID | Severity | Finding (newcomer's words) | Root cause | Rec. size |
|----|----------|----------------------------|-----------|-----------|
| **F1** | 🔴 High | "It said I was logged in but everything was failing." Confident authed shell while the session token was stale → 401/500 flood, no "reconnecting" state. | Shell renders cached identity; no silent-refresh-first / error-suppression policy. | M |
| **F2** | 🔴 High | "I clicked *Editor* to write and it was a dead end. Nothing let me make a chapter." | Manuscript rail "+" **intentionally** opens Plan Hub; Editor empty state has no create; the real write door is buried in Plan Hub → Simple. | M |
| **F3** | 🔴 High | "I saved a chapter and the sidebar still said **0 chapters**." (Reads as data loss.) | `useManuscriptTree` is hand-rolled `useState`; the create mutation invalidates only react-query keys it can't reach. | M |
| **F4** | 🟠 Med | "My first chapter is named `editor-2d0fc71f-…​.txt`." | FE sends `title:''`; book-service stores the storage **filename** and the UI shows it as the title. | S–M |
| **F5** | 🟡 Low | "The planner opened in the scary Advanced canvas, not the friendly Simple list." | **Not a code bug** — code default is `simple=true`; the shared test account carried a persisted Advanced pref. Add a planless-book guard. | XS–S |
| **F6** | 🔴 High (structural) | "*Act* and *Arc* are two different things and I couldn't tell which is the real outline." | Two real layers — manuscript **parts/acts** (book-service) vs plan **arcs** (composition outline) — with colliding names and no in-UI bridge. | S now (rename+explain) / XL later (unify) |
| **F7** | 🟡 Low | Polish: lowercase "plan" tab; "99+" badge on a fresh account; a 2-sentence AI ask cost ~22.6k input tokens. | i18n casing; seeded test data; co-writer preloads 48 tools + 5 skills for every message. | XS each; 7c may spin out |

## What this track is / isn't
- **Is:** a coherent UX polish + bug-fix pass on the Writing Studio's *first-run* path, driven by
  real friction. Whole-effort size ≈ **L** (write a plan before BUILD).
- **Isn't:** a re-architecture. F6's "unify the two hierarchies" and F7c's "context budget for chat"
  are called out as **separate larger tracks** (defer-gate #2, structural) — this spec proposes the
  cheap clarity fixes now and flags the big ones, rather than scope-creeping.

## Status
`PLAN complete` — spec + plan drafted, **decisions sealed** (2026-07-18): rename **Part/Arc**, default
title **"Chapter {n}"**, and **add a real rail "New chapter"** (a conscious reversal of the 2026-07-17
"creation lives on the Plan rail" stance). Ready for BUILD on the M1→M6 order in [plan.md](plan.md).
No code changed yet.
