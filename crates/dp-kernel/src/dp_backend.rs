//! `5-WIRE` — `dp-kernel` behind `dp`'s storage seams.
//!
//! # What this closes
//!
//! `crates/dp` declares no I/O, so its write and read surfaces are traits and
//! nothing more. Until this file their only implementors were `#[cfg(test)]`
//! doubles — the same standing `ControlPlane` had before `5A`. This is the
//! production side: `dp::WriteBackend` over the kernel's `EventStore` append,
//! and `dp::ReadBackend` over its snapshot store.
//!
//! # Why the dependency points this way
//!
//! `dp-kernel` depends on `dp`, not the reverse. `dp` is a contract crate with
//! no I/O of its own, so the arrow runs from the I/O-bearing crate to the
//! contract — which is the direction that keeps the contract clean. The same
//! choice `meta-rs` made for `ControlPlane` in `5A`.
//!
//! This crate carries `[package.metadata.dp] dp-crate = true`, so `DP-R3` lets
//! it hold the raw clients underneath. That marker is not a convenience here;
//! it is the statement that this crate IS the data plane, which is exactly what
//! being the backend means.
//!
//! # The sync/async bridge, and why it is guarded at construction
//!
//! `dp`'s seams are synchronous — deliberately, so the contract crate carries
//! no runtime. `EventStore` is `async`. The bridge is `block_in_place` +
//! `Handle::block_on`, which **panics on a current-thread runtime**, so both
//! adapters refuse one when they are built. `meta-rs`'s `PgConnectionWriter`
//! established that guard and `PgConnectionReader` repeated it; a panic in the
//! middle of a write is worse than an error before one starts.

use std::sync::Arc;

use dp::{DpError, ReadBackend, WriteAck, WriteBackend, WriteRequest};
use tokio::runtime::{Handle, RuntimeFlavor};
use uuid::Uuid;

use crate::envelope::EventEnvelope;
use crate::event_store::EventStore;

/// Shared guard: both adapters need a multi-thread runtime handle.
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

/// `dp::WriteBackend` over the kernel's event store.
///
/// Every write becomes an appended event. That is the kernel's model, and it is
/// why `WriteRequest` had to carry the reality and the aggregate id as VALUES:
/// an `EventEnvelope` needs both, and the only other place they appeared was
/// inside the `DP-K7` cache key as formatted text.
pub struct KernelWriteBackend<S: EventStore> {
    store: Arc<S>,
    handle: Handle,
    /// What `event_type` an SDK write records.
    ///
    /// One type for all SDK writes rather than one per aggregate: the aggregate
    /// is already named by `aggregate_type`, and minting an event type per
    /// aggregate would put a second, unregistered vocabulary next to
    /// `contracts/events/_registry.yaml`.
    event_type: String,
}

impl<S: EventStore> KernelWriteBackend<S> {
    /// Default event type for SDK-originated writes.
    pub const SDK_EVENT_TYPE: &'static str = "dp.write.applied";

    pub fn new(store: Arc<S>) -> Result<Self, DpError> {
        Ok(Self {
            store,
            handle: multi_thread_handle("KernelWriteBackend")?,
            event_type: Self::SDK_EVENT_TYPE.to_string(),
        })
    }
}

impl<S: EventStore> WriteBackend for KernelWriteBackend<S> {
    fn apply(&self, req: &WriteRequest<'_>) -> Result<WriteAck, DpError> {
        // `Rfc3339Timestamp` is a type alias for `String`, so there is nothing
        // to call `now()` on. Every other value of it in this crate is a test
        // literal; this is the first production one.
        let now: crate::envelope::Rfc3339Timestamp =
            chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
        let envelope = EventEnvelope {
            event_id: Uuid::new_v4(),
            event_type: self.event_type.clone(),
            event_version: 1,
            aggregate_id: req.aggregate_id.as_str().to_string(),
            aggregate_type: req.aggregate_type.to_string(),
            // The envelope records the version this write lands AT; the store
            // is told separately what version the caller expected.
            aggregate_version: req.expected_version.saturating_add(1),
            reality_id: req.reality.as_uuid(),
            occurred_at: now.clone(),
            recorded_at: now,
            // The payload is bytes at the seam and JSON in the envelope. Base64
            // rather than a lossy utf-8 cast: an `Encode` impl is free to
            // produce arbitrary bytes, and silently corrupting a non-utf-8
            // payload would be a data bug that surfaces only on read.
            payload: serde_json::json!({ "b64": b64(req.payload) }),
            metadata: Some(serde_json::json!({
                "dp_tier": req.tier.as_key(),
                "dp_cache_key": req.cache_key,
            })),
            ruleset_digest: None,
        };

        let position = tokio::task::block_in_place(|| {
            self.handle
                .block_on(async { self.store
                    .append_events(
                        req.reality.as_uuid(),
                        req.aggregate_type,
                        req.aggregate_id.as_str(),
                        req.expected_version,
                        &[envelope],
                    )
                    .await })
        })
        .map_err(|e| DpError::BackendIo(Box::new(e)))?;

        Ok(WriteAck { position })
    }
}

