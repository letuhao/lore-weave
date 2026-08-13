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
use crate::cache::KeyId;
use crate::error::DpError;
use crate::ids::{ChannelId, RealityId};
use crate::scope::RealityScope;
use crate::session::{Millis, SessionContext};
use crate::tier::Tier;

/// `DP-K4` forms not built here, with what each waits on.
pub const DEFERRED_READ_FORMS: &[(&str, &str)] = &[
    // `read_projection_channel` was here until slice `5D`. Its blocker —
    // "DP-Ch9 move_session_to_channel produces ChannelId" — is now discharged,
    // and the function is below. The register keeps two rows, so unlike its
    // three sibling registers this one survives and its oracle test with it.
    // `DP-A19` is the ACCESS-PATTERN statement of this rule — a T2/T3 write
    // within a session returns an opaque `CausalityToken`, and handing that
    // token to another service is what preserves intra-session causality. The
    // TYPE is tracked as `DP-Ch38`; both ids name the same guarantee from two
    // directions, and only one of them was greppable to this line.
    ("wait_for", "DP-Ch38 CausalityToken, also deferred by DpError"),
    ("query_scoped_reality", "DP-K4 typed Predicate, unbuilt"),
];

/// The projection-store seam. Implemented by `dp-kernel` (slice 5).
///
/// Returns raw bytes rather than `A::Projection` because a trait object cannot
/// be generic: the backend finds and returns the stored form, and the caller —
/// which knows `A` — decodes it. That split is also why `Decode` exists below.
/// Everything a backend needs to locate a projection.
///
/// A STRUCT for the same reason [`crate::write::WriteRequest`] is one, and this
/// side learned it the hard way. `fetch(aggregate, key)` gave the backend no
/// `aggregate_id`, so `dp-kernel` recovered one by taking the last segment of
/// the cache key — the precise anti-pattern the write seam's own documentation
/// condemns two files away. It was also WRONG, not merely inelegant: a
/// `DP-K7` key with a subkey ends `…:{id}:{subkey}`, so the last segment is the
/// SUBKEY and every subkeyed read resolved the wrong aggregate.
///
/// The ids the caller already holds travel as values. Nothing re-derives them
/// from formatted text.
#[derive(Debug)]
pub struct ReadRequest<'a> {
    /// The verified reality. Only session bind can produce one.
    pub reality: &'a RealityId,
    /// `DP-Ch5` type token, from `A::TYPE_NAME`.
    pub aggregate_type: &'static str,
    /// The aggregate's own id, already validated as a key segment.
    pub aggregate_id: KeyId,
    /// The `DP-K7` cache key, for a cache-first backend to try before the store.
    pub cache_key: &'a str,
    /// The channel this read is addressed to, or `None` for a reality-scoped
    /// read (`DFO-2`).
    ///
    /// # The same gap the WRITE side had, found by fixing that one
    ///
    /// [`read_projection_channel`] checked that the session IS in a channel and
    /// then built a request that could not say WHICH — so a backend could only
    /// address it through the cache key, and `dp-kernel`'s snapshot reader
    /// ignores the key and looks up `(reality, aggregate_type, aggregate_id)`.
    /// A channel-scoped read was therefore servable only by accident, and two
    /// channels holding the same aggregate id would have collided silently.
    ///
    /// Carrying the channel does not by itself make such a read CORRECT — the
    /// snapshot store has no channel dimension to look in. What it does is make
    /// the wrongness visible to the backend, which can now refuse instead of
    /// answering confidently. The reader that serves it belongs with the first
    /// thing that needs to read a channel back.
    pub channel: Option<ChannelId>,
}

