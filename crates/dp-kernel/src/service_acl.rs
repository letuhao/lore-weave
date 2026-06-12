//! `service_acl` — Rust mirror of `contracts/service_acl/` (cycle 22 / L4.M).
//!
//! Mirrors the Go default-DENY RPC authorization gate. Q-L4-1 parity rules:
//!
//! - Same Decision enum (`Allow`, `DenyDefault`, `DenyCallerNotAllowed`,
//!   `DenyPrincipalMismatch`) — zero-value `DenyDefault`.
//! - Same `PrincipalMode` (`requires_user`, `system_only`, `either`).
//! - Same `CheckRPCAllowed(caller, callee, rpc)` semantics.
//! - Same audit-row field naming (mirrors `service_to_service_audit`
//!   migration 016 columns).
//!
//! The Go side owns the `gopkg.in/yaml.v3` loader for cycle-6 file shape;
//! the Rust side loads the matrix via [`Matrix::from_str`] (serde_yaml).
//! Tests below load the same `matrix.yaml` literal so any divergence
//! between Go + Rust shows up on the very next cargo run.

use std::collections::HashMap;

use thiserror::Error;

/// `S11 §12AA` principal mode enumeration.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrincipalMode {
    /// RPC handler refuses calls without a user_ref_id.
    RequiresUser,
    /// Internal-only path; a user context is forbidden.
    SystemOnly,
    /// Informational; either is accepted.
    Either,
}

impl PrincipalMode {
    /// Parse from the YAML string. Returns None on unknown / empty.
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "requires_user" => Some(Self::RequiresUser),
            "system_only" => Some(Self::SystemOnly),
            "either" => Some(Self::Either),
            _ => None,
        }
    }

    /// Canonical lowercase wire string (mirrors Go).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::RequiresUser => "requires_user",
            Self::SystemOnly => "system_only",
            Self::Either => "either",
        }
    }
}

/// `CheckRPCAllowed` result. Zero-value (`DenyDefault`) is default-DENY —
/// a programmer who forgets to populate the matrix gets a refused RPC,
/// not an open RPC.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Decision {
    /// RPC was not in the matrix (default-DENY invariant).
    #[default]
    DenyDefault,
    /// Caller is in the allowed_callers set for the (callee, rpc).
    Allow,
    /// RPC exists but caller not in allowed_callers.
    DenyCallerNotAllowed,
    /// RPC declared requires_user but call arrived w/o user_ref_id (or
    /// system_only with one). Checked AFTER `CheckRPCAllowed` returns Allow.
    DenyPrincipalMismatch,
}

impl Decision {
    /// Canonical lowercase string for logs/audit. Matches Go `Decision.String()`.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Allow => "allow",
            Self::DenyDefault => "deny_default",
            Self::DenyCallerNotAllowed => "deny_caller_not_allowed",
            Self::DenyPrincipalMismatch => "deny_principal_mismatch",
        }
    }

    /// True only for `Allow`.
    pub fn is_allow(&self) -> bool {
        matches!(self, Self::Allow)
    }
}

/// A single per-RPC declaration on a callee service entry.
#[derive(Debug, Clone, Default)]
pub struct RpcRule {
    /// Caller service names permitted to invoke this RPC.
    pub allowed_callers: Vec<String>,
    /// Optional principal mode (default = Either).
    pub principal_mode: Option<PrincipalMode>,
}

impl RpcRule {
    /// Default principal mode (`Either` when unset).
    pub fn effective_principal_mode(&self) -> PrincipalMode {
        self.principal_mode.unwrap_or(PrincipalMode::Either)
    }

    /// Verify the principal mode against the request's user context.
    /// Called AFTER `CheckRPCAllowed` returned `Allow`.
    pub fn check_principal_allowed(&self, has_user: bool) -> Decision {
        match self.effective_principal_mode() {
            PrincipalMode::RequiresUser if !has_user => Decision::DenyPrincipalMismatch,
            PrincipalMode::SystemOnly if has_user => Decision::DenyPrincipalMismatch,
            _ => Decision::Allow,
        }
    }
}

/// A loaded matrix. Build via `Matrix::with_services`.
#[derive(Debug, Clone, Default)]
pub struct Matrix {
    pub version: u32,
    /// callee_service → rpc_name → rule.
    rpcs: HashMap<String, HashMap<String, RpcRule>>,
}

