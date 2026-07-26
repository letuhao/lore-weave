# Context Budget Optimization — Results (2026-07-04)

Methodology: [`OPTIMIZATION-EVAL-METHODOLOGY.md`](OPTIMIZATION-EVAL-METHODOLOGY.md). Driver:
`scripts/eval/run_budget_sweep.py` (captures per-turn input/output tokens, compaction events,
first-token/total latency + a per-session aggregation incl. hidden summarizer spend). Model:
`google/gemma-4-26b-a4b-qat` via the 40K-window registration `019eeb08` ($0). All token figures
are the script-aware estimate (consistent across arms → valid for RELATIVE comparison).

## ⚑ Headline finding (S1 long session) — the current default is a REGRESSION

The task-elastic compaction flip (`COMPACT_TASK_ELASTIC_ENABLED=true`, shipped default-ON this
session) is **strictly dominated** by the flat trigger on a long session:

| S1 — 15-turn session | Recall t7 / t14 | session_total_est | summarizer calls | overhead_ratio | latency/turn |
|---|---|---|---|---|---|
| **C0** task-elastic ON *(default)* | 5/9 · 5/9 | **343,102** | **11** | **0.62** | 6–10 s |
| **C1** flat trigger (OFF) | 5/9 · 5/9 | **285,518** | 0 | 0.00 | ~1 s |

- **Quality: EQUAL.** Both recall the same facts at both checkpoints. C0's breadcrumb preserves
  recall even across 11 re-summarization cycles; C1 keeps the raw history (never compacts —
  19.8K < the 28K flat trigger) so it trivially recalls. No confabulation in either.
- **Cost: C1 is ~17% cheaper** (285K vs 343K).
- **UX/latency: C1 is ~7× faster** (~1 s vs 6–10 s per turn).

