//! `dependencies` — Rust mirror of `contracts/dependencies/` (cycle 18 / L4.N).
//!
//! Mirrors the Go [`Matrix`] + [`ClientFactory`] + DAG validator so Rust
//! services receive the same SR06 §12AI.2 contract.
//!
//! ## Why JSON-only on the Rust side
//!
//! The canonical `matrix.yaml` file is parsed Go-side (Go has yaml.v3 in
//! its module graph already; Rust does not have `serde_yaml` in the
//! workspace dep set). Rust services consume the matrix via:
//!
//! 1. JSON dump produced by the Go loader at service-bootstrap, OR
//! 2. programmatic [`Matrix::new`] for tests + embedded use.
//!
//! Either way, the Rust side enforces the SAME invariants as Go:
//! per-entry validation + duplicate detection + DAG cycle check.
//!
//! ## Parity with Go
//!
//! Field names + enum wire strings match the Go YAML schema 1-for-1
//! (lowercase + snake_case). [`Dependency::validate`] returns the same
//! categories of errors as Go [`Dependency::Validate`]. The DAG check
//! algorithm (3-color DFS WHITE/GREY/BLACK) is identical.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// P0/P1/P2 criticality per SR06 §12AI.2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Criticality {
    /// Platform-critical (full outage on failure).
    P0,
    /// Feature-critical (one feature degraded).
    P1,
    /// Background (active play unaffected).
    P2,
}

/// Transport kind.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DepType {
    HttpExternal,
    HttpInternal,
    Postgres,
    Redis,
    S3,
    Grpc,
}

/// Retry-class enum (mirrors Go `RetryClass` YAML strings).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RetryClass {
    Idempotent,
    NonIdempotent,
    CriticalWrite,
}

/// matrix.yaml `circuit_breaker` block.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BreakerSpec {
    /// Error rate in `(0, 1]` that trips closed → open.
    pub error_rate_threshold: f64,
    /// Minimum window size before threshold is meaningful.
    pub min_requests: usize,
    /// Time open stays before allowing a half-open probe.
    pub open_duration_ms: u64,
}

/// matrix.yaml `bulkhead` block.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BulkheadSpec {
    /// Concurrent in-flight calls.
    pub max_concurrent: usize,
    /// Pending callers allowed.
    pub queue_depth: usize,
    /// How long a queued caller waits.
    pub queue_timeout_ms: u64,
}

/// One matrix.yaml entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Dependency {
    /// Canonical lowercase name.
    pub name: String,
    /// Primary caller.
    pub owner_service: String,
    /// Other services that call this dep.
    #[serde(default)]
    pub also_used_by: Vec<String>,
    /// Tier.
    pub criticality: Criticality,
    /// Transport kind.
    #[serde(rename = "type")]
    pub dep_type: DepType,
    /// Upstream SLA (informational; alert routing uses internal SLI).
    pub sla_target: String,
    /// Default per-call timeout.
    pub timeout_ms: u64,
    /// Circuit breaker config.
    pub circuit_breaker: BreakerSpec,
    /// Retry class.
    pub retry_class: RetryClass,
    /// Bulkhead config.
    pub bulkhead: BulkheadSpec,
    /// Ordered fallback chain (DAG-validated by [`Matrix::new`]).
    #[serde(default)]
    pub fallback: Vec<String>,
    /// Service modes activated when this dep is down.
    #[serde(default)]
    pub degraded_modes: Vec<String>,
    /// Path to docs/sre/runbooks/...
    pub runbook: String,
}

/// Top-level matrix struct (matches YAML root).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MatrixFile {
    /// Schema version (V1 = 1).
    pub version: u32,
    /// Dependency entries.
    pub dependencies: Vec<Dependency>,
}

/// Validated immutable matrix. Construct via [`Matrix::new`] or
/// [`Matrix::from_json`]; both validate the same way as Go's
/// `LoadAndValidate`.
#[derive(Debug, Clone)]
pub struct Matrix {
    file: MatrixFile,
    by_name: HashMap<String, usize>,
}

