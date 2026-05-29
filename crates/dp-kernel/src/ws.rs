//! Cycle 21 / L4.L — `ws` Rust mirror of `contracts/ws/` (Go).
//!
//! # Purpose (Q-L4-1 parity)
//!
//! Rust services that surface WS endpoints (none today — gateway is
//! TypeScript NestJS per Q-L6-1 — but future Rust ws-shard candidates
//! need the same envelope + close codes) consume the same wire contract
//! the Go gateway speaks.
//!
//! # Q-IDs honored
//!
//! - **Q-L4-1**: wire shapes mirror Go side. Envelope uses `#[serde(rename)]`
//!   to match `v/kind/type/dir/seq/nonce/payload` field names byte-for-byte.
//! - **Q-L6-3**: SERVER side only — no browser TS bindings emitted from
//!   this crate.
//! - **Q-L6-2**: 10K connections per replica is a deployment decision,
//!   not enforced in this contract. Mentioned for SRE awareness only.
//!
//! # ServiceMode parity (cycle 18)
//!
//! `ServiceMode` integer values + wire strings MUST match
//! `contracts/lifecycle::ServiceMode` (cycle 7) + `contracts/ws::ServiceMode`
//! (Go cycle 21 mirror). Re-exported from `crate::lifecycle::ServiceMode`
//! to avoid double-definition; the Go `contracts/ws` package duplicates
//! the enum locally (Go has no module re-export) but with the same values.

use crate::lifecycle::ServiceMode;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::{Duration, SystemTime};

// ── Envelope ────────────────────────────────────────────────────────────

/// Current envelope schema version. Bumping is a cross-language change.
pub const ENVELOPE_VERSION: u8 = 1;

/// control vs data classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageKind {
    /// Protocol/control: ws.ping/pong/refresh/close. Bypasses S2/S3.
    Control,
    /// Application data: chat.*/session.*/presence.*/event.*. S2/S3 enforced.
    Data,
}

/// Direction marker (client→server vs server→client).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Direction {
    #[serde(rename = "c2s")]
    ClientToServer,
    #[serde(rename = "s2c")]
    ServerToClient,
}

/// Wire-shape every WS frame deserializes to.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Envelope {
    /// `v` — envelope schema version; must equal `ENVELOPE_VERSION`.
    #[serde(rename = "v")]
    pub version: u8,

    /// `kind` — control vs data.
    pub kind: MessageKind,

    /// `type` — message-type string.
    #[serde(rename = "type")]
    pub message_type: String,

    /// `dir` — direction.
    #[serde(rename = "dir")]
    pub direction: Direction,

    /// `seq` — per-(connection, type) monotonic counter; required for data.
    #[serde(default, skip_serializing_if = "is_zero_u64")]
    pub seq: u64,

    /// `nonce` — replay-defense nonce; required for data.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub nonce: String,

    /// `payload` — opaque per-type payload.
    #[serde(default, skip_serializing_if = "JsonValue::is_null")]
    pub payload: JsonValue,
}

fn is_zero_u64(n: &u64) -> bool { *n == 0 }

impl Envelope {
    /// Foundation-level shape check. Per-Type validation owned by L6 router.
    pub fn validate(&self) -> Result<(), String> {
        if self.version != ENVELOPE_VERSION {
            return Err(format!("envelope version {} != current {}", self.version, ENVELOPE_VERSION));
        }
        if self.message_type.is_empty() {
            return Err("envelope type empty".into());
        }
        if matches!(self.kind, MessageKind::Data) && self.nonce.is_empty() {
            return Err("data envelope requires nonce (replay defense)".into());
        }
        Ok(())
    }
}

// ── Close codes ─────────────────────────────────────────────────────────

/// Enumerated S12 §12AB.9 close codes (1000 + 4001..4010).
#[repr(u16)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseCode {
    Normal = 1000,
    TokenExpired = 4001,
    TokenRevoked = 4002,
    UserErased = 4003,
    RealityArchived = 4004,
    AdminKick = 4005,
    RateLimitExceeded = 4006,
    OriginMismatch = 4007,
    ConnectionLimitExceeded = 4008,
    FingerprintMismatch = 4009,
    SchemaInvalid = 4010,
}

