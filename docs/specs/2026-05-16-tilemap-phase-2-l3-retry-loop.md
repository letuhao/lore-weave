# Spec — Tilemap Phase 2: L3 zone-classifier retry loop + fixture bootstrap

> **Status:** DESIGN 2026-05-16. AMAW (12-phase), `/amaw` enabled. Size **L**.
> Branch `mmo-rpg/zone-map-amaw`.
> **Source:** [TMP_008b](../03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_008b_llm_contract_spec.md)
> §4.2 (retry messages) + §5 (per-object retry) + §6 (canonical fallback);
> handoff "Phase 2".
> **Scope decision (CLARIFY, PO 2026-05-16):** the retry loop + a
> **fixture-object** bootstrap — Phase 1's engine produces no objects (object
> placement is TMP_006, unbuilt), so the bootstrap classifies a synthetic
> object set; engine→L3 object flow stays a later phase.

## 1. Goal

The full L3 zone-classifier retry pipeline on top of the Phase-0b harness:
structured per-object retry messages (§4.2), a per-object partial-success
retry loop (§5), and a deterministic canonical-default fallback (§6) so the
system is **always playable even at 100 % LLM failure**. Plus a small-reality
bootstrap that runs the Phase-1 placement engine and drives a fixture object
set through the full L3 loop end-to-end.

## 2. Scope

**In:** TMP_008b §4.2 `format_errors_for_retry` (+ `L3ValidationError::obj_id`);
§5 `run_l3_with_retries` (per-object partial-success retry, 3 attempts/batch per
TMP-LLM-C-Q3); §6 `canonical_default_classification` + `generate_default_tag`;
an `L3Result` carrier; a `bootstrap_small_reality` that wires `place_tilemap` +
a fixture object set through the loop; a `bootstrap` CLI subcommand; mock-gateway
integration tests for the retry branches.

**Out (later phases):** engine object placement (TMP_006 TreasurePlacer /
ObjectManager — objects are fixture here); L4 regional narration (Phase 3);
L3/L4 cache-key derivation (§8); prompt-injection escaping (§7); folding
classified objects into `TilemapView.object_placements` (needs the TMP_006
typed object records); a live continent-scale cost measurement (Phase 0b
already proved the live path — a live run stays an optional extra, not the
VERIFY gate).

## 3. Design decisions

### D1 — `run_l3_with_retries` is async + gateway-backed

`run_l3_with_retries(client, model_source, model_ref, user_id, placeholders,
book_canon_refs, max_attempts) -> Result<L3Result>`.

**Precondition — the sole `Err` path:** every placeholder's
`suggested_canon_kind` MUST be non-empty, checked once at entry **before any
gateway call**; a violation returns `Err(Error::Config(..))` naming the
offending `obj_id`. This is malformed input rejected at the door — §6's
fallback indexes `suggested_canon_kind[0]`, so this precondition is what makes
the fallback total (it cannot panic).

Given a valid input the function **never returns `Err` on the retry/LLM path**:
each attempt streams one gateway call for the still-unaccepted subset; a
transport/stream failure on an attempt is treated as "that attempt classified
nothing" — the attempt still counts as a gateway call (D6) and the loop
continues to the §6 fallback, which guarantees a complete result.

`max_attempts == 0` is well-defined: no gateway call is made — every object
goes straight to the §6 fallback.

### D2 — extract a reusable single-attempt call

A `call_l3_attempt(client, …, placeholders, retry_context: Option<&str>)`
helper builds the request (Phase-0b request shape), streams, accumulates the
tool call, and parses → `Vec<L3Classification>` (empty on any failure). The
Phase-0b `run_l3_measurement` is refactored to call it — its behaviour and the
`harness_mock.rs` test are preserved (R-B).

### D3 — retry context message (§4.2, reframed for subset retries)

On attempt > 1 the loop passes `format_errors_for_retry(errors)` as
`retry_context` — appended as an extra user message so the LLM sees the exact
failing cases.

