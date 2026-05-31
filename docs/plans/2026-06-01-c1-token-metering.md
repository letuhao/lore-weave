# PLAN — C1 real token metering (DEFERRED-052)

> Branch: `lore-enrichment/foundation` · Size: **L** (7 src files + tests, side-effect: cost-cap behavior) · Mode: default v2.2 (human-in-loop)
> Closes the last "real token metering" gap before P2/P3 multi-call strategies go live (PO ruling, audit C1 / DEFERRED-052).

## CLARIFY (PO-signed-off 2026-06-01)

- **Cap units** → **Real tokens (re-scale).** `max_spend_usd` (legacy column name) is reinterpreted as a TOKEN budget. The `cost.py` unit was already declared opaque/no-currency; this makes it concretely *tokens*, consistent with chat/knowledge (provider-registry bills `input+output(+reasoning)` tokens).
- **Embed leg** → **Estimate via platform char-convention.** `/internal/embed` returns no token usage (foundation contract, out-of-scope to change on this branch). Estimate embed input tokens from the query text with the platform's `EstimateTokens` formula. Track a follow-up deferral to add real embed usage to provider-registry later.
- **Charge model** → **Pre-estimate gate + post-actual reconcile.** BEFORE a gap: charge a conservative token estimate (so a runaway pauses before the next gap). AFTER the gap: reconcile to the ACTUAL tokens. One gap may overshoot the working cap; the 15% eval-reserve absorbs it. Mirrors provider-registry reserve/reconcile.

## Platform token convention (verified, the SSOT we mirror)

- LLM stream emits a final `event: usage` frame: `{input_tokens, output_tokens, reasoning_tokens}` — reasoning bills as output. (`provider-registry .../streamer.go`, `stream_billing.go`.) **Currently discarded by `complete.py:collect_stream_text`.**
- `/internal/embed` returns only `{embeddings, dimension, model}` — **no token usage.**
- Char→token: `ceil(chars / divisor)`, divisor `1.0` when non-ASCII share ≥ 0.2 (CJK), else `3.5`. (`provider-registry .../billing/estimate.go:estimateInputTokens`.)

## DESIGN

Metering is harvested **at the seam** via a per-job `UsageMeter` the runner observes — so the `complete → str`, `generate → facts`, `run_gap → StageResult` contracts stay **unchanged** (no blast to fabrication/recook/generate or their stubs). The meter is the cross-cutting carrier; the runner reconciles per gap from the meter delta.

| # | Change | File |
|---|---|---|
| D1 | `TokenUsage` (input/output/+`.total`/`__add__`), `estimate_tokens(text)` (platform char-convention), `UsageMeter` (sequential accumulator) | **NEW** `app/jobs/tokens.py` |
| D2 | Parse the `usage` SSE frame → `TokenUsage`; `make_complete_fn(..., meter=None)` adds real usage (or estimate-fallback from prompt+text when the frame is absent) to the meter. Returns `str` (contract unchanged). | `app/generation/complete.py` |
| D3 | `make_embed_query_fn(..., meter=None)` adds `TokenUsage(input=estimate_tokens(query))` per call. Returns vector (unchanged). | `app/retrieval/embedding.py` |
| D4 | Re-denominate `RETRIEVAL_GAP_COST`/`GENERATION_GAP_COST` to **token** magnitudes (conservative per-gap pre-charge); add `JobCostBudget.reconcile(delta)`. | `app/jobs/cost.py` |
| D5 | `CostGuardrail.record_actual(delta)` — unconditional spend true-up (work already ran; negative delta refunds; floors at 0). | `app/jobs/cost_guardrail.py` |
| D6 | `JobRunner(..., meter=None)`; per gap: snapshot meter after the pre-charge, run gap, `reconcile(meter_delta − pre_estimate)` on success AND skip. | `app/jobs/runner.py` |
| D7 | Construct one `UsageMeter`; wire into both seams; pass it to the runner **only on the P1 (GapCostModel) branch**; P2/P3 pass `meter=None` (opaque pre-charge unchanged, gate-locked). Document the token-unit reinterpretation. | `app/jobs/assembly.py` |

**Pre-charge constants (tokens):** `RETRIEVAL_GAP_COST = 64.0` (embed query upper-ish), `GENERATION_GAP_COST = 1200.0` (grounding prompt + completion, typical) → `PER_GAP_WORKING_COST = 1264.0`. Conservative typical; reconcile trues-up to real.

**Sequential-safety invariant:** the per-gap meter delta is correct because the runner processes gaps strictly sequentially (awaits each fully). Documented in the runner; if gaps are ever parallelized, the meter must become per-gap-scoped.

**Deferral (new):** token-denominate P2/P3 `estimate_cost` + enable meter-reconcile for fabrication/recook **when the eval gate activates them** (they currently pre-charge opaque 8.0/12.0 and are gate-locked → not live, so no unit mismatch today; the runner gets `meter=None` for those branches).

## BUILD — TDD tasks (RED → GREEN per task)