impl CloseCode {
    /// Canonical short name (matches §12AB.9 + Go `CloseCode::String`).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Normal => "normal_closure",
            Self::TokenExpired => "token_expired",
            Self::TokenRevoked => "token_revoked",
            Self::UserErased => "user_erased",
            Self::RealityArchived => "reality_archived",
            Self::AdminKick => "admin_kick",
            Self::RateLimitExceeded => "rate_limit_exceeded",
            Self::OriginMismatch => "origin_mismatch",
            Self::ConnectionLimitExceeded => "connection_limit_exceeded",
            Self::FingerprintMismatch => "fingerprint_mismatch",
            Self::SchemaInvalid => "schema_invalid",
        }
    }

    /// All 11 enumerated codes in numeric order.
    pub fn all() -> &'static [CloseCode] {
        &[
            Self::Normal,
            Self::TokenExpired,
            Self::TokenRevoked,
            Self::UserErased,
            Self::RealityArchived,
            Self::AdminKick,
            Self::RateLimitExceeded,
            Self::OriginMismatch,
            Self::ConnectionLimitExceeded,
            Self::FingerprintMismatch,
            Self::SchemaInvalid,
        ]
    }

    /// Parse from u16 wire value; returns None for unknown codes.
    pub fn from_u16(n: u16) -> Option<Self> {
        for c in Self::all() {
            if (*c as u16) == n {
                return Some(*c);
            }
        }
        None
    }
}

// ── Ticket ──────────────────────────────────────────────────────────────

/// Canonical V1 TTL (60s, one-shot).
pub const TICKET_TTL: Duration = Duration::from_secs(60);

/// One-shot handshake credential.
#[derive(Debug, Clone)]
pub struct Ticket {
    pub ticket_id: String,
    pub user_ref_id: String,
    pub allowed_realities: Vec<String>,
    pub allowed_scopes: Vec<String>,
    pub origin_hash: [u8; 32],
    pub client_fingerprint_hash: [u8; 32],
    pub issued_at: SystemTime,
    pub expires_at: SystemTime,
}

impl Ticket {
    /// Shape + expiry validation. Mirrors Go `Ticket::Validate`.
    pub fn validate(&self, now: SystemTime) -> Result<(), String> {
        if self.ticket_id.is_empty() {
            return Err("ticket_id empty".into());
        }
        if self.user_ref_id.is_empty() {
            return Err("user_ref_id empty".into());
        }
        if self.origin_hash == [0u8; 32] {
            return Err("origin_hash zero".into());
        }
        if self.client_fingerprint_hash == [0u8; 32] {
            return Err("client_fingerprint_hash zero".into());
        }
        if now >= self.expires_at {
            return Err("ticket expired".into());
        }
        match self.expires_at.duration_since(self.issued_at) {
            Ok(d) if d <= TICKET_TTL * 2 => Ok(()),
            Ok(d) => Err(format!("ticket TTL window too wide: {:?} > {:?}", d, TICKET_TTL * 2)),
            Err(_) => Err("ticket exp < iat (clock skew)".into()),
        }
    }

    pub fn binds_to_origin(&self, origin_hash: &[u8; 32]) -> bool {
        &self.origin_hash == origin_hash
    }
    pub fn binds_to_fingerprint(&self, fp: &[u8; 32]) -> bool {
        &self.client_fingerprint_hash == fp
    }
}

// ── Session ─────────────────────────────────────────────────────────────

/// 15-minute session window (S12 §12AB.3).
pub const SESSION_TTL: Duration = Duration::from_secs(15 * 60);

/// Server-side per-connection state.
///
/// Scope/reality narrowing on `refresh` is enforced via the same `state`
/// mutex (NOT exposed for direct mutation) — `allowed_*` getters return
/// the current intersection. This matches the Go-side narrowing behavior.
#[derive(Debug)]
pub struct WSSession {
    pub connection_id: String,
    pub user_ref_id: String,
    pub origin_hash: [u8; 32],
    pub client_fingerprint: [u8; 32],
    /// Protects [`SessionState`] in full — including `allowed_scopes` +
    /// `allowed_realities` so [`WSSession::refresh`] can narrow them
    /// (refresh must NOT widen — intersection semantics; see method docs).
    state: Mutex<SessionState>,
}

