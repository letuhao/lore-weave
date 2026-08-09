//! `DP-K4` — the read primitives.
//!
//! # Scope-typed, where the write surface is tier-typed
//!
//! `DP-K5` names its primitives after tiers (`t2_write`); `DP-K4` names its
//! after SCOPE (`read_projection_reality` / `_channel`). That is not an
//! inconsistency — the two dispatch on different things. A write's guarantees
//! come from its tier, so the tier is in the name and in the bound. A read's
//! ADDRESS comes from its scope: a reality-scoped aggregate is found by
//! `reality_id` alone, a channel-scoped one needs a channel too, and those are
//! different argument lists rather than different promises.
//!
//! So [`read_projection_reality`] is bounded `A: DpAggregate<Scope =
//! RealityScope>`, and asking it for a channel-scoped aggregate is `E0271` at
//! the call site — the same mechanism `DP-R5` gets on the write side.
//!
//! # DEFERRED, and all three for the same missing producer
//!
//! `read_projection_channel`, `wait_for` and `causality_timeout` are specified
//! and not built:
//!
//!   * the channel read needs a `ChannelId`, which nothing produces (`DP-Ch9`,
//!     slice 5) — the same reason `cache_key!` has no channel arm and
//!     `SessionContext` has no channel fields;
//!   * `wait_for` takes a `CausalityToken`, which is `DP-Ch38` and is one of
//!     the five variants `DpError` itself defers.
//!
//! Taking a `wait_for` parameter and ignoring it would be worse than omitting
//! it: a caller that passes a token and gets no wait has been told its
//! read-your-writes is honoured when it is not. Recorded in
//! [`DEFERRED_READ_FORMS`], which `tests/spec_oracle.rs` reads.

use crate::aggregate::DpAggregate;
use crate::error::DpError;
use crate::scope::RealityScope;
use crate::session::{Millis, SessionContext};
use crate::tier::Tier;

/// `DP-K4` forms not built here, with what each waits on.
pub const DEFERRED_READ_FORMS: &[(&str, &str)] = &[
    ("read_projection_channel", "DP-Ch9 move_session_to_channel produces ChannelId (slice 5)"),
    ("wait_for", "DP-Ch38 CausalityToken, also deferred by DpError"),
    ("query_scoped_reality", "DP-K4 typed Predicate, unbuilt"),
];

/// The projection-store seam. Implemented by `dp-kernel` (slice 5).
///
/// Returns raw bytes rather than `A::Projection` because a trait object cannot
/// be generic: the backend finds and returns the stored form, and the caller —
/// which knows `A` — decodes it. That split is also why `Decode` exists below.
pub trait ReadBackend {
    /// Fetch the stored projection at `key`, or `None` if absent.
    ///
    /// `None` is a MISS, not an error. `DpError::AggregateNotFound` is the
    /// caller's decision to make, because "absent" is legitimate for some
    /// aggregates and a fault for others.
    fn fetch(&self, aggregate: &'static str, key: &str) -> Result<Option<Vec<u8>>, DpError>;
}

/// How an aggregate's projection is reconstructed from what the store holds.
///
/// Separate from [`DpAggregate`] on purpose: an aggregate's identity (tier,
/// scope, name) is a design-time fact, while its wire encoding is an
/// implementation detail that may differ per backend. Bundling them would make
/// every aggregate declare an encoding before it has a store.
pub trait Decode: DpAggregate {
    /// Decode, or say why not.
    ///
    /// Returning [`DpError::SchemaVersionMismatch`] is the expected shape when
    /// the stored form predates this build.
    fn decode(bytes: &[u8]) -> Result<Self::Projection, DpError>;
}

/// `DP-K4` — read a reality-scoped aggregate's projection.
///
/// The scope bound is the address discipline: a channel-scoped aggregate
/// cannot be read here, because this signature has nowhere to put the channel
/// it would need.
pub fn read_projection_reality<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    key: &str,
) -> Result<A::Projection, DpError>
where
    A: DpAggregate<Scope = RealityScope> + Decode,
    B: ReadBackend,
{
    // Same ordering rule as the write side: the session is checked before the
    // store is touched.
    ctx.check_live(now_ms)?;

    match backend.fetch(A::TYPE_NAME, key)? {
        Some(bytes) => A::decode(&bytes),
        None => Err(DpError::AggregateNotFound {
            aggregate: A::TYPE_NAME,
            id: key.to_string(),
        }),
    }
}

/// The tier a read is served under, for telemetry and for `DP-X1`'s coherency
/// promise.
///
/// Exposed so a caller can report WHICH contract its read was answered under
/// without re-deriving it — and derived from the type, so it cannot disagree
/// with the aggregate's declaration.
pub fn read_tier<A: DpAggregate>() -> crate::tier::TierLevel {
    <A::Tier as Tier>::LEVEL
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::{BindRequest, ControlPlane, VerifiedBind};
    use crate::tier::{TierLevel, T2};

    struct Prof;
    impl DpAggregate for Prof {
        type Tier = T2;
        type Scope = RealityScope;
        type Id = u64;
        type Delta = ();
        type Projection = u32;
        const TYPE_NAME: &'static str = "read_fixture";
    }
    impl Decode for Prof {
        fn decode(bytes: &[u8]) -> Result<u32, DpError> {
            if bytes.len() != 4 {
                return Err(DpError::SchemaVersionMismatch { on_disk: 0, expected: 1 });
            }
            Ok(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
        }
    }

    struct Store(Option<Vec<u8>>);
    impl ReadBackend for Store {
        fn fetch(&self, _a: &'static str, _k: &str) -> Result<Option<Vec<u8>>, DpError> {
            Ok(self.0.clone())
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
    fn a_hit_decodes_through_the_aggregates_own_decoder() {
        let s = Store(Some(7u32.to_le_bytes().to_vec()));
        assert_eq!(read_projection_reality::<Prof, _>(&s, &ctx(), 0, "k").unwrap(), 7);
    }

    #[test]
    fn a_miss_is_aggregate_not_found_naming_the_type() {
        let s = Store(None);
        let e = read_projection_reality::<Prof, _>(&s, &ctx(), 0, "k").expect_err("miss");
        assert_eq!(e.variant_name(), "AggregateNotFound");
        assert!(e.to_string().contains("read_fixture"), "{e}");
    }

    #[test]
    fn an_expired_session_never_reaches_the_store() {
        // Same property as the write side, and worth its own test rather than
        // an assumption that the shared rule was applied.
        struct Exploding;
        impl ReadBackend for Exploding {
            fn fetch(&self, _a: &'static str, _k: &str) -> Result<Option<Vec<u8>>, DpError> {
                panic!("the store was touched despite an expired session");
            }
        }
        let e = read_projection_reality::<Prof, _>(&Exploding, &ctx(), 1_000, "k")
            .expect_err("expired");
        assert_eq!(e.variant_name(), "CapabilityExpired");
    }

    #[test]
    fn a_short_record_surfaces_as_a_schema_mismatch_not_a_panic() {
        let s = Store(Some(vec![1, 2]));
        let e = read_projection_reality::<Prof, _>(&s, &ctx(), 0, "k").expect_err("short");
        assert_eq!(e.variant_name(), "SchemaVersionMismatch");
    }

    #[test]
    fn the_read_tier_is_the_aggregates_declared_tier() {
        assert_eq!(read_tier::<Prof>(), TierLevel::T2);
    }
}