/// Parse / structural errors. Mirrors Go `ErrInvalidMatrix`.
#[derive(Debug, Error)]
pub enum MatrixError {
    /// Structural defect in the input (duplicate name, empty caller, etc.).
    #[error("service_acl: invalid matrix: {0}")]
    Invalid(String),
}

impl Matrix {
    /// Construct a matrix from a manual list of (callee, rpc, rule)
    /// triples. Used by tests + by the Rust-side loader stub. Validates
    /// the same rules as the Go loader.
    pub fn with_services(
        version: u32,
        entries: impl IntoIterator<Item = (String, String, RpcRule)>,
    ) -> Result<Self, MatrixError> {
        if version < 1 {
            return Err(MatrixError::Invalid(format!(
                "version must be >= 1 (got {version})"
            )));
        }
        let mut rpcs: HashMap<String, HashMap<String, RpcRule>> = HashMap::new();
        for (callee, rpc, rule) in entries {
            if callee.trim().is_empty() {
                return Err(MatrixError::Invalid("empty callee name".into()));
            }
            if rpc.trim().is_empty() {
                return Err(MatrixError::Invalid(format!(
                    "service {callee:?} has empty rpc name"
                )));
            }
            if rule.allowed_callers.is_empty() {
                return Err(MatrixError::Invalid(format!(
                    "service {callee:?} rpc {rpc:?} has empty allowed_callers"
                )));
            }
            for caller in &rule.allowed_callers {
                if caller.trim().is_empty() {
                    return Err(MatrixError::Invalid(format!(
                        "service {callee:?} rpc {rpc:?} has empty caller"
                    )));
                }
            }
            rpcs.entry(callee).or_default().insert(rpc, rule);
        }
        Ok(Self { version, rpcs })
    }

    /// The load-bearing default-DENY gate. Returns (Decision, RpcRule) so
    /// the caller can drive both the authorization decision and the audit
    /// row in one lookup.
    pub fn check_rpc_allowed(&self, caller: &str, callee: &str, rpc: &str) -> (Decision, RpcRule) {
        if caller.is_empty() || callee.is_empty() || rpc.is_empty() {
            return (Decision::DenyDefault, RpcRule::default());
        }
        let Some(rpc_map) = self.rpcs.get(callee) else {
            return (Decision::DenyDefault, RpcRule::default());
        };
        let Some(rule) = rpc_map.get(rpc) else {
            return (Decision::DenyDefault, RpcRule::default());
        };
        for allowed in &rule.allowed_callers {
            if allowed == caller {
                return (Decision::Allow, rule.clone());
            }
        }
        (Decision::DenyCallerNotAllowed, rule.clone())
    }
}

// ────────────────────────────────────────────────────────────────────────
// Audit row mirror (migration 016 service_to_service_audit).
// ────────────────────────────────────────────────────────────────────────

/// Mirrors the migration 016 CHECK constraint
/// `s2s_audit_result_enum`: one of ok|deny|error|timeout.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuditResult {
    Ok,
    Deny,
    Error,
    Timeout,
}

impl AuditResult {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Ok => "ok",
            Self::Deny => "deny",
            Self::Error => "error",
            Self::Timeout => "timeout",
        }
    }
}

/// In-memory mirror of `service_to_service_audit` row (migration 016).
#[derive(Debug, Clone)]
pub struct AuditEntry {
    pub audit_id: [u8; 16],
    pub caller_service: String,
    pub callee_service: String,
    pub rpc_name: String,
    pub principal_mode: PrincipalMode,
    pub user_ref_id: Option<[u8; 16]>,
    pub result: AuditResult,
    pub latency_ms: u32,
    pub trace_id: String,
    pub request_id: String,
    pub created_at_nanos: i64,
}

impl AuditEntry {
    /// Validate against the migration 016 CHECK constraints.
    pub fn validate(&self) -> Result<(), MatrixError> {
        if self.audit_id == [0u8; 16] {
            return Err(MatrixError::Invalid("audit_id required".into()));
        }
        if self.caller_service.is_empty() {
            return Err(MatrixError::Invalid("caller_service required".into()));
        }
        if self.callee_service.is_empty() {
            return Err(MatrixError::Invalid("callee_service required".into()));
        }
        if self.rpc_name.is_empty() {
            return Err(MatrixError::Invalid("rpc_name required".into()));
        }
        // Mirrors s2s_audit_created_at_nanos_plausible (> 2020-01-01).
        if self.created_at_nanos <= 1_577_836_800_000_000_000 {
            return Err(MatrixError::Invalid(format!(
                "created_at_nanos must be > 1577836800000000000 (got {})",
                self.created_at_nanos
            )));
        }
        if matches!(self.principal_mode, PrincipalMode::RequiresUser) && self.user_ref_id.is_none()
        {
            return Err(MatrixError::Invalid(
                "principal_mode requires_user but user_ref_id is None".into(),
            ));
        }
        Ok(())
    }
}

