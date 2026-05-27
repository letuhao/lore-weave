# Spec — Tilemap Phase 3: L4 regional narration + key-phrase extraction

> **Status:** DESIGN 2026-05-17. AMAW (12-phase), `/amaw`. Size **L**.
> Branch `mmo-rpg/zone-map-amaw`.
> **Source:** [TMP_008b](../03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_008b_llm_contract_spec.md)
> §3.3 (`submit_zone_narrations` tool) + §4.3 (L4 validation) + §9.2 (few-shot)
> + §10 (deterministic key-phrase extraction) + §11 (closed style enums);
> handoff "Phase 3".
> **Scope (CLARIFY, self-scoped — autonomous run):** the L4 regional-narration
> pipeline mirroring the Phase-2 L3 retry loop, plus deterministic key-phrase
> extraction, the bootstrap extended to run L3→L4, and folding the measurement
> findings back into TMP_008b. This is the **final phase** of the tilemap
> map-generation plan (0b→1→2→3).

## 1. Goal

A per-zone L4 regional-narration pipeline on top of the Phase-2 harness:
the `submit_zone_narrations` tool (§3.3), §4.3 validation, a per-zone
partial-success retry loop with a deterministic canonical-default fallback
(so every zone is always narrated, even at 100 % LLM failure), and §10
deterministic key-phrase extraction. The bootstrap is extended to run the
full L3→L4 chain end-to-end on a small reality.

## 2. Scope

**In:** `submit_zone_narrations` tool + L4 prompt (§3.3 + §9.2 one-shot);
`validate_l4` (§4.3 R1-R4 — R5 World Oracle is V2); `format_l4_errors_for_retry`
+ `partition_l4_response` (reusing the Phase-2 subset-retry shape); `call_l4_attempt`
+ `run_l4_with_retries` + `L4Result`; `canonical_default_narration` (§6 — a
deterministic engine stub); the §11 closed enums `NarrativeTone` /
`NarrationLanguage` / `NarrationVoice`; deterministic key-phrase extraction
(§10, V1 simple frequency rank); the bootstrap extended to run L3 then L4;
mock-gateway L4 tests; the TMP_008b §12.8 measurement-findings update.

**Out (later phases / V2):** §4.3 R5 World-Oracle semantic check (V2); §8.2 L4
cache-key derivation (no caching needed to demo the loop); §12.4 cross-zone
neighbour context (TMP-LLM-Q4 — needs a neighbour-adjacency feed; Phase-3 L4 is
single-zone-context per call, documented cut); KeyBERT / IDF corpus weighting
(§10 V2+ — Phase 3 uses frequency rank); a live continent-scale measurement.

## 3. Design decisions

### D1 — L4 mirrors the Phase-2 L3 retry architecture (pinned, not asserted)

`run_l4_with_retries` is a per-zone partial-success retry loop structurally
identical to `run_l3_with_retries`. L3 and L4 keep **separate** typed loops
(payloads differ — `L3Placeholder`/`L3Classification` vs `ZoneNarrationInput`/
`L4Narration`); a generic loop is a later refactor, not Phase 3. The three
Phase-2 retry-loop holes (ContextHub lesson `2c94cf3c`) are closed for L4 by
pinning the L4 equivalents **here** (not by assertion):

- **Subset-retry preamble (Hole 1).** `format_l4_errors_for_retry` owns the
  whole retry message. Empty error slice → `""`. Non-empty → this exact
  reframed preamble as the **first line**, a blank line, then one `[TAG] …`
  line per error: *"Your previous narration of the zones below failed
  validation. Previously-valid narrations are already saved — re-narrate ONLY
  the zones in this payload."* §4.3 gives L4 no retry-message format, so it is
  defined here — do NOT copy §4.2's L3 "keep all other entries unchanged".
- **Transport-vs-validation discriminator (Hole 2).** `call_l4_attempt` returns
  an `L4Attempt` with an explicit `failure: Option<String>`. The loop derives
  the next retry context from validation errors **iff `failure.is_none()`** — a
  parsed-but-empty `{"zone_narrations":[]}` is a *validation* failure (every
  zone `[MISSING-NARRATION]`), never discriminated on `narrations.is_empty()`.
