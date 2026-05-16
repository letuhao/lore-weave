# Adversary findings — phase-2-l3-retry-loop, design review, round 2

Cold-start adversarial re-review of the **revised**
`docs/specs/2026-05-16-tilemap-phase-2-l3-retry-loop.md` against TMP_008b
4.2/5/6 and the Phase-0b harness (`harness/mod.rs`, `validate.rs`,
`prompt.rs`). Round 1 was REJECTED (2 BLOCK + 1 WARN); this round verifies
those fixes and hunts the revision's own new holes.

**Round-1 verification:** BLOCK-1 (empty `suggested_canon_kind` panic) — D1's
entry precondition + AC-8 genuinely close it; `[0]` is now provably reachable
only after a non-empty check. BLOCK-2 (subset-retry vs "keep all other
entries") — D3 reframes the preamble in prose and the 4.2 deviation is
documented; the contradiction is resolved, but the reframing is
under-specified at the function-contract level (see BLOCK-1 below). WARN-1
(`L3Result` field contradictions) — D6 now gives single authoritative
definitions and AC-9/AC-10 pin `max_attempts==0` and the transport case;
resolved.

3 findings — 1 BLOCK, 2 WARN.

---

## BLOCK-1 — D3's reframed preamble is described but never assigned a home: `format_errors_for_retry` is specced to return "" on empty input, yet the reframed preamble must NOT be empty when errors exist — the function now has two undefined modes

**Problem.** D3 makes three claims about `format_errors_for_retry(errors: &[L3ValidationError]) -> String`:
1. it emits "one line per error with the 4.2 tag set";
2. "an **empty error slice yields an empty string** — the function is total; it
   never assembles a 'had errors' preamble over zero cases";
3. the 4.2 preamble is **reframed** to the new subset-aware wording: "Your
   previous classification of the objects below failed validation.
   Previously-valid classifications are already saved — re-classify ONLY the
   objects in this payload."

Claims (2) and (3) are not reconciled. The current TMP_008b 4.2 reference
code builds the string as `String::from(<preamble>)` then appends per-error
lines — the preamble is unconditional. The revision says: empty slice -> ""
(no preamble); non-empty slice -> presumably preamble + lines. But the spec
never states that the reframed preamble is prepended to the non-empty branch,
nor where its text is stored, nor whether it is part of
`format_errors_for_retry` at all or a separate concatenation done by the retry
loop. A BUILD engineer reading D3 literally can produce any of: (a) preamble
inside the function, emitted only when non-empty; (b) function returns only the
lines and the loop prepends the preamble; (c) preamble dropped entirely because
claim (2) is read as "no preamble ever". Round 1's BLOCK-2 fix is therefore
only half landed: the contradiction is gone but the replacement contract is
ambiguous — exactly the "prior round's incomplete fix" pattern the captured
rules warn of.

**Why it matters.** The retry-message wording is load-bearing (CSC_001 v4:
70-90% vs 20-40% retry success). If interpretation (c) is picked, retries ship
with raw `[INVALID-CANON-KIND] ...` lines and no framing sentence — the LLM is
never told these objects previously failed or that prior work is saved, and
retry success collapses toward the 20-40% floor. AC-1 only asserts "one
structured line per error" + "empty list yields no per-object lines" — it does
NOT assert the reframed preamble appears on the non-empty path, so VERIFY would
pass interpretation (c). This is an untested contract gap on the spec's most
quality-sensitive string.

**Concrete fix.** In D3, state the function contract precisely: e.g.
"`format_errors_for_retry` returns "" for an empty slice; for a non-empty slice
it returns `<reframed-preamble>` + two newlines + `<one line per error>`, where
`<reframed-preamble>` is the exact sentence above." Decide explicitly whether
the preamble lives in the function or is prepended by the caller, and name that
in D3. Strengthen AC-1: "a non-empty error list yields output whose first line
is the reframed subset-aware preamble (not 4.2's 'keep all other entries'
wording)" — so VERIFY actually gates the BLOCK-2 fix.

---

## WARN-2 — `L3ValidationError::obj_id()` totality is asserted from a 6-variant count, but the accessor is referenced by 5's reference loop yet never added by any design decision and never tested

**Problem.** D4 says "This needs `L3ValidationError::obj_id() -> &str`; all 6
error variants carry an `obj_id`, so the accessor is total." That is true of the
enum as it stands today (`validate.rs:32-49`): all 6 variants —
`MissingObjectClassification`, `UnknownObjId`, `DuplicateObjId`,
`CanonKindNotInSuggested`, `CanonRefNotFound`, `InvalidNarrativeTag` — do have
an `obj_id: String` field, so a `match` returning `&self.obj_id` compiles and is
total. But the spec asserts totality by counting variants, not by pinning the
method as a required deliverable with a test. TMP_008b 5's reference loop calls
`e.obj_id()` (line 338) as if it exists — it does NOT exist in `validate.rs`
today (only `describe()` does). Scope 2 lists "`L3ValidationError::obj_id`" in
parentheses, but no design decision (D1-D8) owns adding it, no AC exercises it,
and D4's "all 6 carry an obj_id" is a claim a reader must independently
re-verify against `validate.rs` rather than a tested guarantee. If a future
variant is added without an `obj_id` (plausible — e.g. a 4.3-style
cross-zone-context error, or a "tool returned zero classifications" error), the
`match` breaks and `partition_response`'s accept/narrow logic silently loses its
ground truth.

**Why it matters.** `partition_response`'s entire correctness — "a
classification is accepted iff `validate_l3` reports no error naming its
`obj_id`" — rests on `obj_id()` being total and returning the right field for
every variant. The captured "contract holes" rejection lesson says
under-specified accessors are a recurring REJECT cause. This is the contract
seam between the pure core and the validator; it deserves an explicit owner and
a test, not a parenthetical.

**Concrete fix.** Add a one-line design decision (extend D4) that explicitly
adds `impl L3ValidationError { pub fn obj_id(&self) -> &str }` as a Phase-2
deliverable, with an exhaustive `match` (no wildcard arm — so a future variant
without `obj_id` is a compile error, not a silent bug). Add an AC: "`obj_id()`
returns the obj_id of every `L3ValidationError` variant" — a trivial unit test
over one instance of each of the 6 variants. State the no-wildcard rule in D4
so the totality is enforced by the compiler going forward, not by a variant
count that will rot.

---

## WARN-3 — exactly-once holds for `classifications` but `fallback_count`'s direct-tally correctness rests on an unstated loop-ordering invariant, and no AC covers a partial final attempt

**Problem.** D6 says `fallback_count` is "the count of objects filled by
`canonical_default_*`, tallied directly as they are inserted (not derived by
subtraction)" and `classifications` "covers every input obj_id exactly once,
the union disjoint by construction (accepted XOR fallback-filled)". The
exactly-once claim for `classifications` is sound — `to_classify` is rebuilt
from `!accepted.contains_key()` each attempt (TMP_008b 5 lines 346-349), and the
fallback loop iterates the same residue. But the spec never states the ordering
invariant that makes the XOR true on the final attempt. Consider: on the last
attempt `max_attempts` the LLM accepts object `obj_K`; `obj_K` is inserted into
`accepted`; the loop exits (range exhausted); the fallback loop then iterates
`placeholders.filter(!accepted.contains_key)` — `obj_K` is excluded, correct.
That works only because `accepted` is updated before the fallback loop reads it.
D6 asserts the XOR "by construction" but the construction
(insert-then-rebuild-then-fallback) is in TMP_008b 5's reference code, NOT
restated in the spec — and the spec explicitly says (D6) "these override [5's
reference code]". So the spec overrides 5's `L3Result` field derivation but
silently depends on 5's loop ordering for its disjointness proof. If BUILD
reorders (e.g. tallies `fallback_count` by pre-counting `to_classify.len()`
after the loop, a natural simplification), `fallback_count` double-counts any
object the final attempt accepted, or an object accepted on attempt N and never
in the final `to_classify` is missed. AC-4 ("`fallback_count` is exact") and
AC-9 ("`fallback_count == placeholders.len()`") assert the number but neither
pins how it is derived nor tests the boundary where the final attempt partially
succeeds.

**Why it matters.** `fallback_count` is a public `L3Result` field and the
playability/telemetry signal ("how much did the LLM actually do"). D6 took
pains to forbid derivation-by-subtraction precisely because it is fragile — but
then leaves the direct-tally path's correctness resting on an unstated
loop-ordering invariant. A wrong `fallback_count` is a silent metric corruption
that no other AC catches.

**Concrete fix.** In D6, state the ordering invariant explicitly:
"`fallback_count` is incremented exactly once per `canonical_default_*` insert,
and the fallback pass runs after the retry loop has fully updated `accepted`; an
object is fallback-filled iff `!accepted.contains_key(obj_id)` at that point."
Add an AC for the partial-final-attempt case: "the final attempt accepts J of K
residual objects -> `fallback_count == K - J`, and `classifications.len() ==
placeholders.len()` with no obj_id appearing twice" — a mock-gateway test that
scripts a last-attempt partial success, which AC-3 (partial retry) and AC-4
(all-fail) between them do not cover.

---

Captured rules: read pre-loaded (3 lessons); Guardrails relevant: none
