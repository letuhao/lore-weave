# Continent-Scale Measurement + Per-Zone L3 Batching — Spec

> **Track:** `LLM_MMO_RPG` tilemap-service · **Branch:** `mmo-rpg/zone-map-amaw`
> **Workflow:** default v2.2 human-in-loop · **Size:** L
> **Plan:** [`docs/plans/2026-05-18-tilemap-continent-measurement.md`](../plans/2026-05-18-tilemap-continent-measurement.md)

---

## §1 Context

The tilemap engine (placers + the engine→L3→L4 bootstrap) is complete, but every
verification so far was mock-gateway or small-reality (48²). The only **live**
data point is the Phase-0b 3-object run. This task produces a **continent-scale
measurement**: generation timing at 256², and a live engine→L3→L4 run against
lmstudio.

The L3 classifier today sends **all** objects in one tool call — fine for 48²
(~80 objects) but a 256² continent emits hundreds–thousands; one call would
overwhelm a local model. **PO-1 (CLARIFY 2026-05-18): build per-zone L3 batching
now**, so a continent can be classified in bounded chunks.

## §2 Scope

### In scope
- **`run_l3_batched`** — group L3 placeholders by `zone_id`, sub-chunk any zone
  exceeding a batch cap, run the existing `run_l3_with_retries` per batch, and
  aggregate the `L3Result`s. The §6 "every object classified exactly once"
  invariant holds across the union.
- **A continent template** — a `TilemapTemplate` with enough zones to be a real
  continent, placed at `GridSize::CONTINENT_DEFAULT` (256²).
- **A `measure` CLI subcommand** — offline: time `place_tilemap` at 256² + report
  zone/object/road/river counts. Live: run engine→L3-batched→L4 against the
  gateway, report per-stage token totals, attempt/fallback counts, elapsed.
- **A findings doc** capturing the measured numbers.

### Out of scope
- **L4 batching** — a continent has far fewer zones than objects, so the L4
  zone-narration payload is much smaller; if it still proves too large that is a
  *measurement finding*, not a build item here.
- HTTP service surface, Postgres, Forge AdminActions (DESIGN.md §9 Phase 4+).

## §3 Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | `run_l3_batched` groups placeholders by `zone_id` (first-appearance order), sub-chunks any zone over the batch cap, and runs `run_l3_with_retries` once per batch. |
| AC-2 | The aggregated `L3Result` classifies **every** input object **exactly once** — the §6/D6 invariant holds across the batch union (no duplicate, no drop). |
| AC-3 | `llm_attempts` and `fallback_count` of the aggregate are the sums of the per-batch values; classifications are the concatenation. |
| AC-4 | A continent template places at 256² and yields many zones + a large object set; placement is deterministic for a fixed seed (TMP-A4). |
| AC-5 | `measure` offline path times `place_tilemap` and reports zone/object/road/river-segment counts + elapsed wall time. |
| AC-6 | `measure` live path runs engine→L3-batched→L4 against the gateway and reports per-stage token totals, attempt + fallback counts, and elapsed time; any gateway failure is recorded in the report, never panicked (the Phase-0b honesty precedent). |
| AC-7 | A findings doc records the measured continent numbers (offline timing; live token cost + latency + classification quality, infra permitting). |

## §5 Module design

### §5.1 Token totals on `L3Result` / `L4Result`

A token-cost measurement (the D1 motivation) needs per-stage token counts, but
`run_l3_with_retries` / `run_l4_with_retries` discard the per-attempt
`L3Attempt` / L4-attempt token fields. Extend both result structs with
`input_tokens: u32` + `output_tokens: u32`, **summed across every attempt**
(each loop already holds the `outcome`). Additive — existing field readers are
unaffected; the two struct construction sites (`run_l3_with_retries`,
`run_l4_with_retries`) are updated.

### §5.2 `run_l3_batched` (`harness/retry.rs`)

