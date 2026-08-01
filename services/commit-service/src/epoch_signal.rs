//! `Q0b B3b` — how a running channel finds out its reality's rules changed.
//!
//! ```text
//! admin-cli / Forge  ──▶ activate_reality_epoch ──▶ reality_ruleset_binding INSERT
//!                                                 └▶ meta_outbox {reality.ruleset.bound}
//!                        meta-outbox-relay ──▶ XADD lw.meta.events
//!   ┌────────────────────────────────────────────────────────────────────┐
//!   │ THIS MODULE: the spine reads that stream, re-reads the BINDING, and │
//!   │ hands the host an ordered `IngressItem::EpochSwitch` to submit.     │
//!   └────────────────────────────────────────────────────────────────────┘
//! ```
//!
//! ## The stream is a NUDGE. The table is the TRUTH.
//!
//! The obvious implementation reads `epoch` and `ruleset_digest` out of the
//! event payload and switches to them. This one does not, and the difference is
//! the whole design:
//!
//! * The stream is **at-least-once**. A redelivered `bound` event for epoch 4
//!   arriving after epoch 5 already applied would, on the payload-trusting
//!   version, be an attempt to move a live island *backwards*. `RLS-I1` refuses
//!   it — so it would be safe, but it would be safe by rejection, and every
//!   redelivery would produce a refusal metric an operator has to learn to
//!   ignore. Re-reading the table collapses N deliveries into one correct
//!   answer, because the table always names the *current* epoch.
//! * The payload is a **copy** of a row. `reality_ruleset_binding` is
//!   append-only and audited (`migrations/meta/033`, `meta_write`); the Redis
//!   entry is a derived artifact that can be trimmed by `MAXLEN`, replayed by an
//!   operator, or emitted twice. When a copy and its source disagree, an engine
//!   that believed the copy is an engine that runs rules nobody authorised.
//! * It makes a **missed signal survivable**. See `reconcile`.
//!
//! So the event carries exactly one bit of information — *something changed,
//! look* — and everything acted upon is read from the meta DB.
//!
//! ## Why each channel gets its OWN consumer group
//!
//! `lw.meta.events` is one stream for the whole deployment. A consumer group is
//! a *work-splitting* primitive: two members of the same group each get a
//! DIFFERENT subset of entries. Two channels of one reality sharing a group
//! would therefore split the binding events between them, and the channel that
//! did not get the entry would never switch — half the reality on the old rules,
//! no error anywhere. Each writer takes a group named for its own
//! `(reality, channel)` so every one of them sees every entry. The group is the
//! *fan-out* mechanism here, not the load-balancing one.

use meta_rs::metawrite::{pk_as_string, ValueMap};
use sim_core::RulesetEpoch;

use crate::bus::BusMessage;
use crate::ruleset_boot::RulesetBoot;

/// The meta event name the binding table declares on INSERT
/// (`contracts/meta/events_allowlist.yaml`). One name for both creation and a
/// later switch — a consumer that cares reads the epoch, per the allowlist's
/// own note.
pub const BINDING_EVENT: &str = "reality.ruleset.bound";

/// The stream `meta-outbox-relay` drains the meta outbox onto.
pub const META_STREAM: &str = "lw.meta.events";

/// The consumer group for one channel's writer.
///
/// Distinct per `(reality, channel)` — see the module doc. Two writers must
/// never share one, and the shape of this function is what makes that hard to
/// get wrong by accident.
pub fn signal_group(reality_id: &str, channel: i64) -> String {
    format!("epoch-signal:{reality_id}:ch{channel}")
}

/// Connect this channel's writer to the binding-signal rail.
///
/// Reuses [`crate::bus::ProposalBus`] rather than growing a second Redis
/// consumer: the discipline it already implements — idempotent `XGROUP CREATE`,
/// ack-only-after-processing, `XAUTOCLAIM` reclaim, dead-letter after
/// `max_attempts` instead of a silent drop — is the same discipline this rail
/// needs, and a second implementation of it is a second place for those rules to
/// be got subtly wrong.
///
/// `block_ms: 0` NEVER blocks. The proposal fetch already owns the loop's
/// latency; blocking here would add this timeout to every idle iteration for a
/// stream that is empty almost always.
pub async fn connect_signal_bus(
    redis_url: &str,
    reality_id: &str,
    channel: i64,
) -> anyhow::Result<crate::bus::ProposalBus> {
    crate::bus::ProposalBus::connect(
        redis_url,
        crate::bus::BusConfig {
            stream: META_STREAM.to_string(),
            group: signal_group(reality_id, channel),
            consumer: format!("writer-ch{channel}"),
            block_ms: 0,
            batch: 32,
            max_attempts: 5,
            reclaim_min_idle_ms: 30_000,
        },
    )
    .await
}

/// `authorised_by` for a committed `RulesetEpochActivated`: the primary key of
/// the `reality_ruleset_binding` row this transcribes.
///
/// **Composed by `meta_rs::pk_as_string`, not by a `format!` here**, and that is
/// deliberate. The composite spelling (`epoch=4|reality_id=<uuid>` — sorted by
/// column name, so `epoch` precedes `reality_id`) is decided by the meta layer
/// and is already pinned by a live Postgres test. A second hand-written
/// implementation of it in this file would be a mirror nothing forces to agree,
/// and the day the two disagreed the audit join would silently return no rows —
/// the failure mode being a *missing* match, which looks like "no such
/// authorisation" rather than like a bug.
pub fn authorised_by(reality_id: &str, epoch: u32) -> String {
    let mut pk = ValueMap::new();
    pk.insert("reality_id".into(), serde_json::Value::String(reality_id.to_string()));
    pk.insert("epoch".into(), serde_json::Value::from(epoch));
    pk_as_string(&pk)
}

