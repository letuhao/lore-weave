//! L6.D — Forced-disconnect control channel types (Rust mirror).
//!
//! Cycle 29 L6.D extends the cycle 7 (L1.J) shared Redis pubsub control
//! channel `lw:dependency:control` with a new message kind, rather than
//! creating a new channel. Subscribers ignore kinds they don't care about
//! (see `contracts/lifecycle/mode_propagation.go`).
//!
//! The Go canonical lives at `contracts/lifecycle/mode_propagation.go`:
//!   - `KindWsDisconnectUser MessageKind = "ws_disconnect_user"`
//!   - `EncodeWsDisconnectUser` builder + `DecodeControlMessage` validator
//!
//! Wire compatibility:
//!   * 11 close codes (1000, 4001..4010) from `super::close_codes::CloseCode`
//!   * Nonce required (idempotency — subscribers de-dupe on a small LRU)
//!   * Reason free-form short string (e.g. "logout", "token_revoked",
//!     "user_erased", "admin_kick", "compromise_detected")

use crate::close_codes::CloseCode;
use serde::{Deserialize, Serialize};

/// Wire-format version. Bump on breaking changes; subscribers accept N + N-1.
pub const WS_CONTROL_VERSION: i32 = 1;

/// Message kind discriminator on the shared `lw:dependency:control` topic.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WsControlKind {
    /// Force-close all WS connections owned by a user_ref_id.
    WsDisconnectUser,
}

/// Subset of `ControlMessage` (Go) we care about for WS forced-disconnect.
/// Downstream Rust services that publish forced-disconnects construct this
/// envelope; subscribers (gateway) decode it via the TS consumer using the
/// JSON wire. Rust producers (e.g. roleplay-service on session-end) call
/// `to_json()` and XADD the bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WsControlMessage {
    /// Wire version (= 1).
    pub version: i32,
    /// Discriminator — currently only `ws_disconnect_user`.
    pub kind: WsControlKind,
    /// Producer service name (e.g. "auth-service", "admin-cli").
    pub service: String,
    /// Producer instance id — distinguishes pods within a service.
    pub instance: String,
    /// Free-form short reason — logged + surfaced in close-frame text.
    pub reason: String,
    /// Wall-clock timestamp in nanos for end-to-end SLA tracking.
    pub ts_nanos: i64,
    /// REQUIRED — user whose connections to close.
    pub user_ref_id: String,
    /// REQUIRED — one of the 11 codes in `CloseCode`.
    pub close_code: u16,
    /// REQUIRED — UUID for idempotency (subscribers de-dupe).
    pub nonce_id: String,
}

impl WsControlMessage {
    /// Build a well-formed disconnect-user message. Returns `Err` for any
    /// empty required field or unknown close-code.
    pub fn disconnect_user(
        service: impl Into<String>,
        instance: impl Into<String>,
        user_ref_id: impl Into<String>,
        close_code: CloseCode,
        reason: impl Into<String>,
        nonce_id: impl Into<String>,
        ts_nanos: i64,
    ) -> Self {
        Self {
            version: WS_CONTROL_VERSION,
            kind: WsControlKind::WsDisconnectUser,
            service: service.into(),
            instance: instance.into(),
            reason: reason.into(),
            ts_nanos,
            user_ref_id: user_ref_id.into(),
            close_code: close_code.into(),
            nonce_id: nonce_id.into(),
        }
    }

    /// Serialize to a JSON byte vector suitable for Redis XADD payload.
    pub fn to_json(&self) -> Result<Vec<u8>, serde_json::Error> {
        serde_json::to_vec(self)
    }