`format_errors_for_retry(errors: &[L3ValidationError]) -> String` — exact
output shape (**the function owns the whole message**, preamble included; the
caller passes the returned string verbatim as `retry_context`, it never
re-assembles the preamble itself):
- **empty `errors`** → `""` — the function is total; it never assembles a
  "had errors" preamble over zero cases (the loop only calls it non-empty).
- **non-empty `errors`** → the reframed preamble (below) as the **first
  line**, a blank line, then one line per error with the §4.2 tag set
  (`[MISSING]` / `[UNKNOWN]` / `[DUPLICATE]` / `[INVALID-CANON-KIND]` /
  `[INVALID-CANON-REF]` / `[INVALID-TAG]`). AC-1 asserts the first line is the
  preamble.

**Spec deviation from §4.2 (documented):** TMP_008b §4.2's preamble — "Fix
ONLY the entries below; keep all other entries unchanged" — assumes the LLM
still holds the *full* object set. This design sends only the still-failing
**subset** each retry (§5's token-reduction intent — D2/D4), so that wording
would reference objects no longer in the payload (the BLOCK-2 contradiction
the design Adversary caught). The preamble is reframed: *"Your previous
classification of the objects below failed validation. Previously-valid
classifications are already saved — re-classify ONLY the objects in this
payload."*

If a **transport** failure (not a validation failure) ended the prior attempt,
there are no validation errors to show — the next attempt re-requests the
subset with **no `retry_context`** (a fresh try, not a correction).

### D4 — per-object accept/narrow is a pure, unit-tested function

`partition_response(subset, response, book_canon_refs) -> (accepted:
Vec<L3Classification>, errors: Vec<L3ValidationError>)` validates `response`
against the **requested subset** (`subset` = the placeholders sent on this
attempt — not the full set). A classification is accepted iff `validate_l3`
reports **no error naming its `obj_id`**. This is decided via a new
`L3ValidationError::obj_id() -> &str` accessor, added by this design with an
**exhaustive `match` (no `_` wildcard)** — so a future error variant lacking an
`obj_id` forces a compile error rather than silently breaking the accept/narrow
ground truth. All 6 current variants carry an `obj_id` (AC-11).

A response entry whose `obj_id` is **not in the requested subset** produces an
`UnknownObjId` error and is **ignored** — it is either an already-accepted
object (subset retries never revisit accepted objects) or noise; either way it
cannot be accepted because it is not a subset member. `accepted` therefore only
ever contains subset members, and `classifications` stays exactly-once (D6).

The retry loop is a thin async shell over this pure core; the core is
unit-tested without a gateway.

### D5 — canonical-default fallback (§6)

`canonical_default_classification(p: &L3Placeholder) -> L3Classification`:
`canon_kind = suggested_canon_kind[0]` (the engine default — index `[0]` is
safe because D1's entry precondition rejects any empty `suggested_canon_kind`
before this code is reached), `narrative_tag = generate_default_tag(p)`
(deterministic — `format!("{}_{}_default", kind_lower, zone_short)`),
`canon_ref = None`, `rationale = "Canonical default (LLM failed validation
after max retries)"`. `L3Placeholder` gains a `zone_id: String`
field (it has none today) so the default tag and the bootstrap can associate
objects with zones; `fixture_placeholders` is updated.

### D6 — `L3Result` carrier

`L3Result { classifications: Vec<L3Classification>, llm_attempts: u32,
fallback_count: usize }`. Authoritative field definitions — TMP_008b §5's
reference code is loose here (derives counts by subtraction); these override it:
- `classifications` — covers every input `obj_id` **exactly once**: the union
  of LLM-accepted classifications and §6 fallbacks, disjoint by construction
  (an object is accepted XOR fallback-filled — once accepted it leaves
  `to_classify` and is never revisited).
- `llm_attempts` — the count of gateway calls actually **issued**, including
  transport-failed ones. `0` when `max_attempts == 0`; always ≤ `max_attempts`.
- `fallback_count` — the count of objects filled by `canonical_default_*`,
  tallied directly as each fallback is inserted into the result **after the
  retry loop ends**. Invariant: it is NEVER derived by pre-counting
  `to_classify` nor by `placeholders.len() - accepted.len()` — a partial final
  attempt (objects accepted on the *last* attempt) makes any such derivation
  double-count. AC-12 covers the partial-final-attempt case.

### D7 — fixture-object bootstrap

`bootstrap_small_reality(client, …) -> Result<BootstrapReport>`: a hardcoded
small `TilemapTemplate`, run `place_tilemap` (Phase 1), take a fixture
`Vec<L3Placeholder>` whose `zone_id`s reference the placed zones, run
`run_l3_with_retries`, return `{ TilemapView, L3Result }`. Exposed as a
`bootstrap` CLI subcommand beside the Phase-0b `classify`. Honest framing: the
objects are fixture, not engine-placed.

### D8 — VERIFY uses a mock gateway

The retry branches (clean first try / partial retry / persistent fallback /
all-fail) need controlled LLM failures a clean live model never produces. A
wiremock gateway (the `tests/harness_mock.rs` pattern) scripts fail-then-succeed
SSE responses. The pure `partition_response` + `canonical_default_*` +
`format_errors_for_retry` are additionally unit-tested directly.

## 4. Acceptance criteria

- AC-1: `format_errors_for_retry` on a non-empty error list — the **first line
  is the reframed subset-retry preamble**, then one structured line per error
  with the correct §4.2 tag; an empty error list yields `""`.
- AC-2: a clean first L3 response → `L3Result` with `llm_attempts == 1`,
  `fallback_count == 0`, every object classified by the LLM.
- AC-3: a response with K invalid objects → the next attempt re-classifies
  **only** those K; already-valid classifications are preserved (partial
  success).
- AC-4: objects still failing after `max_attempts` → `canonical_default_*`;
  `fallback_count` is exact; the pipeline returns an `L3Result`, never `Err`.
- AC-5: `canonical_default_classification` is deterministic — same placeholder
  ⇒ identical output; `canon_kind == suggested_canon_kind[0]`.
- AC-6: `bootstrap_small_reality` runs `place_tilemap` + the L3 loop and
  returns an `L3Result` classifying every fixture object exactly once.
- AC-7: mock-gateway integration tests cover clean / partial-retry /
  full-fallback; `cargo test --workspace` + `cargo clippy --workspace` green;
  the Phase-0b `harness_mock.rs` test still passes (no measurement regression).
- AC-8: a placeholder with an empty `suggested_canon_kind` → `run_l3_with_retries`
  returns `Err` at entry, naming the `obj_id`, before any gateway call.
- AC-9: `max_attempts == 0` → no gateway call; every object is a §6 fallback —
  `llm_attempts == 0`, `fallback_count == placeholders.len()`.
- AC-10: a mid-loop transport/stream error on an attempt → the loop still
  returns a complete `L3Result` (that attempt counts toward `llm_attempts` and
  classifies nothing; survivors retry or fall back) — never `Err`.
- AC-11: `L3ValidationError::obj_id()` returns the correct `obj_id` for each of
  the 6 error variants.
- AC-12: a partial final attempt — the last attempt classifies some objects
  validly and leaves others failing → `classifications` covers every `obj_id`
  exactly once and `fallback_count` equals exactly the still-failing count (no
  double-count of the last-attempt acceptances).

## 5. Risks

- R-A: mock-gateway fidelity — the retry loop is async + gateway-coupled.
  Mitigation: wiremock scripted multi-response per the proven `harness_mock.rs`
  pattern; the pure core (`partition_response`) is unit-tested independently.
- R-B: refactoring `run_l3_measurement` to share `call_l3_attempt` could
  regress the Phase-0b measurement path. Mitigation: `harness_mock.rs` is an
  AC-7 gate; behaviour is preserved, not changed.
- R-C: `L3Placeholder` gains a `zone_id` field — a struct change touching
  `prompt.rs` + `validate.rs` tests. Small + additive; covered by recompile +
  existing tests.

## 6. New dependencies

None — `wiremock` is already a dev-dependency (used by `harness_mock.rs`).