```
pub async fn run_l3_batched(client, model_source, model_ref, user_id,
    placeholders: &[L3Placeholder], book_canon_refs: &[String],
    max_attempts: u32, batch_size: usize) -> crate::Result<L3Result>
```

1. **Entry precondition** (the sole `Err` path, mirrors `run_l3_with_retries`):
   every `obj_id` globally unique + every `suggested_canon_kind` non-empty —
   checked once, before batching, so a cross-batch duplicate cannot slip the
   per-batch checks.
2. Group placeholders by `zone_id` in **first-appearance order** (deterministic).
3. Each zone group → `chunks(batch_size)` sub-batches.
4. `run_l3_with_retries` once per sub-batch.
5. Aggregate: `classifications` concatenated, `llm_attempts` / `fallback_count`
   / `input_tokens` / `output_tokens` summed. Batches are a disjoint partition
   of the input, so the union classifies every object **exactly once** (AC-2).
- Empty input ⇒ an empty `L3Result` (0/0/0).
- `L3_BATCH_SIZE: usize = 40` — the default cap the `measure` command passes.

### §5.3 Continent template (`harness/continent.rs`, NEW)

`continent_template()` — a `TilemapTemplate` of ~16 zones built by a loop: a
`Hub` capital, a chain of `Wilderness` regions (each with a `min ≥ 2000`
`treasure_tiers` entry), two `Sea` zones, and a `Portal`-reached `Forbidden`
vault. Connections form a connected graph. Placed at
`GridSize::CONTINENT_DEFAULT` (256²).

### §5.4 `measure` subcommand (`harness/continent.rs` + `main.rs`)

`measure_continent` orchestration:
- **Offline** (always): time `place_tilemap(continent_template, 256²)`; record
  zone / object / road-segment / river-segment counts + elapsed.
- **Live** (when the gateway env is present): `engine_placeholders` →
  `run_l3_batched` → `build_l4_inputs` → `run_l4_with_retries`; record per-stage
  token totals, attempt + fallback counts, batch count, elapsed. A gateway
  failure is recorded in the report, never panicked (Phase-0b precedent).

`MeasurementReport { offline: OfflineMeasurement, live: Option<LiveMeasurement> }`
+ `render_measurement_report`. `main.rs` gains `measure` →
`run_measure()` (offline always; live when `gateway_from_env()` succeeds).

`bootstrap.rs` — `engine_placeholders` is lifted to `pub(super)`, and the L4
input join is extracted to `pub(super) fn build_l4_inputs(&TilemapView,
&[L3Placeholder], &L3Result) -> Vec<ZoneNarrationInput>`, reused by both
`bootstrap_small_reality` and `measure_continent` (no duplication).

### §5.5 File census

| File | Change |
|---|---|
| `harness/retry.rs` | MOD — `L3Result` token fields; `run_l3_batched` + `L3_BATCH_SIZE` |
| `harness/l4_retry.rs` | MOD — `L4Result` token fields, summed across attempts |
| `harness/bootstrap.rs` | MOD — `engine_placeholders` → `pub(super)`; extract `build_l4_inputs` |
| `harness/continent.rs` | **NEW** — `continent_template`, `measure_continent`, report types + render |
| `harness/mod.rs` | MOD — `pub mod continent;` |
| `main.rs` | MOD — `measure` subcommand |
| `docs/measurements/2026-05-18-continent.md` | **NEW** — findings doc |

### §5.6 Test plan

- `run_l3_batched` against the mock gateway: a multi-zone placeholder set is
  classified across batches; the aggregate covers every `obj_id` exactly once
  (AC-2); attempts/fallbacks/tokens sum (AC-3); a zone exceeding `batch_size`
  sub-chunks; empty input ⇒ empty result; a duplicate `obj_id` ⇒ `Err`.
- `continent_template` + `place_tilemap`: places at 256², many zones, large
  object set, deterministic for a fixed seed (AC-4).
- Token sums on `L3Result` / `L4Result` round-trip a mock `usage` event.

