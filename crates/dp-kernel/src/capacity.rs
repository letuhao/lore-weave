//! `capacity` — Rust mirror of `contracts/capacity/` (cycle 19 / L4.I).
//!
//! Mirrors the Go [`Budgets`] + [`Admission`] so Rust services receive
//! the SAME SR08 §12AK capacity admission contract.
//!
//! ## Why JSON-only on the Rust side
//!
//! Same architectural pattern as cycles 18 (`dependencies`) and 19
//! (`observability`): the canonical `budgets.yaml` file is parsed Go-side;
//! Rust services consume it via JSON dump at bootstrap or programmatic
//! [`Budgets::new`] in tests.
//!
//! Either way, the Rust side enforces the SAME invariants as Go:
//! per-entry validation + duplicate detection + admission behavior.
//!
//! ## Parity with Go
//!
//! Field names + enum wire strings match the Go YAML schema 1-for-1.
//! `Service::validate` returns the same categories of errors as Go
//! `Service.Validate`.

use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::RwLock;

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Autoscaling-strategy classifier (R04 §12D.6 + SR08).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Class {
    Web,
    LlmGateway,
    Worker,
    Cron,
    Library,
}

/// One (v1|v3) capacity-plan tier.
///
/// `cpu_per_replica`, `memory_per_replica`, `scale_trigger` are
/// `Option` because the v3 tier may inherit them from v1.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tier {
    pub min_replicas: i32,
    pub max_replicas: i32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cpu_per_replica: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub memory_per_replica: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scale_trigger: Option<String>,
}

/// One entry under `services:` in budgets.yaml.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Service {
    pub name: String,
    pub class: Class,
    pub v1: Tier,
    pub v3: Tier,
}

/// Top-level budgets shape.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Budgets {
    pub version: u32,
    pub services: Vec<Service>,
}

/// Errors.
#[derive(Debug, Error, PartialEq, Eq)]
pub enum CapacityError {
    #[error("invalid service: {0}")]
    InvalidService(String),
    #[error("unsupported budgets version: {0} (expected 1)")]
    UnsupportedVersion(u32),
    #[error("duplicate service name: {0}")]
    DuplicateService(String),
    #[error("service not in budgets.yaml: {0}")]
    UnregisteredService(String),
    #[error("unknown tier: {0}")]
    UnknownTier(String),
}

fn is_kebab_lowercase(n: &str) -> bool {
    if n.is_empty() {
        return false;
    }
    let mut it = n.chars();
    let Some(first) = it.next() else { return false };
    if !first.is_ascii_lowercase() {
        return false;
    }
    let rest: Vec<char> = it.collect();
    if rest.is_empty() {
        return true;
    }
    // No trailing '-'
    if rest.last() == Some(&'-') {
        return false;
    }
    rest.iter()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == '-')
}

fn is_valid_memory_suffix(s: &str) -> bool {
    // ^[1-9][0-9]*(Mi|Gi|Ti|M|G|T|K|Ki)?$
    if s.is_empty() {
        return false;
    }
    let bytes = s.as_bytes();
    if !(bytes[0] as char).is_ascii_digit() || bytes[0] == b'0' {
        return false;
    }
    // Strip trailing suffix
    let suffixes = ["Mi", "Gi", "Ti", "Ki", "M", "G", "T", "K"];
    let mut digits_end = s.len();
    for sfx in &suffixes {
        if s.ends_with(sfx) {
            digits_end = s.len() - sfx.len();
            break;
        }
    }
    if digits_end == 0 {
        return false;
    }
    s[..digits_end].chars().all(|c| c.is_ascii_digit())
}

impl Service {
    pub fn validate(&self) -> Result<(), CapacityError> {
        if self.name.trim().is_empty() {
            return Err(CapacityError::InvalidService("name empty".into()));
        }
        if !is_kebab_lowercase(&self.name) {
            return Err(CapacityError::InvalidService(format!(
                "name={} must be lowercase kebab-case",
                self.name
            )));
        }
        if matches!(self.class, Class::Library) {
            return Ok(());
        }
        self.v1.validate_full("v1", &self.name)?;
        self.v3.validate_sparse("v3", &self.name)?;
        Ok(())
    }
}

