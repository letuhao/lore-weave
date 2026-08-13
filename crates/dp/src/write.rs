//! `DP-K5` — the tier-typed write primitives, and the backend seam under them.
//!
//! # `DP-R5` is the property, and it is enforced by the type checker
//!
//! *"No cross-tier mixing in a single write operation."* A `T2` aggregate
//! written through `t1_write` must not compile — not "should be caught in
//! review", not "returns `TierViolation` at runtime". Each primitive is bounded
//! `A: DpAggregate<Tier = T2>`, so the tier in the function name and the tier
//! in the aggregate's own type are the same fact, and a mismatch is `E0271` at
//! the call site. `tests/ui/write_wrong_tier.rs` pins it.
//!
//! `DpError::TierViolation` still exists and is still correct — it is what a
//! BACKEND returns when a dynamic path (an admin tool, a replay) reaches a tier
//! it may not. The compile-time rule is for feature code, where the tier is
//! known statically. Two mechanisms, two situations, and neither replaces the
//! other.
//!
//! # Why a seam and not an implementation
//!
//! `crates/dp` declares no I/O (`S2.3`), so a write surface HERE can only be a
//! trait — exactly as [`crate::session::ControlPlane`] is. [`WriteBackend`] is
//! that trait; its production implementor is `dp-kernel` (event store, outbox,
//! projection runner), which is slice 5's wiring.
//!
//! This is the shape §0.6c seals — *a trait ships WITH its first implementor* —
//! and the first implementor here is a `#[cfg(test)]` double, the same standing
//! `ControlPlane` has. Stated plainly rather than dressed up: **nothing in
//! production writes through this surface yet.** What IS proven today is the
//! part that is this crate's job — that the tier cannot be mixed, that the
//! session is checked before any backend is touched, and that backpressure is
//! returned rather than swallowed.
//!
//! # Not async, and that is a decision rather than an omission
//!
//! `DP-K5` writes `t1_write`..`t3_write` as `async fn`. They are synchronous
//! here, because the async-ness belongs to the BACKEND, not to the contract:
//! [`WriteBackend`] is the thing that talks to Redis and Postgres, and a
//! consumer wanting an async backend implements it on an async client and
//! drives it however it likes. Putting `async fn` in this crate would pull a
//! runtime contract into the one crate whose defining property is having none,
//! to describe waiting that this crate never does.
//!
//! Recorded as a deviation in [`DEFERRED_WRITE_FORMS`] rather than silently
//! taken: the day the seam needs to express cancellation or backpressure that
//! only a future can carry, this is the line to revisit.

use crate::aggregate::DpAggregate;
use crate::cache::KeyId;
use crate::error::DpError;
use crate::ids::{ChannelId, RealityId};
use crate::scope::{ChannelScope, RealityScope};
use crate::session::{Millis, SessionContext};
use crate::tier::{Tier, TierLevel, T0, T1, T2, T3};

/// `DP-K5` forms not built here, with what each waits on.
///
/// Same register discipline as `DEFERRED_VARIANTS` / `DEFERRED_IDS` /
/// `DEFERRED_CACHE_FORMS`, and read by `tests/spec_oracle.rs`.
pub const DEFERRED_WRITE_FORMS: &[(&str, &str)] = &[
    ("t3_write_multi", "DP-K5 multi-aggregate atomic write needs a transaction \
                        handle the seam does not model yet"),
    ("async_signatures", "deliberate deviation: async belongs to the backend \
                          impl, not to this no-I/O contract crate"),
];

/// Acknowledgement of a durable write (`DP-K5`).
///
/// One type for `T2` and `T3` rather than the spec's `T2Ack`/`T3Ack`, because
/// the two differ in *when* they are returned, not in what they carry — and
/// two structurally identical types would be a distinction the compiler
/// enforces and no reader can explain. If they diverge, split them then.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WriteAck {
    /// Monotonic position the write landed at, as the backend reports it.
    pub position: u64,
}

