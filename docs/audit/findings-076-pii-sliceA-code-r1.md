# AMAW Adversary — Code Review R1 — 076 D-PII-PRODUCTION, Slice A

Cold-start adversarial review. Reviewed ONLY the 7 listed files. Exactly 3 findings.

---

## [BLOCK] Non-`any` container leaves bypass the scrubber entirely -> PII under-redaction

**File:** `contracts/meta/scrubber.go:181-204` (`scrubValueDepth`), reached from `ScrubValuesMap` at `metawrite.go:258-259`.

`scrubValueDepth` only recurses into `string`, `map[string]any`, and `[]any`. Everything
else falls to the `default:` arm and is returned **by reference, unscrubbed**:

    default:
        // Numbers, bools, nil, and other scalar types carry no free text.
        return v

The comment is false for several concrete cases that legitimately appear in
caller-built audit maps (BeforeValues/AfterValues are map[string]any, but their
*values* are arbitrary):

- `[]byte` — a JSON/text blob field stored as bytes passes through verbatim. A
  contact_email stored as []byte("alice@example.com") lands in meta_write_audit RAW.
  This is exactly the leak the slice exists to stop.
- `map[string]string` / `[]string` — a typed string map/slice (common when a caller
  copies a struct field that isn't map[string]any) is never walked, so every PII string
  inside is persisted raw.
- `json.RawMessage`, fmt.Stringer, any struct with string fields — same.

The design note (scrubber.go:177) claims "numbers/bools/nil pass through untouched,
bounding the collateral" — but the actual default arm catches FAR more than
numbers/bools/nil. Since the spec's own rule is "under-redaction is the risk"
(scrubber.go:122), silently shipping a []byte/map[string]string PII value to the audit
table verbatim is a ship-stopping correctness/privacy defect, not over-redaction.

The test suite only ever exercises string, map[string]any, []any, int, bool, float64,
nil (scrubber_value_test.go:9-44) — the gap is untested.

**Remediation (pick one):**
1. Reflection fallback in default: if reflect.Kind is Map/Slice/Array over string-bearing
   elements, deep-copy + scrub; else pass through.
2. Cheaper/fail-closed: redact any default-arm value whose reflect.Kind()==String or that
   is []byte/json.RawMessage to "[UNSCRUBBABLE]", and document that audit maps must use
   map[string]any/[]any/string/scalar only. Add tests for []byte, map[string]string,
   []string proving no raw PII survives.

Either way the default: comment must stop asserting "carry no free text" — that is the
load-bearing falsehood.

---

## [WARN] `ScrubVersion` hardcoded to regex-v1 regardless of which Scrubber is injected

**File:** `contracts/meta/metawrite.go:261` (`scrubVersion = regexScrubberVersion`).

Config.Scrubber is the pluggable Scrubber interface, but writeOneInTx stamps the version
from the package const regexScrubberVersion ("regex-v1") rather than from the Scrubber
that actually ran. If a caller injects anything other than RegexScrubber — e.g.
PassthroughScrubber (does NOT redact) or a future regex-v2 — scrub_version LIES. A
retroactive re-scrub job keyed on scrub_version (the column's stated purpose, migration
027:3-4) would skip rows never actually redacted, or run the wrong ruleset. Today prod
only injects RegexScrubber so the label is accidentally correct, but coupling the label
to a concrete type while accepting the interface is a latent integrity hole.

**Remediation:** the Scrub(in.Reason) call on metawrite.go:260 already returns a
ScrubbedField{Version: ...} — set scrubVersion from that .Version instead of the const.
(Or add Version() string to the Scrubber interface.)

---

## [WARN] RequestContext (trace_id/request_id/source_service) never scrubbed even with a Scrubber

**File:** `contracts/meta/metawrite.go:273` -> serialized raw at `query_builder.go:109-113`.

With a Scrubber configured, writeOneInTx scrubs before/after/reason but copies
in.RequestContext straight through, and BuildAuditInsert marshals trace_id/request_id/
source_service into the request_context JSON column verbatim. Usually opaque IDs (hence
WARN not BLOCK), but RequestID is caller-controlled free text in some services and can
carry user-supplied correlation strings (emails, account refs) on diagnostic paths. The
slice's goal is "stop PII landing verbatim in meta_write_audit"; one un-scrubbed
free-text-capable column in the same row is an inconsistency worth a tracked decision.

**Remediation:** either (a) document in migration 027 + scrubber.go that request_context
is contractually ID-only and add an intent validator rejecting non-ID RequestID, or
(b) run scrubString over the three RequestContext fields in the Scrubber-on branch. A
one-line Deferred-Items row is the minimum.

---

Captured rules: read pre-loaded.
