//! L6.C.2 — Per-message authz types (Rust mirror).
//!
//! Cycle 29 L6.C ships per-message re-authorization on the WS gateway
//! (NestJS). Downstream Rust services (roleplay-service, future
//! presence-service) need the rejection-reason enum + the request shape
//! so they can implement `SessionAuthzProvider` over RPC.
//!
//! The TypeScript canonical is
//! `services/api-gateway-bff/src/ws/per-message-authz.ts`. This module
//! mirrors the wire-visible types only — the cache + evaluator live in
//! the gateway.

use serde::{Deserialize, Serialize};

/// Per S12 §12AB.L3 + cycle 28 `metrics.ts::AuthzRejectionReason`.
/// Stable wire enum; do not reorder (mapped onto Prometheus label values).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthzRejectionReason {
    /// S2: user not (or no longer) in session_participants.
    S2NotInSession,
    /// S3: user lacks the required privacy_level grant.
    S3PrivacyViolation,
    /// Required message-type scope absent from ticket.allowed_scopes.
    ScopeNotAllowed,
    /// reality_id of the message not in ticket.allowed_realities.
    RealityNotAllowed,
    /// Message envelope failed `validateEnvelope` (router-stage reject).
    SchemaInvalid,
}

impl AuthzRejectionReason {
    /// Canonical short name matching `metrics.ts::AuthzRejectionReason`.
    pub fn name(self) -> &'static str {
        match self {
            Self::S2NotInSession => "s2_not_in_session",
            Self::S3PrivacyViolation => "s3_privacy_violation",
            Self::ScopeNotAllowed => "scope_not_allowed",
            Self::RealityNotAllowed => "reality_not_allowed",
            Self::SchemaInvalid => "schema_invalid",
        }
    }
}

/// Wire-format authz outcome — used by downstream RPC clients.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "tag", rename_all = "snake_case")]
pub enum AuthzOutcome {
    /// Allow — message proceeds to forward/fanout.
    Allow,
    /// Deny — message dropped with metric increment.
    Deny {
        /// One of `AuthzRejectionReason`.
        reason: AuthzRejectionReason,
    },
}

impl AuthzOutcome {
    /// Convenience for downstream `if outcome.is_allow() { ... }`.
    pub fn is_allow(&self) -> bool {
        matches!(self, Self::Allow)
    }
}

/// Inbound + outbound authz request payload. Mirrors
/// `per-message-authz.ts::AuthzRequest`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthzRequest {
    /// User ref id from the ticket.
    pub user_ref_id: String,
    /// Allowed realities from the ticket (deny-list complement).
    pub allowed_realities: Vec<String>,
    /// Allowed scopes from the ticket.
    pub allowed_scopes: Vec<String>,
    /// Envelope type for routing the required scope (caller derives).
    pub message_type: String,
    /// Session id (S2 lookup key). None for session-less messages
    /// (e.g. presence heartbeats).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    /// Reality id (matched against allowed_realities). None when N/A.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reality_id: Option<String>,
    /// Privacy level for S3 check. None when N/A.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub privacy_level: Option<String>,
    /// Scope required by this message type. None means scope-free.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub required_scope: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejection_reason_names_match_ts_enum() {
        // Cardinality budget — keep these in lockstep with the TS
        // `AuthzRejectionReason` union literal in metrics.ts (5 values).
        let all = [
            AuthzRejectionReason::S2NotInSession,
            AuthzRejectionReason::S3PrivacyViolation,
            AuthzRejectionReason::ScopeNotAllowed,
            AuthzRejectionReason::RealityNotAllowed,
            AuthzRejectionReason::SchemaInvalid,
        ];
        let names: Vec<&str> = all.iter().map(|r| r.name()).collect();
        assert_eq!(
            names,
            vec![
                "s2_not_in_session",
                "s3_privacy_violation",
                "scope_not_allowed",
                "reality_not_allowed",
                "schema_invalid",
            ],
        );
    }

    #[test]
    fn outcome_serde_round_trip_allow() {
        let v = AuthzOutcome::Allow;
        let json = serde_json::to_string(&v).unwrap();
        assert_eq!(json, r#"{"tag":"allow"}"#);
        let back: AuthzOutcome = serde_json::from_str(&json).unwrap();
        assert_eq!(back, v);
        assert!(back.is_allow());
    }

    #[test]
    fn outcome_serde_round_trip_deny() {
        let v = AuthzOutcome::Deny { reason: AuthzRejectionReason::S2NotInSession };
        let json = serde_json::to_string(&v).unwrap();
        assert!(json.contains("\"tag\":\"deny\""));
        assert!(json.contains("\"reason\":\"s2_not_in_session\""));
        let back: AuthzOutcome = serde_json::from_str(&json).unwrap();
        assert_eq!(back, v);
        assert!(!back.is_allow());
    }

    #[test]
    fn request_serde_round_trip_minimal() {
        let r = AuthzRequest {
            user_ref_id: "u1".into(),
            allowed_realities: vec!["r1".into()],
            allowed_scopes: vec!["chat".into()],
            message_type: "chat.message".into(),
            session_id: None,
            reality_id: None,
            privacy_level: None,
            required_scope: None,
        };
        let json = serde_json::to_string(&r).unwrap();
        // None fields skip — round-trip MUST be lossless.
        let back: AuthzRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(back, r);
    }
}
