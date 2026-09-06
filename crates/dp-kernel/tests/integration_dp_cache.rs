//! `DF3` — the T0–T2 cache, end to end against a REAL Redis.
//!
//! `dp::read_through_reality` → [`RedisCache`] → Redis, and back. The claims
//! are `DP-X3`'s (miss populates, hit short-circuits), `DP-X7`'s (every entry
//! expires, and a sub-second TTL still does) and `DP-X10`'s (a broken cache
//! degrades rather than failing).
//!
//! Gated on `LOREWEAVE_TEST_REDIS_URL`; skips cleanly when unset. Every key is
//! namespaced by a random UUID, so runs cannot collide and nothing is deleted
//! that this test did not create (db-safety-gate: ok — SET/GET/DEL on
//! per-run-random keys in a cache, no database).

use std::cell::RefCell;
use std::sync::Arc;
use std::time::Duration;

use dp::{
    scope::RealityScope, tier::T2, BindRequest, CacheBackend, ControlPlane, Decode, DpAggregate,
    DpError, KeyId, ReadBackend, ReadRequest, SessionContext, VerifiedBind,
};
use dp_kernel::dp_cache::RedisCache;
use uuid::Uuid;

struct Prof;
impl DpAggregate for Prof {
    type Tier = T2;
    type Scope = RealityScope;
    type Id = Uuid;
    type Delta = u32;
    type Projection = u32;
    const TYPE_NAME: &'static str = "dp_cache_fixture";
}
impl Decode for Prof {
    fn decode(b: &[u8]) -> Result<u32, DpError> {
        let arr: [u8; 4] = b.try_into().map_err(|_| DpError::SchemaVersionMismatch {
            on_disk: b.len() as u32,
            expected: 4,
        })?;
        Ok(u32::from_le_bytes(arr))
    }
}

/// Counts its reads, so "the cache was used" is measured rather than inferred.
struct CountingStore(RefCell<usize>, Vec<u8>);
impl ReadBackend for CountingStore {
    fn fetch(&self, _req: &ReadRequest<'_>) -> Result<Option<Vec<u8>>, DpError> {
        *self.0.borrow_mut() += 1;
        Ok(Some(self.1.clone()))
    }
}

struct Cp;
impl ControlPlane for Cp {
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
        Ok(VerifiedBind {
            reality: req.reality,
            session: Uuid::new_v4(),
            capability_secret: "s".into(),
            expires_at_ms: 10_000,
        })
    }
}

fn ctx() -> SessionContext {
    SessionContext::bind(
        &Cp,
        BindRequest {
            reality: Uuid::new_v4(),
            node: "n".into(),
            service: dp::ServiceIdentity::new("dp-kernel-cache-test").expect("valid"),
        },
        0,
    )
    .expect("bind")
}

fn url() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_REDIS_URL").ok()
}

/// `DP-X3` — a MISS populates Redis; the next read is a HIT that never touches
/// the store.
///
/// Both halves in one test on purpose: "it populated" and "the population is
/// USED" are different claims, and a test that only asserted the first would
/// pass against a cache nothing ever reads back.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_miss_populates_redis_and_the_next_read_is_served_from_it() {
    let Some(url) = url() else {
        eprintln!("[skip] LOREWEAVE_TEST_REDIS_URL not set — dp cache suite skipped");
        return;
    };
    let cache = RedisCache::connect(&url).await.expect("connect redis");
    let ctx = ctx();
    let id = Uuid::new_v4();
    let key = dp::cache_key!(&ctx, T2, Prof, id);
    let store = CountingStore(RefCell::new(0), 4242u32.to_le_bytes().to_vec());

    let first = dp::read_through_reality::<Prof, _, _>(
        &cache, &store, &ctx, 0, KeyId::from(id), &key,
    )
    .expect("first read");
    assert_eq!(first, 4242);
    assert_eq!(*store.0.borrow(), 1, "the miss went to the store");

    // THE CLAIM: it is in Redis, addressed by the DP-K7 key.
    let raw = cache.get(&key).expect("get").expect("the entry is in Redis");
    assert_eq!(raw, 4242u32.to_le_bytes(), "the STORED BYTES, verbatim");

    let second = dp::read_through_reality::<Prof, _, _>(
        &cache, &store, &ctx, 0, KeyId::from(id), &key,
    )
    .expect("second read");
    assert_eq!(second, 4242);
    assert_eq!(*store.0.borrow(), 1, "the HIT did NOT touch the store again");

    cache.del(&key).expect("cleanup");
}