/// How a delta becomes bytes.
///
/// Separate from [`DpAggregate`] for the same reason [`crate::read::Decode`] is:
/// an aggregate's identity is design-time, its wire encoding is per-backend.
pub trait Encode: DpAggregate {
    /// Serialise a delta for the backend, or say why not.
    fn encode(delta: &Self::Delta) -> Result<Vec<u8>, DpError>;
}

/// Everything a backend needs to place a write.
///
/// A STRUCT, not five positional arguments, and the shape was decided by
/// writing the first real implementor rather than by taste. The seam originally
/// passed `(aggregate, tier, key, &dyn Any)`, and `dp-kernel` cannot build an
/// `EventEnvelope` from that: an envelope needs `reality_id`, `aggregate_id`,
/// `aggregate_type` and a payload, and the only place the first two appeared
/// was INSIDE the cache key as text. A backend parsing ids back out of a
/// formatted key would be re-deriving what the caller already knew, and would
/// silently break the day `DP-K7`'s format changed.
#[derive(Debug)]
pub struct WriteRequest<'a> {
    /// The verified reality. Only session bind can produce one.
    pub reality: &'a RealityId,
    /// `DP-Ch5` type token, from `A::TYPE_NAME`.
    pub aggregate_type: &'static str,
    /// The aggregate's own id, already validated as a key segment.
    pub aggregate_id: KeyId,
    /// The tier, from `A::Tier`.
    pub tier: TierLevel,
    /// The `DP-K7` cache key this write lands under.
    pub cache_key: &'a str,
    /// The encoded delta.
    pub payload: &'a [u8],
    /// The domain event this write records (`DF1b-i`), from
    /// [`DpAggregate::EVENT_TYPE`].
    ///
    /// Travels as data for the same reason the tier does: the backend
    /// dispatches on it at runtime, and the caller's side of the boundary is
    /// the aggregate's own declaration.
    pub event_type: &'static str,
    /// Whether [`Self::payload`] is the event's JSON body rather than opaque
    /// bytes, from [`DpAggregate::PAYLOAD_IS_JSON`].
    pub payload_is_json: bool,
    /// The event-taxonomy category, from [`DpAggregate::EVENT_CATEGORY`]
    /// (`DF1b-ii`). `None` for an aggregate that declares none.
    pub event_category: Option<&'static str>,
    /// The channel this write is addressed to, or `None` for a reality-scoped
    /// write.
    ///
    /// # This field is `DF1a`, and its absence is why the SDK had no callers
    ///
    /// `WriteRequest` had seven fields and none of them was a channel, while
    /// [`SessionContext`] has carried `current_channel_id` since slice 4 and
    /// the READ side takes the channel from exactly there
    /// ([`crate::read::read_projection_channel`]). So the write surface was
    /// structurally incapable of producing a channel-ordered event — and a
    /// channel-ordered event is what `DP-Ch11`/`DP-Ch13` make every live
    /// consumer read.
    ///
    /// A backend given `None` writes a reality-scoped event; per
    /// `0014_channel_ordering.up.sql`, *"reality-scoped events keep channel
    /// columns NULL"*. That is a legitimate shape — and it was the ONLY shape
    /// this seam could ask for, which made the wrong answer the silent one.
    ///
    /// It is `Option<ChannelId>` rather than two request types because the
    /// backend genuinely dispatches on it at runtime, which is the same
    /// argument [`WriteBackend`] already makes for carrying the tier as data.
    /// The COMPILE-time half is the caller's side: `t2_write` binds
    /// `Scope = RealityScope` and `t2_write_channel` binds
    /// `Scope = ChannelScope`, so which variant arrives here is decided by the
    /// aggregate's own declaration, not by a caller remembering.
    pub channel: Option<ChannelId>,
    /// The aggregate version the caller believes it is writing on top of.
    ///
    /// **`DP-K5` does not have this field, and the kernel requires it.** Its
    /// signatures are `t2_write(ctx, id, delta)`, but
    /// `EventStore::append_events` documents `expected_version` as MUST-equal
    /// the store's current high-water or the append returns
    /// `ConcurrencyConflict`. Discovered by wiring the real backend.
    ///
    /// The alternative — having the backend read the high-water and then append
    /// — is a lost update: two writers both read version 7, both append, and
    /// the second silently overwrites the first's intent. Optimistic
    /// concurrency only works if the EXPECTATION comes from the caller, so it
    /// travels here rather than being invented one layer down. `0` for a new
    /// aggregate.
    pub expected_version: u64,
}