    /// Decode from a JSON byte slice. Validates required fields are present
    /// AND that close_code is one of the canonical 11.
    pub fn from_json(buf: &[u8]) -> Result<Self, WsControlDecodeError> {
        let msg: WsControlMessage = serde_json::from_slice(buf).map_err(WsControlDecodeError::Json)?;
        if msg.version != WS_CONTROL_VERSION {
            return Err(WsControlDecodeError::UnsupportedVersion(msg.version));
        }
        if msg.service.is_empty() || msg.instance.is_empty() {
            return Err(WsControlDecodeError::MissingIdentity);
        }
        if msg.user_ref_id.is_empty() {
            return Err(WsControlDecodeError::MissingUserRefID);
        }
        if msg.reason.is_empty() {
            return Err(WsControlDecodeError::MissingReason);
        }
        if msg.nonce_id.is_empty() {
            return Err(WsControlDecodeError::MissingNonce);
        }
        // Validates close_code is in the canonical set via try_from.
        CloseCode::try_from(msg.close_code).map_err(|_| WsControlDecodeError::InvalidCloseCode(msg.close_code))?;
        if msg.ts_nanos <= 0 {
            return Err(WsControlDecodeError::InvalidTimestamp);
        }
        Ok(msg)
    }
}

/// Decode-side errors. Producers should ALWAYS use the constructor; failed
/// decodes happen on the consumer when malformed payloads land — those
/// MUST be dropped (with a metric increment), NEVER crash the consumer.
#[derive(Debug, thiserror::Error)]
pub enum WsControlDecodeError {
    /// JSON malformed.
    #[error("ws-control: JSON parse: {0}")]
    Json(#[from] serde_json::Error),
    /// Wire-format version unsupported.
    #[error("ws-control: unsupported version {0}")]
    UnsupportedVersion(i32),
    /// Producer identity missing.
    #[error("ws-control: missing service/instance")]
    MissingIdentity,
    /// `user_ref_id` empty on a disconnect kind.
    #[error("ws-control: missing user_ref_id")]
    MissingUserRefID,
    /// Reason field empty.
    #[error("ws-control: missing reason")]
    MissingReason,
    /// Nonce empty — idempotency broken.
    #[error("ws-control: missing nonce_id")]
    MissingNonce,
    /// Close code not one of the canonical 11.
    #[error("ws-control: invalid close code {0}")]
    InvalidCloseCode(u16),
    /// Timestamp non-positive.
    #[error("ws-control: invalid timestamp")]
    InvalidTimestamp,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn good() -> WsControlMessage {
        WsControlMessage::disconnect_user(
            "auth-service",
            "auth-service-7f2c",
            "00000000-0000-0000-0000-000000000abc",
            CloseCode::TokenRevoked,
            "logout",
            "11111111-1111-1111-1111-111111111111",
            1_700_000_000_000_000_000,
        )
    }

    #[test]
    fn round_trip_disconnect_user() {
        let m = good();
        let bytes = m.to_json().unwrap();
        let back = WsControlMessage::from_json(&bytes).unwrap();
        assert_eq!(back, m);
        assert_eq!(back.close_code, 4002);
    }

    #[test]
    fn rejects_unknown_close_code() {
        let mut m = good();
        m.close_code = 9999;
        let bytes = serde_json::to_vec(&m).unwrap();
        let err = WsControlMessage::from_json(&bytes).unwrap_err();
        assert!(matches!(err, WsControlDecodeError::InvalidCloseCode(9999)));
    }

    #[test]
    fn rejects_missing_user_ref_id() {
        let mut m = good();
        m.user_ref_id = String::new();
        let bytes = serde_json::to_vec(&m).unwrap();
        let err = WsControlMessage::from_json(&bytes).unwrap_err();
        assert!(matches!(err, WsControlDecodeError::MissingUserRefID));
    }

    #[test]
    fn rejects_missing_nonce() {
        let mut m = good();
        m.nonce_id = String::new();
        let bytes = serde_json::to_vec(&m).unwrap();
        let err = WsControlMessage::from_json(&bytes).unwrap_err();
        assert!(matches!(err, WsControlDecodeError::MissingNonce));
    }

    #[test]
    fn rejects_garbage_json() {
        let err = WsControlMessage::from_json(b"not json").unwrap_err();
        assert!(matches!(err, WsControlDecodeError::Json(_)));
    }

    #[test]
    fn rejects_version_mismatch() {
        let mut m = good();
        m.version = 99;
        let bytes = serde_json::to_vec(&m).unwrap();
        let err = WsControlMessage::from_json(&bytes).unwrap_err();
        assert!(matches!(err, WsControlDecodeError::UnsupportedVersion(99)));
    }
}
