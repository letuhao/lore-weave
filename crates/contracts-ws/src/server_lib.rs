//! Server-lib primitives for downstream Rust services.
//!
//! Per Q-L6-1: the WS impl lives in the NestJS gateway. Downstream
//! services talk to the gateway over RPC (HTTP / gRPC; not WS). This
//! crate exposes the typed surface they use to assemble outbound
//! envelopes the gateway will fan out.

use crate::envelope::Envelope;

/// What downstream services hand to the gateway to be fanned out.
///
/// Each `OutboundFrame` carries the destination topic (e.g.
/// `reality:<id>:events`) and the wire envelope. The gateway's
/// `outbound-fanout.ts` walks subscribed connections per topic and
/// forwards the envelope intact.
#[derive(Debug, Clone)]
pub struct OutboundFrame {
    /// Topic the frame is published on. Topic shape is owned by the
    /// gateway's subscription model (not foundation here).
    pub topic: String,
    /// The wire envelope.
    pub envelope: Envelope,
}

/// `ServerLib` — typed builder for outbound frames. Implementors will
/// be downstream service `WriterCtx` types that wrap their own RPC
/// client.
pub trait ServerLib {
    /// Publish an outbound frame to the gateway's Redis stream so the
    /// gateway's `outbound-fanout.ts` consumer picks it up and sends
    /// it to every subscribed connection.
    fn publish(&self, frame: OutboundFrame) -> Result<(), ServerLibError>;
}

/// `ServerLib` failure modes.
#[derive(Debug, thiserror::Error)]
pub enum ServerLibError {
    /// Underlying RPC / stream publish failed.
    #[error("publish failed: {0}")]
    Publish(String),
    /// Envelope failed validation before publish.
    #[error("envelope invalid: {0}")]
    Envelope(#[from] crate::envelope::EnvelopeError),
}
