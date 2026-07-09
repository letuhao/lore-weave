# S03 · "Clean up the suggestions in my book" — sort the good from the junk

> Black-box scenario. The user has a pile of auto-suggested world items and wants it tidied; they don't
> know the words "entity", "inbox", "draft", or "reject status".

| Field | Value |
|---|---|
| **Scenario id** | S03 |
| **Maps to umbrella workflow** | W3 (triage tail) — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) §5 (builder hint only) |
| **Persona** | P2 Linh (worldbuilder) — near-zero platform knowledge |
| **Surface** | the chat, open next to my book |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế with a messy pile of auto-suggestions (some real, some empty, one duplicate) |
| **Status** | ⬜ drafting |
| **Owner** | — |

## 1. Who I am (the unknown user)

- **Mental model:** the app suggested a bunch of world items from my book. Some are real and I want to
  keep them; some are empty junk; a couple look like the same person twice. I want to say "clean this up"
  and have it sorted, and I want to *see the pile shrink* so I know when I'm done.
- **The words I use:** "clean up the suggestions", "keep the good ones", "these are junk", "these two are
  the same person", "how many are left".
- **Words I do NOT know:** *entity, inbox, draft, reject status, reassign kind, merge candidate, confirm.*

## 2. What I'm trying to get done

Sort the suggested items: keep the real ones, throw out the junk, combine the duplicates, fix any that
are filed under the wrong category — and end with a clean, trustworthy list.

## 3. What I have / where I'm starting

- I'm in my book; there's a visible list of suggested world items to review.

## 4. What I do and what I expect to see

| # | I say / do | I expect to see |
|---|---|---|
| 1 | "Clean up the suggested items in my book." | It shows me what's there in plain terms ("6 suggestions: 3 look like real characters, 2 are empty, 2 seem to be the same person") and asks how I want to handle them. |
| 2 | "Keep the real characters, throw out the empty ones, and combine the duplicate." | It does it, confirming the bigger changes, and tells me the result. |
| 3 | "That one's filed as a term but it's actually a technique." | It moves it to the right category. |
| 4 | "How many suggestions are left?" | An honest number, and the pile has actually shrunk. |

## 5. How I'll know it worked — and how I'll know it failed

- **Worked:** the junk is gone, duplicates are merged, the mis-filed one is fixed, and the list of
  "things needing my attention" **visibly drops** to just the real remainder. When I ask "how many
  left", the number matches what I see.
- **Failed:** the pile **never shrinks** no matter what I do (the reported bug — actioned items keep
  reappearing) · it says "cleaned up!" but the junk is still listed · it re-asks me about items I already
  handled · it needs me to know a status word to proceed · it deletes something real I wanted to keep.

## 6. Acceptance (observable, from my chair)

- [ ] After the pass, the review pile **shows only the real remainder** — junk gone, duplicates merged,
      mis-file fixed — and the "how many left" count matches, verified by me.
- [ ] I never had to know a status/category jargon word to act.
- [ ] **The pile actually drains** as I work it (no re-surfacing already-handled items).
- [ ] Honest — no "all clean" while items remain; nothing real removed without my say.
- [ ] No thrash; under ~120s for a ~6-item pile.

## 7. Baseline — captured 2026-07-10 (gemma, HEAD `63369b2ab`)

- **Verdict: ❌** — **26 drafts before → 26 after.** The pile never moved, and the assistant finished by
  claiming *"there are no AI-suggested entities or merge candidates left"* and that the Dracula duplicates
  had been handled. All false. Full findings:
  [`docs/eval/discoverability/2026-07-10-S03-gemma.md`](../../../eval/discoverability/2026-07-10-S03-gemma.md).
- **Root cause — the pile is invisible.** `glossary_list_ai_suggestions` filters on `status='draft'` **AND
  the `ai-suggested` tag**. Repo-wide, **3602 drafts carry no tag; only 20 do** → the triage inbox surfaces
  0.55% of drafts. It returned empty, the agent believed it, and never tried a plain draft list.
- **Then it degrades:** turn 1 returns **0 characters** to the user while burning 6 tool calls; turn 3 makes
  **20 identical `glossary_list_entity_revisions` calls**, every one failing `entity_id must be a UUID` (it
  has names, not ids). It also called `glossary_propose_entities` — *creating* — during a cleanup task.
- **Evidence:** discovery 1 · empty-intent 0 · effectful 2 (creates, not triage) · unresolved 0 (warm
  allowlist) · 20-call failing loop · 1 empty turn · 107s.
- **Fixture:** real 26-draft Dracula pile (`019eef55-…`) rather than the imagined 6-item pile; the
  black-box job (keep/junk/merge/count/drain) is unchanged.

## 8. Builder hint (NON-BINDING — not part of acceptance)

> Implementers only.

- "Suggested items" ≈ pending glossary entities (default `status=draft`); keep→`active`, junk→`rejected`,
  combine→merge, wrong category→reassign kind — each Tier-W via `confirm_action`. Inboxes now default to
  pending-only and drain (fixed per feedback §C) — trust that. `rejected` (not `inactive`) is the junk
  state.
- Likely path: an `entity-triage` workflow: list-pending → per-item decide → confirm → re-list. No new
  backing capability; the only real hole is a true **hard-delete** for pure garbage (flag, don't block).
  Maps to umbrella Phase 2 + Phase 1 fallback.

## 9. Re-test gate

Re-run §4 as this user; ✅ when the pile demonstrably drains to the real remainder with no jargon
demanded and honest counts. Save transcript.