/// Validation error categories. Mirrors Go's typed sentinel errors.
#[derive(Debug, Error)]
pub enum MatrixError {
    /// Unsupported schema version.
    #[error("dependencies: unsupported matrix version {0} (expected 1)")]
    UnsupportedVersion(u32),
    /// One entry failed per-field validation.
    #[error("dependencies: invalid dependency {dep}: {reason}")]
    InvalidDependency {
        /// Offending dep name.
        dep: String,
        /// Human-readable reason.
        reason: String,
    },
    /// Two deps share a name.
    #[error("dependencies: duplicate dependency {0:?}")]
    DuplicateDependency(String),
    /// A fallback references a name not in the matrix.
    #[error("dependencies: {from:?} references unknown fallback {to:?}")]
    UnknownFallback {
        /// Dep with the bad reference.
        from: String,
        /// Missing fallback name.
        to: String,
    },
    /// Fallback graph contains a cycle.
    #[error("dependencies: fallback cycle detected: {0:?}")]
    FallbackCycle(Vec<String>),
    /// JSON parse failed.
    #[error("dependencies: json parse: {0}")]
    JsonParse(#[source] serde_json::Error),
}

impl Dependency {
    /// Per-field validation (mirror of Go `Dependency.Validate`).
    pub fn validate(&self) -> Result<(), MatrixError> {
        let bad = |reason: String| MatrixError::InvalidDependency {
            dep: self.name.clone(),
            reason,
        };
        if self.name.is_empty() {
            return Err(bad("name empty".into()));
        }
        if self.owner_service.is_empty() {
            return Err(bad("owner_service empty".into()));
        }
        if self.timeout_ms == 0 {
            return Err(bad("timeout_ms must be > 0 (SR06 I16)".into()));
        }
        if self.circuit_breaker.error_rate_threshold <= 0.0
            || self.circuit_breaker.error_rate_threshold > 1.0
        {
            return Err(bad(format!(
                "error_rate_threshold={} must be in (0, 1]",
                self.circuit_breaker.error_rate_threshold
            )));
        }
        if self.circuit_breaker.min_requests == 0 {
            return Err(bad("min_requests must be > 0".into()));
        }
        if self.circuit_breaker.open_duration_ms == 0 {
            return Err(bad("open_duration_ms must be > 0".into()));
        }
        if self.bulkhead.max_concurrent == 0 {
            return Err(bad("bulkhead.max_concurrent must be > 0".into()));
        }
        if self.runbook.is_empty() {
            return Err(bad("runbook path required (SR06 §12AI.2 governance)".into()));
        }
        Ok(())
    }
}

impl Matrix {
    /// Construct from an in-memory [`MatrixFile`]. Validates per-entry +
    /// uniqueness + fallback DAG.
    pub fn new(file: MatrixFile) -> Result<Self, MatrixError> {
        if file.version != 1 {
            return Err(MatrixError::UnsupportedVersion(file.version));
        }
        let mut by_name = HashMap::with_capacity(file.dependencies.len());
        for (i, d) in file.dependencies.iter().enumerate() {
            d.validate()?;
            if by_name.insert(d.name.clone(), i).is_some() {
                return Err(MatrixError::DuplicateDependency(d.name.clone()));
            }
        }
        for d in &file.dependencies {
            for fb in &d.fallback {
                if !by_name.contains_key(fb) {
                    return Err(MatrixError::UnknownFallback {
                        from: d.name.clone(),
                        to: fb.clone(),
                    });
                }
            }
        }
        check_dag(&file.dependencies, &by_name)?;
        Ok(Self { file, by_name })
    }

    /// Parse from a JSON dump (produced by the Go loader at bootstrap).
    pub fn from_json(json: &[u8]) -> Result<Self, MatrixError> {
        let file: MatrixFile = serde_json::from_slice(json).map_err(MatrixError::JsonParse)?;
        Self::new(file)
    }

    /// Find a dep by name. O(1).
    pub fn find(&self, name: &str) -> Option<&Dependency> {
        self.by_name.get(name).map(|&i| &self.file.dependencies[i])
    }

    /// All deps. Stable iteration order = matrix.yaml order.
    pub fn dependencies(&self) -> &[Dependency] {
        &self.file.dependencies
    }