| T | Task | Files | Test gate |
|---|---|---|---|
| ☐ T1 | `tokens.py`: `TokenUsage` + `estimate_tokens` + `UsageMeter` | `app/jobs/tokens.py` | **new** `test_tokens.py`: CJK divisor=1.0, Latin=3.5, ceil, empty=0; `TokenUsage.__add__`/`.total`; meter accumulates + snapshot delta |
| ☐ T2 | `complete.py`: parse `usage` frame + meter add + estimate-fallback | `app/generation/complete.py` | `test_generation_complete*`: usage frame → real TokenUsage; no frame → estimate(prompt,text); meter receives; `str` return unchanged |
| ☐ T3 | `embedding.py`: meter add of `estimate_tokens(query)` | `app/retrieval/embedding.py` | new/extended embed-seam test: meter gains query-token estimate; vector return unchanged |
| ☐ T4 | `cost.py` + `cost_guardrail.py`: token constants + `reconcile`/`record_actual` | `app/jobs/cost.py`, `app/jobs/cost_guardrail.py` | `test_job_cost.py` + `test_cost_guardrail.py`: token-magnitude per-gap; reconcile up/down; floor at 0; reconcile may exceed working_cap then next pre-check pauses |
| ☐ T5 | `runner.py`: per-gap reconcile from meter delta (success + skip) | `app/jobs/runner.py` | `test_job_runner.py`: actual<estimate refunds headroom (more gaps fit); actual>estimate overshoots one gap then pauses; skip reconciles embed-only spend |
| ☐ T6 | `assembly.py`: wire meter into seams + runner (P1 only); doc unit | `app/jobs/assembly.py` | assembly import/smoke (no DB); guard test: P1 runner gets a meter, P2/P3 get None |
| ☐ T7 | Deferral row (DEFERRED-059) + SESSION_HANDOFF + this plan tracker | docs | n/a |
| ☐ T8 | VERIFY: full pytest suite green + live-smoke (or documented infra skip) | — | suite pass count recorded; cross-service token-meter live-smoke or explicit defer |

## Acceptance

- The cost-cap charges **real tokens**: a P1 job's `actual_cost` reflects (real LLM input+output tokens) + (estimated embed tokens), not a fixed 5.0/gap.
- Cap still **bites before** a runaway (pre-estimate gate intact); a cheap job that under-runs its estimate gets headroom back (reconcile down).
- `complete`/`generate`/`run_gap` signatures unchanged → fabrication/recook + all existing stubs unaffected.
- Suite green; live-smoke confirms a real LLM `usage` frame is harvested into the budget (or explicit infra-skip).

## Progress tracker (single source of truth)

- ✅ T1 tokens.py — `TokenUsage`/`estimate_tokens`/`UsageMeter`; 9 tests (`test_tokens.py`)
- ✅ T2 complete.py usage harvest — `collect_stream_usage` (reasoning→output) + `meter` param + estimate-fallback; 6 tests (`test_generation_complete.py`); `str` contract unchanged
- ✅ T3 embedding.py meter — `make_embed_query_fn(meter=)` adds `estimate_tokens(query)`; 2 tests (`test_embedding_seam.py`)
- ✅ T4 cost.py + cost_guardrail.py — token constants (embed 64 / gen 1200); `JobCostBudget.reconcile` + `CostGuardrail.record_actual` (unconditional, floors at 0); +5 tests
- ✅ T5 runner.py reconcile — `JobRunner(meter=)`; per-gap snapshot + `_reconcile_gap` on success AND skip; 4 reconcile tests + 1 no-meter back-compat
- ✅ T6 assembly.py wiring — one `UsageMeter` wired into both seams; passed to runner **only on the P1 branch** (`runner_meter`); P2/P3 `meter=None`. **Also re-denominated P2/P3 pre-charge to tokens** (`FABRICATION_GAP_COST` 8→3000, `RECOOK_GAP_COST` 12→4500) to keep all pre-charges in one unit + preserve tier ordering (their *reconcile* stays deferred → DEFERRED-059). +2 strategy files.
- ✅ T7 deferral (DEFERRED-059) + SESSION_HANDOFF + this tracker
- ✅ T8 VERIFY — unit suite **499 passed / 29 skipped** (was 471, +28, 0 regress); **live smoke:** provider-registry `/internal/llm/stream` (qwen3.6) emitted `usage` frame → meter harvested real **input=24/output=832** tokens (not estimate). 2-stage code review: 0 issues.

**Scope note (announced):** the token re-denomination forced P2/P3 pre-charge constants into token units too (else a latent unit-mismatch: an 8-token cap pre-charge wouldn't bite a P2 job). Mechanical (2 constants + 2 stale comments); still **L** (9 files). P2/P3 *post-call reconcile* remains deferred (gate-locked, not live) → DEFERRED-059.

## /review-impl (adversarial pass at POST-REVIEW) — 2 fixed, 2 accepted

- ✅ **MED-1 fixed** — an `event: usage` frame present but with NO counts (`total == 0`, some OpenAI-compatible local servers) bypassed the estimate fallback → the gap was metered as **0 tokens**, silently weakening the cap. Fixed in `complete.py`: fall back to the char-estimate when `usage is None OR usage.total == 0`. Test `test_complete_fn_empty_usage_frame_falls_back_to_estimate`.
- ✅ **LOW-1 fixed** — usage counts weren't clamped ≥ 0; a buggy/hostile upstream could refund headroom with negatives. Fixed: `max(0, …)` in `collect_stream_usage`. Test `test_collect_stream_usage_clamps_negative_to_zero`.
- **LOW-2 accepted** — `actual_cost_usd` column now stores tokens (legacy name; functionally consistent, documented in DEFERRED-052).
- **COSMETIC accepted** — SSE body parsed twice (`collect_stream_text` + `collect_stream_usage`); bodies are small.
- Verified NOT broken: reconcile robust to pre-charge magnitude; skip reconciles embed-only; resume seeds token spend + skips done gaps; single-gap overshoot bounded upstream by provider-registry's own stream hard-abort; multi-usage-frame → last wins.
- Suite after fixes: **501 passed / 29 skipped**.