impl Tier {
    /// v1 tier — all fields required.
    pub fn validate_full(&self, tier: &str, svc: &str) -> Result<(), CapacityError> {
        if self.min_replicas < 0 {
            return Err(CapacityError::InvalidService(format!(
                "name={} {}.min_replicas={} must be >= 0",
                svc, tier, self.min_replicas
            )));
        }
        if self.max_replicas <= 0 {
            return Err(CapacityError::InvalidService(format!(
                "name={} {}.max_replicas={} must be > 0",
                svc, tier, self.max_replicas
            )));
        }
        if self.max_replicas < self.min_replicas {
            return Err(CapacityError::InvalidService(format!(
                "name={} {}.max_replicas={} < min_replicas={}",
                svc, tier, self.max_replicas, self.min_replicas
            )));
        }
        match self.cpu_per_replica {
            Some(c) if c > 0.0 => {}
            _ => {
                return Err(CapacityError::InvalidService(format!(
                    "name={} {}.cpu_per_replica must be > 0",
                    svc, tier
                )))
            }
        }
        match &self.memory_per_replica {
            Some(m) if is_valid_memory_suffix(m) => {}
            _ => {
                return Err(CapacityError::InvalidService(format!(
                    "name={} {}.memory_per_replica invalid (e.g., 512Mi, 2Gi)",
                    svc, tier
                )))
            }
        }
        match &self.scale_trigger {
            Some(s) if !s.trim().is_empty() => Ok(()),
            _ => Err(CapacityError::InvalidService(format!(
                "name={} {}.scale_trigger empty (use 'none' for cron)",
                svc, tier
            ))),
        }
    }

    /// v3 tier — only min/max required (other fields inherit v1).
    pub fn validate_sparse(&self, tier: &str, svc: &str) -> Result<(), CapacityError> {
        if self.min_replicas < 0 {
            return Err(CapacityError::InvalidService(format!(
                "name={} {}.min_replicas={} must be >= 0",
                svc, tier, self.min_replicas
            )));
        }
        if self.max_replicas <= 0 {
            return Err(CapacityError::InvalidService(format!(
                "name={} {}.max_replicas={} must be > 0",
                svc, tier, self.max_replicas
            )));
        }
        if self.max_replicas < self.min_replicas {
            return Err(CapacityError::InvalidService(format!(
                "name={} {}.max_replicas={} < min_replicas={}",
                svc, tier, self.max_replicas, self.min_replicas
            )));
        }
        Ok(())
    }
}

impl Budgets {
    pub fn new(version: u32, services: Vec<Service>) -> Result<Self, CapacityError> {
        let b = Budgets { version, services };
        b.validate()?;
        Ok(b)
    }

    pub fn validate(&self) -> Result<(), CapacityError> {
        if self.version != 1 {
            return Err(CapacityError::UnsupportedVersion(self.version));
        }
        let mut seen = HashSet::new();
        for s in &self.services {
            s.validate()?;
            if !seen.insert(&s.name) {
                return Err(CapacityError::DuplicateService(s.name.clone()));
            }
        }
        Ok(())
    }

    pub fn find(&self, name: &str) -> Option<&Service> {
        self.services.iter().find(|s| s.name == name)
    }
}

/// Runtime admission gate.
pub struct Admission {
    lookup: HashMap<String, Service>,
    registered: RwLock<HashSet<String>>,
    checks: AtomicU64,
    rejections: AtomicU64,
}

impl Admission {
    pub fn new(b: &Budgets) -> Self {
        Admission {
            lookup: b.services.iter().map(|s| (s.name.clone(), s.clone())).collect(),
            registered: RwLock::new(HashSet::new()),
            checks: AtomicU64::new(0),
            rejections: AtomicU64::new(0),
        }
    }

    pub fn register_service(&self, name: &str) -> Result<Service, CapacityError> {
        self.checks.fetch_add(1, Ordering::Relaxed);
        match self.lookup.get(name) {
            Some(s) => {
                self.registered
                    .write()
                    .expect("Admission registered poisoned")
                    .insert(name.to_string());
                Ok(s.clone())
            }
            None => {
                self.rejections.fetch_add(1, Ordering::Relaxed);
                Err(CapacityError::UnregisteredService(name.to_string()))
            }
        }
    }

    pub fn is_registered(&self, name: &str) -> bool {
        self.registered
            .read()
            .expect("Admission registered poisoned")
            .contains(name)
    }

