# Studio S3 (PlanForge) — blackbox usability test

> **Different from the coverage test.** The coverage test knows the features and checks each one works.
> THIS test is **blackbox**: the tester is a real web-novel author who has **never seen this tool**,
> knows **nothing** about passes/checkpoints/PlanForge, and is handed only a **goal**. They must
> **discover** how to do it. We judge one thing: **can a real author actually get their job done — and
> does it feel usable, or do they get lost, confused, or stuck?** The output is a **usability verdict
> per task**, not a pass/fail per feature. A feature that "works" but no author can find or understand
> is a FAILURE here.

## Rules of engagement (blackbox discipline)
- The tester is given the **goal only** — never the steps, never a feature name.
- No reading the code, the specs, or this repo's docs. Only the running app + its own UI text/tooltips/
  guide.
- Narrate out loud: what they're trying, what they expected, what confused them, where they'd give up.
- For each task record: **outcome** (done unaided / done with struggle / gave up), **time-to-first-
  correct-action**, **confusion points**, **a 1–5 usability score**, and **the author's own words**.
- Environment: the **real built app** (Docker/static build, not vite dev — no HMR churn). A real chat
  model (gemma-4-26B-A4B QAT) so the LLM steps actually run.

## Persona
> "I'm **Mai**, I write xianxia web-novels. I have a premise and a few chapters. I've used Scrivener and
> Notion. I'm not technical — I don't know what a 'compiler pass' or a 'checkpoint' is. I opened this
> 'Writing Studio' because someone said it can help me **plan my book with AI**."

## The goals (handed to the tester, one at a time — NO instructions)

### Goal 1 — "Get the AI to help me plan my book's structure."
Watch: does Mai find the Planner at all? The command palette is ⌘⇧P — does she discover it, or does she
expect a visible button/menu? Does she understand "propose"? Does she know to paste a premise?
- ⛳ **Usability probes:** Is there a discoverable entry point, or must she know the palette shortcut?
  Once in the Planner, is "Propose" self-explanatory? Does she understand what she got back
  (self-check gaps, arcs)? **Is the artifact view (raw JSON) meaningful to her, or does she recoil?**

### Goal 2 — "Review the characters/plot the AI came up with, and approve the ones I like."
This is the Pass Rail + checkpoints. Watch: does Mai connect "Planner" → "Pass Rail"? Does she
understand the 7-pass rail, the badges (BLOCKING/advisory), "fresh/stale", "blocked"? Does she know
what "run…" costs? At the cast checkpoint, does she understand the **seed gate** ("apply the glossary
seed") — or is it jargon that stops her cold?
- ⛳ **Usability probes:** Is the rail's model (run each pass, approve blocking ones) learnable without
  a manual? Does she understand WHY a pass is 🔒 blocked? Is "review →" obviously the way to approve?
  **Does the seed-gate copy make sense to a non-technical author?** Is "the cursor advanced" visible
  and satisfying, or invisible?

### Goal 3 — "Fix something the AI got wrong."
The self-check gaps + the repair strip (Explain / Apply fix / Autofix). Watch: does Mai find the repair
strip? Does she trust "Fix the top gaps automatically"? Does she understand the paid confirm? **When she
wants to fix a specific wrong character in the cast, can she — or does she hit the read-only wall?**
- ⛳ **Usability probes:** Is "the plan has gaps → here's how to fix them" a clear flow? Is the read-only
  checkpoint (can't edit the cast inline) a blocker to her real workflow? Would she expect to just click
  a name and edit it?

### Goal 4 — "Put this plan into my book so I can start writing."
The Link-to-outline + the manuscript. Watch: does Mai understand "Link to outline"? After linking, can
she FIND the planned arcs/chapters where she writes? Does the hand-off feel complete, or does the plan
seem to vanish?
- ⛳ **Usability probes:** Is the loop closed for her — plan → outline → write? Or does "Link to outline"
  feel like a dead-end button whose effect she can't see?

### Goal 5 — "I made a mess. Clean up the runs I don't want."
Archive/restore. Watch: does she find archive? Does the Undo toast catch her if she mis-clicks? Can she
get a run back?
- ⛳ **Usability probes:** Is archive discoverable + safe (undo)? Is "Show archived" findable?

### Goal 6 — "Ask the AI assistant to run a pass for me" (agent parity)
If Mai uses the chat instead of the rail, does the rail stay in sync when the agent acts?
- ⛳ **Usability probes:** Does driving via chat vs. the rail give a coherent, non-contradictory picture?

## Usability verdict framework (fill per goal)
| goal | outcome (unaided / struggled / gave up) | time-to-first-correct | score /5 | confusion points | author's words |
|---|---|---|---|---|---|
| 1 plan structure | | | | | |
| 2 review + approve | | | | | |
| 3 fix a mistake | | | | | |
| 4 into the book | | | | | |
| 5 clean up runs | | | | | |
| 6 agent parity | | | | | |

## The single question this test answers
> **Would a real, non-technical web-novel author actually use this to plan their book — unaided — and
> come away feeling it helped, not fought them?**

A "yes" needs: discoverable entry (Goal 1), a learnable rail model (Goal 2), a trustworthy fix loop
(Goal 3), a visible plan→book hand-off (Goal 4). Predicted friction from the coverage findings:
**discoverability** (palette-only entry), the **raw-JSON artifact view** for non-technical readers
(F-1 improved the checkpoint render but the json-editor "open ↗" is still raw), **jargon** (seed gate /
"PF-7" — F-4 improved the copy), the **read-only checkpoint** (can't fix a name inline —
D-S3-CHECKPOINT-STRUCTURED-EDITS), and the **plan→manuscript hand-off visibility** (F-6 — chapters may
not appear). This blackbox run CONFIRMS or REFUTES each from a real author's seat, and its findings feed
the next polish cycle. Blackbox usability is the truest "cho có vs. thực sự dùng được" gate.
