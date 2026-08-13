//! `DF1a` — `dp`'s CHANNEL seams, behind the kernel's channel machinery.
//!
//! # What this closes
//!
//! [`dp_backend`](crate::dp_backend) put the kernel behind `dp`'s
//! reality-scoped write and read. Two channel-scoped seams were left with no
//! production implementor at all:
//!
//! * **[`dp::WriteBackend`] for a channel write.** `KernelWriteBackend` appends
//!   through `EventStore::append_events`, which writes an `events` row with no
//!   `channel_id`, no `channel_event_id`, no `writer_epoch` and no
//!   `channel_event_index` entry. `0014_channel_ordering.up.sql` defines that
//!   row as *reality-scoped* — a legitimate shape, and the wrong one for a
//!   channel-scoped aggregate. [`KernelChannelWriteBackend`] is the other one.
//! * **[`dp::ChannelTree`].** `SessionContext::move_to_channel` is the ONLY
//!   producer of a verified `ChannelId`, and it needs a tree to resolve
//!   against. Every implementor in the tree was a `#[cfg(test)]` double, so no
//!   production session could enter a channel — which is the other half of why
//!   the channel write surface had no callers. [`PgChannelTree`] answers it
//!   against the real `channels` table.
//!
//! # The sync/async bridge
//!
//! Same as `dp_backend`, for the same reason and with the same guard: `dp`'s
//! seams are synchronous so the contract crate carries no runtime, `sqlx` is
//! async, and `block_in_place` panics on a current-thread runtime — so both
//! types refuse one at construction rather than panicking mid-write.

use std::sync::Arc;

use dp::{ChannelResolution, ChannelTree, DpError, RealityId, WriteAck, WriteBackend, WriteRequest};
use tokio::runtime::{Handle, RuntimeFlavor};
use uuid::Uuid;

use crate::channel::{ChannelError, ChannelWriter};
use crate::envelope::EventEnvelope;

/// Shared guard: both types need a multi-thread runtime handle.
fn multi_thread_handle(who: &str) -> Result<Handle, DpError> {
    let handle = Handle::try_current().map_err(|_| DpError::ControlPlaneUnavailable {
        reason: format!("{who} must be constructed inside a tokio runtime"),
    })?;
    if handle.runtime_flavor() != RuntimeFlavor::MultiThread {
        return Err(DpError::ControlPlaneUnavailable {
            reason: format!(
                "{who} requires a MULTI-THREAD tokio runtime: dp's seams are synchronous, so \
                 this adapter blocks with block_in_place, which panics on a current-thread \
                 runtime"
            ),
        });
    }
    Ok(handle)
}

/// `dp::WriteBackend` over one channel's [`ChannelWriter`].
///
/// # One channel per backend, and that is the honest shape
///
/// `DP-Ch14` describes an SDK that looks up a writer lease per channel and
/// routes to whichever node holds it. **That is not built** — `route_to_writer`
/// has zero occurrences in the tree and is a row in
/// `CHANNEL_SPECIFIED_NOT_BUILT`. A backend pretending to dispatch across
/// channels while holding exactly one lease would be that unbuilt router
/// wearing a costume: it would accept a write for any channel and either write
/// it under the wrong lease or fail obscurely.
///
/// So this wraps ONE `(reality, channel)` writer under ONE lease — which is
/// what a writer node actually is — and REFUSES a request addressed elsewhere.
/// The day the lease cache lands, that refusal is the thing it replaces.
pub struct KernelChannelWriteBackend {
    writer: Arc<ChannelWriter>,
    handle: Handle,
    event_type: String,
    /// `RLS-A13`'s pin — the digest of the rules this writer node is running.
    ///
    /// Held by the BACKEND because it is a fact about the node, not about any
    /// one write. Today every call site stamps it by hand, so a forgotten one
    /// produces a committed fact that cannot say which rules made it, and
    /// nothing reports the omission. One place to set it is one place to
    /// forget it.
    ruleset_digest: Option<String>,
    /// `DP-A17`'s per-channel turn counter, shared with whoever advances it.
    ///
    /// # Why the WRITER holds this and the database does not
    ///
    /// `DF1b-ii`'s first design said the channel owned it, because
    /// `channel_writer_state.last_turn_number` is DB-authoritative and
    /// `ChannelAppended` returns it. Measuring the spine before building that
    /// showed it wrong: **the spine never calls `advance_turn`**, so that
    /// column stays 0 on its channel, and `recovery` reads the turn back out
    /// of EVENT METADATA. The writer's counter, persisted in metadata, is the
    /// source of truth — so moving the stamp to the DB would have replaced a
    /// correct value with a zero.
    ///
    /// An `AtomicU64` rather than a value: the caller advances it (only an
    /// APPLIED resolution does, per `EVT-V4`) and the backend reads it at
    /// append time, so the two cannot drift apart the way a copied number can.
    turn_counter: Option<Arc<std::sync::atomic::AtomicU64>>,
}