#[derive(Debug, Default)]
struct SessionState {
    allowed_realities: Vec<String>,
    allowed_scopes: Vec<String>,
    subscribed_topics: Vec<String>,
    expires_at: Option<SystemTime>,
    last_refresh_at: Option<SystemTime>,
    seq_counter: HashMap<String, u64>,
    seen_nonces: HashMap<String, SystemTime>,
}

impl WSSession {
    /// Build from a redeemed ticket + new connection_id + wall-clock now.
    pub fn new(t: &Ticket, connection_id: String, now: SystemTime) -> Self {
        Self {
            connection_id,
            user_ref_id: t.user_ref_id.clone(),
            origin_hash: t.origin_hash,
            client_fingerprint: t.client_fingerprint_hash,
            state: Mutex::new(SessionState {
                allowed_realities: t.allowed_realities.clone(),
                allowed_scopes: t.allowed_scopes.clone(),
                expires_at: Some(now + SESSION_TTL),
                ..Default::default()
            }),
        }
    }

    /// Returns the current allowed scope set (post-narrowing). Cloned for
    /// safe concurrent read.
    pub fn allowed_scopes(&self) -> Vec<String> {
        self.state.lock().unwrap().allowed_scopes.clone()
    }

    /// Returns the current allowed reality set (post-narrowing). Cloned.
    pub fn allowed_realities(&self) -> Vec<String> {
        self.state.lock().unwrap().allowed_realities.clone()
    }

    pub fn is_expired(&self, now: SystemTime) -> bool {
        let st = self.state.lock().unwrap();
        match st.expires_at {
            Some(exp) => now >= exp,
            None => true,
        }
    }

    /// Strictly monotonic per-Type seq. Returns `Err` on replay or out-of-order.
    /// Mirrors Go `WSSession::AcceptSeq`.
    pub fn accept_seq(&self, msg_type: &str, incoming: u64) -> Result<(), String> {
        let mut st = self.state.lock().unwrap();
        let last = st.seq_counter.get(msg_type).copied().unwrap_or(0);
        if last == 0 {
            if incoming == 0 {
                return Err(format!("seq=0 reserved for control; type={}", msg_type));
            }
            st.seq_counter.insert(msg_type.to_string(), incoming);
            return Ok(());
        }
        if incoming <= last {
            return Err(format!(
                "seq replay or out-of-order: type={} last={} incoming={}",
                msg_type, last, incoming
            ));
        }
        st.seq_counter.insert(msg_type.to_string(), incoming);
        Ok(())
    }

    /// O(N)-bounded nonce TTL set (60s). `Err` on replay within the window.
    pub fn seen_nonce(&self, nonce: &str, now: SystemTime) -> Result<(), String> {
        if nonce.is_empty() {
            return Err("empty nonce".into());
        }
        let mut st = self.state.lock().unwrap();
        // Sweep expired (>60s old).
        let cutoff = now.checked_sub(Duration::from_secs(60));
        if let Some(cutoff) = cutoff {
            st.seen_nonces.retain(|_, t| *t >= cutoff);
        }
        if st.seen_nonces.contains_key(nonce) {
            return Err(format!("nonce replay: {}", nonce));
        }
        st.seen_nonces.insert(nonce.to_string(), now);
        Ok(())
    }

    /// Adds a subscription. Idempotent; cap at 5 (S12 §12AB.6).
    pub fn subscribe(&self, topic: &str) -> Result<(), String> {
        if topic.is_empty() {
            return Err("empty topic".into());
        }
        let mut st = self.state.lock().unwrap();
        if st.subscribed_topics.iter().any(|t| t == topic) {
            return Ok(());
        }
        if st.subscribed_topics.len() >= 5 {
            return Err("subscription limit exceeded (max 5)".into());
        }
        st.subscribed_topics.push(topic.to_string());
        Ok(())
    }

