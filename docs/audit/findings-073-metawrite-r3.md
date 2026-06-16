# Findings - 073 admin-cli MetaWrite audit adapter - DESIGN REVIEW R3 (FINAL)

Task: pgx meta.DB driver (sdks/go/metapg) + admin-cli MetaWriteSink mapping
audit_emitter.Action -> admin_action_audit via contracts/meta.MetaWrite.
Reviewer: AMAW Adversary, cold-start, round 3 (design-final).
Files reviewed (ONLY these): plan shimmying-splashing-micali.md sec1-3; contracts/meta/metawrite.go;
migrations/meta/015_admin_action_audit.up.sql; services/admin-cli/internal/audit_emitter/emitter.go.

Verdict: APPROVED_WITH_WARNINGS (0 BLOCK, 3 WARN).

---

## R1+R2 resolution check

R1-BLOCK1 (hex-hash vs BYTEA(32)) - RESOLVED. Plan sec2 specifies hex.DecodeString(Action.ErrorDetailHash)
-> reject unless len==32 -> bind raw bytes. Action.ErrorDetailHash (emitter.go:37) is the 64-char hex
SHA-256; decoded 32B satisfies admin_action_audit_error_hash_sha256 (length(...)=32). Correct.

R1-BLOCK2a (actor_type vocab) - RESOLVED. Plan sec2 pins actor_type='admin' constant (a member of the
015 enum {admin,system,service,retention_cron,owner,cron}); Action.ActorRole (admin/sre/founder) is NOT
mapped into actor_type. The residual gap (role silently dropped) is now W1 below.

R1-BLOCK2b (actor_id non-UUID) - RESOLVED. Plan sec2 uuid.Parse(Action.Actor) + reject non-UUID; sec3
makes dev-token subjects (non-UUID) structurally unable to reach this Sink (refuse ALLOW_DEV_TOKENS
when META_DATABASE_URL set). Sound.

R1-WARN3b (fail-open destructive) - RESOLVED. sec3 refuses destructive + no-DB + non-dry-run unless
ADMIN_CLI_ALLOW_UNAUDITED=1. Conscious opt-out.

R2-BLOCK1/BLOCK2 (error_detail_scrubbed + parameters unsourced) - RESOLVED via HASH-ONLY mode. sec2:
parameters={"params_hash":...}; on error the quad = decoded 32B hash + sentinel
"[admin-cli: error hash retained; raw text not stored]" + scrub_version="admincli-hashonly-v1" +
scrubbed_at=cfg.Clock; non-error all four NULL. Satisfies scrubber_quad_consistent,
error_kind_has_scrubber, and error_hash_sha256 honestly. Raw-error-TEXT retention correctly DEFERRED
(D-ADMINAUDIT-ERROR-TEXT). Resolved.

All-three-outcome CHECK sweep (the r3 focus):
- started -> SKIP (no row); no result_kind ever attempted -> avoids enum violation. OK
- success -> quad all-NULL -> passes error_kind_has_scrubber (<>'error' AND raw_hash NULL) + quad-consistent. OK
- dry_run -> keyed on result_kind=='error', NOT "non-success" -> quad all-NULL -> both error-CHECKs pass.
  Plan sec2 wording ("On non-error: all four NULL") is correct: dry_run is non-error. Confirmed (this was the
  specific trap; mapping branches failed->error, everything-else->quad-NULL, so dry_run is safe).
- created_at GENERATED column never inserted (sec2); only created_at_nanos from cfg.Clock (> 2020 boundary
  1577836800000000000 holds for any real clock). OK
- NOT-NULL columns all sourced: audit_id(UUIDGen), command_name(Action.CommandName), command_version
  (const "1.0.0"), actor_id(parsed UUID), actor_type('admin'), parameters({params_hash}),
  result_kind(mapped), created_at_nanos(Clock). reality_id NULL ok; result has DEFAULT. OK

R1+R2 are genuinely closed. The three items below are the most serious REMAINING problems.

---

## [WARN] W1 - MetaWriteIntent.Actor (Type/ID) for the meta_write_audit row is UNSPECIFIED; risks intent.Validate failure or wrong actor mapping