    /// Schema version.
    pub fn version(&self) -> u32 {
        self.file.version
    }
}

/// 3-color DFS WHITE/GREY/BLACK cycle check. Mirrors Go `checkFallbackDAG`.
fn check_dag(
    deps: &[Dependency],
    by_name: &HashMap<String, usize>,
) -> Result<(), MatrixError> {
    #[derive(Copy, Clone, PartialEq, Eq)]
    enum Color {
        White,
        Grey,
        Black,
    }
    let mut color: Vec<Color> = vec![Color::White; deps.len()];
    let mut path: Vec<String> = Vec::new();

    fn dfs(
        idx: usize,
        deps: &[Dependency],
        by_name: &HashMap<String, usize>,
        color: &mut [Color],
        path: &mut Vec<String>,
    ) -> Result<(), MatrixError> {
        color[idx] = Color::Grey;
        path.push(deps[idx].name.clone());
        for fb in &deps[idx].fallback {
            let &fb_idx = by_name.get(fb).expect("fallback resolved earlier");
            match color[fb_idx] {
                Color::Grey => {
                    let mut start = 0;
                    for (i, p) in path.iter().enumerate() {
                        if p == fb {
                            start = i;
                            break;
                        }
                    }
                    let mut cycle: Vec<String> = path[start..].to_vec();
                    cycle.push(fb.clone());
                    return Err(MatrixError::FallbackCycle(cycle));
                }
                Color::White => dfs(fb_idx, deps, by_name, color, path)?,
                Color::Black => {}
            }
        }
        color[idx] = Color::Black;
        path.pop();
        Ok(())
    }
    for i in 0..deps.len() {
        if color[i] == Color::White {
            dfs(i, deps, by_name, &mut color, &mut path)?;
        }
    }
    Ok(())
}

// ────────────────────────────────────────────────────────────────────────
// ClientFactory — resolves per-(service, dep) configs.
// ────────────────────────────────────────────────────────────────────────

/// Resolved per-(caller_service, dep) wrapped-client config. Mirrors Go
/// `WrappedClientConfig`. Service code uses these fields to construct
/// `dp_kernel::resilience::{CircuitBreaker, Bulkhead, RetryPolicy}` and
/// wrap its transport client.
#[derive(Debug, Clone)]
pub struct WrappedClientConfig {
    /// Calling service (for per-(caller_service, dep) breaker isolation).
    pub service: String,
    /// Dep name (for metric labels + audit-row dep_name).
    pub dep_name: String,
    /// Transport kind (callers may dispatch by this).
    pub dep_type: DepType,
    /// Tier.
    pub criticality: Criticality,
    /// Per-call timeout (matrix-derived).
    pub timeout: std::time::Duration,
    /// Breaker config — feeds [`crate::resilience::BreakerConfig`].
    pub breaker: crate::resilience::BreakerConfig,
    /// Retry class.
    pub retry_class: RetryClass,
    /// Bulkhead config — feeds [`crate::resilience::BulkheadConfig`].
    pub bulkhead: crate::resilience::BulkheadConfig,
    /// Ordered fallback chain.
    pub fallback: Vec<String>,
    /// Runbook path; include in alert log lines.
    pub runbook: String,
}

/// Factory error.
#[derive(Debug, Error)]
pub enum FactoryError {
    /// Caller service is not in the dep's owner_service or also_used_by.
    #[error("dependencies: service {service:?} not registered as caller of {dep:?}")]
    ServiceUnregistered {
        /// Caller asking.
        service: String,
        /// Dep being asked for.
        dep: String,
    },
    /// Dep not in the matrix.
    #[error("dependencies: unknown dependency {0:?}")]
    UnknownDep(String),
}

/// Thread-safe matrix-backed factory.
pub struct ClientFactory {
    matrix: Matrix,
}

impl ClientFactory {
    /// Wrap a validated matrix.
    pub fn new(matrix: Matrix) -> Self {
        Self { matrix }
    }

    /// Underlying matrix (caller may enumerate all deps for bootstrap-time
    /// pool sizing).
    pub fn matrix(&self) -> &Matrix {
        &self.matrix
    }