### Root cause — the automatic compaction re-summarizes EVERY turn
C0 fires compaction at t4 (input 18K→5K) **and every turn after** (comp=1, summarizer call on
t4…t14 = 11 calls). The automatic pre-send compaction operates on the RAW history re-loaded from
Postgres each turn and does **not persist** the summary — so the summarizer re-runs every turn.
The per-turn input "savings" (18K→5K) are **more than eaten** by the per-turn summarizer overhead
(**62% of the whole session's tokens**) + its latency. The per-turn token metric was misleading;
only the **session-level, hidden-spend-inclusive** cost (the whole point of the methodology)
reveals the regression.

Corroborated on S2 (short 6-turn): even there, C0's overhead was already 31% and its
session_total (116K) exceeded what a non-compacting run would cost (~103K).

## Decision (per §3 floor-then-minimize)

Both configs pass the quality/consistency floor (equal recall, zero confabulation) → minimize
cost → **C1 wins**, UX tiebreaker reinforces it. ⇒ **`COMPACT_TASK_ELASTIC_ENABLED` should
revert to default OFF.** Its recall-quality was fine (the breadcrumb works), but its *cost and
latency* are a net loss because compaction isn't persisted.

## The real optimization this surfaces — PERSISTENT compaction

The win isn't a smarter *trigger*; it's **persistence**: compact ONCE, store the summary +
mark the raw turns compacted, and reuse it — so a long session gets the lean per-turn context
**without re-summarizing every turn**. That converts the 62%-overhead loser into a genuine
saver (one summarizer call amortized over many turns, not one per turn). This is a BUILD (wire
the automatic path to the persisted-compaction store, à la the W3 manual `/compact`), and the
natural next candidate config **C_persist** — expected to beat both C0 and C1 on long sessions.

## Caveats / validity (don't over-read yet)

- **N=1, one scenario shape (S1), 40K model.** The cost/latency gap is structural (re-summarize
  every turn is deterministic), so the *direction* is robust; the *magnitude* needs N=4 + S2–S5
  to generalize. Recall scored programmatically (fact-token match); a blind-judge pass is still
  owed for the correctness/coherence scores.
- **40K model** puts the flat trigger at 28K (rarely fires) and the task-elastic target at 14K
  (fires early). On a 200K model the flat trigger is ~146K (≈never) and task-elastic ~32K — so
  C0 would still re-summarize every turn once a session crosses 32K = the same regression, just
  later. C1 on 200K ≈ "compaction basically never fires" = the safe pre-T2 behavior.

## ⚑⚑ C_persist — built + validated: the Pareto-dominant winner (S1)

**C_persist** (`COMPACT_PERSIST_ENABLED`, `compact_service.persist_auto_compact`): before loading
history, if the live history exceeds `compute_target(context_length)`, summarize the droppable
middle ONCE and **persist** `{compact_summary, compacted_before_seq}` (reusing the W3
manual-compact mechanism + loader + the deterministic breadcrumb). Later turns load the summary
via the loader — **no re-summarizing every turn.** Config: `COMPACT_PERSIST_ENABLED=true`,
`COMPACT_TASK_ELASTIC_ENABLED=false`.

Live S1 (same 15-turn session, gemma-4-26b): input ~18K for t0–t3, then **t4 persists ONCE (one
5.7 s summarizer call) → input drops to ~5K and STAYS ~5–6K for all 11 remaining turns at ~1 s
each.**

| S1 — 15 turns | Recall t7 / t14 | session cost | summarizer calls | latency/turn |
|---|---|---|---|---|
| C0 task-elastic | 5/9 · 5/9 | 343 K | 11 | 6–10 s |
| C1 flat | 5/9 · 5/9 | 285 K | 0 | ~1 s |
| **C_persist** | **5/9 · 5/9** | **~155 K**¹ | **1** | ~1 s |

¹ The driver's raw C_persist total was 135.9 K — it undercounts the ONE pre-load persist
summarizer call (~19 K; the persist is not a stream compaction event, so the driver misses it).
True ≈ 155 K — still **46% cheaper than C1 and 55% cheaper than C0.** (Driver follow-up: emit a
persist event / detect the input-drop so the cost is captured natively.)

**Verdict (capability-first):** recall is EQUAL across all three (5/9 each — the breadcrumb-led
persisted summary is as good as raw context). Capability tied → cost/latency decide →
**C_persist wins decisively** (cheapest, C1-fast). It's the config that keeps the agent just as
smart at ~½ the cost — exactly the "compact once, reuse" fix.

**Caveat:** S1 triggered only ONE persist cycle. A very long session (30+ turns) triggers a 2nd+
persist that FOLDS the prior summary into a new one (summary-of-summary) — untested for drift.
Needs a multi-cycle scenario before default-on.

## Confirmation runs — C_persist cleared both gates

**Multi-persist-cycle drift (S1-XL, 30 turns, gemma-4-26b):** C_persist fired **2 persist cycles**
(t4 + t29, the 2nd folding the 1st summary = summary-of-summary). Recall at t9/t19/t29 was
**stable 7/9 at all three** — no drift across the fold, no confabulation (t29 named Verithrax,
Oldan Vex, seven star-anchors, 4,400 salt-marks, Warden Sarel Vex/estranged-brother, the
Lantern-Guild betrayal; the 2 omitted items — forge location, lamp detail — are abbreviations,
absent from t9 onward, not lost over cycles).

**Blind capability judge (cold-start Agent, the S1-XL outputs):** `depth_nuance 5/5`,
`consistency 5/5`, `collaborative_competence 5/5`, `craft_quality 4/5`, `confabulation false`,
`degrades_over_session false`. Verdict: *"richly anchored in the established world… zero canon
contradictions… neither shallow nor world-blind. A collaborator a human would gladly keep working
with."* — i.e. compression did NOT make the agent dumber (the capability-first concern). (Craft
docked one point for stock adjectives, unrelated to compression.)

**Measurement is provider-truth:** the agent cost is the real LM Studio usage
(`chat_messages.input_tokens`/`output_tokens`); the sweep driver was upgraded to read it (the one
estimate left is the unmetered BYOK-local summarizer). The earlier A/B numbers were already
input-accurate (`used_tokens == chat_messages.input_tokens`, t4=5,347 in both).

## Decision — DONE (defaults flipped)

1. **`COMPACT_TASK_ELASTIC_ENABLED` → default OFF** ✅ (the confirmed cost/latency regression).
2. **`COMPACT_PERSIST_ENABLED` → default ON** ✅ (C_persist — the sweep winner: capability equal
   or better, ~46% cheaper, C1-fast, drift-free, judge-passed). The capability-first rule
   (maximize usefulness under cost ceilings) selects it decisively.

## Remaining (optional hardening)

- Broader sweep S2–S5 × N=4 for variance/generalization (the S1 direction is structural).
- A stronger-model spot-check (gemma's weak tool-use understates the recovery net).
- Driver: emit a native persist event so the summarizer cost is captured, not estimated.
