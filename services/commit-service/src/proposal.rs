//! What a proposal CARRIES — the wire contract, separate from the stages.
//!
//! Split out of `admission.rs` when `SEALED-SUBJECT` pushed that file past its
//! `IMP-D3` ceiling (398 -> 457 against 400). The cap's siblings answer this the
//! same way every time — `spine.rs` shed `spine_args`, `ruleset_boot` and
//! `reject_commit` rather than grow — and the split here is a real seam rather
//! than a line-count trick: one file defines what the wire carries, the other
//! runs stages over it.
//!
//! The question this module exists to answer in one screen: **what can a
//! submitter assert, and what can it not?**

/// A T6 proposal as carried on the bus (flat fields → parsed).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Proposal {
    /// EVT-L3 idempotency triple, parts 1..3.
    pub producer_service: String,
    pub proposal_id: String,
    pub target_channel: i64,
    /// The AGT-A6 Decision this proposal carries (executes nothing).
    pub decision: serde_json::Value,
    /// WHO submitted this — never WHICH ACTOR they are acting as.
    ///
    /// `SEALED-SUBJECT`. This was `pub actor: u64`: the island entity the
    /// submitter claimed to be, taken from the wire and believed. The producer
    /// SIGNATURE was verified and the SUBJECT was not, so the field naming the
    /// acting entity arrived from the party asserting it — `PID-D5`'s own
    /// argument, eleven lines below, applied to a different field and never to
    /// this one.
    ///
    /// The subject is now RESOLVED from `actor_control_binding` on the
    /// authoritative side (`crate::subject::resolve_subject`) and passed to
    /// [`admit_signed`] as a parameter. **A subject the caller cannot assert
    /// cannot be forged**, and the way to make it unassertable is for the field
    /// to be absent rather than ignored — an ignored field comes back.
    pub user_ref_id: uuid::Uuid,
    /// Offered candidates at decision time — (entity id, token) pairs; the
    /// validation set for `strike.target` (THR-A4 / REC-79).
    pub candidates: Vec<(u64, String)>,
}

/// Read ONLY `user_ref_id` out of a raw proposal.
///
/// The caller must know WHO submitted before it can resolve WHICH ACTOR they
/// may act as, and the resolution needs a database while admission is pure and
/// synchronous. So the caller peeks, resolves, and passes the answer in.
///
/// **Not a validation step and not a substitute for one.** It answers one
/// question and returns `None` for every other reason a body might be wrong;
/// `admit_signed` still runs the full schema stage over the same bytes and is
/// still what rejects a malformed proposal.
pub fn peek_user_ref_id(raw_json: &str) -> Option<uuid::Uuid> {
    serde_json::from_str::<serde_json::Value>(raw_json)
        .ok()?
        .get("user_ref_id")?
        .as_str()?
        .parse()
        .ok()
}
