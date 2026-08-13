//! `DF1b-ii` — the admission refusal, committed **through the data-plane SDK**.
//!
//! # The first production caller of a DP tier primitive
//!
//! Measured at `718c29fc9`: `crates/dp` exposed six primitives and **zero
//! production call sites**. The only `t2_write` in the tree was inside
//! `dp_backend`'s own `#[cfg(test)]`, and the two services depending on `dp`
//! used it solely for `RealityId`. A contract with no traffic.
//!
//! This is the traffic. The spine's REJECT-COMMIT — whose own comment already
//! called it *"the doc-15 `t2_write` outcome"* — stops hand-building an
//! `EventEnvelope` and goes through `dp::t2_write_channel`.
//!
//! # Why it could not simply be re-pointed
//!
//! Routing it at `DF1a` would have BROKEN it four ways, each measured:
//!
//! * `event_type` would have become `dp.write.applied`, and
//!   `game-server/src/wire/turnOutcome.ts`'s `TURN_OUTCOME_TYPES` dispatches on
//!   the NAME — the refusal would have stopped rendering. Fixed by
//!   `DpAggregate::EVENT_TYPE` (`DF1b-i`).
//! * the payload would have become a base64 blob, and both projectors read
//!   named fields. Fixed by `PAYLOAD_IS_JSON`.
//! * `event_category` would have been dropped. Fixed by `EVENT_CATEGORY`.
//! * `ruleset_digest` — `RLS-A13`'s pin — would have become `NULL`. Fixed by
//!   `KernelChannelWriteBackend::with_ruleset_digest`, which stamps the writer
//!   node's declaration once instead of at every call site that might forget.
//!
//! # Extracted rather than inlined
//!
//! `bin/spine.rs` sits at its `IMP-D3` 375-line ceiling, and the gate refuses a
//! file that grows past its allowlisted size. `epoch_commit.rs` is the
//! precedent: the lease-holding writer's other transcription lives in its own
//! module for the same reason.

use std::sync::atomic::AtomicU64;
use std::sync::Arc;

use dp::{scope::ChannelScope, tier::T2, DpAggregate, DpError, Encode, KeyId, SessionContext};
use dp_kernel::channel::ChannelWriter;
use dp_kernel::dp_channel::{KernelChannelWriteBackend, PgChannelTree};

/// The channel-scoped aggregate an admission refusal writes.
///
/// `aggregate_type` stays `combat_session` and the id stays `enc-{channel}`:
/// this continues the channel's existing aggregate line, and renaming it would
/// orphan every row already written against it. The name is legacy vocabulary
/// (`D-14`) and is not this change's to rewrite.
pub struct ProposalRejected;

impl DpAggregate for ProposalRejected {
    type Tier = T2;
    type Scope = ChannelScope;
    type Id = String;
    type Delta = serde_json::Value;
    type Projection = ();
    const TYPE_NAME: &'static str = "combat_session";
    /// Registered in `contracts/events/_registry.yaml` by `DFO-4`, which found
    /// that the one domain event this system produces in anger had no contract.
    const EVENT_TYPE: &'static str = "proposal.rejected";
    const PAYLOAD_IS_JSON: bool = true;
    /// `T6`. Stamped by the WRITER — `PID-D5` removed this from the proposal
    /// wire format because reading it off an untrusted payload let a proposal
    /// pick its own privilege tier.
    const EVENT_CATEGORY: Option<&'static str> = Some("T6");
}

impl Encode for ProposalRejected {
    fn encode(d: &serde_json::Value) -> Result<Vec<u8>, DpError> {
        serde_json::to_vec(d).map_err(|e| DpError::BackendIo(Box::new(e)))
    }
}

/// Everything the writer node needs to make SDK writes on its channel: a
/// session ADDRESSED to that channel, and a backend carrying the node's facts.
///
/// Returned as a pair from one function because the two are useless apart — a
/// channel-scoped write needs both, and building them at separate call sites is
/// how one of them ends up pointed at a different channel. It also keeps
/// `bin/spine.rs` under its `IMP-D3` ceiling, which is a real constraint rather
/// than a tidiness preference: the gate refuses the commit.
///
/// `move_to_channel` is the only producer of a verified `ChannelId`, and until
/// `PgChannelTree` shipped no production session could hold one — so this is
/// also the first production use of the channel-tree seam.
pub fn wire(
    pool: Arc<sqlx::postgres::PgPool>,
    session: &SessionContext,
    channel: i64,
    now_ms: u64,
    ruleset_digest: String,
    turn_counter: Arc<AtomicU64>,
    writer: Arc<ChannelWriter>,
) -> Result<(SessionContext, KernelChannelWriteBackend), DpError> {
    // The reality comes from the SESSION, not from a parameter.
    //
    // It was a `reality: uuid::Uuid` argument, and `reality-id-adoption-gate`
    // red on it: `commit-service` went 0 -> 1 adoptable sites. The gate is
    // right and the finding is not cosmetic — the caller already holds a
    // VERIFIED `RealityId` in `session`, so a second bare `Uuid` beside it is
    // a value that can disagree with the one the control plane authorised.
    // Two sources for one identity, which is `DFO-5`'s shape.
    let tree = PgChannelTree::new(pool, session.reality_id().as_uuid())?;
    let ctx = session.move_to_channel(&tree, channel, now_ms)?;
    let backend = KernelChannelWriteBackend::new(writer)?
        // `RLS-A13` and `DP-A17`: both are facts about this NODE, so it
        // declares them once here instead of at every write.
        .with_ruleset_digest(ruleset_digest)
        .with_turn_counter(turn_counter);
    Ok((ctx, backend))
}

/// Commit one refusal. Returns the channel position the SDK acknowledged.
///
/// `expected_version` is the caller's belief about the aggregate's current
/// version, and the backend writes at `expected + 1` — so the caller passes the
/// version it has and advances its own afterwards. That is `DP-K5`'s optimistic
/// concurrency, and it is why the version travels rather than being read one
/// layer down: two writers both reading 7 and both appending is a lost update.
///
/// **`EVT-V4`: a refusal does NOT advance the turn.** Nothing here touches the
/// counter; the backend stamps its current value.
pub fn commit_rejection(
    backend: &KernelChannelWriteBackend,
    ctx: &SessionContext,
    now_ms: u64,
    channel: i64,
    expected_version: u64,
    stage: &str,
    reason: &str,
) -> Result<u64, DpError> {
    // `KeyId::new` VALIDATES the segment (a `:` in an id would forge a key
    // boundary), which is why there is no `From<String>` to reach for.
    let id = KeyId::new(format!("enc-{channel}")).ok_or_else(|| DpError::SessionNotFound {
        session_id: format!("enc-{channel} is not a legal DP-K7 key segment"),
    })?;
    let key = dp::cache_key!(channel: ctx, T2, ProposalRejected, id.clone())
        .ok_or_else(|| DpError::SessionNotFound {
            session_id: format!(
                "the writer's session is not in channel {channel}, so it has no DP-K7 channel key"
            ),
        })?;
    let body = serde_json::json!({ "rejected_at_stage": stage, "reason": reason });
    let ack = dp::t2_write_channel::<ProposalRejected, _>(
        backend,
        ctx,
        now_ms,
        id,
        &key,
        expected_version,
        body,
    )?;
    Ok(ack.position)
}