The double-audit path is the spec'd design ("Forks resolved"): one admin_action_audit row (the Sink's
NewValues) AND one meta_write_audit row written by MetaWrite itself (metawrite.go:280-300). The
meta_write_audit row is populated from intent.Actor.Type / intent.Actor.ID (metawrite.go:287-288),
NOT from the Sink's NewValues. The plan details the eight admin_action_audit columns but is SILENT on
what intent.Actor.Type and intent.Actor.ID are set to.

Two failure modes:
1. MetaWrite calls intent.Validate(cfg.Allowlist) BEFORE touching the DB (metawrite.go:150). If
   MetaWriteIntent.Validate enforces Actor.Type in vocab and/or non-empty Actor.ID (likely - it is the
   universal write-audit actor), an intent omitting Actor fails at the contract boundary and NO audit row of
   either kind lands. (intent.go was outside the review set -> must-confirm, not proven -> WARN not BLOCK.)
2. If Actor.ID = Action.Actor (UUID string) that is fine for meta_write_audit.actor_id (ActorID string), but
   the plan must say so explicitly so the builder does not leave it empty or reuse the params_hash NewValues.

Fix (one line): Sink sets intent.Actor = meta.Actor{Type: ActorTypeAdmin, ID: Action.Actor} (same validated
UUID string), matching the admin_action_audit mapping. Confirm intent.Validate's Actor rules at BUILD before
first green test.

## [WARN] W2 - cfg.Scrubber (RegexScrubber) runs over the Sink's NewValues for the meta_write_audit COPY - incl the BYTEA hash and params_hash - with undefined behaviour on []byte

MetaWrite is configured with Scrubber=meta.NewRegexScrubber(nil) (sec3). At metawrite.go:268-270 it deep-copies
and scrubs auditAfter = ScrubValuesMap(in.NewValues, cfg.Scrubber) for the meta_write_audit copy. The Sink's
NewValues for an error row contains error_detail_raw_hash as []byte (32 raw bytes) plus the sentinel string
and params_hash hex.
- ScrubValuesMap over a []byte leaf: behaviour on non-string/byte-slice leaves is unverified (scrubber.go
  outside review set). If it stringifies or regex-walks raw bytes, the meta_write_audit.after_values JSONB
  copy of the hash is corrupted. The admin_action_audit row itself is fine - inserted from in.NewValues
  verbatim by BuildInsert, not the scrubbed copy. Fidelity bug in the write-log copy only -> WARN.
- The 64-hex params_hash and 32B raw hash are high-entropy; a careless PII regex (long hex-run matcher) could
  rewrite them in the copy. Low probability but unverified.

At BUILD: PG-gated assertion that meta_write_audit.after_values round-trips the hash fields unmangled, OR an
explicit decision that the copy may differ. Add to Verification section.

## [WARN] W3 - params_hash empty-string vs absent, and parameters NOT-NULL/'{}' default interaction underspecified

Action.ParamsHash (emitter.go:31) is a plain string with no not-empty guarantee. Plan sec2 says
parameters={"params_hash": Action.ParamsHash} ({} if absent). "If absent" is ambiguous for an empty string:
{"params_hash":""} is valid JSONB and passes NOT-NULL, but is a misleading forensic fingerprint (reads as
"params hashed to empty" not "no params"). Pin: empty/absent ParamsHash -> emit {} (omit key); non-empty ->
{"params_hash":<v>}. Trivial, but it is the load-bearing forensic field - do not leave to builder discretion.

---

Net: the hash-only redesign closes every 015 CHECK for all three persisted outcomes (success/dry_run/error),
the started-skip avoids the enum gap, and metapg defer-rollback-after-commit is safe (pgx ErrTxClosed swallowed
at metawrite.go:181/203; nil-Outbox is a safe skip at metawrite.go:303). No ship-stopping defect remains - the
three WARNs are confirm-at-BUILD design clarifications (intent.Actor mapping, scrubber-over-bytes fidelity,
params_hash empty-vs-absent), not unsatisfiable contracts. Approving the design.

Captured rules: read pre-loaded.
