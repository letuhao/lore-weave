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

## Next steps

1. **Revert `COMPACT_TASK_ELASTIC_ENABLED` → default OFF** (evidence above) — pending user OK
   (it reverses this session's approved flip).
2. Build **C_persist** (persistent automatic compaction) and A/B it vs C1 on S1 (+ S2–S5).
3. Complete the sweep: author S3/S4/S5, run C1 vs C_persist × N=4, blind-judge pass, scorecard.
