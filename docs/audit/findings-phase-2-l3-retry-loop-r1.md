# Adversary findings — phase-2-l3-retry-loop, design review, round 1

Cold-start adversarial review of `docs/specs/2026-05-16-tilemap-phase-2-l3-retry-loop.md`
against TMP_008b §4.2/§5/§6 and the Phase-0b harness (`harness/mod.rs`,
`validate.rs`, `prompt.rs`, `tests/harness_mock.rs`).

3 findings — 2 BLOCK, 1 WARN.

---

## BLOCK-1 — §6 fallback `suggested_canon_kind[0]` panics on an empty list; the "never `Err`, always playable" guarantee is unproven

**Problem.** D5 specifies `canonical_default_classification` as
`canon_kind = suggested_canon_kind[0]`. TMP_008b §6 does the same
(`p.suggested_canon_kind[0].clone()`). `L3Placeholder.suggested_canon_kind` is a
`Vec<String>` (`prompt.rs:15`) with **no non-empty invariant** — nothing in the
type, the constructor `L3Placeholder::new`, or the spec forbids an empty list.
`run_l3_with_retries`'s contract (D1) takes an arbitrary
`placeholders: Vec<L3Placeholder>`, and D7's `bootstrap_small_reality` builds a
fixture set by hand. An empty `suggested_canon_kind` makes `[0]` an
out-of-bounds index -> **panic**.

**Why it matters.** D1 + §6's headline promise is *"never returns `Err` — §6
guarantees a result"* and *"always playable even at 100 % LLM failure"*. A panic
is a strictly worse failure than `Err`: it is exactly the path §6 exists to make
unreachable, and it triggers precisely in the worst case (LLM failed, fallback
engaged). The captured "contract holes" rejection lesson names under-specified
contracts as the recurring REJECT cause — `run_l3_with_retries`'s input contract
is under-specified here. The review brief explicitly flags this case ("an object
whose `suggested_canon_kind` list is empty (§6 fallback indexes `[0]`)") and D5
does not address it.

**Concrete spec fix.** Pin the input contract in D5/D6: either (a) state
`run_l3_with_retries` requires `suggested_canon_kind` non-empty for every
placeholder and have it return `Err` (or assert at the boundary) with a named
error if violated — making the precondition explicit and testable — or (b) make
`canonical_default_classification` total: `suggested_canon_kind.first()` with a
documented terminal fallback `canon_kind` (e.g. a const `"Unknown"` /
`"Generic"` engine kind) when the list is empty. Add an AC: "a placeholder with
an empty `suggested_canon_kind` does not panic the pipeline" (option (a): asserts
`Err`; option (b): asserts the terminal default). Phase-0b `validate_l3` R3 is
silent for an empty list — note that too, since an empty list also means *no*
LLM `canon_kind` can ever be R3-valid, so such an object always reaches §6.

---

## BLOCK-2 — §5 retry contradiction: the attempt requests only the failing subset, but the §4.2 retry message tells the LLM to "keep all other entries unchanged"

**Problem.** D2/D4 send each retry attempt **only the still-unaccepted subset**
(`call_l3_attempt(... placeholders ...)` where `placeholders` is `to_classify`,
the failing subset — TMP_008b §5 line 334 `call_l3_llm(&to_classify, ...)`).
But D3's retry context is `format_errors_for_retry`, whose fixed preamble
(TMP_008b §4.2) is: *"Fix ONLY the entries below; keep all other entries
unchanged."* That sentence tells the LLM the *other* entries still exist and
must be preserved — yet the request payload no longer contains them. The LLM is
asked to "keep" objects it can no longer see. A compliant LLM re-emits the
already-accepted objects from memory (or refuses, or hallucinates them).

`partition_response` validates each attempt's response against `to_classify`
only (D4). So a re-emitted already-accepted obj_id is **not** in the subset ->
`validate_l3` R1 flags it `UnknownObjId` -> it lands in `errors` -> it is silently
dropped from that attempt's `accepted`. No correctness bug *yet* (it was already
accepted), but the spec never states this interaction, and it has two real
consequences: (1) the LLM spends output tokens re-classifying objects that are
discarded — defeating §5's "~80-95 % retry token cost reduction" claim; (2) if
the LLM, told to "keep entries unchanged", instead returns *only* the failing
subset *plus a different classification* for a previously-accepted obj, the spec
has no rule — `partition_response` drops it as `UnknownObjId`, so the LLM's
correction is silently ignored. This is the captured "silent-drop hole" pattern
that took the sibling phase-0b-sse-parser spec 4 rounds.

