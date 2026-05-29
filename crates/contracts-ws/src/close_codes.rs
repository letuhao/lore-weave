//! WS close codes — Rust mirror of the Go canonical at
//! `contracts/ws/envelope.go::CloseCode`. Cycle 29 L6.D ships the
//! full enum (force-disconnect via Redis control channel); cycle 28
//! ships the shared subset the gateway emits during handshake failure.

use serde::{Deserialize, Serialize};

/// Enumerated S12 §12AB.9 close codes. Wire values match WebSocket
/// spec: 1000 + 4001..4010.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(into = "u16", try_from = "u16")]
pub enum CloseCode {
    /// 1000 — client-initiated normal closure.
    Normal,
    /// 4001 — refresh failed before expiry / ticket expired during handshake.
    TokenExpired,
    /// 4002 — user logout / JWT revoked.
    TokenRevoked,
    /// 4003 — S8 crypto-shred fired.
    UserErased,
    /// 4004 — S10 reality archived / dropped.
    RealityArchived,
    /// 4005 — admin force-kick.
    AdminKick,
    /// 4006 — persistent rate-limit violation.
    RateLimitExceeded,
    /// 4007 — origin violation mid-connection.
    OriginMismatch,
    /// 4008 — per-user / per-replica connection cap reached (Q-L6-2).
    ConnectionLimitExceeded,
    /// 4009 — client binding broken (fingerprint mismatch).
    FingerprintMismatch,
    /// 4010 — persistent malformed messages.
    SchemaInvalid,
}

impl From<CloseCode> for u16 {
    fn from(c: CloseCode) -> u16 {
        match c {
            CloseCode::Normal => 1000,
            CloseCode::TokenExpired => 4001,
            CloseCode::TokenRevoked => 4002,
            CloseCode::UserErased => 4003,
            CloseCode::RealityArchived => 4004,
            CloseCode::AdminKick => 4005,
            CloseCode::RateLimitExceeded => 4006,
            CloseCode::OriginMismatch => 4007,
            CloseCode::ConnectionLimitExceeded => 4008,
            CloseCode::FingerprintMismatch => 4009,
            CloseCode::SchemaInvalid => 4010,
        }
    }
}

impl TryFrom<u16> for CloseCode {
    type Error = UnknownCloseCode;
    fn try_from(v: u16) -> Result<Self, Self::Error> {
        Ok(match v {
            1000 => Self::Normal,
            4001 => Self::TokenExpired,
            4002 => Self::TokenRevoked,
            4003 => Self::UserErased,
            4004 => Self::RealityArchived,
            4005 => Self::AdminKick,
            4006 => Self::RateLimitExceeded,
            4007 => Self::OriginMismatch,
            4008 => Self::ConnectionLimitExceeded,
            4009 => Self::FingerprintMismatch,
            4010 => Self::SchemaInvalid,
            _ => return Err(UnknownCloseCode(v)),
        })
    }
}

/// Raised when an unknown close-code value lands on the wire.
#[derive(Debug, thiserror::Error)]
#[error("unknown WS close code: {0}")]
pub struct UnknownCloseCode(pub u16);

impl CloseCode {
    /// Canonical short name matching §12AB.9 vocab.
    pub fn name(self) -> &'static str {
        match self {
            CloseCode::Normal => "normal_closure",
            CloseCode::TokenExpired => "token_expired",
            CloseCode::TokenRevoked => "token_revoked",
            CloseCode::UserErased => "user_erased",
            CloseCode::RealityArchived => "reality_archived",
            CloseCode::AdminKick => "admin_kick",
            CloseCode::RateLimitExceeded => "rate_limit_exceeded",
            CloseCode::OriginMismatch => "origin_mismatch",
            CloseCode::ConnectionLimitExceeded => "connection_limit_exceeded",
            CloseCode::FingerprintMismatch => "fingerprint_mismatch",
            CloseCode::SchemaInvalid => "schema_invalid",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_all_codes() {
        let all = [
            CloseCode::Normal,
            CloseCode::TokenExpired,
            CloseCode::TokenRevoked,
            CloseCode::UserErased,
            CloseCode::RealityArchived,
            CloseCode::AdminKick,
            CloseCode::RateLimitExceeded,
            CloseCode::OriginMismatch,
            CloseCode::ConnectionLimitExceeded,
            CloseCode::FingerprintMismatch,
            CloseCode::SchemaInvalid,
        ];
        for c in all {
            let wire: u16 = c.into();
            let back: CloseCode = wire.try_into().unwrap();
            assert_eq!(c, back);
        }
    }

    #[test]
    fn rejects_unknown_wire_value() {
        assert!(CloseCode::try_from(9999_u16).is_err());
    }
}
