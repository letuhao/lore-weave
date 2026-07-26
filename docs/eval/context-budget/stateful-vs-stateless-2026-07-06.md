# Stateful `/v1/responses` vs stateless — 12-turn A/B eval

**Date:** 2026-07-06 · **Model:** `google/gemma-4-26b-a4b-qat` (LM Studio, local, $0) ·
**Branch:** `feat/context-budget-law` · Validates [Provider Context Strategy P2](../../specs/2026-07-06-provider-context-strategy-p2-transport.md)
(§12 verification) · Commits `d1f967ab2` (P2.a) + `f5c9a874d` (P2.b/c).

## Method

Identical 12-turn worldbuilding chat run twice through the real stack (gateway → SDK →
chat-service → LM Studio), once with `LLM_STATEFUL_CACHE=0` (stateless, today's default)
and once with `=1` (stateful). The scenario establishes facts (hero Kael/blacksmith,
village Emberfall, villain Sorenth, weapon Dawnbreaker, fortress Rimehold, …) and
interleaves **4 fact-recall questions** (turns 5, 8, 10, 12) that force the model to
answer from earlier context — the answer-quality gate. Per turn we capture the
persisted `contextBudget.caching` frame (`used_tokens`, `read_tok`, `uncached_tok`,
`hit_rate`) and check the recall answer contains the expected facts.

The base context is **tool-schema-dominated** (~29.4K fixed: advertised tool schemas +
system + memory), so this directly exercises the original context-explosion case — the
fixed tool base re-sent every turn (`docs/eval/context-budget/context-explosion-investigation-2026-07-06.md`).

## Result

| Metric (Σ over 12 turns) | Stateless | Stateful | Δ |
|---|---|---|---|
| **Uncached tokens** (billed at full rate) | 355,126 | **29,753** | **−91.6%** |
| Cache-read tokens (served warm) | 0 | 325,351 | — |
| Total input processed | 355,126 | 355,104 | ~equal |
| **Fact-recall correctness** | **4/4** | **4/4** | **no change** |

Per-turn shape:
- **Stateless:** every turn re-sends the full ~29.5K (hit_rate 0.00) — the fixed tool
  base is paid in full, every turn.
- **Stateful:** turn 1 establishes (29,440 uncached, the one-time cost); turns 2–12 send
  only the **~27-token delta** each (hit_rate **1.00**) — the tool base + history are
  held server-side and served from cache.

**91.6% of the stateful input was served from cache**; the billed-at-full-rate volume
dropped from 355K to 29.7K. Answer quality is identical — the provider holds the full
context, so recall is unaffected (4/4 both arms).

## Interpretation

- **P2 is a decisive win for the common (tool-heavy) chat turn** — it removes the exact
  re-prefill that inflated cost in the original investigation, with **no quality cost**.
- This scenario keeps short turns, so the accumulated context never approached the model
  window (~29.7K ≪ 200K). The **P3 window-boundary case (E5 smart re-chain) was NOT
  exercised** — the P2 §5a rule-4 guard is present but never fired. Per the repo's
  fix-when-profiling-shows-pain rule, P3's compaction-cache-write-penalty + intelligent
  re-chain **tuning stays deferred** until a long-session (window-approaching) eval shows
  it matters. No pain observed in the common case.

## Recommendation

The evidence supports **flipping `LLM_STATEFUL_CACHE` on** (for `responses_api` providers)
after a broader model/scenario sweep. The path is capability-gated + degrade-safe (E1
re-establish live-verified) and default-off today, so a staged rollout is low-risk.

## P3 addendum — the window-boundary case (long sessions)

The 12-turn A/B never neared the window, so a separate **22-turn growing-context probe**
(~2K filler/turn) exercised the boundary + the P3 chain-management fixes:

- **Correct across a long session** — recall of a turn-1 secret **passed after 21 turns**
  of filler; no overflow, no crash. Continue turns held **~95% cache** (uncached ~2K vs a
  50–73K accumulated context).
- **The accumulated server-side size grows** (32K→73K) — stateful holds the full chain,
  unlike stateless (which the compaction keeps ~32K). So the chain MUST be bounded.
- **R1 bug fixed:** rule-4 was reading the persisted `input_tokens`, which SUMS the
  tool-loop (an N-iteration turn ≈ N× the real context) → the window guard fired ~N× too
  early. Now it reads the **true single-call `context_size`** (the last completion's
  `input_tokens`), surfaced on the `caching` frame; `chain_action` (continue /
  establish_first / reestablish_{stateless_prev,model_switch,compaction,window}) is
  surfaced too so a re-chain is visible + attributable.
- **Bounded re-chain verified** (via an artificial low cap `LLM_STATEFUL_MAX_CHAIN_TOKENS=45000`
  to force the boundary at turn 9 instead of ~90): the re-establish **resets** `ctx_size`
  (46947→39107 — it sends a *compacted* context, not the accumulation), then cycles
  39K↔47K — **no overflow, no thrashing** (re-establish ~every 5 turns, not every turn).
- **Key finding — keep the re-chain threshold NEAR the window.** At the 45K cap (22% of a
  200K window) recall FAILED: forcing compaction that early summarized away the turn-1
  fact. At the default (`0.75 × effective_limit` ≈ 143K for 200K) the chain holds the full
  recent history far longer and recall held. **The real long-session lever is the T6
  fact-preserving summarizer's *quality* at the boundary**, not the chain logic — a
  separate, existing Context-Budget-Law concern. The optional `LLM_STATEFUL_MAX_CHAIN_TOKENS`
  cap exists only for a provider that loads a smaller `n_ctx` than advertised; it should be
  set near that real window, never low.

## Reproduce

`scratchpad/eval_stateful.py <mode> <out.json>` run once per arm (toggle the flag via
`infra/docker-compose.stateful-smoke.yml`), then diff the two JSONs. Raw per-turn data
captured 2026-07-06.
