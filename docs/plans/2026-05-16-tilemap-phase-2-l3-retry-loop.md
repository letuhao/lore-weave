# Plan — Tilemap Phase 2: L3 zone-classifier retry loop + fixture bootstrap

> **Spec:** [docs/specs/2026-05-16-tilemap-phase-2-l3-retry-loop.md](../specs/2026-05-16-tilemap-phase-2-l3-retry-loop.md)
> **Size:** L, AMAW (`/amaw`). Branch `mmo-rpg/zone-map-amaw`.
> **BUILD is chunked** — each chunk compiles + tests green before the next; a
> chunk boundary is a safe session-resumption point.

## Build order (6 chunks)

### Chunk 1 — validation extensions (`harness/validate.rs`)
- `L3ValidationError::obj_id(&self) -> &str` — exhaustive `match`, no `_`
  wildcard (spec D4 / AC-11).
- `format_errors_for_retry(errors: &[L3ValidationError]) -> String` — spec D3
  exact shape: `""` for empty; else reframed subset-retry preamble as line 1,
  blank line, one `[TAG] …` line per error (§4.2).
- `partition_response(subset, response, book_canon_refs) -> (accepted, errors)`
  — pure accept/narrow (spec D4): accepted iff no error names the obj_id;
  out-of-subset obj_ids ignored.
- Tests: `obj_id()` over all 6 variants (AC-11); `format_errors_for_retry`
  empty→`""` + non-empty first-line-is-preamble (AC-1); `partition_response`
  clean / mixed / out-of-subset.

### Chunk 2 — `L3Placeholder.zone_id` + §6 fallback (`harness/prompt.rs` + `harness/validate.rs`)
- Add `zone_id: String` to `L3Placeholder`; update `L3Placeholder::new` +
  `fixture_placeholders` (assign fixture objects to a zone).
- `canonical_default_classification(p) -> L3Classification` (spec D5):
  `canon_kind = suggested_canon_kind[0]`, `narrative_tag = generate_default_tag`,
  `canon_ref = None`, fixed rationale.
- `generate_default_tag(p) -> String` — deterministic
  `format!("{}_{}_default", kind_lower, zone_short)`.
- Tests: determinism (AC-5); `canon_kind == suggested[0]`.
- Gate: `cargo test -p tilemap-service` green; `harness_mock.rs` still green.

### Chunk 3 — `call_l3_attempt` extraction (`harness/mod.rs`)
- Extract `call_l3_attempt(client, …, subset, retry_context: Option<&str>) ->
  Vec<L3Classification>` (empty on any failure) from `run_l3_measurement`'s
  request-build + stream + accumulate + parse.
- Refactor `run_l3_measurement` to call it — behaviour preserved.
- Gate: `harness_mock.rs` green (spec R-B — no measurement regression).

### Chunk 4 — `run_l3_with_retries` + `L3Result` (`harness/retry.rs`, new)
- `L3Result { classifications, llm_attempts, fallback_count }` (spec D6).
- `run_l3_with_retries(...) -> Result<L3Result>` (spec D1): entry precondition
  (empty `suggested_canon_kind` → `Err`); `max_attempts == 0` → all fallback;
  per-attempt subset call → `partition_response` → accept/narrow; transport
  failure counts an attempt, classifies nothing; §6 fallback after the loop;
  `fallback_count` tallied at insert time (D6 invariant).
- Tests: pure-path unit tests over the loop's decision core.

### Chunk 5 — fixture bootstrap (`harness/bootstrap.rs`, new + `main.rs`)
- `bootstrap_small_reality(client, …) -> Result<BootstrapReport>` (spec D7):
  hardcoded small `TilemapTemplate` → `place_tilemap` → fixture
  `Vec<L3Placeholder>` (zone_ids reference placed zones) → `run_l3_with_retries`
  → `BootstrapReport { TilemapView, L3Result }`.
- `bootstrap` CLI subcommand beside `classify`.

### Chunk 6 — mock-gateway integration tests (`tests/retry_mock.rs`, new)
- wiremock scripted SSE (the `harness_mock.rs` pattern): clean first try (AC-2);
  partial retry — K bad → only K re-sent (AC-3); persistent failure → fallback
  (AC-4); `max_attempts == 0` (AC-9); mid-loop transport error (AC-10);
  partial final attempt (AC-12).
- Gate: `cargo test --workspace` + `cargo clippy --workspace` green.

## VERIFY gate

`cargo test --workspace` + `cargo clippy --workspace` green; AC-1..AC-12 each
have covering tests; `harness_mock.rs` (Phase 0b) still green.

## Multi-session note

L — BUILD may span sessions. Each chunk boundary (1–6) is a clean resume point:
code compiles + its tests pass. SESSION_HANDOFF records the last completed chunk.
