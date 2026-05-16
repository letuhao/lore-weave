# AMAW Adversary findings — phase-2-l3-retry-loop, round 2 (code review)

Task: Phase 2 `tilemap-service` — L3 zone-classifier retry loop (TMP_008b §4.2/§5/§6) + fixture bootstrap. Size L.
Round-1 verdict: REJECTED (1 BLOCK + 2 WARN). Code revised; this is the round-2 re-review.

## Round-1 findings — verified against the revised code

- BLOCK-1 (transport-vs-validation discriminator) — RESOLVED. retry.rs:122 now
  discriminates on `outcome.failure.is_some()`, not `classifications.is_empty()`.
  A parsed-but-empty `{"classifications":[]}` has `failure == None`, so `last_errors`
  is set to the real `validate_l3` errors (every object `[MISSING]`) which drive the
  next attempt's retry context. Genuinely fixed.
- WARN-2 (D1 precondition missed duplicate obj_ids) — RESOLVED. retry.rs:56+65-71 add
  a `seen_ids` HashSet uniqueness check; a duplicate obj_id now returns Err(Config(..))
  naming the id, before any gateway call. Genuinely fixed.
- WARN-3 (AC-6 had no executing test; retry preamble unverified) — RESOLVED.
  retry_mock.rs:174 adds ac6_bootstrap_small_reality_end_to_end, and ac3:167-170
  asserts the retry body contains "re-classify ONLY". Genuinely fixed.

cargo test -p tilemap-service — 8 retry tests + 3 harness_mock + smoke green.
cargo clippy -p tilemap-service --tests — clean.

## Remaining findings — EXACTLY 3

### WARN-1 — out-of-subset UnknownObjId errors leak into the retry context
File: src/harness/retry.rs:108-126, src/harness/validate.rs:243-259
On a retry the loop sends only the still-failing subset, but a real LLM frequently
re-emits already-accepted objects. partition_response runs validate_l3(response,subset,..)
which emits UnknownObjId for every out-of-subset response entry (validate.rs:157-163).
The loop assigns the WHOLE errors vec to last_errors with no subset filter, so the next
attempt's format_errors_for_retry prints "[UNKNOWN] obj_id='obj_1' ... Remove this entry."
about objects that were correctly classified earlier. D4 says out-of-subset entries are
"ignored" — but the loop only ignores them for acceptance, not for the retry message.
Why it matters: the retry context is the LLM's only feedback channel; feeding it
self-contradictory instructions ("re-classify ONLY the objects in this payload" then
[UNKNOWN] lines for objects not in the payload) degrades retry quality exactly when the
loop is trying to recover.
Fix: before assigning last_errors, retain only errors naming a current-subset member —
build subset_ids and `errors.retain(|e| subset_ids.contains(e.obj_id()))`, or have
partition_response return only subset-relevant errors. Add a test that re-includes an
accepted object in attempt 2 and asserts no [UNKNOWN] line for it in attempt 3's body.

### WARN-2 — bootstrap fixture zone_ids never reach the LLM payload
File: src/harness/prompt.rs:92-110 (user_payload), src/harness/bootstrap.rs:114-126
D5/D7 add L3Placeholder.zone_id so the bootstrap associates objects with placed zones,
and bootstrap_placeholders assigns each of the 6 objects a real template zone
(jianghu_capital / western_wilds / lotus_grove). But user_payload — the actual L3
request body — hardcodes a single `zone_1` block and renders each object as only
`obj_id: kind=.. suggested_canon_kind=[..]`; zone_id is never emitted. The LLM is told
all 6 objects sit in one wilderness zone_1, contradicting their assigned zones (one is
a Hub capital, not wilderness).
Why it matters: L3 classification depends on zone role/terrain; a capital-hub treasure
and a wilderness treasure should classify differently but the model cannot tell them
apart. Mock tests pass only because wiremock ignores request content, so this is
invisible to VERIFY. It also desyncs the generate_default_tag zone component (which
does use zone_id) from what the LLM was shown.
Fix: either render per-object zone_id + a per-zone summary block in user_payload, or —
if multi-zone payloads are deliberately Phase-2-out — document it in spec §2 "Out" and
make bootstrap_placeholders use a single zone so the fixture is honest. The code
currently does neither.

### WARN-3 — Scripted responder panics on an empty responses vec
File: tests/retry_mock.rs:54-70
Scripted::respond computes `fetch_add(1,..).min(self.responses.len() - 1)`. len() is
usize; if the vec is empty, `len() - 1` underflows to usize::MAX and `&responses[i]`
panics. Running on a wiremock worker thread, the panic surfaces as an opaque hung/
aborted request rather than a clear test failure.
Why it matters: test-harness fragility (hence WARN). The captured rule "input-validation
gaps recur" applies to scaffolding too — a future scripted_server(vec![]) gets an
inscrutable failure instead of an assertion.
Fix: assert !responses.is_empty() in scripted_server (or a Scripted constructor), or use
saturating_sub(1) with an empty-vec guard so the failure mode is a clear message.

---
Captured rules: read pre-loaded; Guardrails relevant: none