/// The storage seam. Implemented by `dp-kernel` (slice 5), never by feature code.
///
/// One method rather than four: the tier travels as DATA because a backend
/// genuinely dispatches on it at runtime — a `T1` write goes to Redis, a `T3`
/// write to the event log. The compile-time tier discipline is the caller's
/// side of the boundary, enforced by the free functions below; the backend's
/// side is dynamic by nature.
pub trait WriteBackend {
    /// Apply one write.
    fn apply(&self, req: &WriteRequest<'_>) -> Result<WriteAck, DpError>;
}

/// The one gate every primitive passes through.
///
/// Ordering is deliberate and is the reason this is a function rather than a
/// line copied five times: **the session is checked BEFORE the backend is
/// touched.** An expired capability must not reach storage — a write that is
/// rejected after it has been applied is not a rejection.
fn guard(ctx: &SessionContext, now_ms: Millis) -> Result<(), DpError> {
    ctx.check_live(now_ms)
}

/// The shared body. Private, so the only public doors are the four tier-typed
/// functions below.
///
/// NOT a `macro_rules!`, and that is a deliberate reversal. The first version
/// generated the four functions from a macro, and `dp-aggregate-gate`'s `R10`
/// refused it: a `macro_rules!` body mentioning `DpAggregate` is opaque to
/// `syn`, so the gate cannot see whether it emits an impl and REFUSES rather
/// than guesses. That is over-broad for this case — the macro emitted functions,
/// not impls — and it is still the right default, because the alternative is a
/// gate that trusts a token stream it cannot read. Four explicit wrappers cost
/// forty lines and keep the guard at full strength; weakening `R10` to buy back
/// a macro would trade a hardened check for convenience.
fn write_at_tier<A, T, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    T: Tier,
    A: DpAggregate<Tier = T, Scope = RealityScope> + Encode,
    B: WriteBackend,
{
    // The session is checked BEFORE the backend is touched. A write rejected
    // after it has been applied is not a rejection.
    guard(ctx, now_ms)?;
    let payload = A::encode(&delta)?;
    backend.apply(&WriteRequest {
        reality: ctx.reality_id(),
        aggregate_type: A::TYPE_NAME,
        aggregate_id: id,
        tier: <T as Tier>::LEVEL,
        cache_key: key,
        event_type: A::EVENT_TYPE,
        payload_is_json: A::PAYLOAD_IS_JSON,
        event_category: A::EVENT_CATEGORY,
        // A reality-scoped aggregate has no channel to be addressed to, and
        // the bound above is what makes that a fact rather than a hope.
        channel: None,
        payload: &payload,
        expected_version,
    })
}

/// The channel-scoped sibling of [`write_at_tier`].
///
/// # Why the channel is not a parameter
///
/// `13_channel_ordering_and_writer.md DP-Ch14` sketches
/// `t2_write_channel(ctx, channel: &ChannelId, id, delta)`. This crate takes
/// the channel from the CONTEXT instead, for the reason
/// [`crate::read::read_projection_channel`] already gives: a channel argument
/// would let a caller write to a channel its session was never moved into, and
/// `SessionContext::move_to_channel` is the only producer of a verified
/// [`ChannelId`]. The read side made that choice first; two halves of one
/// surface disagreeing about where an address comes from would be worse than
/// either convention.
fn write_at_tier_channel<A, T, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    T: Tier,
    A: DpAggregate<Tier = T, Scope = ChannelScope> + Encode,
    B: WriteBackend,
{
    guard(ctx, now_ms)?;

    // Checked BEFORE the backend is touched, and before the delta is even
    // encoded — the same ordering, and the same words, as the read side.
    let Some(channel) = ctx.current_channel_id() else {
        return Err(DpError::SessionNotFound {
            session_id: format!(
                "{} is not in a channel, so it cannot write the channel-scoped {}",
                ctx.session_id(),
                A::TYPE_NAME
            ),
        });
    };

    let payload = A::encode(&delta)?;
    backend.apply(&WriteRequest {
        reality: ctx.reality_id(),
        aggregate_type: A::TYPE_NAME,
        aggregate_id: id,
        tier: <T as Tier>::LEVEL,
        cache_key: key,
        event_type: A::EVENT_TYPE,
        payload_is_json: A::PAYLOAD_IS_JSON,
        event_category: A::EVENT_CATEGORY,
        channel: Some(channel),
        payload: &payload,
        expected_version,
    })
}

/// `DP-K5` — T0 ephemeral write. No durability, no broadcast.
///
/// The tier bound is `DP-R5`: passing an aggregate of a different tier is a
/// type error, not a runtime one.
pub fn t0_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T0, Scope = RealityScope> + Encode,
    B: WriteBackend,
{
    write_at_tier::<A, T0, B>(backend, ctx, now_ms, id, key, expected_version, delta)
}

/// `DP-K5` — T1 volatile write. In-memory update + broadcast.
///
/// The tier bound is `DP-R5`.
pub fn t1_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T1, Scope = RealityScope> + Encode,
    B: WriteBackend,
{
    write_at_tier::<A, T1, B>(backend, ctx, now_ms, id, key, expected_version, delta)
}

/// `DP-K5` — T2 durable-async write. Cache write-through + outbox append.
///
/// The tier bound is `DP-R5`.
pub fn t2_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T2, Scope = RealityScope> + Encode,
    B: WriteBackend,
{
    write_at_tier::<A, T2, B>(backend, ctx, now_ms, id, key, expected_version, delta)
}

/// `DP-K5` — T3 durable-sync write. Event-log append + invalidation broadcast.
///
/// The tier bound is `DP-R5`.
pub fn t3_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T3, Scope = RealityScope> + Encode,
    B: WriteBackend,
{
    write_at_tier::<A, T3, B>(backend, ctx, now_ms, id, key, expected_version, delta)
}

/// `DP-Ch14` — T2 durable-async write to a CHANNEL.
///
/// The scope bound is the address discipline, and it is the write side finally
/// matching the read side: a reality-scoped aggregate cannot be written here,
/// because this signature would have nowhere to put the channel it does not
/// have. `tests/ui/write_wrong_scope.rs` is that claim executed by rustc.
///
/// # What this does NOT do, stated rather than implied
///
/// `DP-Ch14` also specifies **cross-node routing**: a writer-lease cache, and a
/// `RouteChannelWrite` gRPC hop when the calling node does not hold the lease.
/// Neither is built — `route_to_writer` has zero occurrences in the tree and is
/// a row in `CHANNEL_SPECIFIED_NOT_BUILT`. This is the LOCAL path only: the
/// backend it is handed either holds the lease for this channel or refuses.
/// A second node to route to does not exist yet, and a router with one node is
/// a mock wearing a distributed system's costume.
pub fn t2_write_channel<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T2, Scope = ChannelScope> + Encode,
    B: WriteBackend,
{
    write_at_tier_channel::<A, T2, B>(backend, ctx, now_ms, id, key, expected_version, delta)
}

/// `DP-Ch14` — T3 durable-sync write to a CHANNEL.
///
/// Same shape and same limits as [`t2_write_channel`]; the tier bound is
/// `DP-R5`.
pub fn t3_write_channel<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
    expected_version: u64,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T3, Scope = ChannelScope> + Encode,
    B: WriteBackend,
{
    write_at_tier_channel::<A, T3, B>(backend, ctx, now_ms, id, key, expected_version, delta)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cache_key;
    use crate::scope::RealityScope;
    use crate::session::{BindRequest, ControlPlane, VerifiedBind};
    use crate::tier::TierLevel;
    use core::cell::RefCell;

    struct Inv;
    impl DpAggregate for Inv {
        type Tier = T2;
        type Scope = RealityScope;
        type Id = uuid::Uuid;
        type Delta = i32;
        type Projection = ();
        const TYPE_NAME: &'static str = "write_fixture";
    }
    impl Encode for Inv {
        fn encode(delta: &i32) -> Result<Vec<u8>, DpError> {
            Ok(delta.to_le_bytes().to_vec())
        }
    }

    /// What the spy recorded. A named struct rather than a five-tuple:
    /// `clippy::type_complexity` refused the tuple, and it was right that
    /// `(&str, TierLevel, String, Vec<u8>, Uuid)` tells a reader nothing.
    struct Seen {
        aggregate_type: &'static str,
        tier: TierLevel,
        cache_key: String,
        payload: Vec<u8>,
        reality: uuid::Uuid,
    }

    /// `3D.4`-style first implementor: the thing that makes these primitives a
    /// live path rather than four signatures.
    #[derive(Default)]
    struct Spy {
        seen: RefCell<Vec<Seen>>,
        fail: Option<()>,
    }

    impl WriteBackend for Spy {
        fn apply(&self, req: &WriteRequest<'_>) -> Result<WriteAck, DpError> {
            if self.fail.is_some() {
                return Err(DpError::RateLimited {
                    tier: req.tier,
                    retry_after: core::time::Duration::from_millis(5),
                });
            }
            self.seen.borrow_mut().push(Seen {
                aggregate_type: req.aggregate_type,
                tier: req.tier,
                cache_key: req.cache_key.to_string(),
                payload: req.payload.to_vec(),
                reality: req.reality.as_uuid(),
            });
            Ok(WriteAck { position: 1 })
        }
    }

    struct Cp;
    impl ControlPlane for Cp {
        fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
            Ok(VerifiedBind {
                reality: req.reality,
                session: uuid::Uuid::from_u128(7),
                capability_secret: "s".into(),
                expires_at_ms: 1_000,
            })
        }
    }

