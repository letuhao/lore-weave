//! `DP-K7` — `dp::cache_key!`, and the `KeyId` it converts through.
//!
//! # What the macro is for
//!
//! `DP-R4`: *"Cache keys are built only via the `dp::cache_key!` macro. Feature
//! code does not concatenate strings for cache keys."* The stated violation
//! mode is worth quoting, because it is why a macro rather than a helper
//! function: *"Key format drift (missing `reality_id`, wrong tier prefix, typos
//! in `aggregate_type`) produces silent coherency bugs — the write lands at one
//! key and the read misses elsewhere."* A bug that looks like a stale cache and
//! is actually two different keys.
//!
//! # The shape, and where every token comes from
//!
//! ```text
//! dp:{reality}:r:{tier}:{typ}:{id}[:{subkey}]
//!    ^          ^  ^     ^     ^
//!    |          |  |     |     `- Into<KeyId>, at the call site
//!    |          |  |     `------- <A as DpAggregate>::TYPE_NAME
//!    |          |  `------------- <A::Tier as Tier>::LEVEL.as_key()
//!    |          `---------------- <A::Scope as Scope>::KIND.as_key()
//!    `--------------------------- ctx.reality_id(), which only bind can produce
//! ```
//!
//! **Nothing in that line is a literal at the call site.** Four of the five
//! tokens are read off the aggregate's own types, and the fifth is the session's
//! verified `RealityId`. That is what makes a typo impossible rather than
//! discouraged — the failure mode `DP-R4` describes needs a hand-written string
//! to happen in, and there is nowhere to write one.
//!
//! # The tier argument is CHECKED, not decoration
//!
//! `DP-K7` requires *"`$tier` must match the tier trait of `$aggregate` — else
//! type-check failure"*. It does, and by construction rather than by assertion:
//! the macro passes the tier as a **type parameter** to a function whose bound
//! is `A: DpAggregate<Tier = T>`. Writing `cache_key!(ctx, T1, X, id)` for a
//! `T2` aggregate is then an ordinary type mismatch, reported by rustc at the
//! call site. `tests/ui/cache_key_wrong_tier.rs` pins that.
//!
//! # The channel-scoped arm (`DP-K7`'s second form) — BUILT in slice `5D`
//!
//! ```text
//! dp:{reality}:c:{channel}:{tier}:{typ}:{id}[:{subkey}]
//! ```
//!
//! It was deferred while nothing produced a `ChannelId`; `DP-Ch9`'s
//! `SessionContext::move_to_channel` now does, so [`channel_key`] exists and
//! `DEFERRED_CACHE_FORMS` is gone.
//!
//! **The channel token comes from the SESSION, never from an argument.** An arm
//! accepting any `Display` as a channel would take a forged value and put it in
//! a key — worse than not having the arm — and the whole point of a verified
//! `ChannelId` is that the session is what holds the address.
//!
//! **The segment ORDER is checked against the locked doc**, not against this
//! comment: `tests/spec_oracle.rs` parses the shape out of
//! `04c_subscribe_and_macros.md` and compares it to a key this code builds. The
//! first draft put `{channel}` after `{typ}`, which reads just as sensibly and
//! is wrong, and nothing but the doc could have said so.

use core::time::Duration;

use crate::aggregate::DpAggregate;
use crate::error::DpError;
use crate::scope::{RealityScope, Scope};
use crate::session::SessionContext;
use crate::tier::Tier;

// `DEFERRED_CACHE_FORMS` IS GONE, AND ITS ORACLE TEST WITH IT (slice 5D).
//
// Its one row deferred the channel-scoped form on the grounds that nothing
// produced a `ChannelId`. `SessionContext::move_to_channel` does, and
// `channel_key` below is the form. Deleted rather than left empty: the oracle
// test asserted the register was non-empty precisely so an emptied one could
// not sit there as a check with nothing to check.

/// The `{id}` token of a cache key.
///
/// A newtype rather than `impl Display` at the call site, because the set of
/// things that may become a key segment is deliberately small and closed. Two
/// rules it enforces that a bare `to_string()` would not:
///
///   * **A colon in an id would forge a key segment.** `dp:R:r:t2:x:a:b` is
///     indistinguishable from a subkey, so an id containing `:` could collide
///     with a different aggregate's entry. [`KeyId::new`] rejects it.
///   * **An empty id is not an id.** It would produce a trailing colon and a
///     key that reads as a prefix, which is how a targeted read becomes a
///     scan.
#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct KeyId(String);