    /// Resolve per-(service, dep) wrapped-client config. Mirrors Go
    /// `ClientFactory.For`.
    pub fn for_service_dep(
        &self,
        service: &str,
        dep_name: &str,
    ) -> Result<WrappedClientConfig, FactoryError> {
        let dep = self
            .matrix
            .find(dep_name)
            .ok_or_else(|| FactoryError::UnknownDep(dep_name.to_string()))?;
        if dep.owner_service != service && !dep.also_used_by.iter().any(|s| s == service) {
            return Err(FactoryError::ServiceUnregistered {
                service: service.to_string(),
                dep: dep_name.to_string(),
            });
        }
        Ok(WrappedClientConfig {
            service: service.to_string(),
            dep_name: dep.name.clone(),
            dep_type: dep.dep_type.clone(),
            criticality: dep.criticality,
            timeout: std::time::Duration::from_millis(dep.timeout_ms),
            breaker: crate::resilience::BreakerConfig {
                error_rate_threshold: dep.circuit_breaker.error_rate_threshold,
                min_requests: dep.circuit_breaker.min_requests,
                open_duration: std::time::Duration::from_millis(dep.circuit_breaker.open_duration_ms),
                half_open_probe_interval: std::time::Duration::from_secs(1),
            },
            retry_class: dep.retry_class,
            bulkhead: crate::resilience::BulkheadConfig {
                dep: dep.name.clone(),
                max_concurrent: dep.bulkhead.max_concurrent,
                queue_depth: dep.bulkhead.queue_depth,
                queue_timeout: std::time::Duration::from_millis(dep.bulkhead.queue_timeout_ms),
            },
            fallback: dep.fallback.clone(),
            runbook: dep.runbook.clone(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_dep(name: &str, fallback: Vec<String>) -> Dependency {
        Dependency {
            name: name.into(),
            owner_service: "roleplay-service".into(),
            also_used_by: vec!["chat-service".into()],
            criticality: Criticality::P1,
            dep_type: DepType::HttpExternal,
            sla_target: "99.5%".into(),
            timeout_ms: 60_000,
            circuit_breaker: BreakerSpec {
                error_rate_threshold: 0.25,
                min_requests: 20,
                open_duration_ms: 30_000,
            },
            retry_class: RetryClass::NonIdempotent,
            bulkhead: BulkheadSpec {
                max_concurrent: 30,
                queue_depth: 15,
                queue_timeout_ms: 200,
            },
            fallback,
            degraded_modes: vec!["limited".into()],
            runbook: "runbook.md".into(),
        }
    }

    #[test]
    fn matrix_validates_linear_chain() {
        let file = MatrixFile {
            version: 1,
            dependencies: vec![
                sample_dep("llm-a", vec!["llm-b".into()]),
                sample_dep("llm-b", vec!["llm-c".into()]),
                sample_dep("llm-c", vec![]),
            ],
        };
        let m = Matrix::new(file).expect("linear chain should validate");
        assert_eq!(m.dependencies().len(), 3);
    }

    #[test]
    fn matrix_rejects_cycle() {
        let file = MatrixFile {
            version: 1,
            dependencies: vec![
                sample_dep("llm-a", vec!["llm-b".into()]),
                sample_dep("llm-b", vec!["llm-c".into()]),
                sample_dep("llm-c", vec!["llm-a".into()]),
            ],
        };
        let err = Matrix::new(file).unwrap_err();
        assert!(matches!(err, MatrixError::FallbackCycle(_)));
    }

    #[test]
    fn matrix_rejects_unknown_fallback() {
        let file = MatrixFile {
            version: 1,
            dependencies: vec![sample_dep("a", vec!["ghost".into()])],
        };
        let err = Matrix::new(file).unwrap_err();
        assert!(matches!(err, MatrixError::UnknownFallback { .. }));
    }

    #[test]
    fn matrix_rejects_unsupported_version() {
        let file = MatrixFile {
            version: 99,
            dependencies: vec![],
        };
        assert!(matches!(
            Matrix::new(file).unwrap_err(),
            MatrixError::UnsupportedVersion(99)
        ));
    }

    #[test]
    fn matrix_rejects_duplicate_name() {
        let file = MatrixFile {
            version: 1,
            dependencies: vec![sample_dep("dup", vec![]), sample_dep("dup", vec![])],
        };
        assert!(matches!(
            Matrix::new(file).unwrap_err(),
            MatrixError::DuplicateDependency(_)
        ));
    }

    #[test]
    fn dependency_validate_bad_timeout() {
        let mut d = sample_dep("d", vec![]);
        d.timeout_ms = 0;
        assert!(matches!(
            d.validate().unwrap_err(),
            MatrixError::InvalidDependency { .. }
        ));
    }

    #[test]
    fn from_json_round_trips() {
        let file = MatrixFile {
            version: 1,
            dependencies: vec![sample_dep("a", vec![])],
        };
        let json = serde_json::to_vec(&file).unwrap();
        let m = Matrix::from_json(&json).expect("json round-trip");
        assert!(m.find("a").is_some());
    }

    #[test]
    fn client_factory_happy_path() {
        let m = Matrix::new(MatrixFile {
            version: 1,
            dependencies: vec![sample_dep("llm-anthropic", vec![])],
        })
        .unwrap();
        let f = ClientFactory::new(m);
        let cfg = f
            .for_service_dep("roleplay-service", "llm-anthropic")
            .unwrap();
        assert_eq!(cfg.dep_name, "llm-anthropic");
        assert_eq!(cfg.timeout, std::time::Duration::from_secs(60));
        assert_eq!(cfg.bulkhead.max_concurrent, 30);
    }

    #[test]
    fn client_factory_rejects_unregistered_service() {
        let m = Matrix::new(MatrixFile {
            version: 1,
            dependencies: vec![sample_dep("llm-anthropic", vec![])],
        })
        .unwrap();
        let f = ClientFactory::new(m);
        let err = f.for_service_dep("rogue", "llm-anthropic").unwrap_err();
        assert!(matches!(err, FactoryError::ServiceUnregistered { .. }));
    }

    #[test]
    fn client_factory_rejects_unknown_dep() {
        let m = Matrix::new(MatrixFile {
            version: 1,
            dependencies: vec![sample_dep("a", vec![])],
        })
        .unwrap();
        let f = ClientFactory::new(m);
        let err = f.for_service_dep("roleplay-service", "ghost").unwrap_err();
        assert!(matches!(err, FactoryError::UnknownDep(_)));
    }
}