- **Out-of-subset guard (Hole 3) — both sides.** `partition_l4_response`
  validates the response against the requested **subset** and **accepts a
  narration iff its `zone_id` ∈ the subset AND no error names it** (mirroring
  Phase-2 `partition_response`) — an out-of-subset narration is never accepted,
  so it cannot overwrite a previously-saved good narration. Separately, before
  the errors feed the next retry context the loop runs
  `errors.retain(|e| subset_ids.contains(e.zone_id()))` so an out-of-subset
  `UnknownZoneId` never tells the model to drop good work.

### D2 — `call_l4_attempt` is a sibling of `call_l3_attempt`

One L4 gateway call: builds the request with the `submit_zone_narrations` tool,
streams, reassembles, parses → `L4Attempt` (every failure in `.failure`, never
`Err`). It duplicates `call_l3_attempt`'s stream/accumulate skeleton with an
L4-typed parse; the duplication is accepted for Phase 3 (a generic
`call_tool_attempt` is a later cleanup — tracked, not done here).

### D3 — L4 validation (§4.3, R1-R4)

`validate_l4(narrations, inputs, language) -> Vec<L4ValidationError>`:
- R1 — every input `zone_id` has a narration, and every output narration's
  `zone_id` is an input zone (an extra/unknown one → `UnknownZoneId`).
- R2 — no duplicate `zone_id`.
- R3 — each narration is 50..=2000 chars.
- R4 — language match: a cheap script-class heuristic (CJK-codepoint ratio for
  `Zh`/`Ja`/`Ko`, Latin ratio for `Vi`/`En`) compared to the requested
  `NarrationLanguage`. A heuristic with tolerance, not a classifier — documented.
  A narration whose alphabetic-character count is too low to classify (mostly
  punctuation/digits) is NOT flagged R4 (R3 length already covers degenerate
  text); R4 only fires on a confident script mismatch.
- R5 (World Oracle) — **out** (V2).

`L4ValidationError` carries a `zone_id() -> &str` accessor — an exhaustive
`match`, no `_` wildcard (a future variant lacking a `zone_id` then fails to
compile, per the Phase-2 `obj_id()` pattern). Every variant carries a `zone_id`.

### D4 — `canonical_default_narration` — the terminal §6 fallback

`canonical_default_narration(input) -> L4Narration` returns a deterministic
engine stub from this **fixed template**:

> "The region known as {zone_id} stretches across {terrain} terrain. Its tale
> awaits the telling. (Engine-default narration.)"

The slot-independent fixed text is ~100 chars, so the narration is **always
≥50** even with an empty `zone_id`/`terrain` — R3's lower bound holds by
construction, no run-time padding rule needed. The result is truncated with
`.chars().take(2000)` so R3's upper bound also holds for a pathologically long
`zone_id`. AC-5 tests the shortest possible `zone_id`.

It is the **terminal** answer — NOT re-validated. The engine stub is English;
if the reality requested another language it is degraded-but-present, which
§6's "always playable" contract permits. The only Phase-3 consumer of
`L4Result.narrations` is §10 `extract_key_phrases`, which runs fine on the
English stub — no consumer breaks on an un-revalidated stub.

### D5 — §11 closed style enums

Add `NarrativeTone`, `NarrationLanguage`, `NarrationVoice` (the §11 variant
sets). Phase 3 actively uses `NarrationLanguage` (R4); `NarrativeTone` /
`NarrationVoice` are carried in the L4 request context. `serde` derives;
`snake_case`.

### D6 — §10 deterministic key-phrase extraction

`extract_key_phrases(narration, n) -> Vec<String>`: split on every
non-alphanumeric character, lowercase each token, drop tokens shorter than 3
chars, **all-digit tokens** (a kept token must contain at least one `[a-z]`
char — bare numbers like `2026` are not key phrases), and the fixed stopword
set below, count term frequency, rank by
`(count desc, first-appearance index asc)`, take the first `n` (fewer if the
narration has fewer distinct kept terms). Fully deterministic — same narration
⇒ same phrases.

The stopword set is this fixed inline constant (no external list):
`the and for are was were its with this that from has had have not but you
your they their them she her his him`.

