# 13 · Frontend Shell & Mobile — detailed design

**Date:** 2026-07-11 · **Phase:** P1 · **Status:** DESIGN · Implements **D12**.
UI drafts: `design-drafts/work-assistant/` (all subfolders carry mobile variants).

---

## Q1. 🔴 The all-day session is unreadable today (EDGE-2)

The most important finding in this doc, and it invalidates "the GUI already exists":

**The FE loads only the FIRST 50 messages, with no tail mode and no pagination.** `list_messages` has exactly
one code path — `ORDER BY sequence_num ASC LIMIT 50` from the start (or the same ASC order gated by
`before_seq`, which pages **further backward**). `listMessages` never even sends a limit; `useChatMessages`
does a single fetch with no pagination loop.

So on **reload**, **session switch**, **next-morning reopen**, or a **second device** opening the same session,
the user sees **the morning's first 50 turns** and nothing recent. There is no "load more". The endpoint cannot
even *express* "latest N".

**Fix (P1, named work item):**
- **Server:** add `after_seq` (mirroring `before_seq`) **plus a tail-default**: with neither param, fetch the
  **last N** (`ORDER BY sequence_num DESC LIMIT n`, re-sorted ASC for display). No schema change — the existing
  B-tree indexes scan DESC equally well.
- **FE:** initial fetch = **last N**; upward "load earlier" pagination using the existing `before_seq`.
- **Test:** a ≥100-message day reloads with the **latest** turn visible, desktop **and** mobile.

## Q2. The responsive shell is net-new shared infrastructure

`DashboardLayout` is a fixed 240px `aside` with **no breakpoint behavior**, and there is **no
`useMediaQuery` / drawer / bottom-nav pattern anywhere in the codebase**. The chat feature itself has only
~25 responsive classes.

→ Below a breakpoint the sidebar becomes a **drawer or bottom tab bar**; ChatView gets a mobile pass (input
bar, session sidebar → sheet, settings panel → full-screen). **This benefits every other page too** — it is
shared infra, not assistant-specific.

## Q3. 🔴 The mobile scope is three items, not one (PUX-6)

A phone is the all-day companion's **natural device** — and every human gate D4 makes **mandatory** currently
dead-ends into a desktop-shaped surface:

| Gate | Where it lives today | Mobile? |
|---|---|---|
| Confirm the day's entry | `ChapterEditorPage` — a **1360-line novel-writing editor** with PublishControl | ❌ |
| Review captured people/projects | glossary AI-suggestions — in the **book workspace** or a **dockview panel** (dockview has a known fixed-positioning bug) | ❌ |
| Confirm facts | PendingFactsCard | partial |

So on mobile the user can **accumulate review debt but never clear it** — which starves the KG the whole
product depends on.

**Three items, stated honestly:**
1. **Shell** (drawer/bottom-nav) + ChatView mobile pass + tail-first loading. *(P1)*
2. **Mobile-capable entity + fact review.** *(P1/P2)*
3. **Mobile-capable diary entry review/keep.** *(P2)*

Items 2+3 collapse into **one artifact** if the diary review is done as the **kind-adapted book GUI**
([`03`](03-book-kinds-diary-gui.md)) rather than routing into the writer surfaces — which also solves the
vocabulary problem. **Do that.**

## Q4. Vocabulary (the S06 rule)

Success must **never require** the user to understand *chapter · publish · entity · kind · draft · inbox*.
They see **Entry · Keep · People I noticed · Worth remembering**. A **jargon deny-list check** is part of S14's
acceptance, so the rule is testable rather than aspirational.

## Q5. Surfaces

- **Nav row** (`Assistant`) + the **fifth C22 onboarding intent** ([`02`](02-assistant-mode-session.md) §Q4).
- **Home strip** — capture-status chip **with reason**, "today so far" live rail, pending-entry nudge, inbox
  counts, week-1 empty state, and the failure states (extraction unconfigured · **memory paused, cap reached**).
- **Diary** — the reused book workspace, kind-branched; **hidden from the library grid** (D16).
- **Coaching** — reflection + practice + scorecard ([`08`](08-coaching-reflection.md)).

## Q6. i18n

Every new string goes through the locale pipeline (`scripts/i18n_translate.py`, 18 locales). The **diary
itself** must be written in the user's language ([`06`](06-journal-distiller.md) §Q8) — and so must rubric
anchors and reflection prompts, or a Vietnamese user gets an English rubric anchor.

## Q7. Acceptance

Playwright: first-run intent → provision → chat → home-strip states → **review the day and keep it** → browse
the diary — **on a mobile viewport**, end to end. Plus: a ≥100-message session reloads showing the **latest**
turn; the jargon deny-list passes; every review gate is reachable and completable on a phone.
