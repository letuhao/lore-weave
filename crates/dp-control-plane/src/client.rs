//! [`dp::ControlPlane`], implemented over the wire.
//!
//! # Why the client is not optional
//!
//! A gRPC server with no client is the orphan shape §0.6c seals against: it
//! compiles, it has tests, and nothing in the tree can call it. This type is the
//! consumer, and it is also the thing that makes the cost of the sealed
//! bearer-capability deviation concrete — with the control plane in another
//! process, `refresh` and every validation are a network round trip. That cost
//! is stated in the `DP-C8` amendment rather than discovered here.
//!
//! # Sync over async, the same bridge `meta-rs` uses
//!
//! [`dp::ControlPlane`] is synchronous, because `crates/dp` declares no I/O and
//! therefore cannot name a runtime. tonic is async. The bridge is
//! `block_in_place`, which PANICS on a current-thread runtime — so the
//! constructor refuses one, turning a panic in the middle of a session bind into
//! an error before one starts. `PgConnectionWriter` and `PgConnectionReader`
//! refuse for the same reason and with the same words.

use dp::{BindRequest, ControlPlane, DpError, VerifiedBind};
use tokio::runtime::{Handle, RuntimeFlavor};
use tonic::transport::Channel;

use crate::pb;
use crate::pb::dp_control_plane_client::DpControlPlaneClient;

/// A [`dp::ControlPlane`] that talks to a remote control plane.
#[derive(Clone)]
pub struct GrpcControlPlane {
    inner: DpControlPlaneClient<Channel>,
    handle: Handle,
}

impl GrpcControlPlane {
    /// Connect to a control plane at `endpoint` (e.g. `http://127.0.0.1:50151`).
    ///
    /// Async because connecting is; everything after is callable from sync code.
    pub async fn connect(endpoint: String) -> Result<Self, DpError> {
        let handle = Handle::try_current().map_err(|_| DpError::ControlPlaneUnavailable {
            reason: "GrpcControlPlane must be constructed inside a tokio runtime — it bridges \
                     the synchronous dp::ControlPlane trait onto async tonic"
                .into(),
        })?;
        if handle.runtime_flavor() != RuntimeFlavor::MultiThread {
            return Err(DpError::ControlPlaneUnavailable {
                reason: "GrpcControlPlane requires a MULTI-THREAD tokio runtime: \
                         dp::ControlPlane is synchronous, so the adapter blocks with \
                         block_in_place, which panics on a current-thread runtime."
                    .into(),
            });
        }
        let inner = DpControlPlaneClient::connect(endpoint)
            .await
            .map_err(|e| DpError::ControlPlaneUnavailable { reason: e.to_string() })?;
        Ok(Self { inner, handle })
    }

    /// `RefreshCapability` — extend a live grant.
    ///
    /// Returns the SAME secret that was presented, because the server does not
    /// re-issue one; the expiry moves on the stored row. Echoing it keeps the
    /// return shape identical to `verify_bind`'s so a caller can treat a refresh
    /// as a bind that happened to keep its credential.
    pub fn refresh_capability(&self, capability_secret: &str) -> Result<VerifiedBind, DpError> {
        let mut client = self.inner.clone();
        let secret = capability_secret.to_string();
        let resp = self
            .block_on(async move {
                client
                    .refresh_capability(pb::RefreshCapabilityRequest {
                        capability_secret: secret,
                    })
                    .await
            })
            .map_err(status_to_dp)?
            .into_inner();

        Ok(VerifiedBind {
            reality: parse_uuid(&resp.reality_id, "reality_id")?,
            session: parse_uuid(&resp.session_id, "session_id")?,
            capability_secret: capability_secret.to_string(),
            expires_at_ms: resp.expires_at_ms,
        })
    }

    /// `VerifyReality` — does this reality exist and accept commands?
    pub fn verify_reality(&self, reality: uuid::Uuid) -> Result<bool, DpError> {
        let mut client = self.inner.clone();
        let resp = self
            .block_on(async move {
                client
                    .verify_reality(pb::VerifyRealityRequest {
                        reality_id: reality.to_string(),
                    })
                    .await
            })
            .map_err(status_to_dp)?
            .into_inner();
        Ok(resp.bindable)
    }