impl KeyId {
    /// Build a key segment, rejecting anything that would change the key's
    /// shape.
    ///
    /// Returns `None` rather than panicking: a bad id is a caller error to
    /// handle, and a panic inside a cache-key expansion would abort a request
    /// path over a data problem.
    pub fn new(raw: impl Into<String>) -> Option<Self> {
        let s = raw.into();
        if s.is_empty() || s.contains(':') {
            return None;
        }
        Some(Self(s))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl From<uuid::Uuid> for KeyId {
    /// Always valid: a hyphenated UUID contains no colon and is never empty.
    fn from(u: uuid::Uuid) -> Self {
        Self(u.to_string())
    }
}

impl From<u64> for KeyId {
    fn from(n: u64) -> Self {
        Self(n.to_string())
    }
}

impl From<i64> for KeyId {
    fn from(n: i64) -> Self {
        Self(n.to_string())
    }
}

/// The CACHE seam (`DP-X3`) — the third, alongside [`crate::ReadBackend`] and
/// [`crate::WriteBackend`].
///
/// # Why `dp` holds a trait and not a Redis client
///
/// `01_scope_and_boundary.md §2.4` lists *"Direct Redis access for T0–T2 reads
/// and cache"* among the SDK's jobs, and this crate declares no I/O. So the SDK
/// owns the read-through ALGORITHM (`DP-X3`) and the backend owns the socket.
/// `crate-purity-gate` pins this crate's externals to `{uuid}`, which is what
/// makes the split structural rather than a convention.
///
/// Measured before it was written: **`redis` appeared in exactly one Cargo.toml
/// in the Rust tree — `commit-service`, for its proposal bus — and in zero DP
/// crates.** Every tier therefore collapsed to the durable path, which made
/// `DP-T0..T3` a taxonomy with one implementation.
///
/// # A FAILURE is not a MISS, and `DP-X10` is why that distinction is load-bearing
///
/// On cache failure a READ degrades silently to the projection, a **T2 write
/// continues** (the outbox is authoritative), and a **T3 write returns
/// `DpError::CircuitOpen { service: "redis" }`** because it cannot fan out its
/// invalidation. Collapsing an error into `Ok(None)` would make that third case
/// unrepresentable: the write would ack having invalidated nothing, which is
/// exactly the guarantee `DP-X1` says T3 exists to provide.
pub trait CacheBackend {
    /// `Ok(Some)` hit · `Ok(None)` clean miss · `Err` the cache is FAULTY.
    fn get(&self, key: &str) -> Result<Option<Vec<u8>>, DpError>;

    /// Populate after a miss (`DP-X3` step 4).
    ///
    /// `ttl` comes from [`crate::Tier::CACHE_TTL`], parsed out of `DP-X7`'s
    /// table by `tests/spec_oracle.rs` — so the number cannot drift from the
    /// locked document without a test going red.
    fn set(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), DpError>;

    /// Drop one entry (`DP-X2` invalidation).
    fn del(&self, key: &str) -> Result<(), DpError>;
}

/// Build a reality-scoped cache key. **Call it through [`crate::cache_key!`].**
///
/// Public because the macro expands to a path into it, not because feature code
/// should call it directly — calling it directly is not a *violation* (it still
/// derives every token from types), it is just less readable than the macro.
///
/// The two type parameters are the enforcement. `A: DpAggregate<Tier = T,
/// Scope = RealityScope>` makes a wrong tier and a channel-scoped aggregate
/// both type errors rather than runtime surprises.
pub fn reality_key<A, T>(ctx: &SessionContext, id: impl Into<KeyId>, subkeys: &[&str]) -> String
where
    T: Tier,
    A: DpAggregate<Tier = T, Scope = RealityScope>,
{
    let mut out = format!(
        "dp:{reality}:{scope}:{tier}:{typ}:{id}",
        reality = ctx.reality_id(),
        scope = <A::Scope as Scope>::KIND.as_key(),
        tier = <A::Tier as Tier>::LEVEL.as_key(),
        typ = A::TYPE_NAME,
        id = id.into().as_str(),
    );
    for sk in subkeys {
        out.push(':');
        out.push_str(sk);
    }
    out
}

/// Build a channel-scoped cache key. **Call it through [`crate::cache_key!`].**
///
/// # The channel comes from the CONTEXT, never from an argument
///
/// A `channel:` parameter would let a caller key an entry under a channel its
/// session is not in — which is the cross-channel leak `DP-A14`'s scope choice
/// exists to prevent, arriving through the cache instead of through a read.
/// The session already knows which channel it is in, because
/// `SessionContext::move_to_channel` put it there, so taking it from anywhere
/// else is strictly a way to be wrong.
///
/// Returns `None` when the session is reality-scoped: there is no correct key
/// for a channel-scoped aggregate without a channel, and inventing one — a
/// literal `0`, the reality id, an empty segment — would silently merge every
/// channel's entries into one.
pub fn channel_key<A, T>(
    ctx: &SessionContext,
    id: impl Into<KeyId>,
    subkeys: &[&str],
) -> Option<String>
where
    T: Tier,
    A: DpAggregate<Tier = T, Scope = crate::scope::ChannelScope>,
{
    let channel = ctx.current_channel_id()?;
    // ORDER IS THE SPEC'S, NOT A CHOICE. `DP-K7` writes
    // `dp:{reality}:c:{channel}:{tier}:{typ}:{id}` — the channel sits directly
    // after the scope token, BEFORE tier and type. The first draft put it after
    // `{typ}`, which reads just as sensibly and is wrong: a key format is a
    // cross-process contract, and `dp-kernel`'s invalidation prefixes are built
    // by truncating at these boundaries, so a rearranged segment silently
    // changes which entries a prefix invalidation reaches. `tests/spec_oracle.rs`
    // now parses the shape out of the locked doc rather than trusting this line.
    let mut out = format!(
        "dp:{reality}:{scope}:{channel}:{tier}:{typ}:{id}",
        reality = ctx.reality_id(),
        scope = <A::Scope as Scope>::KIND.as_key(),
        channel = channel,
        tier = <A::Tier as Tier>::LEVEL.as_key(),
        typ = A::TYPE_NAME,
        id = id.into().as_str(),
    );
    for sk in subkeys {
        out.push(':');
        out.push_str(sk);
    }
    Some(out)
}

/// `DP-K7` — the only sanctioned way to build a cache key.
///
/// ```ignore
/// let k = dp::cache_key!(ctx, T2, PlayerInventory, player_id);
/// let k = dp::cache_key!(ctx, T2, PlayerInventory, player_id, "equipped");
/// // channel-scoped (slice 5D) — yields Option<String>:
/// let k = dp::cache_key!(channel: ctx, T2, Chatter, msg_id);
/// ```
///
/// The two arms produce different TYPES on purpose — `String` and
/// `Option<String>` — so a caller cannot use a channel-scoped key without
/// deciding what to do about a session that is not in a channel.
#[macro_export]
macro_rules! cache_key {
    (channel: $ctx:expr, $tier:ident, $aggregate:ty, $id:expr $(, $subkey:expr)* $(,)?) => {
        $crate::cache::channel_key::<$aggregate, $crate::tier::$tier>(
            $ctx,
            $id,
            &[$($subkey),*],
        )
    };
    ($ctx:expr, $tier:ident, $aggregate:ty, $id:expr $(, $subkey:expr)* $(,)?) => {
        $crate::cache::reality_key::<$aggregate, $crate::tier::$tier>(
            $ctx,
            $id,
            &[$($subkey),*],
        )
    };
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scope::RealityScope;
    use crate::session::{BindRequest, ControlPlane, SessionContext, VerifiedBind};
    use crate::tier::{T1, T2};
    use crate::DpError;

    struct Inventory;
    impl DpAggregate for Inventory {
        type Tier = T2;
        type Scope = RealityScope;
        type Id = uuid::Uuid;
        type Delta = ();
        type Projection = ();
        const TYPE_NAME: &'static str = "cache_key_fixture";
    }

    struct Cp;
    impl ControlPlane for Cp {
        fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
            Ok(VerifiedBind {
                reality: req.reality,
                session: uuid::Uuid::from_u128(7),
                capability_secret: "s".into(),
                expires_at_ms: 10_000,
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

    struct Chatter;
    impl DpAggregate for Chatter {
        type Tier = T2;
        type Scope = crate::scope::ChannelScope;
        type Id = u64;
        type Delta = ();
        type Projection = ();
        const TYPE_NAME: &'static str = "cache_key_channel_fixture";
    }

    struct Tree(i64);
    impl crate::session::ChannelTree for Tree {
        fn resolve(
            &self,
            _r: &crate::RealityId,
            _raw: i64,
        ) -> Result<crate::session::ChannelResolution, DpError> {
            Ok(crate::session::ChannelResolution { channel: self.0, ancestors: vec![] })
        }
    }

    fn ctx_in_channel(channel: i64) -> SessionContext {
        ctx().move_to_channel(&Tree(channel), channel, 0).expect("move")
    }

    #[test]
    fn a_channel_scoped_key_carries_the_channel_between_type_and_id() {
        let k = cache_key!(channel: &ctx_in_channel(77), T2, Chatter, 5u64).expect("in a channel");
        assert_eq!(
            k,
            "dp:00000000-0000-0000-0000-000000000001:c:77:t2:cache_key_channel_fixture:5"
        );
    }

    #[test]
    fn two_channels_do_not_share_a_key_for_the_same_aggregate_id() {
        // The whole reason the channel is IN the key. Without it, every
        // channel's entry for id 5 would be the same cache entry — a
        // cross-channel leak arriving through the cache rather than a read.
        let a = cache_key!(channel: &ctx_in_channel(1), T2, Chatter, 5u64).expect("a");
        let b = cache_key!(channel: &ctx_in_channel(2), T2, Chatter, 5u64).expect("b");
        assert_ne!(a, b);
    }

    #[test]
    fn a_session_with_no_channel_gets_no_channel_key() {
        // `None`, not a key with an invented channel. A literal 0 or an empty
        // segment would silently merge every channel's entries into one.
        assert!(cache_key!(channel: &ctx(), T2, Chatter, 5u64).is_none());
    }

    #[test]
    fn channel_subkeys_append_after_the_id_as_they_do_reality_scoped() {
        let k = cache_key!(channel: &ctx_in_channel(9), T2, Chatter, 1u64, "seen")
            .expect("in a channel");
        assert!(k.ends_with(":c:9:t2:cache_key_channel_fixture:1:seen"), "{k}");
    }

    #[test]
    fn the_key_has_the_dp_k7_shape() {
        let k = cache_key!(&ctx(), T2, Inventory, uuid::Uuid::from_u128(2));
        assert_eq!(
            k,
            "dp:00000000-0000-0000-0000-000000000001:r:t2:cache_key_fixture:\
             00000000-0000-0000-0000-000000000002"
                .replace(' ', "")
        );
    }

    #[test]
    fn every_token_comes_from_a_type_not_the_call_site() {
        // The point of DP-R4: nothing here is spelled by the caller. Changing
        // TYPE_NAME or the tier changes the key without the call site moving.
        let k = cache_key!(&ctx(), T2, Inventory, 42u64);
        assert!(k.contains(":r:"), "scope token from A::Scope::KIND: {k}");
        assert!(k.contains(":t2:"), "tier token from A::Tier::LEVEL: {k}");
        assert!(k.contains(":cache_key_fixture:"), "type token from TYPE_NAME: {k}");
        assert!(k.starts_with("dp:00000000-0000-0000-0000-000000000001:"), "reality: {k}");
        assert!(k.ends_with(":42"), "id: {k}");
    }

    #[test]
    fn subkeys_append_in_order() {
        let k = cache_key!(&ctx(), T2, Inventory, 1u64, "equipped", "left");
        assert!(k.ends_with(":1:equipped:left"), "{k}");
    }

    #[test]
    fn a_colon_in_an_id_is_refused() {
        // Without this, an id could forge a subkey boundary and collide with a
        // different entry — a silent coherency bug, which is the exact failure
        // DP-R4 exists to prevent.
        assert!(KeyId::new("a:b").is_none());
        assert!(KeyId::new("").is_none(), "an empty id makes the key read as a prefix");
        assert_eq!(KeyId::new("ok").unwrap().as_str(), "ok");
    }

    #[test]
    fn uuid_and_integer_ids_are_always_valid() {
        assert!(!KeyId::from(uuid::Uuid::from_u128(3)).as_str().contains(':'));
        assert_eq!(KeyId::from(7u64).as_str(), "7");
        assert_eq!(KeyId::from(-7i64).as_str(), "-7");
    }

    /// The tier argument is load-bearing: `T1` here would not compile.
    /// `tests/ui/cache_key_wrong_tier.rs` is that claim executed by rustc;
    /// this test only records that `T1` exists and is a different type, so the
    /// ui case is not passing because the name is undefined.
    #[test]
    fn the_wrong_tier_is_a_real_type_that_simply_does_not_match() {
        assert_eq!(<T1 as Tier>::LEVEL.as_key(), "t1");
        assert_eq!(<T2 as Tier>::LEVEL.as_key(), "t2");
    }
}