impl KernelChannelWriteBackend {
    /// Default event type for SDK-originated channel writes.
    ///
    /// Deliberately the same value `KernelWriteBackend` uses: the scope of a
    /// write is recorded by the `channel_id` COLUMN, which is exactly the
    /// distinction `0014` introduced. A second event type would encode the
    /// same fact twice in two places that can disagree.
    pub const SDK_EVENT_TYPE: &'static str = crate::dp_backend::KernelWriteBackend::<
        crate::event_store::shared_test_suite::InMemoryEventStore,
    >::SDK_EVENT_TYPE;

    pub fn new(writer: Arc<ChannelWriter>) -> Result<Self, DpError> {
        Ok(Self {
            writer,
            handle: multi_thread_handle("KernelChannelWriteBackend")?,
            event_type: Self::SDK_EVENT_TYPE.to_string(),
            ruleset_digest: None,
            turn_counter: None,
        })
    }

    /// Declare the ruleset this writer node is running (`RLS-A13`).
    ///
    /// Every event this backend appends carries it. A node that does not
    /// declare one writes `ruleset_digest: NULL`, which is the honest record of
    /// "this writer could not say" — not a default worth inventing.
    pub fn with_ruleset_digest(mut self, digest: impl Into<String>) -> Self {
        self.ruleset_digest = Some(digest.into());
        self
    }

    /// Share the channel's `DP-A17` turn counter (see the field's note on why
    /// the writer holds it and the database does not).
    pub fn with_turn_counter(mut self, counter: Arc<std::sync::atomic::AtomicU64>) -> Self {
        self.turn_counter = Some(counter);
        self
    }
}

impl WriteBackend for KernelChannelWriteBackend {
    fn apply(&self, req: &WriteRequest<'_>) -> Result<WriteAck, DpError> {
        // A channel backend handed a reality-scoped request is a wiring bug
        // with no correct answer: writing it here would put it on a channel it
        // was never addressed to. `t2_write`'s `Scope = RealityScope` bound
        // means feature code cannot produce this, so reaching it means a
        // hand-built request — which is exactly when a loud error is worth
        // more than a plausible one.
        let Some(channel) = req.channel else {
            return Err(DpError::SessionNotFound {
                session_id: format!(
                    "a reality-scoped write of {} reached the CHANNEL backend; \
                     the request carries no channel to write it to",
                    req.aggregate_type
                ),
            });
        };

        // The refusal message names `DP-Ch14` and NOT the unbuilt symbol, and
        // that is deliberate: a bare symbol name in a STRING LITERAL is code,
        // not a comment, so `CHANNEL_SPECIFIED_NOT_BUILT`'s existence check
        // cannot tell it from an implementation. Writing it here fired that
        // trigger — correctly. Do not put it back.
        let held = self.writer.lease().channel_id;
        if channel != held {
            return Err(DpError::ChannelDissolved {
                channel: format!(
                    "{} addressed channel {}, but this backend holds the lease for channel {} \
                     — cross-channel routing (DP-Ch14) is not built",
                    req.aggregate_type,
                    channel.get(),
                    held.get()
                ),
            });
        }

        let now: crate::envelope::Rfc3339Timestamp =
            chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
        let envelope = EventEnvelope {
            event_id: Uuid::new_v4(),
            // `DF1b-i` — see the sibling in `dp_backend`.
            event_type: if req.event_type == dp::DEFAULT_SDK_EVENT_TYPE {
                self.event_type.clone()
            } else {
                req.event_type.to_string()
            },
            event_version: 1,
            aggregate_id: req.aggregate_id.as_str().to_string(),
            aggregate_type: req.aggregate_type.to_string(),
            aggregate_version: req.expected_version.saturating_add(1),
            reality_id: req.reality.as_uuid(),
            occurred_at: now.clone(),
            recorded_at: now,
            payload: crate::dp_backend::event_payload(
                req.payload,
                req.payload_is_json,
                req.aggregate_type,
            )?,
            metadata: Some({
                let mut m = serde_json::json!({
                    "dp_tier": req.tier.as_key(),
                    "dp_cache_key": req.cache_key,
                    // The scope, recorded where a reader of the row can see it
                    // without joining. The COLUMN is authoritative; this is the
                    // label that makes a log line legible.
                    "dp_scope": "channel",
                });
                let obj = m.as_object_mut().expect("built as an object one line above");
                if let Some(cat) = req.event_category {
                    obj.insert("event_category".into(), cat.into());
                }
                if let Some(c) = &self.turn_counter {
                    // `CWC-A2` — a DECIMAL STRING, not a JSON number: the
                    // browser consuming this through the publisher loses
                    // precision past 2^53, and this is a BIGINT server-side.
                    let n = c.load(std::sync::atomic::Ordering::SeqCst);
                    obj.insert("turn_number".into(), n.to_string().into());
                }
                m
            }),
            // `RLS-A13` — the writer node's own declaration, stamped once here
            // instead of at every call site that might forget.
            ruleset_digest: self.ruleset_digest.clone(),
        };

        // `causal_refs` is `DP-Ch15` and belongs to the CALLER's intent, which
        // `WriteRequest` does not model. Empty rather than invented: a
        // fabricated causal edge is worse than an absent one, because
        // `DP-Ch28`'s aggregator walks these.
        let appended = tokio::task::block_in_place(|| {
            self.handle
                .block_on(async { self.writer.append(&envelope, &serde_json::json!([])).await })
        })
        .map_err(channel_err)?;

        // The channel position, not the aggregate version — this write's place
        // in the order its subscribers read.
        Ok(WriteAck {
            position: appended.channel_event_id as u64,
        })
    }
}

