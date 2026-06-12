# Composition quality — measured results (DURABLE; do NOT re-measure without reason)

> Recorded 2026-06-10 (LOOM-68→72) so we never spend LLM budget re-running these.
> Harness: `services/composition-service/scripts/eval_narrative_thread.py`
> (`--mode=chapter`, `--drafter=<id>`, `--decompose=<id>`). Eval v2 = a FIXED
> SPEC-derived promise set (premise+plan, ledger-blind) scored on both arms as
> paid/progressing/abandoned/absent (denominator-stable). Judge = local gemma
> (disjoint). All runs n=3, chapter mode (single-pass per chapter → arcs reach
> payoff so pay-rate discriminates; per_scene+short-tok truncates → pay-rate≈0).

## The numbers (n=3 chapter, gemma judge)

| metric (↑/↓ better) | qwen3.6-35b-a3b (local) OFF / ON | gpt-4o OFF / ON |
|---|---|---|
| **pay-rate** paid/introduced ↑ | 0.500 / 0.292 | **0.613 / 0.628** |
| **paid/tracked** (strict denom) ↑ | 0.477 / 0.292 | **0.613 / 0.614** |
| **abandon-rate** ↓ (the real "dropped") | 0.056 / 0.000 | 0.074 / **0.033** |
| **sustained** (paid+live) ↑ | 0.926 / — | 0.926 / **0.967** |
| **trigram-repeat** ↓ | ~0.046–0.053 | **0.035 / 0.035** |
| **opening-repeat** ↓ | ~0.034–0.039 | **0.000 / 0.008** |

(OFF = narrative_thread ledger off; ON = ledger on. Per-book gpt-4o pay ranged
0.38→1.00; book-3 ON paid 0.91.)

## Conclusions (the expensive part — keep)

1. **Architecture is SOUND; the prose ceiling was the local 35B model.** Same
   pipeline + a strong drafter (gpt-4o) → clean, tic-free prose (no "the wind did
   not X; it Y" tic, no `紧绷` CJK-leak), beats qwen on every metric. The earlier
   per_scene "re-establishment/seams" critique was mostly MODE-choice (chapter mode
   fixes it) + the model.
2. **The narrative_thread ledger's value is MODEL-DEPENDENT.** On weak qwen the
   ledger HURT pay (0.500→0.292 — it juggles more open threads, resolves fewer). On
   gpt-4o it is neutral-to-positive: pay flat (0.613→0.628), abandon ↓
   (0.074→0.033), sustained ↑ (0.926→0.967). A capable model uses the re-injected
   open-promises constructively; a weak one gets distracted.
3. **The §8 Phase-B-expansion gate is still not DECISIVELY met** (gpt-4o ledger
   lift is small, within n=3 noise; 1/3 books). But the verdict flipped from
   "neutral/negative" (qwen) to "neutral-to-mildly-positive" (gpt-4o). Keep the
   ledger opt-in, default-ON-worthwhile for capable drafters; do NOT build
   FD-9/10/12/13 purely on this.
4. **Quality levers, in order:** (a) author-selectable stronger drafter (exposed
   LOOM-69 settings default-model) — biggest lever; (b) chapter mode; (c) the
   ledger ON for strong models; (d) anti-repetition clause (mild, model-bound).

## Cost reference
- gpt-4o n=3 chapter eval: **~$0.34 on the OpenAI console** (~$0.18 by our internal
  `usage_logs` — a ~2× under-count flagged as a billing-accuracy FD). Local
  (qwen/gemma) arms are $0. Cheap, but recorded here so we re-run only with reason.
- Cadence: gpt-4o calls are SERIAL (no throttle) — ~12–17s per ~2k-token chapter
  draft; one book ≈ 210–246s. Parallelizable ~3× at the same spend if ever needed.