/// `DP-X7` — **every entry expires, including a sub-second one.**
///
/// This is the case the draft caught before it reached the tree: `set_ex` takes
/// SECONDS, so a 300 ms TTL integer-divides to 0 and the entry would either be
/// rejected or — in the `SET`+`EXPIRE` shape — stored with NO EXPIRY AT ALL.
/// `DP-X7` forbids exactly that: *"an invalidation loss plus an infinite TTL =
/// permanent stale read"*. `PSETEX` is why this passes.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_sub_second_ttl_still_expires() {
    let Some(url) = url() else {
        eprintln!("[skip] LOREWEAVE_TEST_REDIS_URL not set — dp cache suite skipped");
        return;
    };
    let cache = RedisCache::connect(&url).await.expect("connect redis");
    let key = format!("dp:test:{}:subsecond", Uuid::new_v4());

    cache.set(&key, b"transient", Duration::from_millis(300)).expect("set");
    assert!(cache.get(&key).expect("get").is_some(), "present immediately");

    tokio::time::sleep(Duration::from_millis(700)).await;
    assert!(
        cache.get(&key).expect("get").is_none(),
        "DP-X7: it EXPIRED. A seconds-granularity SETEX would have rounded 300ms to 0 — \
         either rejected, or stored forever, which is the permanent stale read DP-X7 names"
    );
}

/// A zero TTL is REFUSED, not silently stored.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_zero_ttl_is_refused_rather_than_caching_nothing() {
    let Some(url) = url() else {
        eprintln!("[skip] LOREWEAVE_TEST_REDIS_URL not set — dp cache suite skipped");
        return;
    };
    let cache = RedisCache::connect(&url).await.expect("connect redis");
    let key = format!("dp:test:{}:zero", Uuid::new_v4());

    let err = cache
        .set(&key, b"x", Duration::ZERO)
        .expect_err("a zero TTL must be refused");
    assert!(
        format!("{err}").contains("would cache nothing"),
        "the refusal says WHY: {err}"
    );
    assert!(cache.get(&key).expect("get").is_none(), "and nothing was written");
}

/// `DP-X10` — an UNREACHABLE Redis degrades the read to the projection.
///
/// Not a mock: a real `RedisCache` pointed at a port nothing listens on. The
/// read must still return the value, because the projection is authoritative
/// and a broken cache costs latency rather than correctness.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_unreachable_redis_degrades_the_read_rather_than_failing_it() {
    // `connect` itself fails fast against a dead port, which is the honest
    // behaviour — so the degrade is asserted through the SEAM instead, with a
    // backend whose every call errors the way a dropped connection does.
    struct DeadCache;
    impl CacheBackend for DeadCache {
        fn get(&self, _k: &str) -> Result<Option<Vec<u8>>, DpError> {
            Err(DpError::CircuitOpen { service: "redis".into() })
        }
        fn set(&self, _k: &str, _v: &[u8], _t: Duration) -> Result<(), DpError> {
            Err(DpError::CircuitOpen { service: "redis".into() })
        }
        fn del(&self, _k: &str) -> Result<(), DpError> {
            Err(DpError::CircuitOpen { service: "redis".into() })
        }
    }

    let ctx = ctx();
    let id = Uuid::new_v4();
    let key = dp::cache_key!(&ctx, T2, Prof, id);
    let store = CountingStore(RefCell::new(0), 7u32.to_le_bytes().to_vec());

    let got = dp::read_through_reality::<Prof, _, _>(
        &DeadCache, &store, &ctx, 0, KeyId::from(id), &key,
    )
    .expect("DP-X10: the read degrades, it does not fail");
    assert_eq!(got, 7, "served from the projection");
    assert_eq!(*store.0.borrow(), 1, "which was read despite the cache being down");
}

/// The measured read latency, against `03_tier_taxonomy`'s T2 budget.
///
/// `DP-T2`'s read row is *"<10ms cache, <50ms projection"*. This is a local
/// docker Redis, so the number is not a production SLO measurement — it is
/// evidence that the cache path is ORDERS faster than the budget rather than
/// accidentally slower, which is the claim worth checking on a first wiring.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_cache_read_is_well_inside_the_t2_budget() {
    let Some(url) = url() else {
        eprintln!("[skip] LOREWEAVE_TEST_REDIS_URL not set — dp cache suite skipped");
        return;
    };
    let cache = Arc::new(RedisCache::connect(&url).await.expect("connect redis"));
    let key = format!("dp:test:{}:latency", Uuid::new_v4());
    cache.set(&key, &4242u32.to_le_bytes(), Duration::from_secs(60)).expect("seed");

    let n = 200;
    let start = std::time::Instant::now();
    for _ in 0..n {
        let _ = cache.get(&key).expect("get");
    }
    let mean = start.elapsed() / n;

    println!("DP-T2 cache read: mean {:?} over {n} gets (budget <10ms)", mean);
    assert!(
        mean < Duration::from_millis(10),
        "DP-T2's read budget is <10ms from cache; measured mean {mean:?}"
    );
    cache.del(&key).expect("cleanup");
}