/// `ChannelError` into `DpError`.
///
/// # Why the fence rejection is not `DpError::WrongChannelWriter`
///
/// `DP-K3` declares `WrongChannelWriter { channel, expected: NodeId,
/// stale_epoch }`, and `dp`'s `DEFERRED_VARIANTS` defers it with `NodeId` named
/// as the blocker. **`NodeId` has existed since slice 4** — the row's stated
/// blocker was satisfied and nothing noticed, because the oracle checks that a
/// deferred variant is not also implemented and cannot check that its REASON is
/// still the reason.
///
/// The real blocker is one table short of that: `channel_writer_state` has
/// `reality_id`, `channel_id`, `current_epoch`, `last_event_id` and
/// `updated_at` — **no writer-node column**. The DB can say the epoch you
/// presented is stale; it cannot say who holds the lease instead. So `expected`
/// has no value to carry, and inventing one would be a lie in an error type.
///
/// `BackendIo` keeps `ChannelError`'s own message, which names the channel and
/// the presented epoch — everything the DB actually knows.
fn channel_err(e: ChannelError) -> DpError {
    DpError::BackendIo(Box::new(e))
}

/// `dp::ChannelTree` over the real `channels` table (`0019_channels`).
///
/// The reality is bound at construction for the reason
/// [`crate::dp_backend::KernelReadBackend`] gives: a tree that accepted one per
/// call could be handed a different reality than the session was bound to.
pub struct PgChannelTree {
    pool: Arc<sqlx::postgres::PgPool>,
    handle: Handle,
    reality: Uuid,
}

impl PgChannelTree {
    pub fn new(pool: Arc<sqlx::postgres::PgPool>, reality: Uuid) -> Result<Self, DpError> {
        Ok(Self {
            pool,
            handle: multi_thread_handle("PgChannelTree")?,
            reality,
        })
    }
}

impl ChannelTree for PgChannelTree {
    fn resolve(&self, reality: &RealityId, raw: i64) -> Result<ChannelResolution, DpError> {
        // The session's reality against the one this tree was built for. A
        // mismatch is the cross-tenant read `DP-R1` exists to refuse, and it is
        // checked before the query rather than trusted to the WHERE clause.
        if reality.as_uuid() != self.reality {
            return Err(DpError::RealityMismatch {
                ctx: format!("channel tree bound to {}", self.reality),
                requested: reality.as_uuid().to_string(),
            });
        }

        // Root-first by construction: `depth` is a stored column, so the order
        // is the tree's own, not one this query decides. `parent_depth` makes
        // depth and parentage unable to disagree (REC-106), so walking `parent`
        // and ordering by `depth` are the same walk.
        let rows: Vec<(i64, i16, Option<chrono::DateTime<chrono::Utc>>)> =
            tokio::task::block_in_place(|| {
                self.handle.block_on(async {
                    sqlx::query_as(
                        r#"
                        WITH RECURSIVE up AS (
                            SELECT id, parent, depth, dissolved_at
                              FROM channels
                             WHERE reality_id = $1 AND id = $2
                            UNION ALL
                            SELECT c.id, c.parent, c.depth, c.dissolved_at
                              FROM channels c
                              JOIN up ON c.id = up.parent
                             WHERE c.reality_id = $1
                        )
                        SELECT id, depth, dissolved_at FROM up ORDER BY depth ASC
                        "#,
                    )
                    .bind(self.reality)
                    .bind(raw)
                    .fetch_all(&*self.pool)
                    .await
                })
            })
            .map_err(|e| DpError::BackendIo(Box::new(e)))?;

        // The requested channel is the DEEPEST row, because the walk goes up.
        let Some(&(id, _, dissolved_at)) = rows.last() else {
            return Err(DpError::AggregateNotFound {
                aggregate: "channel",
                id: raw.to_string(),
            });
        };
        debug_assert_eq!(id, raw, "the recursive walk's deepest row is the seed");

        // `0019` constrains `(lifecycle = 'dissolved') = (dissolved_at IS NOT
        // NULL)`, so one column answers it and the two cannot disagree.
        if dissolved_at.is_some() {
            return Err(DpError::ChannelDissolved {
                channel: raw.to_string(),
            });
        }

        Ok(ChannelResolution {
            channel: raw,
            // Root-first, EXCLUDING the channel itself — which is the last row.
            ancestors: rows[..rows.len() - 1].iter().map(|&(id, _, _)| id).collect(),
        })
    }
}
