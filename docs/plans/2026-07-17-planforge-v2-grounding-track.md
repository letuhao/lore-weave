# PlanForge-v2 · Proposer-Grounding track (umbrella plan)

> **STATUS 2026-07-17: GOAL MET + BUILT + QC'd.** A2 (de-fixture) + A1 (deterministic injection) built;
> the B re-eval measured **GROUNDED 2/3 vs BLIND 0/3 on two confirmed gemma runs** → the OQ-2 ceiling
> was **flipped ON** (available/opt-in, per-user default still OFF pending B1). QC: BE 599 + FE 84 green;
> Playwright grounding e2e (2 contract tests green); **blackbox Playwright MCP** drove the real browser —
> a returning author ticked "Continue this book", proposed, and saw the honesty copy replaced by
> *"Grounded on 9 existing chapter(s) + 2 cast member(s); 3 existing arc(s) continued."* A3 remains a
> cross-service (knowledge-gateway TS + glossary Go) quality refinement, off the critical path — spec is
> build-ready for when that track opens. Commits: A2 `f1b34ad17` · A1 `b16a6b21d` · ceiling flip
> `3f134b96f` · Playwright `2bbca1e4a`.


> **Why this track exists.** PROPOSE-BLIND (D-PLANFORGE-PROPOSE-BLIND) is BUILT + CLOSED, but its OQ-2
> A/B eval measured **no cast-continuity improvement** (TIE 0/3, twice) — so the deploy ceiling stays
> OFF and the feature ships dark. The eval also surfaced exactly WHY, and what would make grounding
> actually work. This track turns those follow-ups (previously out-of-scope) into build-ready specs and
> executes them until grounding **measurably beats blind** — then flips the ceiling on evidence.
>
> Source: `docs/plans/2026-07-17-planforge-followups-inventory.md` (items A1–A3, B1–B2) ·
> Eval: `docs/reports/2026-07-17-propose-blind-ab-eval.md`.

## The goal (the finish line, measurable)
A grounded LLM propose on a book with existing cast **references the existing protagonist/cast
materially more than blind** — measured by the SAME A/B harness — with the delta large enough to
justify flipping `PLANFORGE_GROUND_ON_EXISTING_ALLOWED` ON org-wide. Concretely: **grounded cast
continuity ≥ blind + a real margin on ≥2 books × ≥1 model**, with no regression to cold-start propose.

## The measured diagnosis (what the eval proved)
1. A character-less braindump generates **no cast** → `normalize` pads the `Nữ chính` placeholder →
   there is nothing for prompt-grounding to anchor. (Prompt grounding *references* existing entities;
   it does not *invent* a cast.)
2. The MATERIALIZE/ANALYZE **system prompts still carry POC-fixture rules** welded to one novel
   ("use Nữ chính", "Arc 2 = exactly 7 events", specific VN traits) — they compete with grounding and
   pollute any book's output.

## The specs (each is its own build-ready doc)
| id | spec | what it fixes | size | depends on |
|---|---|---|---|---|
| **A2** | `2026-07-17-planforge-defixture-propose-prompts.md` | POC-fixture rules dominate + pollute (a real latent defect) | L | — |
| **A1** | `2026-07-17-planforge-deterministic-cast-injection.md` | grounding can't inject a cast → deterministic protagonist/cast seed | M–L | A2 (cleaner output to measure) |
| **A3** | `2026-07-17-planforge-kal-roster-cast-enrichment.md` | cast is name-only → add role/kind (richer continuity signal) | M · cross-service | — |

## Sequence + gates
1. **A2 first** — de-fixture the prompts + re-baseline the fidelity eval. Unblocks a clean measurement
   (fixtures stop injecting another novel's cast). Gate: existing fidelity suite green on a generic
   scorer; a fresh book's propose no longer contains POC artifacts.
2. **A1 next** — deterministic protagonist/cast injection. Gate: a grounded propose's
   `layers.characters[].name` contains the book's existing protagonist (unit + live smoke).
3. **B1/B2 re-eval** — re-run the A/B (char-rich braindump + on ≥1 stronger model). Gate: grounded
   beats blind by the margin above → **then** flip the ceiling (an infra + a one-line default change),
   guarded by the same fails-closed AND.
4. **A3 anytime** — when the knowledge-gateway track is open; not on the critical path (names alone
   already satisfy A1).

## Non-goals (stay out)
- Re-opening the PROPOSE-BLIND plumbing (gather lens, ceiling, grounded_on, rules-path merge) — it is
  built + correct; this track only improves the LLM-cast payoff.
- The cross-track hygiene items (C1 progress get_goal, C2 S4 SceneMotifsSection, C3 17-locale backlog)
  — each belongs to its own track, listed in the inventory for handoff, not built here.
