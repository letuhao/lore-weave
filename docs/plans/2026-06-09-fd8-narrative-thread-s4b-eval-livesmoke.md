# FD-8 / narrative_thread S4b — eval arm (dropped-promise-rate) + full-loop live-smoke

**Cycle:** LOOM-67 · **Size:** M (code) / effort-L (powered run + stack-up) · **Branch:** `feat/composition-service`
**Predecessors:** S1 foundation (LOOM-58) · S2 producer (LOOM-64) · S3 re-injection (LOOM-65) · S4a debt-check BE (LOOM-66)
**PO decisions (CLARIFY):** both deliverables in ONE cycle; eval **powered n=3+**.

## Goal

Prove the narrative_thread ledger **works** (full loop fires live) AND **helps**
(reduces dropped promises) — the §8 validate-first eval gate for the whole FD-6/7/8
Phase-B spine. Ledger is ADVISORY (D4); this cycle measures, it does not gate generation.

## Two deliverables

### A. Full-loop live-smoke (a real stack)
The loop, end-to-end, on the live stack (composition + book + glossary + knowledge +
provider-registry + Postgres + Neo4j + Redis + LM Studio via provider-registry; auth
booted or a minted JWT):

1. enable `narrative_thread_enabled=true` on a Work (PATCH settings)
2. generate scene 1 → **S2 opens** a promise → assert `GET …/narrative-threads` `open_count > 0`
3. generate a later scene with the flag on → **S3 re-injects** → assert (deterministic)
   the new `reinjected_promise_count > 0` on the generate response
4. observe **S2 pays** a resolved thread → assert (best-effort, LLM-nondeterministic) an
   `open → paid` transition appears in the ledger over the arc
5. control: a flag-OFF Work shows `reinjected_promise_count == 0` and no narrative_thread rows

**Hard (deterministic) asserts:** #2 (open created), #3 (re-injection count), #5 (control).
**Soft (observed):** #4 (a pay) — reported, not gated (depends on the LLM resolving a promise).

### B. Eval arm — dropped-promise-rate (powered n=3+)
For each of n≥3 promise-rich books, build one book + a multi-chapter decompose plan, then
**generate the full arc TWICE**:
- **arm ON** — `narrative_thread_enabled=true` (S2 opens/pays, S3 re-injects+steers)
- **arm OFF** — flag off (no ledger, no re-injection)

Then a **DISJOINT promise-judge** scans each arm's full arc prose and returns
`{introduced, resolved, dropped}` → `dropped_rate = dropped / max(1, introduced)`.
Compare `dropped_rate` ON vs OFF per book + mean across n.
**Hypothesis:** ON < OFF (re-injection makes the model honor/pay open promises).

## Critical eval-design guards (lessons)

1. **Disjoint detection (the self-reinforcement trap, `eval-self-reinforcement`).** The
   promise-judge MUST re-detect promises from the PROSE — it must NOT read the
   `narrative_thread` ledger. If it read the ledger, the OFF arm (no ledger) would score
   0 introduced → 0 dropped by construction, a fake win. Same judge prompt + same judge
   model over both arms' prose = apples-to-apples.
2. **Disjoint judge model (`eval-self-reinforcement`, ~4–5pp).** Judge model ≠ drafter
   model where the registry has two; else the extractor self-grades. Document the caveat
   if only one local model is registered.
3. **Local-LLM-first (`local-llm-first-cloud-fallback`).** Drafter + judge = LM Studio
   models via provider-registry; cloud is calibration-only (cost).
4. **Saturation / honesty (`eval-metric-saturation`).** Promises need LONGER multi-scene
   arcs to exist + drop. Report per-book + mean; if both arms ceiling (0 introduced on
   short content), say so — a tie is not a pass. n=3 is "powered" per PO but still
   directional; do not over-claim.
5. **Judge input is the measurement (no sanitize).** The judge receives generated prose
   AS the thing being judged — sanitizing it would corrupt the metric. Mirror the existing
   `pairwise_judge` precedent (server-controlled prompt, robust delimiting, no content
   sanitize). This is internal eval, not user-facing generation, so the
   `new_prompt_block_must_reuse_sanitize` rule (which governs generation context blocks)
   does not apply — but the judge prompt must delimit the prose robustly against
   forged-delimiter confusion.

## Code changes (prod — minimal, advisory observability)

| File | Change |
|---|---|
| `app/packer/pack.py` | `PackedContext.reinjected_promise_count: int = 0`; set `= len(open_promises)` (the gathered re-injected set; 0 when flag off / no repo / none open). |
| `app/routers/engine.py` | echo `reinjected_promise_count` on the scene-auto + chapter generate responses (advisory, alongside S4a's `open_promise_count`). |
| `app/engine/promise_audit.py` (NEW) | `audit_promises(llm, *, user_id, model_source, model_ref, arc_text, source_language)` → `{introduced[], resolved[], dropped[], introduced_count, resolved_count, dropped_count, dropped_rate}`. Server-controlled prompt; reasoning-disabled (FD-4 lesson); degrade-safe (zeros + error on LLM/parse fail). Re-detects from PROSE only. |
| `app/routers/internal_eval.py` | `POST /internal/composition/eval/promise-audit` (X-Internal-Token, `user_id` in body for BYOK resolution) → `audit_promises`. |

## Dev tooling (NEW, not shipped in the image)

| File | Change |
|---|---|
| `scripts/eval_narrative_thread.py` | The n-book ON/OFF harness + the inline full-loop live-smoke. Modeled on `eval_a_grounded.py` (login, models, book/chapter/work/decompose, generation). |

## Tests (unit)

- `tests/unit/test_promise_audit.py` — audit parse (well-formed → counts + dropped_rate), degrade (LLM raises → zeros + error), dropped_rate math (introduced=0 → rate 0, no div-by-zero), reasoning-disabled kwargs present, a forged-delimiter prose body doesn't break parsing.
- `tests/unit/test_internal_eval_promise_audit.py` — the route delegates + returns the audit; never raises on degrade.
- `tests/unit/test_pack.py` (extend) — `reinjected_promise_count == len(open_promises)` when flag on; `== 0` when flag off / no repo. Non-default lock (set 3 open promises → assert 3, not a hardcoded 0/1).
- `tests/unit/test_engine_router.py` (extend) — the generate response echoes `reinjected_promise_count`.

## VERIFY (evidence gate)

- Full composition unit green (target ~400+).
- **Cross-service live-smoke token REQUIRED** (this cycle is the live-smoke): run
  `scripts/eval_narrative_thread.py 3` against the up stack → record the ON-vs-OFF
  dropped-rate table + the full-loop asserts (#2/#3/#5 deterministic pass; #4 observed).
  If the stack/LM-Studio can't be brought up at dev time → `live infra unavailable: <reason>`
  and defer the run to `D-NARRATIVE-THREAD-S4B-LIVE-SMOKE`.

## /review-impl

Run at POST-REVIEW — new internal endpoint + new LLM-judge abstraction + a new prose
consumer path (memory `review-impl-on-design-cycles`). Focus: the self-reinforcement
guard (judge must not read the ledger), the dropped_rate denominator, degrade paths,
the reinjected-count semantics vs the S4a open_promise_count.

## Out of scope (deferred)

- Formal `ReasoningState` / `generation_job.state` persistence (resumable runs) — optional S3 follow-up, separate concern.
- The steer/spoiler position-filter forward-leak edge (recorded in S3).