    fn ctx() -> SessionContext {
        SessionContext::bind(
            &Cp,
            BindRequest {
                reality: uuid::Uuid::from_u128(1),
                node: "n".into(),
                service: crate::ServiceIdentity::new("test-harness").expect("valid"),
            },
            0,
        )
        .expect("bind")
    }

    #[test]
    fn a_write_reaches_the_backend_with_the_aggregates_own_tier_and_token() {
        let c = ctx();
        let spy = Spy::default();
        let key = cache_key!(&c, T2, Inv, 5u64);
        let ack = t2_write::<Inv, _>(&spy, &c, 0, KeyId::from(5u64), &key, 0, 7).expect("write");

        assert_eq!(ack.position, 1);
        let seen = spy.seen.borrow();
        assert_eq!(seen.len(), 1);
        assert_eq!(seen[0].aggregate_type, "write_fixture", "the DP-Ch5 token comes from the type");
        assert_eq!(seen[0].tier, TierLevel::T2, "the tier comes from the type, not the caller");
        assert!(seen[0].cache_key.contains(":t2:write_fixture:"), "key: {}", seen[0].cache_key);
        assert_eq!(seen[0].payload, 7i32.to_le_bytes().to_vec(), "the ENCODED delta reaches the backend");
        assert_eq!(
            seen[0].reality,
            c.reality_id().as_uuid(),
            "the verified reality travels as a value, not parsed back out of the key"
        );
    }

    #[test]
    fn an_expired_session_never_reaches_the_backend() {
        // The ordering IS the property: a write rejected after it has been
        // applied is not a rejection.
        let c = ctx();
        let spy = Spy::default();
        let err = t2_write::<Inv, _>(&spy, &c, 1_000, KeyId::from(1u64), "k", 0, 1).expect_err("expired");
        assert_eq!(err.variant_name(), "CapabilityExpired");
        assert!(spy.seen.borrow().is_empty(), "the backend was touched despite an expired session");
    }

    #[test]
    fn backpressure_is_returned_not_swallowed() {
        // DP-R6: the primitive must hand RateLimited back to its caller. If it
        // ever grew a retry loop or an `.ok()`, this is what would catch it.
        let c = ctx();
        let spy = Spy { fail: Some(()), ..Default::default() };
        let err = t2_write::<Inv, _>(&spy, &c, 0, KeyId::from(1u64), "k", 0, 1).expect_err("rate limited");
        assert!(err.is_backpressure(), "{} must be backpressure", err.variant_name());
    }
}