/// A binding-change signal addressed to this reality.
///
/// Deliberately carries no digest. The epoch is kept only so the log line can
/// say what prompted the look; the value acted on comes from [`reconcile`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BindingSignal {
    pub reality_id: String,
    pub epoch: u32,
}

/// Recognise a `reality.ruleset.bound` entry for `reality_id`.
///
/// `None` covers three genuinely different things — a different event name, a
/// different reality, or an entry this code cannot parse — and the caller must
/// treat them the same way: **not our business, ack it**. That is correct for
/// the first two and is a judgement call for the third: `lw.meta.events` is a
/// shared stream carrying every meta write in the deployment, so an entry we
/// cannot parse is overwhelmingly likely to be another table's event whose
/// payload shape we have no reason to know. Dead-lettering those would fill the
/// dead stream with other people's traffic.
///
/// The one case that must NOT be silent is an entry that IS ours and IS
/// malformed, and it is separated out below rather than folded in here.
pub fn parse_binding_signal(msg: &BusMessage, reality_id: &str) -> Option<BindingSignal> {
    if msg.field("event_name")? != BINDING_EVENT {
        return None;
    }
    let payload: serde_json::Value = serde_json::from_str(msg.field("payload")?).ok()?;
    let pk = payload.get("pk")?;
    let id = pk.get("reality_id")?.as_str()?;
    if id != reality_id {
        return None;
    }
    Some(BindingSignal {
        reality_id: id.to_string(),
        // `as_u64` and not a string parse: `meta_write` puts the epoch in the
        // payload as a JSON NUMBER (`Value::from(u32)`), and the relay passes
        // the jsonb through verbatim rather than re-marshalling it.
        epoch: pk.get("epoch")?.as_u64()? as u32,
    })
}

/// True when the entry names our reality on the binding event but could not be
/// parsed into a [`BindingSignal`].
///
/// The distinction [`parse_binding_signal`] cannot make on its own: "someone
/// else's event" and "OUR event, broken" both come back as `None`, and the
/// second one is a defect that must reach a human. Used by the caller to
/// dead-letter rather than ack.
pub fn is_malformed_for_us(msg: &BusMessage, reality_id: &str) -> bool {
    if msg.field("event_name") != Some(BINDING_EVENT) {
        return false;
    }
    // The reality id is also present in `aggregate_id` (`epoch=N|reality_id=…`),
    // which is a FLAT string field and therefore survives a payload this code
    // cannot parse. That is the only reason a malformed entry can be attributed
    // to us at all.
    let ours = msg
        .field("aggregate_id")
        .is_some_and(|a| a.contains(&format!("reality_id={reality_id}")));
    ours && parse_binding_signal(msg, reality_id).is_none()
}

/// What the host should submit to the island, if anything.
#[derive(Debug, Clone)]
pub struct PendingSwitch {
    pub from_epoch: RulesetEpoch,
    pub to_epoch: RulesetEpoch,
    pub rules: std::sync::Arc<ruleset_core::Ruleset>,
    pub digest: String,
    pub authorised_by: String,
}

/// Read the reality's CURRENT binding and report whether the island is behind.
///
/// This is the whole of B3b's decision logic, and it is deliberately
/// signal-independent: nothing in it takes the stream entry as a parameter.
/// Three consequences, all wanted:
///
/// 1. **A missed signal is survivable.** The consumer group is created at `$`,
///    so an activation landing between this node's boot read and its group
///    creation is not delivered to it — a real race, narrow but not zero. The
///    host calls this once at startup *after* the group exists, and the gap
///    closes: the table says epoch 5, the island says 4, the switch happens
///    without any event having been received.
/// 2. **Redeliveries are free.** Every duplicate resolves to the same answer,
///    and once the island has caught up the answer is `None` — not a refusal.
/// 3. **It is testable without Redis at all**, which is why the parsing above
///    and the deciding here are separate functions.
///
/// `Ok(None)` = nothing to do. That includes the island being AHEAD of the
/// table, which is not an error the host can act on: it means someone rolled
/// the binding back, which migration 033 forbids, or this node is reading a
/// replica that has not caught up. Either way the correct move is to leave the
/// island where it is and let the next signal re-ask.
pub fn reconcile(
    boot: &RulesetBoot,
    reality_id: &str,
    island_epoch: RulesetEpoch,
) -> anyhow::Result<Option<PendingSwitch>> {
    let (rules, binding) = boot.load(reality_id)?;
    let to = RulesetEpoch(binding.epoch);
    if to <= island_epoch {
        return Ok(None);
    }
    Ok(Some(PendingSwitch {
        from_epoch: island_epoch,
        to_epoch: to,
        rules: std::sync::Arc::new(rules),
        digest: binding.digest.clone(),
        authorised_by: authorised_by(reality_id, binding.epoch),
    }))
}
