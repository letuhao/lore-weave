# Adversary findings — Phase 3 L4 regional-narration spec (round 1)

Spec under review: `docs/specs/2026-05-17-tilemap-phase-3-l4-narration.md`
Reviewer: AMAW Adversary (cold-start). Verdict: **REJECTED** (1 BLOCK).

---

## BLOCK-1 — D1 asserts the L3 retry-loop lesson is "applied verbatim" but pins none of the three holes for L4

**Problem.** D1 says `run_l4_with_retries` is "structurally identical" to `run_l3_with_retries`
and "the Phase-2 retry-loop lesson is applied verbatim." It then names the three holes
("subset-narrowing retries, transport-vs-validation discrimination on an explicit `failure`
field, out-of-subset error filtering") but only *names* them — it pins nothing. Compare
Phase 2's D3, which spends a full section nailing down the exact reframed preamble string,
the empty-vs-non-empty output shape of `format_errors_for_retry`, and the documented
deviation from TMP_008b §4.2's "keep all other entries unchanged" wording. Phase 3's spec
of `format_l4_errors_for_retry` is one bullet in §2 ("reusing the Phase-2 subset-retry
shape") with **no preamble text given**. All three captured holes are re-openable as written:

- **Hole 1 (subset preamble references absent objects).** TMP_008b §4.3 gives L4 *no*
  retry-message format at all — §4.2's preamble is L3-only and says "keep all other
  entries unchanged." The L4 loop re-sends only the failing zone subset, so a verbatim
  copy of that wording references zones not in the payload. The spec must pin the L4
  preamble verbatim (the way Phase-2 D3 does).
- **Hole 2 (discriminate on `failure`, not emptiness).** D2 says `L4Attempt` carries
  "every failure in `.failure`", but the spec never states that `run_l4_with_retries`
  discriminates transport-failure on `L4Attempt.failure.is_some()` and **never** on
  `narrations.is_empty()`. A parsed empty `{"zone_narrations":[]}` is a validation
  failure (every zone `[MISSING]`) whose errors must drive the retry context — retry.rs
  lines 122-132 are the exact pattern that must be re-pinned for L4.
- **Hole 3 (out-of-subset error filtering).** retry.rs lines 117-120 filter
  `errors.retain(|e| subset_ids.contains(e.obj_id()))` so a re-emitted already-accepted
  zone's error does not leak into the next retry context. The L4 spec never states the
  equivalent `L4ValidationError::zone_id()` accessor or the retain filter. Phase-2 D4
  explicitly required an exhaustive-`match` `obj_id()` accessor — Phase 3 must specify the
  `zone_id()` analogue and the retain step.

**Why it matters.** The captured lesson is explicit: Phase 3's L4 loop *mirrors* the L3
loop and must be checked that it does NOT re-introduce the three holes. "Applied verbatim"
is an assertion, not a contract — a BUILD agent with no Phase-2 context will copy §4.2's
L3 wording (the only retry-message format in TMP_008b) and re-open Hole 1, and may
discriminate on `narrations.is_empty()` because nothing forbids it.

**Spec fix.** Add to D1 the three pinned items at Phase-2 D3/D4 granularity: (a) the L4
subset-retry preamble verbatim with a documented deviation note from TMP_008b §4.3; (b) an
explicit sentence "discriminate transport failure on `L4Attempt.failure.is_some()`, never
on `narrations.is_empty()`"; (c) the `L4ValidationError::zone_id()` accessor (exhaustive
`match`) plus the `errors.retain` filter. Add ACs asserting the preamble first line and a
parsed-empty L4 response driving a `[MISSING]`-per-zone retry.

---

## WARN-2 — D4 `canonical_default_narration`: the >=50-char R3 guarantee is not pinned, and the un-revalidated wrong-language stub has no specified consumer contract

**Problem.** D4 says the stub is `"{zone_id} is a quiet {terrain} region. ..."` "padded to
>=50 chars so it satisfies R3." (1) The *padding mechanism* is undefined — a short `zone_id`
plus short `terrain` token yields a string near but possibly not over 50 chars, and
"padded" names no deterministic rule. R3 is `50..=2000`; the lower bound is the live risk.
Phase-2's `generate_default_tag` pinned its determinism precisely (`take(64)`, sanitised);
D4 does not. (2) D4 says the stub is "NOT re-validated" and may be English when another
`NarrationLanguage` was requested — but the spec never says what consumes
`L4Result.narrations`. §10 key-phrase extraction runs on the narration text; an English
stub fed to a per-reality corpus extractor is "degraded but present" only if every
downstream consumer tolerates wrong-language text. That tolerance is asserted via §6's
"always playable" but never verified against an actual consumer.

**Why it matters.** If a real `zone_id`/`terrain` combination produces a 48-char stub, the
"§6 always-succeeds" guarantee silently yields an R3-invalid terminal answer, and since the
stub is "not re-validated" nothing catches it. AC-5 is a test assertion, not a construction
rule; the construction must guarantee >=50.

**Spec fix.** Pin the padding rule deterministically — e.g. state the literal template text
is >=50 chars with both substitution slots empty, or specify an explicit pad-to-50 step.
Name the L4Result consumers in scope (§10 extraction; bootstrap report) and assert each
tolerates a wrong-language stub, or scope the wrong-language degradation explicitly to V2.
AC-5 should assert >=50 chars for the shortest possible `zone_id`, not a fixture zone.

---

## WARN-3 — D6 key-phrase extraction: the stopword set is unspecified, so "fully deterministic" is not implementable from the spec alone

**Problem.** D6 claims `extract_key_phrases` is "fully deterministic" and the tie-break
`(count desc, first-appearance asc)` is correctly pinned. But the stopword set is described
only as "a small ASCII stopword set" — not enumerated. The output is a direct function of
which terms are stopwords; two BUILD implementers choosing different "small" sets produce
different phrase lists for the same narration. Determinism holds only within one
implementation, not as a contract. Secondary: D6 tokenizes "on non-alphanumeric
boundaries" and the narration may legitimately be CJK (R4 supports `Zh`/`Ja`/`Ko`) — CJK
has no whitespace word boundaries, so tokenization yields one giant token or per-codepoint;
D6 does not say which. A 50-char narration that is mostly punctuation/digits is also
unaddressed — whether digit-only tokens are eligible phrases is undefined.

**Why it matters.** Deterministic key-phrase extraction is the §10 selling point and a
named scope item; if the stopword set is left to the implementer it is reproducible only by
accident. TMP_008b §10 only sketches TF-IDF and does not enumerate stopwords — the spec is
the place to close that and does not.

**Spec fix.** Enumerate the stopword set inline in D6 (a fixed ~20-40 word ASCII list), or
state the function takes the set as an argument with a pinned default constant in the spec.
State CJK tokenization behaviour explicitly (per-codepoint, or documented V1 cut). Add an AC
for a digit/punctuation-heavy narration defining whether digit-only tokens are eligible.

---

Captured rules: read pre-loaded (4 lessons incl. the L3 retry-loop holes); Guardrails relevant: none
