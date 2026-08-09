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
use crate::error::DpError;
use crate::session::{Millis, SessionContext};
use crate::tier::{Tier, T0, T1, T2, T3};

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

/// The storage seam. Implemented by `dp-kernel` (slice 5), never by feature code.
///
/// One method rather than four: the tier is passed as data because a BACKEND
/// genuinely does dispatch on it at runtime — a `T1` write goes to Redis, a
/// `T3` write to the event log. The compile-time tier discipline is the
/// caller's side of the boundary, enforced by the free functions below; the
/// backend's side is dynamic by nature.
pub trait WriteBackend {
    /// Apply a delta. `aggregate` is the `DP-Ch5` type token; `key` is the
    /// `DP-K7` cache key the write should land under.
    fn apply(
        &self,
        aggregate: &'static str,
        tier: crate::tier::TierLevel,
        key: &str,
        delta: &dyn core::any::Any,
    ) -> Result<WriteAck, DpError>;
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
    key: &str,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    T: Tier,
    A: DpAggregate<Tier = T>,
    A::Delta: 'static,
    B: WriteBackend,
{
    // The session is checked BEFORE the backend is touched. A write rejected
    // after it has been applied is not a rejection.
    guard(ctx, now_ms)?;
    backend.apply(A::TYPE_NAME, <T as Tier>::LEVEL, key, &delta)
}

/// `DP-K5` — T0 ephemeral write. No durability, no broadcast.
///
/// The tier bound is `DP-R5`: passing an aggregate of a different tier is a
/// type error, not a runtime one.
pub fn t0_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    key: &str,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T0>,
    A::Delta: 'static,
    B: WriteBackend,
{
    write_at_tier::<A, T0, B>(backend, ctx, now_ms, key, delta)
}

/// `DP-K5` — T1 volatile write. In-memory update + broadcast.
///
/// The tier bound is `DP-R5`.
pub fn t1_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    key: &str,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T1>,
    A::Delta: 'static,
    B: WriteBackend,
{
    write_at_tier::<A, T1, B>(backend, ctx, now_ms, key, delta)
}

/// `DP-K5` — T2 durable-async write. Cache write-through + outbox append.
///
/// The tier bound is `DP-R5`.
pub fn t2_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    key: &str,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T2>,
    A::Delta: 'static,
    B: WriteBackend,
{
    write_at_tier::<A, T2, B>(backend, ctx, now_ms, key, delta)
}

/// `DP-K5` — T3 durable-sync write. Event-log append + invalidation broadcast.
///
/// The tier bound is `DP-R5`.
pub fn t3_write<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    key: &str,
    delta: A::Delta,
) -> Result<WriteAck, DpError>
where
    A: DpAggregate<Tier = T3>,
    A::Delta: 'static,
    B: WriteBackend,
{
    write_at_tier::<A, T3, B>(backend, ctx, now_ms, key, delta)
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

    /// `3D.4`-style first implementor: the thing that makes these primitives a
    /// live path rather than four signatures.
    #[derive(Default)]
    struct Spy {
        seen: RefCell<Vec<(&'static str, TierLevel, String)>>,
        fail: Option<()>,
    }

    impl WriteBackend for Spy {
        fn apply(
            &self,
            aggregate: &'static str,
            tier: TierLevel,
            key: &str,
            _delta: &dyn core::any::Any,
        ) -> Result<WriteAck, DpError> {
            if self.fail.is_some() {
                return Err(DpError::RateLimited {
                    tier,
                    retry_after: core::time::Duration::from_millis(5),
                });
            }
            self.seen.borrow_mut().push((aggregate, tier, key.to_string()));
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
            BindRequest { reality: uuid::Uuid::from_u128(1), node: "n".into() },
            0,
        )
        .expect("bind")
    }

    #[test]
    fn a_write_reaches_the_backend_with_the_aggregates_own_tier_and_token() {
        let c = ctx();
        let spy = Spy::default();
        let key = cache_key!(&c, T2, Inv, 5u64);
        let ack = t2_write::<Inv, _>(&spy, &c, 0, &key, 7).expect("write");

        assert_eq!(ack.position, 1);
        let seen = spy.seen.borrow();
        assert_eq!(seen.len(), 1);
        assert_eq!(seen[0].0, "write_fixture", "the DP-Ch5 token comes from the type");
        assert_eq!(seen[0].1, TierLevel::T2, "the tier comes from the type, not the caller");
        assert!(seen[0].2.contains(":t2:write_fixture:"), "key: {}", seen[0].2);
    }

    #[test]
    fn an_expired_session_never_reaches_the_backend() {
        // The ordering IS the property: a write rejected after it has been
        // applied is not a rejection.
        let c = ctx();
        let spy = Spy::default();
        let err = t2_write::<Inv, _>(&spy, &c, 1_000, "k", 1).expect_err("expired");
        assert_eq!(err.variant_name(), "CapabilityExpired");
        assert!(spy.seen.borrow().is_empty(), "the backend was touched despite an expired session");
    }

    #[test]
    fn backpressure_is_returned_not_swallowed() {
        // DP-R6: the primitive must hand RateLimited back to its caller. If it
        // ever grew a retry loop or an `.ok()`, this is what would catch it.
        let c = ctx();
        let spy = Spy { fail: Some(()), ..Default::default() };
        let err = t2_write::<Inv, _>(&spy, &c, 0, "k", 1).expect_err("rate limited");
        assert!(err.is_backpressure(), "{} must be backpressure", err.variant_name());
    }
}
