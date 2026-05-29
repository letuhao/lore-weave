//! WS wire envelope — Rust mirror of `contracts/ws/envelope.go`.
//!
//! The Go file is canonical (shipped cycle 21 L4.L); we serialize JSON
//! that is byte-for-byte compatible.

use serde::{Deserialize, Serialize};

/// Current wire format version. Bumping is a cross-language change.
pub const ENVELOPE_VERSION: u8 = 1;

/// Classifies an envelope as control vs data.
///
/// Routers fast-path control messages (`ws.ping` / `ws.pong` /
/// `ws.refresh`) without hitting the authz cache (S12 §12AB.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MessageKind {
    /// Protocol/control messages. Bypasses S2/S3 authz.
    Control,
    /// Application messages — subject to S2/S3 authz on every send/receive.
    Data,
}

/// Direction marker — server-side validators reject mismatches.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Direction {
    /// Inbound to the gateway.
    #[serde(rename = "c2s")]
    ClientToServer,
    /// Outbound to the browser.
    #[serde(rename = "s2c")]
    ServerToClient,
}

/// The wire-shape every WS frame deserializes to. Wire-compatible with
/// `contracts/ws/envelope.go::Envelope` (Go canonical).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Envelope {
    /// Envelope schema version. Must equal [`ENVELOPE_VERSION`].
    #[serde(rename = "v")]
    pub version: u8,

    /// Control vs data.
    pub kind: MessageKind,

    /// Message-type string (e.g., "chat.message", "ws.ping").
    #[serde(rename = "type")]
    pub message_type: String,

    /// Direction marker.
    #[serde(rename = "dir")]
    pub direction: Direction,

    /// Monotonic per-connection per-type sequence.
    #[serde(default, skip_serializing_if = "is_zero_u64")]
    pub seq: u64,

    /// UUID string; server tracks in TTL set for replay defense.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub nonce: String,

    /// Opaque per-type bytes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub payload: Option<serde_json::Value>,
}

#[inline]
fn is_zero_u64(v: &u64) -> bool {
    *v == 0
}

impl Envelope {
    /// Construct a server→client control envelope.
    pub fn control(message_type: impl Into<String>) -> Self {
        Self {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Control,
            message_type: message_type.into(),
            direction: Direction::ServerToClient,
            seq: 0,
            nonce: String::new(),
            payload: None,
        }
    }

    /// Construct a server→client data envelope.
    pub fn data(message_type: impl Into<String>, nonce: impl Into<String>, payload: serde_json::Value) -> Self {
        Self {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Data,
            message_type: message_type.into(),
            direction: Direction::ServerToClient,
            seq: 0,
            nonce: nonce.into(),
            payload: Some(payload),
        }
    }

    /// Shape validator — mirrors `contracts/ws/envelope.go::Validate`.
    pub fn validate(&self) -> Result<(), EnvelopeError> {
        if self.version != ENVELOPE_VERSION {
            return Err(EnvelopeError::VersionMismatch {
                got: self.version,
                want: ENVELOPE_VERSION,
            });
        }
        if self.message_type.is_empty() {
            return Err(EnvelopeError::EmptyType);
        }
        if matches!(self.kind, MessageKind::Data) && self.nonce.is_empty() {
            return Err(EnvelopeError::NonceRequired);
        }
        Ok(())
    }
}

/// Envelope-level validation errors.
#[derive(Debug, thiserror::Error)]
pub enum EnvelopeError {
    /// Wire version does not match this build.
    #[error("envelope version mismatch: got {got}, want {want}")]
    VersionMismatch {
        /// Version received on the wire.
        got: u8,
        /// Version this build expects.
        want: u8,
    },
    /// Type field is empty.
    #[error("envelope type empty")]
    EmptyType,
    /// Data envelope without nonce.
    #[error("data envelope requires nonce (replay defense)")]
    NonceRequired,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_pinned_at_1() {
        assert_eq!(ENVELOPE_VERSION, 1);
    }

    #[test]
    fn json_round_trip_matches_go_canonical_shape() {
        // This is the wire shape `contracts/ws/envelope.go` serializes.
        // If either side drifts, the JSON below will diverge — pinning
        // the field names guards against accidental rename.
        let env = Envelope::data("chat.message", "n1", serde_json::json!({"body": "hi"}));
        let s = serde_json::to_string(&env).unwrap();
        assert!(s.contains("\"v\":1"));
        assert!(s.contains("\"kind\":\"data\""));
        assert!(s.contains("\"type\":\"chat.message\""));
        assert!(s.contains("\"dir\":\"s2c\""));
        assert!(s.contains("\"nonce\":\"n1\""));

        let back: Envelope = serde_json::from_str(&s).unwrap();
        assert_eq!(back.message_type, "chat.message");
        assert_eq!(back.direction, Direction::ServerToClient);
        assert_eq!(back.kind, MessageKind::Data);
        assert!(back.validate().is_ok());
    }

    #[test]
    fn validate_rejects_version_mismatch() {
        let mut env = Envelope::control("ws.ping");
        env.version = 99;
        assert!(matches!(env.validate(), Err(EnvelopeError::VersionMismatch { .. })));
    }

    #[test]
    fn validate_rejects_data_without_nonce() {
        let env = Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Data,
            message_type: "chat.message".into(),
            direction: Direction::ServerToClient,
            seq: 1,
            nonce: String::new(),
            payload: Some(serde_json::json!({"body": "hi"})),
        };
        assert!(matches!(env.validate(), Err(EnvelopeError::NonceRequired)));
    }
}
