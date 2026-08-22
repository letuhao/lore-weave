//! `Q0b B3c` — the lease-holding writer transcribes the switch into its channel.
//!
//! This is the last link of the chain `B3a` described and the reason the whole
//! path is possible at all:
//!
//! > `RLS-A14` makes `ruleset.epoch_activated` **EVT-T8 Administrative**, and
//! > `EVT-P8` forbids a non-admin emitter — which reads like *"admin-cli must
//! > write the row"*. It cannot. `ChannelWriter::append` CASes on
//! > `channel_writer_state.current_epoch`, so **only the process holding that
//! > channel's writer lease may append**, and admin-cli holds no lease.
//!
//! The two claims are not the same. Producer identity records who
//! **authorised** the change; the authorisation is the durable, audited
//! `reality_ruleset_binding` row. This module's writer merely **transcribes**
//! that decision into its own channel, and it cannot invent one: `authorised_by`
//! is composed from the binding it just read, so an event with no matching row
//! cannot be produced by this path at all.
//!
//! ## Why `N` events and not one
//!
//! One per affected channel, each appended independently by that channel's own
//! writer. `RLS-D17` forbids a reality-wide barrier, and a single reality-scoped
//! event would need a writer — and that writer would BE the barrier. This is
//! also why `dp::channel_pause` was never built: with each channel transcribing
//! its own switch there is nothing to coordinate.

use std::sync::Arc;

use dp_kernel::channel::ChannelWriter;
use dp_kernel::envelope::EventEnvelope;
use sim_core::{Island, Outcome, RulesetEpoch, Seq, StepStatus};
use uuid::Uuid;

use crate::epoch_signal::{reconcile, PendingSwitch};
use crate::hostclock::now_rfc3339;
use crate::ruleset_boot::RulesetBoot;
use crate::CombatDomain;

/// The canonical event name — the registry entry `contracts/events/_registry.yaml`
/// declares with `owner: commit-service`.
pub const EVENT_TYPE: &str = "ruleset.epoch_activated";

/// What happened to one reconciliation attempt.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EpochOutcome {
    /// The island was already at or beyond the bound epoch. The overwhelmingly
    /// common case under at-least-once delivery, and explicitly NOT a refusal:
    /// nothing was attempted, so nothing was refused.
    AlreadyCurrent,
    /// Switched and committed.
    Activated { from: RulesetEpoch, to: RulesetEpoch, channel_event_id: i64 },
    /// The island refused the switch at its pop — a newer epoch had already
    /// applied, so this delivery was stale. **No event is appended**, because
    /// nothing happened on this channel and the log must not claim otherwise.
    Superseded { attempted: RulesetEpoch },
    /// `SC-A8` — the island is poisoned and the host must rebuild it. Reported
    /// rather than swallowed: a poisoned island silently reported as
    /// `AlreadyCurrent` would look like a reality that simply never switches.
    Poisoned,
    /// The binding could not be read, or the append failed. The island stays
    /// where it is and the next iteration re-asks.
    ///
    /// A distinct variant rather than an `Err`, because the CALLER's correct
    /// response is different: an error out of the spine's loop stops a writer
    /// that is otherwise healthy, and "I could not check for a newer epoch" is
    /// not a reason to stop committing turns under the epoch it already holds.
    Unavailable,
}