**Why it matters.** §5 fidelity is a named scrutiny target. The spec couples a
subset request with a full-set instruction and never reconciles them — a genuine
contract hole. The retry message's wording is load-bearing (CSC_001 v4: 70-90 %
vs 20-40 % retry success) and is now factually wrong for a subset request.

**Concrete spec fix.** Pick one and pin it in D3:
(a) **subset-only retries** — the attempt request must use a retry-specific
preamble that does NOT say "keep all other entries"; instead: "Classify ONLY the
N objects below; they previously failed validation for the reasons given."
`format_errors_for_retry` (or a new `format_retry_context`) needs a preamble
variant for the per-object-subset case, distinct from §4.2's full-set wording.
(b) **full-set retries** — send all placeholders every attempt, keep §4.2's
wording, and have `partition_response` validate against the full set; then §5's
token-saving claim must be dropped from the spec. Either way, add an AC asserting
the retry-context preamble text matches the request shape, and state explicitly
in D4 what `partition_response` does with a classification for an obj_id outside
the requested subset (drop vs re-accept).

---

## WARN-1 — `L3Result.llm_attempts` and `fallback_count` are defined two contradictory ways and the transport-error case is unpinned

**Problem.** D6 defines `fallback_count` as *"the §6 count"* (count of fallback
inserts) and `llm_attempts` as a plain `u32`. TMP_008b §5's reference code
defines them differently: `fallback_count: placeholders.len() - <successful LLM
count>` (derived by subtraction) and `llm_attempts: max_attempts.min(<actual
attempts run>)`. These diverge:

- **`fallback_count` by subtraction is wrong** if the loop ever short-circuits
  or the LLM count is computed loosely — and it is redundant: count the §6
  inserts directly (D6's definition is the correct one; the §5 code's is not).
- **`llm_attempts`** — D1 says a transport failure on an attempt is "treated as
  that attempt classified nothing and the loop continues". The spec never says
  whether such a failed attempt **increments `llm_attempts`**, nor whether it
  consumes one of the `max_attempts` budget (it must, or a persistent transport
  failure loops forever — §5 line 331 `for attempt in 1..=max_attempts` does
  consume it, but D1's prose never confirms this). AC-2 asserts
  `llm_attempts == 1` on a clean first try; **no AC** pins `llm_attempts` after a
  transport-failed attempt or after an early `to_classify.is_empty()` break.
- Relatedly, after a transport-failed attempt there are **no validation
  errors** to feed `format_errors_for_retry` for the *next* attempt — D3 says
  retry context is `format_errors_for_retry(errors)`, but `errors` would be
  empty, producing the message "Your previous response had errors. Fix ONLY the
  entries below" *with zero lines* — a self-contradictory prompt. The spec does
  not say whether attempt N+1 after a transport failure carries the previous
  *successful-but-partial* attempt's errors, the empty set, or no retry context
  at all.

**Why it matters.** `L3Result` is the design's public carrier (D6); two
conflicting definitions of its fields will be resolved arbitrarily at BUILD.
`max_attempts == 0` (a brief-named case) with the `1..=0` range runs zero
attempts -> straight to fallback with `llm_attempts` ambiguous (0? `max(0,...)`?).
The empty-`errors` retry message is the same class of LLM-contract hole
(empty-args / contradictory-first-message) that the captured phase-0b lesson
says recurs.

**Concrete spec fix.** In D6, state the single authoritative definition:
`llm_attempts` = number of gateway calls actually issued (including
transport-failed ones, since they consume budget; `0` when `max_attempts == 0`);
`fallback_count` = number of `canonical_default_classification` inserts, counted
directly, never by subtraction. In D3, specify the retry context for an attempt
following a transport-failed attempt (recommended: carry the most recent
*non-empty* error set; if none exists, send no retry context — and have
`format_errors_for_retry` return an empty string for an empty slice rather than
the bare contradictory preamble, which AC-1 already half-implies). Add an AC
covering `max_attempts == 0` and one covering a transport error mid-loop
(`llm_attempts` value + that the run still returns an `L3Result`).

---

Captured rules: read pre-loaded (3 adversary-rejection lessons); Guardrails relevant: none (check_guardrails pass:true)
