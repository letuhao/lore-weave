//! `supply_chain` — Rust mirror of `contracts/supply_chain/` (cycle 19 / L4.J).
//!
//! Mirrors the Go [`Policy`] + [`Verifier`] surface so Rust services
//! receive the SAME SR10 §12AM supply-chain policy contract.
//!
//! ## Why JSON-only on the Rust side
//!
//! Same architectural pattern as cycles 18 (`dependencies`), 19
//! `observability`/`capacity`: the canonical `policy.yaml` is parsed
//! Go-side; Rust services consume it via JSON dump at bootstrap or
//! programmatic [`Policy::new`] in tests.
//!
//! The Rust side enforces the SAME invariants as Go: per-block
//! validation + the policy-aware verifier short-circuit behavior.

use std::collections::HashSet;

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Package ecosystem id.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Ecosystem {
    Go,
    Rust,
    Python,
    Js,
    Docker,
}

/// One entry under dep_pinning.ecosystems.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EcosystemPolicy {
    pub ecosystem: Ecosystem,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub lockfile: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub lockfile_options: Vec<String>,
    pub required: bool,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub notes: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DepPinning {
    pub ecosystems: Vec<EcosystemPolicy>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SBOMDestination {
    #[serde(rename = "type")]
    pub kind: String, // s3 | local | minio
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub bucket: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub prefix: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SBOM {
    pub format: String,        // cyclonedx | spdx
    pub spec_version: String,  // e.g., "1.5"
    pub emit_per_build: bool,
    pub destination: SBOMDestination,
    pub retention_days: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BannedPackage {
    pub ecosystem: Ecosystem,
    pub name: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub version_glob: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Provenance {
    pub enabled: bool,
    pub signer: String, // cosign | sigstore | gpg
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required_for: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub allow_failure_modes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Policy {
    pub version: u32,
    pub dep_pinning: DepPinning,
    pub sbom: SBOM,
    pub license_allowlist: Vec<String>,
    #[serde(default)]
    pub banned_packages: Vec<BannedPackage>,
    pub provenance: Provenance,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum SupplyChainError {
    #[error("invalid policy: {0}")]
    InvalidPolicy(String),
    #[error("unsupported policy version: {0} (expected 1)")]
    UnsupportedVersion(u32),
    #[error("license not in allowlist: {0}")]
    LicenseNotAllowed(String),
    #[error("package is banned: {0}")]
    PackageBanned(String),
    #[error("artifact signature could not be verified: {0}")]
    SignatureUnverified(String),
    #[error("provenance signer not supported: {0}")]
    ProvenanceUnsupported(String),
}

impl Policy {
    pub fn new(
        version: u32,
        dep_pinning: DepPinning,
        sbom: SBOM,
        license_allowlist: Vec<String>,
        banned_packages: Vec<BannedPackage>,
        provenance: Provenance,
    ) -> Result<Self, SupplyChainError> {
        let p = Policy {
            version,
            dep_pinning,
            sbom,
            license_allowlist,
            banned_packages,
            provenance,
        };
        p.validate()?;
        Ok(p)
    }

    pub fn validate(&self) -> Result<(), SupplyChainError> {
        if self.version != 1 {
            return Err(SupplyChainError::UnsupportedVersion(self.version));
        }
        if self.dep_pinning.ecosystems.is_empty() {
            return Err(SupplyChainError::InvalidPolicy(
                "dep_pinning.ecosystems empty".into(),
            ));
        }
        let mut seen: HashSet<Ecosystem> = HashSet::new();
        for e in &self.dep_pinning.ecosystems {
            if !seen.insert(e.ecosystem) {
                return Err(SupplyChainError::InvalidPolicy(format!(
                    "dep_pinning duplicate ecosystem={:?}",
                    e.ecosystem
                )));
            }
            if e.ecosystem != Ecosystem::Docker
                && e.lockfile.is_empty()
                && e.lockfile_options.is_empty()
            {
                return Err(SupplyChainError::InvalidPolicy(format!(
                    "ecosystem={:?} has no lockfile or lockfile_options",
                    e.ecosystem
                )));
            }
            if !e.lockfile.is_empty() && !e.lockfile_options.is_empty() {
                return Err(SupplyChainError::InvalidPolicy(format!(
                    "ecosystem={:?} has both lockfile and lockfile_options",
                    e.ecosystem
                )));
            }
        }
        match self.sbom.format.as_str() {
            "cyclonedx" | "spdx" => {}
            other => {
                return Err(SupplyChainError::InvalidPolicy(format!(
                    "sbom.format={} must be cyclonedx|spdx",
                    other
                )))
            }
        }
        if self.sbom.spec_version.trim().is_empty() {
            return Err(SupplyChainError::InvalidPolicy(
                "sbom.spec_version empty".into(),
            ));
        }
        if self.sbom.retention_days == 0 {
            return Err(SupplyChainError::InvalidPolicy(
                "sbom.retention_days must be > 0".into(),
            ));
        }
        if self.provenance.enabled {
            match self.provenance.signer.as_str() {
                "cosign" | "sigstore" | "gpg" => {}
                other => {
                    return Err(SupplyChainError::ProvenanceUnsupported(other.to_string()))
                }
            }
        }
        Ok(())
    }

    /// True if SPDX id is in the allowlist (case-sensitive per spec).
    pub fn license_allowed(&self, spdx: &str) -> bool {
        self.license_allowlist.iter().any(|l| l == spdx)
    }

    /// Returns Err(PackageBanned) if (eco,name) is on the banned list.
    pub fn check_package(
        &self,
        eco: Ecosystem,
        name: &str,
        version: &str,
    ) -> Result<(), SupplyChainError> {
        for b in &self.banned_packages {
            if b.ecosystem != eco || b.name != name {
                continue;
            }
            if b.version_glob.is_empty() || b.version_glob == "*" || b.version_glob == version {
                return Err(SupplyChainError::PackageBanned(format!(
                    "{:?}/{}@{} reason={}",
                    eco, name, version, b.reason
                )));
            }
        }
        Ok(())
    }
}

/// SBOM emit row (mirrors Go SBOMEmitRow). Cycle-20+ writes this to the
/// meta DB; cycle-19 ships the type + ring buffer only.
#[derive(Debug, Clone)]
pub struct SBOMEmitRow {
    pub service: String,
    pub build_id: String,
    pub format: String,
    pub spec_version: String,
    pub document_ref: String,
    pub component_count: u32,
    pub occurred_at: i64,
}

pub struct SBOMBuffer {
    inner: std::sync::Mutex<SBOMRingBuffer>,
}

struct SBOMRingBuffer {
    rows: Vec<Option<SBOMEmitRow>>,
    head: usize,
    size: usize,
    dropped: u64,
}

impl SBOMBuffer {
    pub fn new(capacity: usize) -> Self {
        let cap = if capacity == 0 { 256 } else { capacity };
        SBOMBuffer {
            inner: std::sync::Mutex::new(SBOMRingBuffer {
                rows: vec![None; cap],
                head: 0,
                size: 0,
                dropped: 0,
            }),
        }
    }

    pub fn write(&self, row: SBOMEmitRow) {
        let mut g = self.inner.lock().expect("SBOMBuffer poisoned");
        let cap = g.rows.len();
        if g.size == cap {
            g.head = (g.head + 1) % cap;
            g.dropped += 1;
        } else {
            g.size += 1;
        }
        let tail = (g.head + g.size - 1) % cap;
        g.rows[tail] = Some(row);
    }

    pub fn drain(&self) -> Vec<SBOMEmitRow> {
        let mut g = self.inner.lock().expect("SBOMBuffer poisoned");
        let cap = g.rows.len();
        if g.size == 0 {
            return vec![];
        }
        let mut out = Vec::with_capacity(g.size);
        for i in 0..g.size {
            let idx = (g.head + i) % cap;
            if let Some(r) = g.rows[idx].take() {
                out.push(r);
            }
        }
        g.head = 0;
        g.size = 0;
        out
    }

    pub fn dropped_count(&self) -> u64 {
        self.inner.lock().expect("SBOMBuffer poisoned").dropped
    }

    pub fn size(&self) -> usize {
        self.inner.lock().expect("SBOMBuffer poisoned").size
    }
}

/// Runtime provenance verifier surface. Cycle 19 ships interface +
/// noop + policy-aware shim. cycle 21+ wires real cosign/sigstore.
pub trait Verifier: Send + Sync {
    fn verify(&self, artifact_ref: &str, signature_ref: &str) -> Result<VerifyResult, SupplyChainError>;
}

#[derive(Debug, Clone)]
pub struct VerifyResult {
    pub verified: bool,
    pub signer: String,
    pub signer_identity: String,
    pub notes: String,
}

pub struct NoopVerifier;

impl Verifier for NoopVerifier {
    fn verify(&self, artifact_ref: &str, _: &str) -> Result<VerifyResult, SupplyChainError> {
        Err(SupplyChainError::SignatureUnverified(format!(
            "NoopVerifier: {} unverified",
            artifact_ref
        )))
    }
}

pub struct PolicyAwareVerifier {
    pub policy: Policy,
    pub delegate: Option<Box<dyn Verifier>>,
}

impl Verifier for PolicyAwareVerifier {
    fn verify(&self, artifact_ref: &str, signature_ref: &str) -> Result<VerifyResult, SupplyChainError> {
        if !self.policy.provenance.enabled {
            return Ok(VerifyResult {
                verified: true,
                signer: self.policy.provenance.signer.clone(),
                signer_identity: String::new(),
                notes: "provenance disabled by policy (V1 adoption window)".into(),
            });
        }
        match self.delegate.as_ref() {
            Some(d) => d.verify(artifact_ref, signature_ref),
            None => Err(SupplyChainError::SignatureUnverified(
                "policy requires verification but no delegate wired".into(),
            )),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mk_policy() -> Policy {
        Policy {
            version: 1,
            dep_pinning: DepPinning {
                ecosystems: vec![EcosystemPolicy {
                    ecosystem: Ecosystem::Go,
                    lockfile: "go.sum".into(),
                    lockfile_options: vec![],
                    required: true,
                    notes: String::new(),
                }],
            },
            sbom: SBOM {
                format: "cyclonedx".into(),
                spec_version: "1.5".into(),
                emit_per_build: true,
                destination: SBOMDestination { kind: "s3".into(), bucket: "lw".into(), prefix: "x".into(), path: String::new() },
                retention_days: 30,
            },
            license_allowlist: vec!["MIT".into(), "Apache-2.0".into()],
            banned_packages: vec![],
            provenance: Provenance { enabled: false, signer: "cosign".into(), required_for: vec![], allow_failure_modes: vec![] },
        }
    }

    #[test]
    fn policy_validate_accepts_canonical() {
        assert!(mk_policy().validate().is_ok());
    }

    #[test]
    fn policy_rejects_unsupported_version() {
        let mut p = mk_policy();
        p.version = 99;
        assert!(matches!(p.validate(), Err(SupplyChainError::UnsupportedVersion(99))));
    }

    #[test]
    fn policy_rejects_dup_ecosystem() {
        let mut p = mk_policy();
        p.dep_pinning.ecosystems.push(p.dep_pinning.ecosystems[0].clone());
        assert!(matches!(p.validate(), Err(SupplyChainError::InvalidPolicy(_))));
    }

    #[test]
    fn policy_rejects_both_lockfile_and_options() {
        let mut p = mk_policy();
        p.dep_pinning.ecosystems[0].lockfile_options = vec!["alt".into()];
        assert!(matches!(p.validate(), Err(SupplyChainError::InvalidPolicy(_))));
    }

    #[test]
    fn policy_rejects_bad_provenance_signer() {
        let mut p = mk_policy();
        p.provenance.enabled = true;
        p.provenance.signer = "yoloware".into();
        assert!(matches!(p.validate(), Err(SupplyChainError::ProvenanceUnsupported(_))));
    }

    #[test]
    fn license_allowlist_check() {
        let p = mk_policy();
        assert!(p.license_allowed("MIT"));
        assert!(!p.license_allowed("GPL-3.0-only"));
    }

    #[test]
    fn check_package_banned() {
        let mut p = mk_policy();
        p.banned_packages.push(BannedPackage {
            ecosystem: Ecosystem::Rust,
            name: "evil-crate".into(),
            version_glob: "*".into(),
            reason: "test".into(),
        });
        assert!(matches!(
            p.check_package(Ecosystem::Rust, "evil-crate", "0.1.0"),
            Err(SupplyChainError::PackageBanned(_))
        ));
        assert!(p.check_package(Ecosystem::Go, "evil-crate", "0.1.0").is_ok());
        assert!(p.check_package(Ecosystem::Rust, "ok-crate", "0.1.0").is_ok());
    }

    #[test]
    fn sbom_buffer_evicts_oldest() {
        let b = SBOMBuffer::new(2);
        for id in ["b1", "b2", "b3"] {
            b.write(SBOMEmitRow {
                service: "s".into(),
                build_id: id.into(),
                format: "cyclonedx".into(),
                spec_version: "1.5".into(),
                document_ref: "x".into(),
                component_count: 1,
                occurred_at: 0,
            });
        }
        let rows = b.drain();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].build_id, "b2");
        assert_eq!(rows[1].build_id, "b3");
        assert_eq!(b.dropped_count(), 1);
    }

    #[test]
    fn noop_verifier_always_unverified() {
        let v = NoopVerifier;
        assert!(matches!(v.verify("s3://x/y", ""), Err(SupplyChainError::SignatureUnverified(_))));
    }

    #[test]
    fn policy_aware_short_circuits_when_disabled() {
        let v = PolicyAwareVerifier { policy: mk_policy(), delegate: None };
        let r = v.verify("s3://x/y", "").expect("ok when disabled");
        assert!(r.verified);
    }

    #[test]
    fn policy_aware_fails_closed_when_no_delegate() {
        let mut p = mk_policy();
        p.provenance.enabled = true;
        let v = PolicyAwareVerifier { policy: p, delegate: None };
        assert!(matches!(v.verify("s3://x/y", ""), Err(SupplyChainError::SignatureUnverified(_))));
    }

    struct AcceptAll;
    impl Verifier for AcceptAll {
        fn verify(&self, _: &str, _: &str) -> Result<VerifyResult, SupplyChainError> {
            Ok(VerifyResult {
                verified: true,
                signer: "cosign".into(),
                signer_identity: "ci@loreweave.dev".into(),
                notes: "ok".into(),
            })
        }
    }

    #[test]
    fn policy_aware_delegates_when_enabled() {
        let mut p = mk_policy();
        p.provenance.enabled = true;
        let v = PolicyAwareVerifier { policy: p, delegate: Some(Box::new(AcceptAll)) };
        let r = v.verify("s3://x/y", "sig").expect("ok");
        assert!(r.verified);
        assert!(!r.signer_identity.is_empty());
    }
}
