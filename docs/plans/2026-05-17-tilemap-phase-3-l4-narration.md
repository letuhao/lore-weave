# Plan — Tilemap Phase 3: L4 regional narration + key-phrase extraction

> **Spec:** [docs/specs/2026-05-17-tilemap-phase-3-l4-narration.md](../specs/2026-05-17-tilemap-phase-3-l4-narration.md)
> **Size:** L, AMAW (`/amaw`). Branch `mmo-rpg/zone-map-amaw`.
> **BUILD is chunked** — each chunk compiles + tests green before the next.

## Build order (6 chunks)

### Chunk 1 — closed style enums + key-phrase extraction (`harness/style.rs`, `harness/keyphrase.rs`, new)
- `style.rs`: §11 closed enums `NarrativeTone`, `NarrationLanguage`, `NarrationVoice` (serde, snake_case).
- `keyphrase.rs`: `extract_key_phrases(narration, n)` — spec D6 (split on non-alphanumeric, lowercase, drop <3-char / all-digit / stopword tokens, frequency rank, `(count desc, first-index asc)` tie-break).
- Tests: determinism, ≤`n`, stopword + all-digit exclusion (AC-6).

### Chunk 2 — L4 prompt + tool (`harness/l4_prompt.rs`, new)
- `ZoneNarrationInput { zone_id, terrain, l3_objects }` (spec D7).
- L4 system prompt (§9.2 one-shot) + `submit_zone_narrations` tool (§3.3, OpenAI-shaped) + `forced_tool_choice` (`"required"`, per Phase-0b §12.8.2) + `l4_user_payload(inputs, language, tone)`.
- Tests: payload renders every zone + the language token.

### Chunk 3 — L4 validation + fallback (`harness/l4_validate.rs`, new)
- `L4Narration`, `L4ToolArguments`, `L4ValidationError` (+ `zone_id()` exhaustive accessor, `retry_line()`).
- `validate_l4` (§4.3 R1-R4 incl. `UnknownZoneId`; R4 script-ratio heuristic).
- `format_l4_errors_for_retry` (spec D1 — reframed L4 preamble), `partition_l4_response` (accept iff in-subset AND no error).
- `canonical_default_narration` (spec D4 — fixed ≥50-char template, `.chars().take(2000)`).
- Tests: R1-R4 each flagged; preamble first line (AC-9); fallback ≥50 chars for a 1-char zone_id (AC-5); partition narrows.

### Chunk 4 — `call_l4_attempt` + `run_l4_with_retries` (`harness/l4_retry.rs`, new + `harness/mod.rs`)
- `call_l4_attempt` (sibling of `call_l3_attempt`; `L4Attempt` with explicit `failure`).
- `run_l4_with_retries` + `L4Result { narrations, llm_attempts, fallback_count }` — per-zone partial-success loop, D1 precondition (empty/duplicate `zone_id` → `Err`), `failure`-discriminator, §6 fallback.
- Gate: `harness_mock.rs` + `retry_mock.rs` still green.

### Chunk 5 — bootstrap L3 → L4 (`harness/bootstrap.rs`)
- Build `ZoneNarrationInput`s from the `TilemapView` (terrain from `ZoneRuntime`; `l3_objects` via the `obj_id`→`zone_id` join — spec D7).
- Run `run_l4_with_retries`; `BootstrapReport` gains `l4: L4Result`; extend `render_bootstrap_report`.

### Chunk 6 — mock-gateway L4 tests + TMP_008b update (`tests/l4_mock.rs`, new)
- wiremock L4 tests: clean (AC-2), partial-retry (AC-3), persistent fallback (AC-4), parsed-empty (AC-10), bootstrap L3→L4 end-to-end (AC-7), all-L3-fallback zone still narrated (AC-11).
- Fold the Phase 2/3 measurement findings into TMP_008b §12.8.
- Gate: `cargo test --workspace` + `cargo clippy --workspace` green.

## VERIFY gate

`cargo test --workspace` + `cargo clippy --workspace` green; AC-1..AC-11 each
covered; `harness_mock.rs` + `retry_mock.rs` (Phases 0b/2) still green.

## Multi-session note

L — each chunk boundary (1–6) is a clean resume point. SESSION_HANDOFF records
the last completed chunk.