/// `dp::ReadBackend` over the kernel's snapshot store.
///
/// A snapshot is what the kernel already stores per `(reality, type, id)`, so
/// it is the natural answer to `fetch`. `None` is a MISS and stays a miss — the
/// `AggregateNotFound` decision belongs to `read_projection_reality`, because
/// absent is legitimate for some aggregates and a fault for others.
pub struct KernelReadBackend<S: EventStore> {
    store: Arc<S>,
    handle: Handle,
    reality: Uuid,
}

impl<S: EventStore> KernelReadBackend<S> {
    /// The reality is bound at construction, not per call.
    ///
    /// `dp::ReadBackend::fetch` takes only `(aggregate, key)` — the session's
    /// reality is the caller's, and a backend that accepted one per call could
    /// be handed a different reality than the session was bound to. Fixing it
    /// here makes that unrepresentable rather than merely discouraged.
    pub fn new(store: Arc<S>, reality: Uuid) -> Result<Self, DpError> {
        Ok(Self {
            store,
            handle: multi_thread_handle("KernelReadBackend")?,
            reality,
        })
    }
}

impl<S: EventStore> ReadBackend for KernelReadBackend<S> {
    fn fetch(&self, req: &dp::ReadRequest<'_>) -> Result<Option<Vec<u8>>, DpError> {
        // The id arrives as a VALUE. It used to be recovered with
        // `key.rsplit(':').next()` — which is the anti-pattern this file's own
        // write-side doc condemns, and was wrong besides: a DP-K7 key with a
        // subkey ends `…:{id}:{subkey}`, so that took the SUBKEY and every
        // subkeyed read resolved the wrong aggregate.
        let found = tokio::task::block_in_place(|| {
            self.handle.block_on(async {
                self.store
                    .snapshot_read(self.reality, req.aggregate_type, req.aggregate_id.as_str())
                    .await
            })
        })
        .map_err(|e| DpError::BackendIo(Box::new(e)))?;

        Ok(found.map(|rec| rec.snapshot_data.to_string().into_bytes()))
    }
}