    /// Remaining replica headroom = max - current. 0 if over-capacity.
    pub fn remaining_budget(
        &self,
        name: &str,
        tier: &str,
        current_replicas: i32,
    ) -> Result<i32, CapacityError> {
        let s = self
            .lookup
            .get(name)
            .ok_or_else(|| CapacityError::UnregisteredService(name.to_string()))?;
        let max_r = match tier {
            "v1" => s.v1.max_replicas,
            "v3" => s.v3.max_replicas,
            _ => return Err(CapacityError::UnknownTier(tier.to_string())),
        };
        Ok((max_r - current_replicas).max(0))
    }

    pub fn stats(&self) -> (u64, u64) {
        (self.checks.load(Ordering::Relaxed), self.rejections.load(Ordering::Relaxed))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn svc(name: &str) -> Service {
        Service {
            name: name.into(),
            class: Class::Web,
            v1: Tier {
                min_replicas: 1,
                max_replicas: 4,
                cpu_per_replica: Some(0.5),
                memory_per_replica: Some("512Mi".into()),
                scale_trigger: Some("rps>10".into()),
            },
            v3: Tier {
                min_replicas: 2,
                max_replicas: 12,
                cpu_per_replica: None,
                memory_per_replica: None,
                scale_trigger: None,
            },
        }
    }

    #[test]
    fn service_validate_accepts_canonical() {
        assert!(svc("auth-service").validate().is_ok());
    }

    #[test]
    fn service_validate_rejects_bad_class_via_serde() {
        // Class is enum so only valid via JSON; we test the validate path.
        let mut s = svc("a");
        s.v1.max_replicas = 0;
        assert!(matches!(s.validate(), Err(CapacityError::InvalidService(_))));
    }

    #[test]
    fn service_validate_rejects_uppercase_name() {
        let s = svc("AuthService");
        assert!(matches!(s.validate(), Err(CapacityError::InvalidService(_))));
    }

    #[test]
    fn budgets_rejects_unsupported_version() {
        let b = Budgets { version: 99, services: vec![] };
        assert!(matches!(b.validate(), Err(CapacityError::UnsupportedVersion(99))));
    }

    #[test]
    fn budgets_rejects_duplicate_service() {
        let b = Budgets { version: 1, services: vec![svc("a"), svc("a")] };
        assert!(matches!(b.validate(), Err(CapacityError::DuplicateService(_))));
    }

    #[test]
    fn admission_register_accepts_known() {
        let b = Budgets::new(1, vec![svc("ok-svc")]).expect("budgets");
        let a = Admission::new(&b);
        let s = a.register_service("ok-svc").expect("ok");
        assert_eq!(s.name, "ok-svc");
        assert!(a.is_registered("ok-svc"));
    }

    #[test]
    fn admission_register_rejects_unknown() {
        let b = Budgets::new(1, vec![]).expect("budgets");
        let a = Admission::new(&b);
        assert!(matches!(
            a.register_service("missing"),
            Err(CapacityError::UnregisteredService(_))
        ));
        let (c, r) = a.stats();
        assert_eq!((c, r), (1, 1));
    }

    #[test]
    fn admission_remaining_budget() {
        let b = Budgets::new(1, vec![svc("svc")]).expect("budgets");
        let a = Admission::new(&b);
        assert_eq!(a.remaining_budget("svc", "v1", 2).unwrap(), 2);
        assert_eq!(a.remaining_budget("svc", "v3", 10).unwrap(), 2);
        assert_eq!(a.remaining_budget("svc", "v1", 99).unwrap(), 0);
        assert!(matches!(
            a.remaining_budget("missing", "v1", 0),
            Err(CapacityError::UnregisteredService(_))
        ));
        assert!(matches!(
            a.remaining_budget("svc", "v99", 0),
            Err(CapacityError::UnknownTier(_))
        ));
    }

    #[test]
    fn library_skips_tier_validation() {
        let s = Service {
            name: "lib".into(),
            class: Class::Library,
            v1: Tier { min_replicas: 0, max_replicas: 0, cpu_per_replica: None, memory_per_replica: None, scale_trigger: None },
            v3: Tier { min_replicas: 0, max_replicas: 0, cpu_per_replica: None, memory_per_replica: None, scale_trigger: None },
        };
        assert!(s.validate().is_ok());
    }
}
