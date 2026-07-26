# Dogfood diary — "Jamie," the talentless hopeful who saw the *"Cursor for writing"* ad

> **Persona:** Jamie. Wants to write a novel, has no craft, loved Cursor for code, saw an ad pitching
> LoreWeave as **"Cursor AI, but for writing your book."** Knows *nothing* about the platform. Goal: open it,
> find the AI co-writer, and write Chapter 1.
> **Setup:** isolated static FE build served on :5310 (one-off nginx container on the infra network, snapshotted
> so a second session's live edits can't confound it). Real backend stack (48 containers). Co-writer model =
> **Gemma-4 26B-A4B QAT (200K)**, local via LM Studio → **$0 spend**. Driven with an isolated Playwright session.
> **Book created:** *The Last Ember* (`019f74c0-1ef6-746a-b34c-c9dd2b06778a`), Chapter 1 *"The Waking Fire."*

## Did the core promise deliver? — **Yes.**

I asked the AI to create Chapter 1 and write the opening scene into it. It **actually did**: Gemma tool-called
`book_chapter_create` + `book_chapter_save_draft`, and when I opened the chapter, my editor held a genuinely
good 150-word opening about Kaila and the forge. Newcomer → co-writer → **prose in my real book**, at $0 on a
local model. That's the magic the ad promised, and it works end-to-end. Verified in the DB and in the editor.

## …but getting there was rough. Ranked friction (most damaging first)

