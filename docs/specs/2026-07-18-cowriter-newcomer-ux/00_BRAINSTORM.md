# Co-writer Newcomer-UX — BRAINSTORM (clear all dogfood findings)

> **Source:** the 2026-07-18 "Cursor-for-writing" dogfood
> ([`docs/dogfood/2026-07-18-jamie-cowriter-cursor-for-writing.md`](../../dogfood/2026-07-18-jamie-cowriter-cursor-for-writing.md)).
> A talentless newcomer who saw *"Cursor AI, but for writing your book"* tried the co-writer. The core loop
> **works** (Gemma wrote a chapter into the book at $0) — but 7 friction points stand between "it works" and
> "a newbie succeeds unaided." **#1 (rail stale after agent create) is already FIXED + shipped** (`b255cb62a`).
> This track clears the rest.
>
> **Goal (this run):** brainstorm → spec → self-evaluate → fix spec → build slice-by-slice, **QC each slice**.
>
> **⚠️ Coordination:** a concurrent session owns the studio FE (onboarding doors, structure-coherence). Several
> findings touch studio-adjacent FE + chat-service. The BUILD section must check for collisions before editing
> and commit each slice via a scoped pathspec commit (never sweep the other agent's work).

---

## The findings still open (from the dogfood, minus the fixed #1)

| ID | Sev | Finding | Surface |
|----|-----|---------|---------|
| F2 | HIGH | Ask↔Write mode is an **undiscoverable unlabeled "Write" chip** with no visible state; default Ask just chats — the newcomer never learns how to let the AI edit the book | co-writer composer (FE) |
| F3 | HIGH | **Runaway agent scope + jargon confirm:** asked for 1 chapter, the AI unprompted adopted glossary "kinds/genres" and blocked with *"high-impact — please confirm"* in dev-speak | chat-service persona (BE) + confirm copy |
| F4 | MED | Ask-mode AI messages have **no "Insert into chapter / Apply"** — only Copy (the Cursor-defining affordance is missing) | co-writer message row (FE) |
| F5 | MED | First screen after login is a **reading catalog** (/browse "0 books found"), not writing; the great "What do you want to do?" chooser is buried behind "Start something new" | routing (FE) |
| F6 | MED | **16-item sidebar** of jargon; no obvious "write my book with AI" entry | nav (FE) |
| F7 | LOW | Agent **double-fired `book_chapter_create`** → duplicate chapter | book-service MCP (BE) |
| F8 | LOW | Polish: co-writer **"Pop out" disabled**; **"99+"** notif badge on a fresh account; benign red console error (`/v1/notifications/stream` ERR_INCOMPLETE_CHUNKED_ENCODING) | misc FE |

---

## Solution brainstorm (options → recommendation) — to be grounded with exact seams post-scout

### F2 · Make Ask↔Write obvious, stateful, explained
- **Opt A (recommended):** turn the chip into a clearly-labelled **segmented toggle "💬 Ask / ✍️ Write"** with an
  active-state style + `aria-pressed`, and a one-time inline hint the first time a newcomer opens the co-writer:
  *"Write mode lets the AI edit your book (create chapters, save drafts). Ask mode just talks."* Persist "hint
  seen" server-side (per User-Boundaries; not localStorage-only).
- Opt B: auto-switch to Write when the user's message clearly asks to write ("write/create/draft chapter…").
  Rejected as primary — magic mode-switching is unpredictable; keep it explicit, but a *suggestion chip* ("This
  looks like a writing task — switch to Write mode?") is a fast-follow.
- **Settings-and-config check:** mode is a per-conversation UI state (fine), not a global env flag. Default =
  **Ask** (safe, read-only) — flipping to Write is a deliberate act. Effective-value visible = the toggle itself.

### F3 · Rein in scope + de-jargon the confirm
- **Two parts.** (a) **Persona/system-prompt restraint** — instruct the co-writer to *do exactly what's asked and
  OFFER follow-ups, never bulk-adopt taxonomies unprompted*; gate world/glossary setup behind an explicit user
  yes. (b) **De-jargon the high-impact confirm copy** — replace "kinds newly adopted 9 — + unknown (always)"
  with human text ("This will add 9 lore categories — Characters, Locations, … — to your book. [Set up my world] [Not now]").
- **Recommendation:** do both; (a) is the root cause (stop the over-reach), (b) is the safety net for any
  genuinely high-impact action that remains. Keep the confirm gate (it's correct per cost-gated-mcp-tool
  discipline) — just make its words human.

### F4 · "Insert into chapter" on Ask-mode messages
- **Opt A (recommended):** add an **"↧ Insert"** action to the assistant message row that appends/creates a draft
  in the **active chapter** (reuse the existing draft-save path the agent's Write mode uses; publish
  `manuscriptChanged` like the F1 fix). If no active chapter, offer "Insert into a new chapter" (reuse
  `useChapterDoor`).
- Opt B: a full Cursor-style inline diff/apply. Over-scoped for now; the append/new-draft covers the newcomer need.

### F5 · Route a brand-new writer to the chooser
- **Opt A (recommended):** on first login **with zero books**, land on **/onboarding/new** (the "What do you want
  to do?" chooser) instead of /books or /browse. Once they have ≥1 book, land on /books (or last-open studio).
- **Opt B:** always land on the chooser. Rejected — returning users want their books, not the chooser.
- Reuses any existing has-books query; the "new user" signal drives the redirect.

### F6 · Tame the sidebar
- **Opt A (recommended):** **group + progressively disclose** — a top "Writing" group (Studio / Co-writer /
  Plan) always visible; fold power-user items (Standards, Campaigns, Roleplay, Extensions, Leaderboard) under a
  collapsible "More". De-jargon a couple of labels.
- Opt B: role-based nav. Over-scoped. Grouping is the cheap 80%.
- **Coordination risk:** the sidebar is core app shell — check whether the other agent is touching it before edit.

### F7 · `book_chapter_create` idempotency
- **Opt A (recommended):** a short-window **idempotency guard** in the MCP tool — dedupe an identical
  (book_id, title) create within N seconds / or accept an idempotency key from the agent envelope. Return the
  existing chapter instead of a second row.
- Opt B: FE de-dupe. Rejected — the double-call is server-observable; guard at the tool (authoritative).

### F8 · Polish
- Enable co-writer **Pop out** (or hide it if unsupported in-dock); cap/soften the **"99+"** badge for accounts
  with little real activity; investigate the **notifications SSE** incomplete-chunk (likely a benign reconnect —
  downgrade from console.error to a debug log or handle the abort cleanly).

---

## Draft slice decomposition (each independently buildable + QC-able)

| Slice | Finding(s) | Tier | Rough size |
|-------|-----------|------|-----------|
| **N1** | F2 Ask/Write toggle + first-run hint | FE | S/M |
| **N2** | F4 Insert-into-chapter on AI messages | FE | M |
| **N3** | F5 first-run routing to chooser | FE | S |
| **N4** | F6 sidebar grouping/disclosure | FE | S/M |
| **N5** | F3a persona scope restraint (BE) + F3b de-jargon confirm | BE(+FE copy) | M |
| **N6** | F7 book_chapter_create idempotency | BE | S |
| **N7** | F8 polish batch (pop-out, badge, SSE console error) | FE | S |

Ordering: **N5/N6 (BE) first** (they gate the agent behavior the FE showcases), then **N1→N4 FE**, then **N7**.
Each slice: BUILD → VERIFY (tests) → per-slice QC (live-smoke where it has a runtime surface) → scoped commit.

*(Seams — exact files/lines per finding — filled in from the 3 scouts before the spec is finalized.)*