pub trait ReadBackend {
    /// Fetch the stored projection, or `None` if absent.
    ///
    /// `None` is a MISS, not an error. `DpError::AggregateNotFound` is the
    /// caller's decision to make, because "absent" is legitimate for some
    /// aggregates and a fault for others.
    fn fetch(&self, req: &ReadRequest<'_>) -> Result<Option<Vec<u8>>, DpError>;
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
    id: KeyId,
    key: &str,
) -> Result<A::Projection, DpError>
where
    A: DpAggregate<Scope = RealityScope> + Decode,
    B: ReadBackend,
{
    // Same ordering rule as the write side: the session is checked before the
    // store is touched.
    ctx.check_live(now_ms)?;

    let req = ReadRequest {
        reality: ctx.reality_id(),
        aggregate_type: A::TYPE_NAME,
        aggregate_id: id,
        cache_key: key,
        // A reality-scoped aggregate has no channel, and the `Scope` bound
        // above is what makes that a fact rather than a hope.
        channel: None,
    };
    match backend.fetch(&req)? {
        Some(bytes) => A::decode(&bytes),
        // Names the AGGREGATE ID, not the cache key. The id is what a reader
        // can look up; the key is an encoding of it.
        None => Err(DpError::AggregateNotFound {
            aggregate: A::TYPE_NAME,
            id: req.aggregate_id.as_str().to_string(),
        }),
    }
}

/// `DP-K4` — read a CHANNEL-scoped aggregate's projection (slice `5D`).
///
/// The sibling of [`read_projection_reality`], bounded to the other scope, and
/// the two bounds are what make a wrong-scope read a compile error rather than
/// a runtime surprise. `tests/ui/read_wrong_scope.rs` is that claim executed by
/// rustc.
///
/// # Why the channel is not a parameter
///
/// It comes from the context, for the same reason [`crate::cache::channel_key`]
/// takes it from there: a channel argument would let a caller read a channel its
/// session was never moved into. `DP-A14` calls scope an ADDRESS, and the
/// session is what holds the address.
///
/// A reality-scoped session reading a channel-scoped aggregate is a caller bug
/// with no correct answer, so it is [`DpError::ChannelDissolved`]'s neighbour
/// rather than an invented default — `SessionNotFound` names the session,
/// because the session is what is missing a channel.
pub fn read_projection_channel<A, B>(
    backend: &B,
    ctx: &SessionContext,
    now_ms: Millis,
    id: KeyId,
    key: &str,
) -> Result<A::Projection, DpError>
where
    A: DpAggregate<Scope = crate::scope::ChannelScope> + Decode,
    B: ReadBackend,
{
    ctx.check_live(now_ms)?;

    // Checked BEFORE the store is touched, so a session with no channel never
    // produces a request the backend has to interpret.
    if ctx.current_channel_id().is_none() {
        return Err(DpError::SessionNotFound {
            session_id: format!(
                "{} is not in a channel, so it cannot read the channel-scoped {}",
                ctx.session_id(),
                A::TYPE_NAME
            ),
        });
    }

    let req = ReadRequest {
        reality: ctx.reality_id(),
        aggregate_type: A::TYPE_NAME,
        aggregate_id: id,
        cache_key: key,
        // Checked `is_none()` above, so this is the same channel that check
        // passed on — taken from the context, never from an argument.
        channel: ctx.current_channel_id(),
    };
    match backend.fetch(&req)? {
        Some(bytes) => A::decode(&bytes),
        None => Err(DpError::AggregateNotFound {
            aggregate: A::TYPE_NAME,
            id: req.aggregate_id.as_str().to_string(),
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

    struct Store {
        answer: Option<Vec<u8>>,
        /// What the backend was actually ASKED for. The regression that
        /// motivated `ReadRequest` was the backend deriving this wrongly, so
        /// the test records it rather than trusting it.
        asked: std::cell::RefCell<Vec<String>>,
    }
    impl Store {
        fn new(answer: Option<Vec<u8>>) -> Self {
            Self { answer, asked: std::cell::RefCell::new(Vec::new()) }
        }
    }
    impl ReadBackend for Store {
        fn fetch(&self, req: &ReadRequest<'_>) -> Result<Option<Vec<u8>>, DpError> {
            self.asked.borrow_mut().push(req.aggregate_id.as_str().to_string());
            Ok(self.answer.clone())
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

    // ── 5D — the channel-scoped read ────────────────────────────────────────

    struct Chatter;
    impl DpAggregate for Chatter {
        type Tier = T2;
        type Scope = crate::scope::ChannelScope;
        type Id = u64;
        type Delta = ();
        type Projection = u32;
        const TYPE_NAME: &'static str = "read_channel_fixture";
    }
    impl Decode for Chatter {
        fn decode(bytes: &[u8]) -> Result<u32, DpError> {
            Ok(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
        }
    }

    struct Tree;
    impl crate::session::ChannelTree for Tree {
        fn resolve(
            &self,
            _r: &RealityId,
            raw: i64,
        ) -> Result<crate::session::ChannelResolution, DpError> {
            Ok(crate::session::ChannelResolution { channel: raw, ancestors: vec![] })
        }
    }

    #[test]
    fn a_channel_scoped_read_works_once_the_session_is_in_a_channel() {
        let ctx = ctx().move_to_channel(&Tree, 12, 0).expect("move");
        let s = Store::new(Some(7u32.to_le_bytes().to_vec()));
        assert_eq!(
            read_projection_channel::<Chatter, _>(&s, &ctx, 0, KeyId::from(9u64), "k").unwrap(),
            7
        );
        assert_eq!(s.asked.borrow().as_slice(), ["9"], "the id travels as a value");
    }

    #[test]
    fn a_reality_scoped_session_cannot_read_a_channel_scoped_aggregate() {
        // …and the store is never touched, so a backend never has to interpret
        // a request with no channel in it.
        let s = Store::new(Some(7u32.to_le_bytes().to_vec()));
        let err = read_projection_channel::<Chatter, _>(&s, &ctx(), 0, KeyId::from(9u64), "k")
            .expect_err("no channel");
        assert_eq!(err.variant_name(), "SessionNotFound");
        assert!(s.asked.borrow().is_empty(), "the store must not have been asked");
    }

    #[test]
    fn an_expired_session_never_reaches_the_store_on_the_channel_path_either() {
        let ctx = ctx().move_to_channel(&Tree, 12, 0).expect("move");
        let s = Store::new(Some(7u32.to_le_bytes().to_vec()));
        let err = read_projection_channel::<Chatter, _>(&s, &ctx, 10_000, KeyId::from(9u64), "k")
            .expect_err("expired");
        assert_eq!(err.variant_name(), "CapabilityExpired");
        assert!(s.asked.borrow().is_empty());
    }

    #[test]
    fn a_channel_miss_names_the_aggregate_id() {
        let ctx = ctx().move_to_channel(&Tree, 12, 0).expect("move");
        let s = Store::new(None);
        let err = read_projection_channel::<Chatter, _>(&s, &ctx, 0, KeyId::from(9u64), "k")
            .expect_err("miss");
        assert_eq!(err.variant_name(), "AggregateNotFound");
        assert!(err.to_string().contains('9'), "{err}");
    }

    #[test]
    fn a_hit_decodes_through_the_aggregates_own_decoder() {
        let s = Store::new(Some(7u32.to_le_bytes().to_vec()));
        assert_eq!(read_projection_reality::<Prof, _>(&s, &ctx(), 0, KeyId::from(9u64), "k").unwrap(), 7);
    }

    #[test]
    fn a_miss_is_aggregate_not_found_naming_the_type() {
        let s = Store::new(None);
        let e = read_projection_reality::<Prof, _>(&s, &ctx(), 0, KeyId::from(9u64), "k").expect_err("miss");
        assert_eq!(e.variant_name(), "AggregateNotFound");
        assert!(e.to_string().contains("read_fixture"), "{e}");
        assert!(e.to_string().contains("9"), "the miss names the aggregate ID: {e}");
    }

    #[test]
    fn an_expired_session_never_reaches_the_store() {
        // Same property as the write side, and worth its own test rather than
        // an assumption that the shared rule was applied.
        struct Exploding;
        impl ReadBackend for Exploding {
            fn fetch(&self, _req: &ReadRequest<'_>) -> Result<Option<Vec<u8>>, DpError> {
                panic!("the store was touched despite an expired session");
            }
        }
        let e = read_projection_reality::<Prof, _>(&Exploding, &ctx(), 1_000, KeyId::from(9u64), "k")
            .expect_err("expired");
        assert_eq!(e.variant_name(), "CapabilityExpired");
    }

    #[test]
    fn a_short_record_surfaces_as_a_schema_mismatch_not_a_panic() {
        let s = Store::new(Some(vec![1, 2]));
        let e = read_projection_reality::<Prof, _>(&s, &ctx(), 0, KeyId::from(9u64), "k").expect_err("short");
        assert_eq!(e.variant_name(), "SchemaVersionMismatch");
    }

    /// THE REGRESSION. `dp-kernel` used to recover the id with
    /// `key.rsplit(':').next()`, which on a subkeyed `DP-K7` key returns the
    /// SUBKEY. This asserts the backend is asked for the id the caller passed,
    /// whatever the key looks like.
    #[test]
    fn a_subkeyed_key_does_not_change_which_aggregate_is_asked_for() {
        let s = Store::new(Some(7u32.to_le_bytes().to_vec()));
        let subkeyed = "dp:00000000-0000-0000-0000-000000000001:r:t2:read_fixture:42:equipped";
        read_projection_reality::<Prof, _>(&s, &ctx(), 0, KeyId::from(42u64), subkeyed)
            .expect("read");
        assert_eq!(
            s.asked.borrow().as_slice(),
            &["42".to_string()],
            "the backend must be asked for the aggregate id, not the trailing key segment"
        );
    }

    #[test]
    fn the_read_tier_is_the_aggregates_declared_tier() {
        assert_eq!(read_tier::<Prof>(), TierLevel::T2);
    }
}
