# S05 · "Translate the chapters that need it into English"

> Black-box scenario. The user wants their new/changed chapters in another language; they don't know
> "coverage", "segments", "dirty", "versions", or "activate".

| Field | Value |
|---|---|
| **Scenario id** | S05 |
| **Maps to umbrella workflow** | W5 (`translation-pass`) — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) §5 (builder hint only) |
| **Persona** | N-T (fan translator) / P1 Mai — near-zero platform knowledge |
| **Surface** | the chat, open next to my book |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế with source chapters + an English target set up |
| **Status** | ⬜ drafting |
| **Owner** | — |

## 1. Who I am (the unknown user)

- **Mental model:** I have chapters in the original language and I want them in English. Some are already
  translated, some are new or I changed them. I want to say "translate what needs it" and get it done and
  published, and I care about roughly what it'll cost and whether it's finished.
- **The words I use:** "translate the new chapters", "update the English", "what needs translating", "is
  it done", "publish it".
- **Words I do NOT know:** *coverage, segment status, dirty, version, set active, retranslate, confirm-token.*

## 2. What I'm trying to get done

Get my not-yet-translated / changed chapters into English and published, spending only on what actually
needs redoing, and knowing when it's really finished.

## 3. What I have / where I'm starting

- I'm in my book; it has source chapters and an English target already set up.

## 4. What I do and what I expect to see

| # | I say / do | I expect to see |
|---|---|---|
| 1 | "Translate the chapters that need it into English." | It tells me what needs translating and roughly the cost, and asks to proceed — not jargon, not "searching…". |
| 2 | "Go — only the ones that changed." | It starts, tells me it's running (in the background if so), and doesn't pretend it's instantly done. |
| 3 | "Is it done?" | An honest progress answer; "done" only when it really is. |
| 4 | "Publish it." | It publishes the finished English — or clearly tells me it can't yet because some parts have serious issues, and offers to show me. |

## 5. How I'll know it worked — and how I'll know it failed

- **Worked:** the chapters that needed it are now in English and published; it only redid what changed;
  it told me the cost up front and when it truly finished.
- **Failed:** it re-translates **everything** when only a few changed (wastes money) · it says "done"
  while it's still running · it publishes silently over good work, or refuses to publish with no
  explanation · it spins searching for how to translate and stalls · it never tells me the cost before
  spending.

## 6. Acceptance (observable, from my chair)

- [ ] The changed/untranslated chapters end up **translated and published** (or an honest "can't publish
      yet — N serious issues, want to see them?"), verified by me.
- [ ] It **only redid what needed it** (didn't re-translate unchanged chapters).
- [ ] I saw the **cost/confirmation before spending**, and "done" meant done (async flagged honestly).
- [ ] No jargon demanded; no thrash; under ~90s of assistant time (excluding the background job itself).

## 7. Baseline — NOT RUN 2026-07-10: **fixture must be built first** (scoped below)

Scenario JSON is authored (`scripts/eval/discoverability_scenarios/S05-translation-pass.json`); it was
deliberately not run, because on the available data it could not fail the right way.

- **The crux:** *only redo what changed* + cost-before-spend + async honesty. That requires **partial
  coverage**: some chapters already translated, at least one new or edited (dirty). A fully-untranslated
  or fully-translated book cannot exercise the over-spend check at all.
- **Why no fixture exists (verified 2026-07-10):** no book carries the needed partial translation state
  (`chapter_translations` / `active_chapter_translation_versions` in `loreweave_translation` have no
  suitable book).
- **Fixture to build (buildable now):** a small book with 2–3 short source chapters + an English target;
  translate them; then edit one chapter so it goes dirty. Use a **local** model — this scenario spends real
  tokens on the translation job, so keep chapters short.
- **Sequencing note:** unlike S04, S05's precondition does **not** depend on the broken glossary path, so
  it is independently runnable once its fixture exists — a good next baseline.

## 8. Builder hint (NON-BINDING — not part of acceptance)

> Implementers only.

- "What needs it" ≈ coverage + dirty/stale segments; "only the changed ones" ≈
  `translation_retranslate_dirty` (cheaper) over a full `translation_start_job`; "publish" ≈
  `translation_set_active_version` (refused on unresolved HIGH issues — surface as a real blocker). Cost
  confirm = the spend gate. Jobs are async — poll before "done".
- Likely path: a `translation-pass` workflow (check → dirty-only → confirm → watch → publish),
  async-aware. No new backing capability. Maps to umbrella Phase 2 + Phase 1 fallback.

## 9. Re-test gate

Re-run §4 as this user; ✅ when a changed-only pass publishes (or honestly blocks) with cost shown, no
over-spend, honest completion, no jargon. Save transcript.