The split is **Unicode-aware** (`char::is_alphanumeric`), so accented Latin —
Vietnamese `Vi`, the user's default-context language — tokenizes correctly.

**V1 cut:** frequency rank only — no IDF corpus weighting, no KeyBERT (§10
V2+). **CJK** narration has no word spaces, so a CJK run is not split into
meaningful tokens — key-phrase quality for `Zh`/`Ja`/`Ko` is a documented V1
limitation (the V2 KeyBERT path handles it).

### D7 — bootstrap runs L3 → L4

`bootstrap_small_reality` is extended: after the L3 loop it builds one
`ZoneNarrationInput` per placed zone, runs `run_l4_with_retries`, and
`BootstrapReport` gains `l4: L4Result`; the `bootstrap` CLI prints both.

`ZoneNarrationInput { zone_id: String, terrain: String, l3_objects: Vec<String> }`
— one per `ZoneRuntime` in the `place_tilemap` `TilemapView`:
- `zone_id` + `terrain` come from the `ZoneRuntime` (`terrain` = the lowercased
  `TerrainKind`). `terrain` is **always populated**, so D4's `{terrain}` slot is
  never empty (no double-space stub).
- `l3_objects` = that zone's L3 result — the `canon_kind`s of the
  `L3Classification`s whose object belongs to the zone, recovered by joining
  `L3Classification.obj_id` → `L3Placeholder.zone_id` (placeholders carry
  `zone_id`; `L3Classification` does not). A zone whose L3 objects all hit the
  §6 fallback, or that has zero objects, still gets a `ZoneNarrationInput`
  (empty/fallback `l3_objects`) and is narrated.

## 4. Acceptance criteria

- AC-1: `validate_l4` flags each of R1 (missing zone), R2 (duplicate zone), R3
  (narration too short / too long), R4 (language mismatch).
- AC-2: a clean first L4 response → `L4Result` with `llm_attempts == 1`,
  `fallback_count == 0`, every zone narrated.
- AC-3: a response with K invalid zones → the next attempt re-sends **only**
  those K; valid narrations preserved.
- AC-4: zones still failing after `max_attempts` → `canonical_default_narration`;
  `fallback_count` exact; the loop returns `L4Result`, never `Err` (the sole
  `Err` is the empty/duplicate-`zone_id` entry precondition).
- AC-5: `canonical_default_narration` is deterministic and ≥50 chars (R3-valid)
  — verified for the **shortest possible** `zone_id` (a 1-char id).
- AC-6: `extract_key_phrases` is deterministic, returns ≤ `n` phrases, excludes
  stopwords and bare all-digit tokens.
- AC-7: `bootstrap_small_reality` runs the L3 loop then the L4 loop end-to-end
  and returns both results.
- AC-8: mock-gateway L4 tests cover clean / partial-retry / fallback;
  `cargo test --workspace` + `cargo clippy --workspace` green; the Phase-0b
  `harness_mock.rs` and Phase-2 `retry_mock.rs` suites still pass.
- AC-9: `format_l4_errors_for_retry` — non-empty errors → the **first line is
  the reframed L4 retry preamble** (D1), then one `[TAG]` line per error;
  empty errors → `""`.
- AC-10: a parsed-but-empty `{"zone_narrations":[]}` L4 response is treated as a
  validation failure — every zone `[MISSING-NARRATION]`, and the next retry
  carries those errors (not a context-free fresh retry).
- AC-11: in the L3→L4 bootstrap, a zone whose L3 objects all hit the §6 fallback
  still produces a `ZoneNarrationInput` with a populated (non-empty) `terrain`
  and is narrated by L4.

## 5. Risks

- R-A: L3/L4 code duplication (`call_l4_attempt`, the retry loop). Accepted for
  Phase 3 — the types genuinely differ; a generic loop is a tracked later
  cleanup, not Phase-3 scope.
- R-B: the R4 language heuristic is script-ratio based, not a real classifier —
  it can misclassify mixed-script or very short text. Mitigation: documented
  tolerance; tests use unambiguous cases; R4 is a soft guard, not a hard gate
  on the always-succeeds fallback.

## 6. New dependencies

None — `wiremock` (dev) already present; key-phrase extraction is hand-rolled
(no `unicode_blocks` / embedding crate — V1 cut per §10).