| # | Sev | What happened (as Jamie felt it) | Root cause (engineer's note) |
|---|-----|----------------------------------|------------------------------|
| 1 | **HIGH — bug** | The AI said *"I've created Chapter 1"* — but my **Manuscript list still said "No chapters yet / 0 ch."** I clicked the rail's **Reload** button: still nothing. I'd have concluded it failed and rage-quit. Only a **full browser reload** made the chapter appear. | The agent Write-mode tool path (`book_chapter_create`) doesn't emit the `manuscriptChanged` studio-bus event the navigator listens on (cf. the M2 polish that wired live refresh for *panel-driven* CRUD — the *agent-tool* path was missed). The rail's own Reload didn't refetch either. **The AI does the work; the UI hides it.** This one bug can sink the whole first impression. |
| 2 | **HIGH — UX** | The one thing I care about — *"let the AI write into my book"* — is gated behind a tiny **"Write"** chip by the composer with **no visible on/off state**. Default mode just *chats*. My first request came back as a chat bubble; I only got a real chapter after I happened to flip "Write." A newcomer will never discover this. | The Ask↔Write mode toggle is under-signposted. Cursor makes Ask/Agent a prominent, obviously-stateful switch. Here it's an unlabelled chip (`title="Write mode — the agent can make undoable changes…"`, no `aria-pressed`, no active styling I could perceive). Needs a loud, stateful, explained toggle + a first-run hint. |
| 3 | **HIGH — UX** | I asked for **one 150-word chapter.** The AI wrote it — then, *unprompted*, went off to "adopt Core Lore + Fantasy Elements categories," set up **9 "kinds" and 2 "genres,"** and **blocked me** with *"This change is high-impact — please confirm"* + `kinds newly adopted 9 — + unknown (always)`. I don't know what a "kind" is. I felt hijacked and a little scared. | Runaway agent scope + jargon leak. The co-writer over-reached far past the ask, then surfaced an internal, developer-worded approval gate on a newcomer's very first turn. Needs scope restraint (do what's asked, *offer* the rest) and human-worded confirm copy. |
| 4 | **MED — UX** | In the default (Ask) mode, the AI wrote me a beautiful paragraph… trapped in a chat bubble. The only actions were **Copy / Regenerate / 👍👎** — **no "Insert into chapter" / "Apply."** In Cursor, suggestions have **Apply**. Here I'd copy-paste by hand. | Missing the Cursor-defining "Apply to file" affordance on Ask-mode messages. A one-click "Insert into current chapter / new draft" would bridge Ask-mode prose → manuscript without forcing Write mode. |
| 5 | **MED — UX** | After login I landed on **/books**, and the public front door is a **reading catalog** (*"Discover Stories… 0 books found"*). For a product sold as a *writing studio*, my first screen was other people's (nonexistent) novels. The friendly **"What do you want to do?"** chooser (with a clear **"Write… with an AI co-writer"** card) was **buried** behind a sidebar item called *"Start something new."* | First-run routing doesn't match the pitch. The onboarding chooser is the best screen in the app and should greet a new writer, not hide two clicks deep. |
| 6 | **MED — UX** | Post-login sidebar = **16 items** (Workspace, Chat, Assistant, Roleplay, Knowledge, Worlds, Campaigns, Standards, Jobs, Usage, Extensions…). None obviously said *"write my book with AI."* I couldn't tell Chat vs Assistant vs Workspace vs Co-writer apart. | Nav overload + undifferentiated jargon for a first-timer. Needs progressive disclosure / a "Writing" grouping that points straight at the studio + co-writer. |
| 7 | **LOW — polish** | Small stuff that chips at trust: the co-writer **"Pop out" is disabled**; a **"99+"** notifications badge screamed at me on a brand-new account; a benign but red **console error** (`ERR_INCOMPLETE_CHUNKED_ENCODING` on `/v1/notifications/stream`); confirm-gate copy leaks raw tokens (`+ universal (always)`, `+ unknown (always)`). | Individually minor; collectively they read as "unfinished" to a newcomer. |

## The one-line verdict (Jamie)

> *"It really can write my book with me — the Gemma co-writer wrote a great opening straight into Chapter 1.
> But it hid that power behind a mystery 'Write' toggle, then my chapter didn't show up until I reloaded the
> whole page, and somewhere in there it tried to make me approve a scary 'high-impact' thing about 'kinds' I
> never asked for. If it just **greeted me with the writer chooser, made Write-mode obvious, showed my chapter
> the instant the AI made it, and stopped throwing jargon at me,** I'd tell everyone it's Cursor for novels."*

## Fix priorities (engineer's cut)

1. **Emit `manuscriptChanged` from the agent effect handler on chapter CREATE.** *(Trust-killer; fix first.)*
   **Root cause (confirmed in code):** the realtime-sync standard works — `ManuscriptNavigator.tsx:107-116`
   subscribes to the studio-bus `manuscriptChangeSeq` and reloads its **hand-rolled** tree when it bumps; FE-driven
   CRUD publishes it (`useChapterDoor.ts:36`, `PlanHubPanel.tsx:57`). But the **agent** path doesn't: `bookDraftEffect`
   ([bookEffects.ts:34-41](../../frontend/src/features/studio/agent/handlers/bookEffects.ts)) only
   `invalidateQueries(['chapter', bookId, chapterId])` + `reloadChapter` — it **never publishes `manuscriptChanged`**,
   and since the tree is hand-rolled (not react-query) `invalidateQueries` can't reach it anyway (the repo's
   `invalidatequeries-cannot-reach-hand-rolled-state` class). **Fix:** in `bookDraftEffect`, publish
   `ctx.host` bus `{ type: 'manuscriptChanged' }` when the tool created a new chapter/part (safe — that event only
   refreshes the tree; unlike the `chapter` focus event it does NOT hijack the editor, per the file's own §33 note).
   **✅ FIXED + LIVE-PROVEN (2026-07-18):** `bookDraftEffect` now publishes `manuscriptChanged` (before the G7
   dirty-guard, so a dirty editor doesn't hide a new sibling). Unit: effectRegistry.test.ts 15/15 (2 new). Live on
   :5310 with the rebuilt bundle — asked the Gemma co-writer to create "Sparks in the Dark"; the rail went **1 → 2
   chapters with NO page reload** (screenshot `jamie-rail-live-update-after-fix.png`), the exact failure this bug was.

> **Adjacent minor observation (not fixed — out of scope):** in the live re-run, Gemma double-fired
> `book_chapter_create` and made two "Sparks in the Dark" chapters. That's an LLM double-tool-call, not the refresh
> bug — but a server-side idempotency guard on `book_chapter_create` (or a client de-dupe) would spare newcomers
> accidental duplicate chapters. Candidate follow-up.
2. **Make Ask↔Write a prominent, stateful, explained toggle** + a first-run hint ("Write mode lets the AI edit your book").
3. **Rein in co-writer scope** + rewrite the high-impact confirm in human language (no "kinds/adopt standards/always" tokens on a newcomer surface).
4. **Add "Insert into chapter / new draft"** on Ask-mode AI messages.
5. **Route a brand-new writer to the "What do you want to do?" chooser** first; de-jargon/regroup the sidebar.

*Evidence: this session drove the real stack; chapter persistence confirmed in `loreweave_book.chapters`;
screenshot `jamie-cowriter-chapter.png`. No source was modified for this dogfood (the studio FE belongs to a
concurrent session).*