    /// Returns a clone of the current subscription set (for tests / introspection).
    pub fn subscribed_topics(&self) -> Vec<String> {
        self.state.lock().unwrap().subscribed_topics.clone()
    }

    /// Extends the session TTL via a fresh ticket AND narrows scope/reality
    /// sets to the intersection of (current ∩ refresh) — refresh MUST NOT
    /// widen. Matches Go `WSSession::Refresh` semantics byte-for-byte.
    /// Returns `Err` on fingerprint / origin / user mismatch or on an empty
    /// intersection (signals server-side revoke; gateway should close 4002).
    pub fn refresh(&self, refresh_ticket: &Ticket, now: SystemTime) -> Result<(), String> {
        refresh_ticket.validate(now)?;
        if refresh_ticket.client_fingerprint_hash != self.client_fingerprint {
            return Err("refresh ticket fingerprint mismatch".into());
        }
        if refresh_ticket.origin_hash != self.origin_hash {
            return Err("refresh ticket origin mismatch".into());
        }
        if refresh_ticket.user_ref_id != self.user_ref_id {
            return Err("refresh ticket user mismatch".into());
        }
        let mut st = self.state.lock().unwrap();
        // Intersect scopes/realities (refresh cannot widen).
        let new_scopes = intersect(&st.allowed_scopes, &refresh_ticket.allowed_scopes);
        let new_realities = intersect(&st.allowed_realities, &refresh_ticket.allowed_realities);
        if new_scopes.is_empty() || new_realities.is_empty() {
            return Err("refresh would empty scopes/realities (likely server-side revoke)".into());
        }
        st.allowed_scopes = new_scopes;
        st.allowed_realities = new_realities;
        st.expires_at = Some(now + SESSION_TTL);
        st.last_refresh_at = Some(now);
        Ok(())
    }
}

fn intersect(a: &[String], b: &[String]) -> Vec<String> {
    let set: HashSet<&String> = b.iter().collect();
    a.iter().filter(|x| set.contains(x)).cloned().collect()
}

// ── ServiceMode gate ────────────────────────────────────────────────────

/// Supplies the current [`ServiceMode`] to the gate.
pub trait ServiceModeProvider: Send + Sync {
    fn current_mode(&self) -> ServiceMode;
}

/// Static provider — useful for tests + bootstrap.
pub struct StaticMode(pub ServiceMode);
impl ServiceModeProvider for StaticMode {
    fn current_mode(&self) -> ServiceMode { self.0 }
}

/// Gate result for [`check_service_mode`].
#[derive(Debug, PartialEq, Eq)]
pub enum ModeGate {
    /// Envelope accepted.
    Accept,
    /// Mode rejects all writes (ReadOnly / Offline).
    RejectsWrites,
    /// Mode accepts essential writes only (Essentials + non-essential msg).
    RejectsScope,
}

/// Foundation gate: control envelopes always accepted; data envelopes
/// gated by ServiceMode + (for Essentials) the caller-supplied
/// `is_essential` flag.
///
/// Mirrors Go `ServiceModeGate::Check` semantics.
pub fn check_service_mode(env: &Envelope, mode: ServiceMode, is_essential: bool) -> ModeGate {
    if matches!(env.kind, MessageKind::Control) {
        return ModeGate::Accept;
    }
    if matches!(mode, ServiceMode::Full | ServiceMode::Limited) {
        return ModeGate::Accept;
    }
    if matches!(mode, ServiceMode::Essentials) {
        return if is_essential { ModeGate::Accept } else { ModeGate::RejectsScope };
    }
    // ReadOnly / Offline.
    ModeGate::RejectsWrites
}

// ── Tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn good_ticket(now: SystemTime) -> Ticket {
        Ticket {
            ticket_id: "wst_xxx".into(),
            user_ref_id: "u1".into(),
            allowed_realities: vec!["r1".into()],
            allowed_scopes: vec!["chat".into(), "presence".into()],
            origin_hash: [1u8; 32],
            client_fingerprint_hash: [2u8; 32],
            issued_at: now,
            expires_at: now + TICKET_TTL,
        }
    }

    // ── Envelope ────────────────────────────────────────────────────

    #[test]
    fn envelope_round_trip() {
        let e = Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Data,
            message_type: "chat.message".into(),
            direction: Direction::ClientToServer,
            seq: 42,
            nonce: "n1".into(),
            payload: serde_json::json!({"text":"hello"}),
        };
        let raw = serde_json::to_string(&e).unwrap();
        let got: Envelope = serde_json::from_str(&raw).unwrap();
        assert_eq!(got.version, e.version);
        assert_eq!(got.message_type, e.message_type);
        assert_eq!(got.seq, e.seq);
        assert_eq!(got.nonce, e.nonce);
        assert_eq!(got.payload, e.payload);
    }

    #[test]
    fn envelope_wire_field_names_match_go() {
        // Field names must equal v/kind/type/dir/seq/nonce/payload
        // (Q-L4-1 cross-language wire parity with Go side).
        let e = Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Data,
            message_type: "chat.message".into(),
            direction: Direction::ClientToServer,
            seq: 1,
            nonce: "n".into(),
            payload: serde_json::Value::Null,
        };
        let raw = serde_json::to_value(&e).unwrap();
        let map = raw.as_object().unwrap();
        for key in &["v", "kind", "type", "dir"] {
            assert!(map.contains_key(*key), "wire missing field {}", key);
        }
    }

    #[test]
    fn envelope_data_requires_nonce() {
        let e = Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Data,
            message_type: "chat.message".into(),
            direction: Direction::ClientToServer,
            seq: 1,
            nonce: String::new(),
            payload: serde_json::Value::Null,
        };
        assert!(e.validate().is_err());
    }

    #[test]
    fn envelope_control_no_nonce_ok() {
        let e = Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Control,
            message_type: "ws.ping".into(),
            direction: Direction::ClientToServer,
            seq: 0,
            nonce: String::new(),
            payload: serde_json::Value::Null,
        };
        assert!(e.validate().is_ok());
    }

    #[test]
    fn envelope_version_mismatch_rejected() {
        let mut e = Envelope {
            version: 99,
            kind: MessageKind::Control,
            message_type: "ws.ping".into(),
            direction: Direction::ClientToServer,
            seq: 0,
            nonce: String::new(),
            payload: serde_json::Value::Null,
        };
        assert!(e.validate().is_err());
        e.version = ENVELOPE_VERSION;
        assert!(e.validate().is_ok());
    }

    // ── Close codes ──────────────────────────────────────────────────

    #[test]
    fn close_code_count_eleven() {
        assert_eq!(CloseCode::all().len(), 11);
    }

    #[test]
    fn close_code_roundtrip_u16() {
        for c in CloseCode::all() {
            let n = *c as u16;
            assert_eq!(CloseCode::from_u16(n), Some(*c));
        }
        assert_eq!(CloseCode::from_u16(0), None);
        assert_eq!(CloseCode::from_u16(4011), None);
    }

    #[test]
    fn close_code_strings_match_go() {
        assert_eq!(CloseCode::Normal.as_str(), "normal_closure");
        assert_eq!(CloseCode::TokenExpired.as_str(), "token_expired");
        assert_eq!(CloseCode::SchemaInvalid.as_str(), "schema_invalid");
    }

    // ── Ticket ───────────────────────────────────────────────────────

    #[test]
    fn ticket_validate_happy() {
        let now = SystemTime::now();
        let tk = good_ticket(now);
        assert!(tk.validate(now).is_ok());
    }

    #[test]
    fn ticket_validate_expired() {
        let now = SystemTime::now();
        let tk = good_ticket(now);
        assert!(tk.validate(now + TICKET_TTL * 2).is_err());
    }

    #[test]
    fn ticket_validate_ttl_window_too_wide() {
        let now = SystemTime::now();
        let mut tk = good_ticket(now);
        tk.expires_at = now + TICKET_TTL * 10;
        assert!(tk.validate(now).is_err());
    }

    #[test]
    fn ticket_binding_helpers() {
        let tk = good_ticket(SystemTime::now());
        assert!(tk.binds_to_origin(&tk.origin_hash));
        assert!(!tk.binds_to_origin(&[99u8; 32]));
        assert!(tk.binds_to_fingerprint(&tk.client_fingerprint_hash));
    }

    // ── Session ──────────────────────────────────────────────────────

    #[test]
    fn session_new_sets_ttl() {
        let now = SystemTime::now();
        let tk = good_ticket(now);
        let s = WSSession::new(&tk, "c1".into(), now);
        assert!(!s.is_expired(now));
        assert!(s.is_expired(now + SESSION_TTL));
    }

    #[test]
    fn session_accept_seq_monotonic() {
        let now = SystemTime::now();
        let tk = good_ticket(now);
        let s = WSSession::new(&tk, "c1".into(), now);
        assert!(s.accept_seq("chat.message", 1).is_ok());
        assert!(s.accept_seq("chat.message", 2).is_ok());
        assert!(s.accept_seq("chat.message", 2).is_err()); // replay
        assert!(s.accept_seq("chat.message", 1).is_err()); // out-of-order
        // different type independent
        assert!(s.accept_seq("presence.update", 5).is_ok());
    }

    #[test]
    fn session_accept_seq_zero_reserved() {
        let now = SystemTime::now();
        let s = WSSession::new(&good_ticket(now), "c1".into(), now);
        assert!(s.accept_seq("chat.message", 0).is_err());
    }

    #[test]
    fn session_seen_nonce_replay() {
        let now = SystemTime::now();
        let s = WSSession::new(&good_ticket(now), "c1".into(), now);
        assert!(s.seen_nonce("n1", now).is_ok());
        assert!(s.seen_nonce("n1", now + Duration::from_secs(5)).is_err());
        // After 120s the sweep evicts; same nonce accepted.
        assert!(s.seen_nonce("n1", now + Duration::from_secs(120)).is_ok());
    }

    #[test]
    fn session_subscribe_limit() {
        let now = SystemTime::now();
        let s = WSSession::new(&good_ticket(now), "c1".into(), now);
        for i in 0..5 {
            assert!(s.subscribe(&format!("t{}", i)).is_ok());
        }
        assert!(s.subscribe("t6").is_err());
        assert_eq!(s.subscribed_topics().len(), 5);
    }

    #[test]
    fn session_subscribe_idempotent() {
        let now = SystemTime::now();
        let s = WSSession::new(&good_ticket(now), "c1".into(), now);
        assert!(s.subscribe("topic.a").is_ok());
        assert!(s.subscribe("topic.a").is_ok());
        assert_eq!(s.subscribed_topics().len(), 1);
    }

    #[test]
    fn session_refresh_extends_ttl() {
        let now = SystemTime::now();
        let tk = good_ticket(now);
        let s = WSSession::new(&tk, "c1".into(), now);
        let later = now + Duration::from_secs(600);
        let mut refresh = good_ticket(later);
        refresh.user_ref_id = s.user_ref_id.clone();
        refresh.origin_hash = s.origin_hash;
        refresh.client_fingerprint_hash = s.client_fingerprint;
        refresh.allowed_scopes = s.allowed_scopes();
        refresh.allowed_realities = s.allowed_realities();
        assert!(s.refresh(&refresh, later).is_ok());
        assert!(!s.is_expired(later + Duration::from_secs(60)));
    }

    #[test]
    fn session_refresh_fingerprint_mismatch() {
        let now = SystemTime::now();
        let s = WSSession::new(&good_ticket(now), "c1".into(), now);
        let mut refresh = good_ticket(now);
        refresh.user_ref_id = s.user_ref_id.clone();
        refresh.origin_hash = s.origin_hash;
        refresh.client_fingerprint_hash = [99u8; 32]; // mismatch
        refresh.allowed_scopes = s.allowed_scopes();
        refresh.allowed_realities = s.allowed_realities();
        assert!(s.refresh(&refresh, now).is_err());
    }

    #[test]
    fn session_refresh_rejects_revoke() {
        let now = SystemTime::now();
        let s = WSSession::new(&good_ticket(now), "c1".into(), now);
        let mut refresh = good_ticket(now);
        refresh.user_ref_id = s.user_ref_id.clone();
        refresh.origin_hash = s.origin_hash;
        refresh.client_fingerprint_hash = s.client_fingerprint;
        refresh.allowed_scopes = vec!["nonexistent".into()]; // empty intersect
        refresh.allowed_realities = s.allowed_realities();
        assert!(s.refresh(&refresh, now).is_err());
    }

    #[test]
    fn session_refresh_does_not_widen() {
        // Q-L4-1 parity with Go: refresh that asks for MORE scopes than the
        // session currently has must narrow to the intersection only.
        let now = SystemTime::now();
        let mut tk = good_ticket(now);
        tk.allowed_scopes = vec!["chat".into()];
        tk.allowed_realities = vec!["r1".into()];
        let s = WSSession::new(&tk, "c1".into(), now);
        let mut refresh = good_ticket(now);
        refresh.user_ref_id = s.user_ref_id.clone();
        refresh.origin_hash = s.origin_hash;
        refresh.client_fingerprint_hash = s.client_fingerprint;
        refresh.allowed_scopes = vec!["chat".into(), "events".into()]; // widen attempt
        refresh.allowed_realities = vec!["r1".into()];
        assert!(s.refresh(&refresh, now).is_ok());
        let scopes = s.allowed_scopes();
        assert_eq!(scopes, vec!["chat".to_string()], "refresh must NOT widen scopes");
    }

    // ── ServiceMode gate ─────────────────────────────────────────────

    fn data_env() -> Envelope {
        Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Data,
            message_type: "chat.message".into(),
            direction: Direction::ClientToServer,
            seq: 1,
            nonce: "n".into(),
            payload: serde_json::Value::Null,
        }
    }

    fn ctrl_env() -> Envelope {
        Envelope {
            version: ENVELOPE_VERSION,
            kind: MessageKind::Control,
            message_type: "ws.ping".into(),
            direction: Direction::ClientToServer,
            seq: 0,
            nonce: String::new(),
            payload: serde_json::Value::Null,
        }
    }

    #[test]
    fn mode_gate_control_always_accept() {
        assert_eq!(check_service_mode(&ctrl_env(), ServiceMode::Offline, false), ModeGate::Accept);
    }

    #[test]
    fn mode_gate_full_accepts_data() {
        assert_eq!(check_service_mode(&data_env(), ServiceMode::Full, false), ModeGate::Accept);
    }

    #[test]
    fn mode_gate_readonly_rejects_writes() {
        assert_eq!(check_service_mode(&data_env(), ServiceMode::ReadOnly, false), ModeGate::RejectsWrites);
        assert_eq!(check_service_mode(&data_env(), ServiceMode::Offline, false), ModeGate::RejectsWrites);
    }

    #[test]
    fn mode_gate_essentials_scope_filter() {
        assert_eq!(check_service_mode(&data_env(), ServiceMode::Essentials, false), ModeGate::RejectsScope);
        assert_eq!(check_service_mode(&data_env(), ServiceMode::Essentials, true), ModeGate::Accept);
    }

    // ── Cross-language string parity (close codes + service mode) ────

    #[test]
    fn close_code_string_parity_with_go() {
        // Go side ground truth strings (contracts/ws::CloseCode::String).
        let pairs: &[(CloseCode, &str)] = &[
            (CloseCode::Normal, "normal_closure"),
            (CloseCode::TokenExpired, "token_expired"),
            (CloseCode::TokenRevoked, "token_revoked"),
            (CloseCode::UserErased, "user_erased"),
            (CloseCode::RealityArchived, "reality_archived"),
            (CloseCode::AdminKick, "admin_kick"),
            (CloseCode::RateLimitExceeded, "rate_limit_exceeded"),
            (CloseCode::OriginMismatch, "origin_mismatch"),
            (CloseCode::ConnectionLimitExceeded, "connection_limit_exceeded"),
            (CloseCode::FingerprintMismatch, "fingerprint_mismatch"),
            (CloseCode::SchemaInvalid, "schema_invalid"),
        ];
        for (c, s) in pairs {
            assert_eq!(c.as_str(), *s);
        }
    }
}