/// Drain the binding signals, then reconcile against the TABLE.
///
/// The drain decides nothing: [`reconcile_and_commit`] re-reads
/// `reality_ruleset_binding` regardless, so this function's only jobs are
/// keeping the consumer group from lagging and noticing a malformed entry that
/// is ours. **It reconciles even on an empty batch** — that is what closes the
/// boot race, since the group is created at `$` and an activation landing
/// between the boot read and the group's creation is never delivered here.
///
/// Lives beside the committer rather than in the binary because the binary is
/// at its `IMP-D3` ceiling and this is the epoch path's business, not the
/// spine loop's.
pub async fn drain_and_reconcile(
    signals: &mut crate::bus::ProposalBus,
    boot: &RulesetBoot,
    reality: &dp::RealityId,
    channel: i64,
    isle: &mut Island<CombatDomain>,
    writer: &ChannelWriter,
    aggregate_version: &mut u64,
    turn_number: u64,
) -> anyhow::Result<EpochOutcome> {
    let reality_str = reality.as_uuid().to_string();
    let mut to_ack = Vec::new();
    for msg in signals.fetch().await? {
        if crate::epoch_signal::is_malformed_for_us(&msg, &reality_str) {
            // OURS and unparseable — a defect, not other people's traffic.
            signals
                .dead_letter(&msg, "reality.ruleset.bound for this reality is malformed")
                .await?;
            continue;
        }
        if let Some(sig) = crate::epoch_signal::parse_binding_signal(&msg, &reality_str) {
            println!(
                "EPOCH-SIGNAL binding moved to epoch {} — re-reading the table",
                sig.epoch
            );
        }
        to_ack.push(msg.id.clone());
    }
    signals.ack(&to_ack).await?;

    // A META-DB FAILURE MUST NOT KILL THE WRITER, and this `match` is the whole
    // reason `drain_and_reconcile` exists as a wrapper.
    //
    // Before this slice the spine's loop never touched the meta DB; the epoch
    // path made it a per-iteration dependency. Propagating the error would mean
    // a transient blip on the meta database takes down a channel writer that is
    // otherwise perfectly healthy — it already HOLDS its rules and is committing
    // turns correctly. Not being able to check for a NEWER epoch is a degraded
    // state, not an incorrect one, and the reconcile is idempotent: the next
    // iteration re-asks and catches up.
    //
    // The append error is folded in with it deliberately. A failed append means
    // the island may have switched while the event did not land — genuinely bad
    // — but the recovery is the same: the island is now AT the bound epoch, so
    // the next reconcile returns `AlreadyCurrent` and no duplicate is written.
    // That gap is why this logs loudly rather than counting silently.
    let outcome = match reconcile_and_commit(
        boot, reality, channel, isle, writer, aggregate_version, turn_number,
    )
    .await
    {
        Ok(o) => o,
        Err(e) => {
            println!(
                "EPOCH-RECONCILE-FAILED channel {channel} (island stays at epoch {}): {e}",
                isle.epoch.0
            );
            return Ok(EpochOutcome::Unavailable);
        }
    };
    match &outcome {
        EpochOutcome::AlreadyCurrent => {}
        EpochOutcome::Activated { from, to, channel_event_id } => println!(
            "EPOCH-ACTIVATED {} -> {} on channel {channel} -> channel_event_id \
             {channel_event_id} (digest {})",
            from.0,
            to.0,
            isle.digest.to_hex()
        ),
        EpochOutcome::Superseded { attempted } => println!(
            "EPOCH-SUPERSEDED attempt at {} lost to a newer switch; NOTHING appended",
            attempted.0
        ),
        EpochOutcome::Poisoned => println!(
            "EPOCH-SKIPPED island {channel} is POISONED (SC-A8); the host must rebuild it"
        ),
        // Unreachable: the only construction site is the `Err` arm above, which
        // returns. Matched explicitly rather than with `_` so a future variant
        // fails to compile here instead of being silently unlogged.
        EpochOutcome::Unavailable => {}
    }
    Ok(outcome)
}

/// Read the binding, switch the island if it is behind, and commit the event.
///
/// The three steps are one function because they must not be separable: an
/// island that switched without the append would run new rules whose activation
/// no consumer can see, and an append without the switch would announce rules
/// this channel is not running. Neither half is meaningful alone.
///
/// **The append happens only on `Outcome::Applied`.** The switch goes in as an
/// ordinary ingress item (`RLS-A14`), so it takes its place in the queue and can
/// legitimately lose: a redelivery that arrives behind a newer switch pops as
/// `Discarded { Superseded }`. Committing an "activated" event for a switch the
/// island rejected is the one outcome that would make the channel log lie, and
/// it is exactly what a naive `submit(); append();` would do.
pub async fn reconcile_and_commit(
    boot: &RulesetBoot,
    reality: &dp::RealityId,
    channel: i64,
    isle: &mut Island<CombatDomain>,
    writer: &ChannelWriter,
    aggregate_version: &mut u64,
    turn_number: u64,
) -> anyhow::Result<EpochOutcome> {
    // SC-A8 poison-not-resume, checked BEFORE the reconcile and not after.
    //
    // A poisoned island returns `StepStatus::Poisoned` from every `step`, which
    // is not `Idle` — so the drain below would spin forever at 100% CPU. And
    // because this runs on EVERY loop iteration rather than only when a proposal
    // arrives, an island that poisoned while behind on epoch would hang the
    // writer the moment it went idle. Refusing here is `SC-A8` anyway: swapping
    // rules is work, and an island the host must rebuild does not get quietly
    // repaired.
    if isle.is_poisoned() {
        return Ok(EpochOutcome::Poisoned);
    }

    let Some(pending) = reconcile(boot, &reality.as_uuid().to_string(), isle.epoch)? else {
        return Ok(EpochOutcome::AlreadyCurrent);
    };

    let seq = isle.submit_epoch_switch(pending.to_epoch, Arc::clone(&pending.rules));
    // Drains everything queued, not just the switch — which is the point of the
    // ordered path. Items queued ahead of it resolve under the OLD rules, items
    // behind it under the new ones, and each is checked at ITS pop.
    //
    // `Poisoned` breaks rather than loops: an `apply` can panic DURING this
    // drain (the queued items ahead of the switch are ordinary domain work), so
    // the guard above is necessary and not sufficient.
    while !matches!(isle.step(), StepStatus::Idle | StepStatus::Poisoned) {}
    if isle.is_poisoned() {
        return Ok(EpochOutcome::Poisoned);
    }

    match outcome_for(isle, seq) {
        Some(Outcome::Applied { .. }) => {}
        Some(Outcome::Discarded { .. }) => {
            return Ok(EpochOutcome::Superseded { attempted: pending.to_epoch })
        }
        // `Buffered` is not reachable for a switch — it has no preconditions to
        // wait on — and a missing seq means `step` did not process what it was
        // just handed. Both are engine defects rather than operational states,
        // so they are errors and not a quiet `AlreadyCurrent`.
        other => anyhow::bail!(
            "epoch switch to {} resolved as {other:?}, which is not a state this path can \
             produce: the switch was submitted to the live lane and stepped to Idle",
            pending.to_epoch.0
        ),
    }

    *aggregate_version += 1;
    let env = envelope(
        reality,
        channel,
        &pending,
        isle.digest.to_hex(),
        *aggregate_version,
        turn_number,
    );
    let appended = writer.append(&env, &serde_json::json!([])).await?;
    Ok(EpochOutcome::Activated {
        from: pending.from_epoch,
        to: pending.to_epoch,
        channel_event_id: appended.channel_event_id,
    })
}