/// Minimal base64, so the payload survives a JSON round trip byte-for-byte.
///
/// Hand-rolled rather than taking a dependency for eleven lines. It is the
/// standard alphabet with padding; `crates/dp`'s `Decode` impls are the only
/// readers and they decode what this produces.
fn b64(bytes: &[u8]) -> String {
    const A: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b = [chunk[0], *chunk.get(1).unwrap_or(&0), *chunk.get(2).unwrap_or(&0)];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(A[(n >> 18) as usize & 63] as char);
        out.push(A[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { A[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { A[n as usize & 63] as char } else { '=' });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn b64_matches_known_vectors() {
        // RFC 4648 §10. A hand-rolled encoder with no test is a data bug
        // waiting for a read.
        assert_eq!(b64(b""), "");
        assert_eq!(b64(b"f"), "Zg==");
        assert_eq!(b64(b"fo"), "Zm8=");
        assert_eq!(b64(b"foo"), "Zm9v");
        assert_eq!(b64(b"foob"), "Zm9vYg==");
        assert_eq!(b64(b"fooba"), "Zm9vYmE=");
        assert_eq!(b64(b"foobar"), "Zm9vYmFy");
    }

    /// END TO END through the SDK: `t2_write` -> `KernelWriteBackend` ->
    /// `EventStore::append_events`, against a real store implementation.
    ///
    /// This is what `5-WIRE` is for. Every earlier test of the write surface
    /// drove a `#[cfg(test)]` spy inside `crates/dp`; this drives the kernel.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_t2_write_reaches_the_event_store_through_the_sdk() {
        use crate::event_store::shared_test_suite::InMemoryEventStore;
        use dp::{
            scope::RealityScope, tier::T2, BindRequest, ControlPlane, DpAggregate, Encode,
            KeyId, SessionContext, VerifiedBind,
        };

        struct Inv;
        impl DpAggregate for Inv {
            type Tier = T2;
            type Scope = RealityScope;
            type Id = Uuid;
            type Delta = i32;
            type Projection = ();
            const TYPE_NAME: &'static str = "wire_fixture";
        }
        impl Encode for Inv {
            fn encode(d: &i32) -> Result<Vec<u8>, DpError> {
                Ok(d.to_le_bytes().to_vec())
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

        let reality = Uuid::new_v4();
        let ctx = SessionContext::bind(
            &Cp,
            BindRequest {
                reality,
                node: "n".into(),
                service: dp::ServiceIdentity::new("dp-kernel-test").expect("valid"),
            },
            0,
        )
        .expect("bind");

        let store = Arc::new(InMemoryEventStore::default());
        let backend = KernelWriteBackend::new(store.clone()).expect("multi-thread runtime");

        let id = Uuid::new_v4();
        let key = dp::cache_key!(&ctx, T2, Inv, id);
        let ack = dp::t2_write::<Inv, _>(&backend, &ctx, 0, KeyId::from(id), &key, 0, 42)
            .expect("write through the SDK");
        assert_eq!(ack.position, 1, "the store assigned version 1 to a new aggregate");

        // DATA: read the event back out of the store and check what landed.
        let events = store
            .read_stream(reality, "wire_fixture", &id.to_string(), 0)
            .await
            .expect("read_stream");
        assert_eq!(events.len(), 1, "exactly one event was appended");
        let e = &events[0];
        assert_eq!(e.reality_id, reality, "the VERIFIED reality reached the envelope");
        assert_eq!(e.aggregate_type, "wire_fixture");
        assert_eq!(e.aggregate_id, id.to_string());
        assert_eq!(e.event_type, KernelWriteBackend::<InMemoryEventStore>::SDK_EVENT_TYPE);
        assert_eq!(
            e.payload["b64"], b64(&42i32.to_le_bytes()),
            "the ENCODED delta survived the seam byte-for-byte"
        );
        let meta = e.metadata.as_ref().expect("metadata");
        assert_eq!(meta["dp_tier"], "t2", "the tier came from the aggregate's TYPE");
        assert_eq!(meta["dp_cache_key"], key, "the DP-K7 key is recorded with the event");
    }

    /// THE REGRESSION, through the real backend.
    ///
    /// `fetch` used to take the last segment of the cache key as the aggregate
    /// id. A subkeyed DP-K7 key ends `…:{id}:{subkey}`, so it asked the store
    /// for the SUBKEY. This writes a snapshot under a known id and reads it
    /// with a subkeyed key: before the fix the read missed.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_subkeyed_key_still_reads_the_right_aggregate() {
        use crate::event_store::shared_test_suite::InMemoryEventStore;
        use dp::{KeyId, ReadBackend, ReadRequest};

        let reality = Uuid::new_v4();
        let store = Arc::new(InMemoryEventStore::default());
        store
            .snapshot_write(reality, "sub_fixture", "42", 1, serde_json::json!({"v": 7}), None)
            .await
            .expect("snapshot_write");

        let backend = KernelReadBackend::new(store, reality).expect("multi-thread runtime");

        // A verified RealityId, obtained the only way there is one.
        struct Cp;
        impl dp::ControlPlane for Cp {
            fn verify_bind(&self, req: &dp::BindRequest) -> Result<dp::VerifiedBind, DpError> {
                Ok(dp::VerifiedBind {
                    reality: req.reality,
                    session: Uuid::new_v4(),
                    capability_secret: "s".into(),
                    expires_at_ms: 10_000,
                })
            }
        }
        let ctx = dp::SessionContext::bind(
            &Cp,
            dp::BindRequest {
                reality,
                node: "n".into(),
                service: dp::ServiceIdentity::new("dp-kernel-test").expect("valid"),
            },
            0,
        )
        .expect("bind");

        let found = backend
            .fetch(&ReadRequest {
                reality: ctx.reality_id(),
                aggregate_type: "sub_fixture",
                aggregate_id: KeyId::from(42u64),
                // The trailing segment is a SUBKEY, not the id.
                cache_key: "dp:r:r:t2:sub_fixture:42:equipped",
            })
            .expect("fetch");

        let bytes = found.expect("the snapshot written under id 42 must be found");
        assert!(
            String::from_utf8_lossy(&bytes).contains("\"v\":7"),
            "got {}",
            String::from_utf8_lossy(&bytes)
        );
    }

    #[test]
    fn b64_is_byte_exact_on_non_utf8() {
        // The reason base64 is here rather than a utf-8 cast: an `Encode` impl
        // may return arbitrary bytes.
        assert_eq!(b64(&[0xff, 0xfe, 0xfd]), "//79");
    }
}