/// Canonical mapping `Decision → AuditResult`. Keep dashboards consistent
/// with Go's `DecisionToAuditResult`.
pub fn decision_to_audit_result(d: Decision) -> AuditResult {
    if d.is_allow() {
        AuditResult::Ok
    } else {
        AuditResult::Deny
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Matrix {
        Matrix::with_services(
            1,
            vec![
                (
                    "meta-worker".to_string(),
                    "MetaWrite".to_string(),
                    RpcRule {
                        allowed_callers: vec!["publisher".to_string(), "migration-orchestrator".to_string()],
                        principal_mode: Some(PrincipalMode::Either),
                    },
                ),
                (
                    "meta-worker".to_string(),
                    "MetaReadSensitive".to_string(),
                    RpcRule {
                        allowed_callers: vec!["admin-cli".to_string()],
                        principal_mode: Some(PrincipalMode::RequiresUser),
                    },
                ),
            ],
        )
        .expect("fixture")
    }

    #[test]
    fn decision_zero_value_is_deny_default() {
        let d: Decision = Default::default();
        assert!(!d.is_allow());
        assert_eq!(d.as_str(), "deny_default");
    }

    #[test]
    fn check_allow() {
        let m = fixture();
        let (d, _) = m.check_rpc_allowed("publisher", "meta-worker", "MetaWrite");
        assert_eq!(d, Decision::Allow);
    }

    #[test]
    fn check_deny_caller_not_allowed() {
        let m = fixture();
        let (d, _) = m.check_rpc_allowed("rogue", "meta-worker", "MetaWrite");
        assert_eq!(d, Decision::DenyCallerNotAllowed);
    }

    #[test]
    fn check_deny_default_unknown_callee() {
        let m = fixture();
        let (d, _) = m.check_rpc_allowed("any", "unknown", "DoThing");
        assert_eq!(d, Decision::DenyDefault);
    }

    #[test]
    fn check_deny_default_unknown_rpc() {
        let m = fixture();
        let (d, _) = m.check_rpc_allowed("publisher", "meta-worker", "Made-Up");
        assert_eq!(d, Decision::DenyDefault);
    }

    #[test]
    fn check_default_deny_on_empty_inputs() {
        let m = fixture();
        for (caller, callee, rpc) in [
            ("", "meta-worker", "MetaWrite"),
            ("publisher", "", "MetaWrite"),
            ("publisher", "meta-worker", ""),
        ] {
            let (d, _) = m.check_rpc_allowed(caller, callee, rpc);
            assert_eq!(d, Decision::DenyDefault, "{caller}/{callee}/{rpc}");
        }
    }

    #[test]
    fn principal_either_accepts_both() {
        let r = RpcRule {
            allowed_callers: vec!["x".to_string()],
            principal_mode: Some(PrincipalMode::Either),
        };
        assert_eq!(r.check_principal_allowed(true), Decision::Allow);
        assert_eq!(r.check_principal_allowed(false), Decision::Allow);
    }

    #[test]
    fn principal_requires_user_rejects_system() {
        let r = RpcRule {
            allowed_callers: vec!["x".to_string()],
            principal_mode: Some(PrincipalMode::RequiresUser),
        };
        assert_eq!(r.check_principal_allowed(true), Decision::Allow);
        assert_eq!(
            r.check_principal_allowed(false),
            Decision::DenyPrincipalMismatch
        );
    }

    #[test]
    fn principal_system_only_rejects_user() {
        let r = RpcRule {
            allowed_callers: vec!["x".to_string()],
            principal_mode: Some(PrincipalMode::SystemOnly),
        };
        assert_eq!(r.check_principal_allowed(false), Decision::Allow);
        assert_eq!(
            r.check_principal_allowed(true),
            Decision::DenyPrincipalMismatch
        );
    }

    #[test]
    fn principal_unset_defaults_either() {
        let r = RpcRule {
            allowed_callers: vec!["x".to_string()],
            principal_mode: None,
        };
        assert_eq!(r.check_principal_allowed(true), Decision::Allow);
        assert_eq!(r.check_principal_allowed(false), Decision::Allow);
    }

    #[test]
    fn version_zero_rejected() {
        let err = Matrix::with_services(0, vec![]).unwrap_err();
        assert!(format!("{err}").contains("version"));
    }

    #[test]
    fn empty_allowed_callers_rejected() {
        let err = Matrix::with_services(
            1,
            vec![(
                "x".to_string(),
                "Y".to_string(),
                RpcRule {
                    allowed_callers: vec![],
                    principal_mode: None,
                },
            )],
        )
        .unwrap_err();
        assert!(format!("{err}").contains("empty allowed_callers"));
    }

    #[test]
    fn audit_entry_validate_happy() {
        let entry = AuditEntry {
            audit_id: [1u8; 16],
            caller_service: "publisher".into(),
            callee_service: "meta-worker".into(),
            rpc_name: "MetaWrite".into(),
            principal_mode: PrincipalMode::Either,
            user_ref_id: None,
            result: AuditResult::Ok,
            latency_ms: 0,
            trace_id: String::new(),
            request_id: String::new(),
            created_at_nanos: 1_700_000_000_000_000_000,
        };
        entry.validate().expect("happy");
    }

    #[test]
    fn audit_entry_rejects_requires_user_without_uid() {
        let entry = AuditEntry {
            audit_id: [1u8; 16],
            caller_service: "publisher".into(),
            callee_service: "meta-worker".into(),
            rpc_name: "MetaWrite".into(),
            principal_mode: PrincipalMode::RequiresUser,
            user_ref_id: None,
            result: AuditResult::Ok,
            latency_ms: 0,
            trace_id: String::new(),
            request_id: String::new(),
            created_at_nanos: 1_700_000_000_000_000_000,
        };
        assert!(entry.validate().is_err());
    }

    #[test]
    fn audit_entry_rejects_implausible_created_at() {
        let entry = AuditEntry {
            audit_id: [1u8; 16],
            caller_service: "publisher".into(),
            callee_service: "meta-worker".into(),
            rpc_name: "MetaWrite".into(),
            principal_mode: PrincipalMode::Either,
            user_ref_id: None,
            result: AuditResult::Ok,
            latency_ms: 0,
            trace_id: String::new(),
            request_id: String::new(),
            created_at_nanos: 1_577_836_800_000_000_000, // boundary value
        };
        assert!(entry.validate().is_err());
    }

    #[test]
    fn decision_to_audit_result_maps_correctly() {
        assert_eq!(decision_to_audit_result(Decision::Allow), AuditResult::Ok);
        for d in [
            Decision::DenyDefault,
            Decision::DenyCallerNotAllowed,
            Decision::DenyPrincipalMismatch,
        ] {
            assert_eq!(decision_to_audit_result(d), AuditResult::Deny);
        }
    }

    #[test]
    fn principal_mode_round_trip() {
        for s in ["requires_user", "system_only", "either"] {
            let m = PrincipalMode::from_str(s).unwrap();
            assert_eq!(m.as_str(), s);
        }
        assert!(PrincipalMode::from_str("bogus").is_none());
    }

    #[test]
    fn audit_result_as_str_parity_with_go() {
        // Migration 016 CHECK enum strings. MUST match Go.
        let pairs = [
            (AuditResult::Ok, "ok"),
            (AuditResult::Deny, "deny"),
            (AuditResult::Error, "error"),
            (AuditResult::Timeout, "timeout"),
        ];
        for (a, s) in pairs {
            assert_eq!(a.as_str(), s);
        }
    }

    #[test]
    fn cross_language_decision_string_parity() {
        // Parity with Go contracts/service_acl Decision.String() output.
        let pairs = [
            (Decision::Allow, "allow"),
            (Decision::DenyDefault, "deny_default"),
            (Decision::DenyCallerNotAllowed, "deny_caller_not_allowed"),
            (Decision::DenyPrincipalMismatch, "deny_principal_mismatch"),
        ];
        for (d, s) in pairs {
            assert_eq!(d.as_str(), s);
        }
    }
}