/// The outcome recorded for exactly this `Seq`.
///
/// Searched from the BACK: `outcomes()` accumulates for the island's whole life,
/// and the switch we just submitted is at or near the end. A forward scan would
/// be correct and get slower every turn.
fn outcome_for(isle: &Island<CombatDomain>, seq: Seq) -> Option<&Outcome<CombatDomain>> {
    isle.outcomes().iter().rev().find(|(s, _)| *s == seq).map(|(_, o)| o)
}

/// The `RulesetEpochActivatedV1` body — the seven fields
/// `contracts/events/reality.go` declares, under the names its `json:` tags
/// give them.
///
/// `pub` so a test can assert that key set against the Go struct without a
/// database, a lease or an island. That parity is the thing most likely to rot:
/// the two definitions live in different languages, in different directories,
/// and nothing but a test makes them agree.
///
/// `digest` comes from the island **after** the swap rather than from
/// `pending`, and that is `RLS-A13`: the pin is DERIVED from the rules the
/// island actually runs (`Domain::rules_digest`), never copied from the record
/// that asked for them.
pub fn activation_payload(
    reality: &dp::RealityId,
    channel: i64,
    from_epoch: RulesetEpoch,
    to_epoch: RulesetEpoch,
    digest: &str,
    authorised_by: &str,
    activated_at: &str,
) -> serde_json::Value {
    serde_json::json!({
        "reality_id": reality.as_uuid().to_string(),
        "channel_id": channel,
        "from_epoch": from_epoch.0,
        "to_epoch": to_epoch.0,
        "digest": digest,
        "authorised_by": authorised_by,
        "activated_at": activated_at,
    })
}

/// Build the `RulesetEpochActivatedV1` envelope around [`activation_payload`].
fn envelope(
    reality: &dp::RealityId,
    channel: i64,
    pending: &PendingSwitch,
    digest: String,
    aggregate_version: u64,
    turn_number: u64,
) -> EventEnvelope {
    let at = now_rfc3339();
    EventEnvelope {
        event_id: Uuid::new_v4(),
        event_type: EVENT_TYPE.into(),
        event_version: 1,
        // The channel's existing aggregate line, same as `proposal.rejected`
        // uses. The switch is not a combat fact, but it IS a fact about this
        // channel's ordered log, and giving it a private aggregate id would
        // start a second version line inside one channel — two counters over one
        // ordering, which is how a replayer ends up with gaps it cannot explain.
        aggregate_id: format!("enc-{channel}"),
        aggregate_type: "combat_session".into(),
        aggregate_version,
        reality_id: reality.as_uuid(),
        occurred_at: at.clone(),
        recorded_at: at.clone(),
        payload: activation_payload(
            reality,
            channel,
            pending.from_epoch,
            pending.to_epoch,
            &digest,
            &pending.authorised_by,
            &at,
        ),
        metadata: Some(serde_json::json!({
            // EVT-T8 Administrative — NOT T6. A rules change is an admin act
            // transcribed here, not gameplay this channel produced.
            "event_category": "T8",
            // EVT-V4: a switch is not a turn, so this is the channel's CURRENT
            // counter, unadvanced — exactly what `proposal.rejected` stamps.
            //
            // The first version OMITTED this field, reasoning that "absent" was
            // the honest encoding of "unchanged". It was not, and it was a live
            // break: `game-server/src/wire/turnOutcome.ts` calls
            // `toU64String(meta.turn_number, …)` UNCONDITIONALLY, before it
            // switches on `event_type`, and that call is outside the replay
            // loop's try/catch. A committed event with no `turn_number` throws
            // `turn_number: missing` and takes down the whole channel
            // projection — permanently, because replay meets the same event
            // every time. The repo's encoding of "unchanged" is *the same
            // number again*, and it always was.
            //
            // CWC-A2 — decimal STRING, never a JSON number: the browser
            // consuming this loses precision past 2^53.
            "turn_number": turn_number.to_string(),
        })),
        // The island's derived pin — the same value the payload carries, and
        // stamped for the same reason every other event on this channel is.
        ruleset_digest: Some(digest),
    }
}
