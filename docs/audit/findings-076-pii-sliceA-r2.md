# Findings — 076 D-PII-PRODUCTION, Slice A (round 2, adversary cold-start)

Scope: PLAN (Slice A) + `contracts/meta/metawrite.go`, `query_builder.go`, `scrubber.go`.
Verdict: **APPROVED_WITH_WARNINGS** (0 BLOCK, 3 WARN). The r1 BLOCK is resolved; the plan is shippable. The three WARNs are correctness/coverage gaps the author should fold into BUILD before they become hidden PII-landing or migration-ordering surprises.

---

## R1 resolution check

- **r1-BLOCK1 (in-place ScrubValuesMap mutates `in.NewValues`, shared by outbox payload + persisted write -> corrupts downstream projections): RESOLVED.**
  Plan step 1 now mandates `ScrubValue`/`ScrubValuesMap` return an immutable DEEP COPY (new maps/slices at every level, never write back). Step 2 is explicit: `writeOneInTx` scrubs ONLY the audit-row copies into FRESH maps; the data write + outbox payload keep the ORIGINAL unscrubbed `in.NewValues`/`in.ExpectedBefore`. Ordering is correct — the CAS/data write (metawrite.go:227) and the outbox `Payload{"after": in.NewValues}` (metawrite.go:274) both read originals; the scrub feeds only `BuildAuditInsert`. Closes the corruption path.

- **r1-WARN2 (structured over-redaction guts the forensic before/after diff): RESOLVED (documented).**
  Plan step 1 restricts redaction to STRING LEAVES only (numbers/bools/nil pass through), limiting collateral; step 3 requires documenting the intentional lossy-diff caveat in the 027 migration comment + a DEFERRED row. Correct security-first posture, now explicit rather than silent.

- **r1-WARN3 (scrub_version nil-contract + column-order + no RawHash correlator): RESOLVED.**
  Plan: nil Scrubber -> `ScrubVersion=""` written EXPLICITLY (not relying on DEFAULT); set -> `"regex-v1"`. Column+arg order agreement in `BuildAuditInsert` is called out (append `scrub_version` as 12th column AND 12th arg). RawHash-quad-vs-version divergence rationale documented. Contract now unambiguous.

---

## [WARN] 1 — A second, hand-rolled `meta_write_audit` writer (`pgwrite`) is invisible to the plan's wiring sweep

`services/meta-worker/pkg/pgwrite/pgwrite.go` `(*Audit).WriteAudit` (lines 142-149) inserts into `meta_write_audit` with its OWN literal 11-column INSERT — it never goes through `MetaWrite`/`Config`/`BuildAuditInsert` and never touches a Scrubber. Plan step 4 finds live sites by grepping `meta.Config{`; that grep will NOT surface pgwrite, so the canon fan-out audit path silently stays un-scrubbed and outside the scrub_version contract.

- Migration safety: OK. 027 is `ADD COLUMN ... NOT NULL DEFAULT ''`, so pgwrite (which omits the column) keeps working and gets `''`, same as nil-Scrubber path. This is why WARN not BLOCK.
- Coverage gap. pgwrite's after-map is a fixed `{book_id, attribute_path}` (non-user-text today), so PII risk is low now — but it is a verbatim `meta_write_audit` writer the plan does not enumerate. Action: step 4 should explicitly enumerate pgwrite and either (a) document it writes only non-PII structured keys (accept), or (b) route its `after` through `ScrubValuesMap`. Choose consciously.

## [WARN] 2 — admin-cli scrub at the emitter scrubs `Reason` but the before/after payload scrub depends on the separate prod Sink wiring

Plan step 5 routes `Action.Reason` through `RegexScrubber` in `audit_emitter/emitter.go`. That correctly fixes the verbatim-Reason leak (emitter.go:24-36 — `ParamsHash`/`ErrorDetailHash` already hashed, but `Reason` is a raw string passed straight to `Sink.Write`). However the admin row lands via the prod `Sink` (a MetaWrite adapter to `admin_action_audit`) — a different seam from `meta_write_audit`. Scrubbing Reason at the emitter is necessary but not sufficient if that adapter's `Config.Scrubber` isn't also wired (step 4). Action: in BUILD confirm the admin Sink's MetaWrite `Config` also gets `NewRegexScrubber`, else Reason is clean but param diffs may not be. Add an emitter test asserting Reason redaction + a note that Sink-side scrub is step-4's responsibility.

## [WARN] 3 — `scrub_version="regex-v1"` is set even when nothing was scrubbed, weakening the retro-rescrub signal

Plan step 2 sets `ScrubVersion="regex-v1"` whenever `cfg.Scrubber != nil`, independent of whether any leaf matched. Most `meta_write_audit` rows have empty/structured before/after with no PII. So `scrub_version='regex-v1'` means "produced under the regex-v1 ruleset", NOT "PII was found/redacted here". Defensible (it lets a retro re-scrub target rows by version) but a job scanning `WHERE scrub_version='regex-v1'` hits a large majority of no-op rows. Action: document this semantic in the 027 migration comment ("version of ruleset applied; presence does NOT imply a redaction occurred") so future re-scrub authors don't assume version => hit.

---

Captured rules: read pre-loaded.
