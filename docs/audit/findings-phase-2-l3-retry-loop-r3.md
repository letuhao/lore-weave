# Adversary findings — Phase 2 L3 zone-classifier retry loop (round 3)

Task: `phase-2-l3-retry-loop` · phase `review-code` · branch `mmo-rpg/zone-map-amaw` · size L
Round 3 overall (design used r1/r2). Cold-start adversarial review of the 7 named files only.
`cargo test -p tilemap-service`: 25 tests pass. Build is clean.

---

## Finding 1 — BLOCK — a parsed-but-empty `{"classifications":[]}` is misclassified as a transport failure, dropping the retry context

**File:** `src/harness/retry.rs:107-111` (the `last_errors` assignment).

```rust
last_errors = if outcome.classifications.is_empty() {
    Vec::new()
} else {
    errors
};
```

**Problem.** The discriminator for "was this a transport failure?" is `outcome.classifications.is_empty()`.
But that condition is also true for a fully successful gateway call that returned a parsed,
well-formed `{"classifications":[]}` — i.e. the model genuinely classified zero objects.
`call_l3_attempt` (`mod.rs:155-169`) sets `failure: None` for that case: `calls.first()` is `Some`,
`serde_json::from_str::<L3ToolArguments>` is `Ok`, and `args.classifications` is an empty `Vec`.

Spec D3 is explicit: "If a **transport** failure (not a validation failure) ended the prior attempt,
there are no validation errors to show — the next attempt re-requests the subset with **no
`retry_context`**." A parsed-empty response is a validation failure — every subset object is
`[MISSING]`. The code suppresses those `MissingObjectClassification` errors, so the next attempt is
sent with `retry_context = None` and the model is never told it omitted every object. The code comment
at lines 104-106 even names the intended trigger as "transport/parse failure", but the chosen
condition silently widens it to "the model said nothing".

**Why it matters.** A direct contract deviation from D3 (transport-only suppression) and hits the
captured lesson "phase-0b-sse-parser: design holes recur (empty-first-fragment, silent-drop)" — a
legitimate validation failure is silently dropped. The retry degrades from a correction (with the
§4.2 `[MISSING]` lines) to a blind fresh try, lowering recovery odds for the exact failure mode the
retry loop exists to fix. Final-result correctness still holds via §6 fallback, but the retry
semantics the spec mandates are violated.

**Fix.** Discriminate on `outcome.failure`, which `call_l3_attempt` already populates for every
transport/parse failure and leaves `None` on a clean parse:

```rust
last_errors = if outcome.failure.is_some() {
    Vec::new()        // transport/parse failure — D3: fresh try, no retry_context
} else {
    errors            // clean call (incl. empty classifications) — real validation errors
};
```

Add a `retry_mock.rs` test: attempt 1 returns `{"classifications":[]}` (200, valid SSE), assert
attempt 2's request body contains the `format_errors_for_retry` preamble ("failed validation").

---

## Finding 2 — WARN — duplicate `obj_id` in the input is unguarded; the §6 fallback then silently drops a placeholder

**File:** `src/harness/retry.rs:52-61` (D1 precondition) and `:118-123` (the §6 fallback loop).

**Problem.** The D1 entry precondition checks only that each placeholder's `suggested_canon_kind` is
non-empty. It does not check that `obj_id`s are unique. The §6 fallback loop is
`for p in placeholders { if accepted_ids.insert(p.obj_id.clone()) { … } }`. If `placeholders`
contains two entries with the same `obj_id` and neither is LLM-accepted, the first inserts a fallback
and the second's `insert` returns `false` → it is skipped. Result: `classifications` has one entry
for that `obj_id` while the input had two placeholders, so `classifications.len() != placeholders.len()`
and one input object is lost. Spec D6's "covers every input `obj_id` exactly once" becomes ambiguous /
violated for duplicate input.

The authors clearly know uniqueness is load-bearing — `bootstrap.rs`'s
`bootstrap_placeholder_obj_ids_are_unique_and_well_formed` test enforces it for the fixture — but the
production entry point `run_l3_with_retries` does not. This is the captured lesson
"amaw-task-slug-validation: input-validation gaps recur (unchecked values reaching downstream code)".

**Why it matters.** A future engine-placed object set (TMP_006) is the real caller; a placement bug
producing a duplicate `obj_id` would surface as a silently shrunk classification set rather than a
loud `Err`, defeating the "always playable, every object classified" guarantee.

**Fix.** Extend the D1 precondition loop to also reject duplicate `obj_id`s
(`Err(Error::Config(..))` naming the repeated id), alongside the empty-`suggested_canon_kind` check.

---

## Finding 3 — WARN — AC-6 (`bootstrap_small_reality`) and the D3 retry-context wiring are both unverified by any test

**Files:** `tests/retry_mock.rs` (whole file) and `src/harness/bootstrap.rs:155-196` (the test module).

**Problem.** Two spec obligations have no executing test:

1. **AC-6** — "`bootstrap_small_reality` runs `place_tilemap` + the L3 loop and returns an
   `L3Result` classifying every fixture object exactly once." `bootstrap.rs`'s tests only assert
   `bootstrap_placeholders` zone references and `obj_id` shape; they never invoke
   `bootstrap_small_reality`. `retry_mock.rs` already proves a wiremock gateway can drive
   `run_l3_with_retries`, so the same harness could drive `bootstrap_small_reality` end-to-end — but
   it does not. AC-6 is asserted by the spec and unproven.

2. **D3 retry-context wiring** — `ac3_retry_re_sends_only_the_failing_subset` asserts the subset
   narrowing (obj_3-only in `body2`) but never asserts `body2` contains the `format_errors_for_retry`
   preamble. The whole path `format_errors_for_retry(last_errors)` → `call_l3_attempt`'s
   `retry_context` → the extra user message (`mod.rs:97-99`) is untested at the integration level. If
   that `messages.push` were deleted, every `retry_mock.rs` test would still pass. AC-1 only tests
   `format_errors_for_retry` in isolation.

**Why it matters.** The captured lesson "rdy-rejected-test: under-specified contracts" — the AC list
claims coverage the tests do not deliver. A regression in the retry-context plumbing (the §4.2
contract's entire point) would ship green.

**Fix.** Add a `retry_mock.rs` test for `bootstrap_small_reality` against a scripted mock gateway
(assert `l3.classifications.len() == 6`, each `obj_id` once). Strengthen
`ac3_retry_re_sends_only_the_failing_subset` (or add a sibling test) to assert the attempt-2 request
body contains the reframed retry-context preamble.

---

Captured rules: read pre-loaded (3 lessons); Guardrails relevant: none