    /// `GetSessionNode` — where a session is pinned, or `None`.
    pub fn session_node(&self, session: uuid::Uuid) -> Result<Option<String>, DpError> {
        let mut client = self.inner.clone();
        let resp = self
            .block_on(async move {
                client
                    .get_session_node(pb::GetSessionNodeRequest {
                        session_id: session.to_string(),
                    })
                    .await
            })
            .map_err(status_to_dp)?
            .into_inner();
        // The `assigned` flag, not `node_id.is_empty()`. An empty string is a
        // node name the server never sends, but reading absence off a field's
        // emptiness is how a protocol grows a second meaning for `""`.
        Ok(resp.assigned.then_some(resp.node_id))
    }

    /// Is the control plane reachable AND able to reach its own state?
    pub fn health(&self) -> Result<(bool, String), DpError> {
        let mut client = self.inner.clone();
        let resp = self
            .block_on(async move { client.health(pb::Empty {}).await })
            .map_err(status_to_dp)?
            .into_inner();
        Ok((resp.healthy, resp.detail))
    }

    fn block_on<F: std::future::Future>(&self, fut: F) -> F::Output {
        tokio::task::block_in_place(|| self.handle.block_on(fut))
    }
}

/// `DP-K10` step 4 over the wire.
///
/// This is where the sealed bearer deviation's cost is actually paid: a refresh
/// is a network round trip. It happens once per `REFRESH_LEAD_MS` before expiry
/// rather than per write, which is what keeps it inside `DP-C3`'s ≤100 req/s
/// budget for the whole control plane.
impl dp::CapabilityRefresh for GrpcControlPlane {
    fn refresh(&self, capability_secret: &str) -> Result<dp::session::Millis, DpError> {
        Ok(self.refresh_capability(capability_secret)?.expires_at_ms)
    }
}

impl ControlPlane for GrpcControlPlane {
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
        let mut client = self.inner.clone();
        let wire = pb::BindSessionRequest {
            reality_id: req.reality.to_string(),
            node_id: req.node.clone(),
            service_identity: req.service.as_str().to_string(),
        };
        let resp = self
            .block_on(async move { client.bind_session(wire).await })
            .map_err(status_to_dp)?
            .into_inner();

        Ok(VerifiedBind {
            reality: parse_uuid(&resp.reality_id, "reality_id")?,
            session: parse_uuid(&resp.session_id, "session_id")?,
            capability_secret: resp.capability_secret,
            expires_at_ms: resp.expires_at_ms,
        })
    }
}

/// A gRPC status becomes a [`DpError`].
///
/// The inverse of the server's mapping, and deliberately NOT a perfect one: the
/// server collapses "never issued" and "revoked" into one `UNAUTHENTICATED` so
/// the endpoint is not an oracle for whether a guessed secret exists. This side
/// therefore cannot recover which it was, and reports `CapabilityExpired` — the
/// variant a caller acts on identically. Reconstructing the distinction here
/// would defeat the reason the server hid it.
fn status_to_dp(s: tonic::Status) -> DpError {
    use tonic::Code;
    match s.code() {
        Code::Unauthenticated => DpError::CapabilityExpired,
        Code::FailedPrecondition => DpError::RealityMismatch {
            ctx: "control plane".to_string(),
            requested: s.message().to_string(),
        },
        // UNIMPLEMENTED is an outage from the caller's point of view — the
        // method exists in the contract and the server cannot serve it — and it
        // keeps its message, which names the missing table.
        Code::Unavailable | Code::Unimplemented => DpError::ControlPlaneUnavailable {
            reason: format!("{:?}: {}", s.code(), s.message()),
        },
        other => DpError::ControlPlaneUnavailable {
            reason: format!("{other:?}: {}", s.message()),
        },
    }
}

fn parse_uuid(raw: &str, field: &str) -> Result<uuid::Uuid, DpError> {
    uuid::Uuid::parse_str(raw).map_err(|_| DpError::ControlPlaneUnavailable {
        reason: format!("control plane returned a non-uuid {field}: {raw:?}"),
    })
}
