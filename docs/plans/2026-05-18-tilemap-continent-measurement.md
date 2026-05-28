# Continent Measurement + L3 Batching — Build Plan

> **Spec:** [`docs/specs/2026-05-18-tilemap-continent-measurement.md`](../specs/2026-05-18-tilemap-continent-measurement.md)
> **Size:** L · 6 TDD build chunks.

---

## Chunk 1 — Token totals on `L3Result` / `L4Result`

`harness/retry.rs` + `harness/l4_retry.rs`: add `input_tokens` / `output_tokens`
to both result structs, summed across every attempt's `outcome`. Update the two
construction sites. Test: a mock `usage` event's tokens surface on the result.

## Chunk 2 — `run_l3_batched`

`harness/retry.rs`: `run_l3_batched` (§5.2) + `L3_BATCH_SIZE`. Entry precondition
(global dup/empty check), group-by-zone, `chunks(batch_size)`, per-batch
`run_l3_with_retries`, aggregate. Tests (mock gateway): multi-zone set classified
across batches, exactly-once union (AC-2), summed attempts/fallbacks/tokens
(AC-3), a zone over the cap sub-chunks, empty ⇒ empty, duplicate ⇒ `Err`.

## Chunk 3 — `bootstrap.rs` refactor

`engine_placeholders` → `pub(super)`. Extract the L4-input join to
`pub(super) fn build_l4_inputs(&TilemapView, &[L3Placeholder], &L3Result)
-> Vec<ZoneNarrationInput>`; `bootstrap_small_reality` calls it. Existing
bootstrap tests stay green (pure refactor).

## Chunk 4 — `harness/continent.rs`

`continent_template()` (~16 zones, modest treasure density so the live object
set is bounded), `MeasurementReport` / `OfflineMeasurement` / `LiveMeasurement`,
`measure_continent` (offline always; live when a client is supplied),
`render_measurement_report`. Register `pub mod continent` in `harness/mod.rs`.
Tests: the template places at 256² with many zones, deterministic for a seed.

## Chunk 5 — `measure` subcommand

`main.rs`: `Some("measure") => run_measure()`. Offline always; live when
`gateway_from_env()` succeeds. Print `render_measurement_report`.

## Chunk 6 — VERIFY + run + findings

`cargo test --workspace` + `cargo clippy` green. Run `tilemap-service measure`:
the offline 256² timing for certain; the live engine→L3-batched→L4 run against
lmstudio if it completes in feasible time. Write
`docs/measurements/2026-05-18-continent.md` with the numbers.

## Chunk → AC map

| Chunk | ACs |
|---|---|
| 1 | (token plumbing for AC-6) |
| 2 | AC-1, AC-2, AC-3 |
| 3 | (refactor — no new AC) |
| 4 | AC-4, AC-5 |
| 5 | AC-5, AC-6 |
| 6 | AC-6, AC-7 |
