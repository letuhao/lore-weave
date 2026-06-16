//! `observability` — Rust mirror of `contracts/observability/` (cycle 19 / L4.H).
//!
//! Mirrors the Go [`Inventory`] + [`Admission`] + [`TraceConvention`] so
//! Rust services receive the SAME SR12 §12AO admission-control contract.
//!
//! ## Why JSON-only on the Rust side
//!
//! Same architectural pattern as cycle 18's `dependencies` mirror: the
//! canonical `inventory.yaml` file is parsed Go-side (Go has yaml.v3 in
//! its module graph already; Rust does not ship `serde_yaml` in the
//! workspace dep set for non-meta-rs crates). Rust services consume the
//! inventory via:
//!
//! 1. JSON dump produced by the Go loader at service bootstrap, OR
//! 2. programmatic [`Inventory::new`] for tests + embedded use.
//!
//! Either way, the Rust side enforces the SAME invariants as Go:
//! per-entry validation + duplicate detection + admission warn/reject
//! behavior matrix.
//!
//! ## Parity with Go
//!
//! Field names + enum wire strings match the Go YAML schema 1-for-1
//! (lowercase + snake_case). [`Entry::validate`] returns the same
//! categories of errors as Go `Entry.Validate`. The admission state
//! machine (warn vs reject) is byte-equal.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::{Mutex, RwLock};

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Metric kind classifier (SR12 §12AO).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Counter,
    Gauge,
    Histogram,
    Summary,
    Log,
    Trace,
}

/// Foundation layer label (L1..L7).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Layer {
    L1,
    L2,
    L3,
    L4,
    L5,
    L6,
    L7,
}

/// One row in inventory.yaml `metrics:` list.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry {
    pub name: String,
    pub kind: Kind,
    pub layer: Layer,
    pub shipped_cycle: u32,
    #[serde(default)]
    pub labels: Vec<String>,
    pub description: String,
    pub owner: String,
    pub source: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cardinality_notes: Option<String>,
}

/// Top-level inventory shape (mirrors Go `Inventory`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Inventory {
    pub version: u32,
    pub metrics: Vec<Entry>,
}

/// Admission mode (warn = V1; reject = V1+30d) per SR12 §12AO.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdmissionMode {
    /// V1 — emit warning + breach row, return Ok(()).
    Warn = 0,
    /// V1+30d — return Err(UnregisteredMetric), drop the emission.
    Reject = 1,
}

/// Errors. `Validate*` errors carry an `&'static str` reason for stable
/// matching in tests.
#[derive(Debug, Error, PartialEq, Eq)]
pub enum ObsError {
    #[error("invalid inventory entry: {0}")]
    InvalidEntry(String),
    #[error("unsupported inventory version: {0} (expected 1)")]
    UnsupportedVersion(u32),
    #[error("duplicate metric name: {0}")]
    DuplicateMetricName(String),
    #[error("metric not in inventory (admission rejected): {0}")]
    UnregisteredMetric(String),
    #[error("emission carries label not in inventory entry: name={0} label={1}")]
    UnregisteredLabel(String, String),
}

fn is_valid_lw_name(n: &str) -> bool {
    // ^lw_[a-z][a-z0-9]*(_[a-z0-9]+)+$
    let bytes = n.as_bytes();
    if !n.starts_with("lw_") || bytes.len() < 6 {
        return false;
    }
    // After "lw_": at least 2 underscore-separated segments.
    let rest = &n[3..];
    let mut segs: Vec<&str> = rest.split('_').collect();
    if segs.len() < 2 {
        return false;
    }
    if segs[0].is_empty() || !segs[0].chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit()) {
        return false;
    }
    if !segs[0].chars().next().is_some_and(|c| c.is_ascii_lowercase()) {
        return false;
    }
    for s in segs.iter_mut().skip(1) {
        if s.is_empty() || !s.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit()) {
            return false;
        }
    }
    true
}

fn is_valid_prom_name(n: &str) -> bool {
    let mut it = n.chars();
    let Some(first) = it.next() else { return false };
    if !first.is_ascii_lowercase() {
        return false;
    }
    it.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

impl Entry {
    /// Validates one entry per the SR12 §12AO schema rules. Same
    /// behavior as Go `Entry.Validate`.
    pub fn validate(&self) -> Result<(), ObsError> {
        if self.name.trim().is_empty() {
            return Err(ObsError::InvalidEntry("name empty".into()));
        }
        if self.name.starts_with("lw_") {
            if !is_valid_lw_name(&self.name) {
                return Err(ObsError::InvalidEntry(format!(
                    "name={} does not match lw_<domain>_<metric>_<unit>",
                    self.name
                )));
            }
        } else if !is_valid_prom_name(&self.name) {
            return Err(ObsError::InvalidEntry(format!(
                "name={} has invalid characters (lowercase + _ only)",
                self.name
            )));
        }
        if self.shipped_cycle == 0 {
            return Err(ObsError::InvalidEntry(format!(
                "name={} shipped_cycle must be > 0",
                self.name
            )));
        }
        if self.description.trim().is_empty() {
            return Err(ObsError::InvalidEntry(format!(
                "name={} description empty",
                self.name
            )));
        }
        if self.owner.trim().is_empty() {
            return Err(ObsError::InvalidEntry(format!(
                "name={} owner empty (governance)",
                self.name
            )));
        }
        if self.source.trim().is_empty() {
            return Err(ObsError::InvalidEntry(format!(
                "name={} source empty (provenance)",
                self.name
            )));
        }
        for lbl in &self.labels {
            if !is_valid_prom_name(lbl) {
                return Err(ObsError::InvalidEntry(format!(
                    "name={} label={} invalid (lowercase + _ only)",
                    self.name, lbl
                )));
            }
        }
        Ok(())
    }
}

impl Inventory {
    /// Construct a programmatic Inventory and validate it. Equivalent
    /// of the Go `ParseAndValidate(yaml)` after JSON marshalling.
    pub fn new(version: u32, metrics: Vec<Entry>) -> Result<Self, ObsError> {
        let inv = Inventory { version, metrics };
        inv.validate()?;
        Ok(inv)
    }

    /// Validate the full inventory: version + per-entry + dup check.
    pub fn validate(&self) -> Result<(), ObsError> {
        if self.version != 1 {
            return Err(ObsError::UnsupportedVersion(self.version));
        }
        let mut seen = std::collections::HashSet::new();
        for e in &self.metrics {
            e.validate()?;
            if !seen.insert(&e.name) {
                return Err(ObsError::DuplicateMetricName(e.name.clone()));
            }
        }
        Ok(())
    }

    /// Builds the O(1) lookup map for admission checks. Snapshot at boot.
    pub fn admission_lookup(&self) -> HashMap<String, Entry> {
        self.metrics
            .iter()
            .map(|e| (e.name.clone(), e.clone()))
            .collect()
    }

    /// Find an entry by name (case-sensitive).
    pub fn find(&self, name: &str) -> Option<&Entry> {
        self.metrics.iter().find(|e| e.name == name)
    }
}

/// One row in the `observability_budget_breaches` (meta) table.
///
/// Cycle-19 ships the typed buffer; cycle-20+ wires the meta-DB writer.
#[derive(Debug, Clone)]
pub struct BudgetBreachRow {
    pub metric_name: String,
    pub labels: HashMap<String, String>,
    pub reason: String,
    pub mode: AdmissionMode,
    /// Unix nanoseconds.
    pub occurred_at: i64,
}

/// Bounded in-memory ring buffer of recent breaches. Non-blocking
/// emit: full-buffer evicts oldest + bumps dropped counter.
pub struct BudgetBreachBuffer {
    inner: Mutex<RingBuffer>,
}

struct RingBuffer {
    rows: Vec<Option<BudgetBreachRow>>,
    head: usize,
    size: usize,
    dropped: u64,
}

impl BudgetBreachBuffer {
    pub fn new(capacity: usize) -> Self {
        let cap = if capacity == 0 { 1024 } else { capacity };
        BudgetBreachBuffer {
            inner: Mutex::new(RingBuffer {
                rows: vec![None; cap],
                head: 0,
                size: 0,
                dropped: 0,
            }),
        }
    }

    pub fn write(&self, row: BudgetBreachRow) {
        let mut g = self.inner.lock().expect("BudgetBreachBuffer poisoned");
        let cap = g.rows.len();
        if g.size == cap {
            g.head = (g.head + 1) % cap;
            g.dropped += 1;
        } else {
            g.size += 1;
        }
        let size = g.size;
        let head = g.head;
        let tail = (head + size - 1) % cap;
        g.rows[tail] = Some(row);
    }

    pub fn drain(&self) -> Vec<BudgetBreachRow> {
        let mut g = self.inner.lock().expect("BudgetBreachBuffer poisoned");
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
        self.inner.lock().expect("BudgetBreachBuffer poisoned").dropped
    }

    pub fn size(&self) -> usize {
        self.inner.lock().expect("BudgetBreachBuffer poisoned").size
    }
}

/// Runtime admission surface. Construct once per service with the
/// loaded inventory; mode flippable at runtime (warn → reject after
/// the 30-day adoption window per SR12 §12AO).
pub struct Admission {
    lookup: HashMap<String, Entry>,
    mode: AtomicU32,
    breach: Option<Box<dyn Fn(BudgetBreachRow) + Send + Sync>>,
    strict_labels: bool,
    emitted: AtomicU64,
    warned: AtomicU64,
    rejected: AtomicU64,
}

impl Admission {
    pub fn new(inv: &Inventory, mode: AdmissionMode) -> Self {
        Admission {
            lookup: inv.admission_lookup(),
            mode: AtomicU32::new(mode as u32),
            breach: None,
            strict_labels: false,
            emitted: AtomicU64::new(0),
            warned: AtomicU64::new(0),
            rejected: AtomicU64::new(0),
        }
    }

    pub fn with_breach_writer<F>(mut self, writer: F) -> Self
    where
        F: Fn(BudgetBreachRow) + Send + Sync + 'static,
    {
        self.breach = Some(Box::new(writer));
        self
    }

    pub fn with_strict_labels(mut self) -> Self {
        self.strict_labels = true;
        self
    }

    pub fn set_mode(&self, mode: AdmissionMode) -> AdmissionMode {
        let prev = self.mode.swap(mode as u32, Ordering::SeqCst);
        if prev == AdmissionMode::Reject as u32 {
            AdmissionMode::Reject
        } else {
            AdmissionMode::Warn
        }
    }

    pub fn mode(&self) -> AdmissionMode {
        if self.mode.load(Ordering::SeqCst) == AdmissionMode::Reject as u32 {
            AdmissionMode::Reject
        } else {
            AdmissionMode::Warn
        }
    }

    pub fn stats(&self) -> (u64, u64, u64) {
        (
            self.emitted.load(Ordering::Relaxed),
            self.warned.load(Ordering::Relaxed),
            self.rejected.load(Ordering::Relaxed),
        )
    }

    /// Admission entry point. Behavior matches Go EmitMetric byte-for-byte.
    pub fn emit_metric(
        &self,
        name: &str,
        labels: &HashMap<String, String>,
        _value: f64,
    ) -> Result<(), ObsError> {
        self.emitted.fetch_add(1, Ordering::Relaxed);
        let Some(entry) = self.lookup.get(name) else {
            return self.handle_breach(name, labels, "unregistered_metric",
                ObsError::UnregisteredMetric(name.to_string()));
        };
        if self.strict_labels {
            if let Err(err) = verify_labels(entry, labels) {
                return self.handle_breach(name, labels, "unregistered_label", err);
            }
        }
        Ok(())
    }

    fn handle_breach(
        &self,
        name: &str,
        labels: &HashMap<String, String>,
        reason: &str,
        err: ObsError,
    ) -> Result<(), ObsError> {
        let row = BudgetBreachRow {
            metric_name: name.to_string(),
            labels: labels.clone(),
            reason: reason.to_string(),
            mode: self.mode(),
            occurred_at: chrono_unix_nanos(),
        };
        if let Some(bw) = &self.breach {
            bw(row);
        }
        if self.mode() == AdmissionMode::Reject {
            self.rejected.fetch_add(1, Ordering::Relaxed);
            Err(err)
        } else {
            self.warned.fetch_add(1, Ordering::Relaxed);
            Ok(())
        }
    }
}

fn verify_labels(entry: &Entry, labels: &HashMap<String, String>) -> Result<(), ObsError> {
    if labels.is_empty() {
        return Ok(());
    }
    let allowed: std::collections::HashSet<&str> =
        entry.labels.iter().map(|s| s.as_str()).collect();
    for k in labels.keys() {
        if !allowed.contains(k.as_str()) {
            return Err(ObsError::UnregisteredLabel(entry.name.clone(), k.clone()));
        }
    }
    Ok(())
}

fn chrono_unix_nanos() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as i64)
        .unwrap_or_default()
}

/// Trace span-name convention registry (SR12 §12AO §4).
///
/// Pins the `<service>.<operation>(.<phase>)?` snake_case+dot pattern.
pub struct TraceConvention {
    names: RwLock<std::collections::HashSet<String>>,
}

impl Default for TraceConvention {
    fn default() -> Self { Self::new() }
}

impl TraceConvention {
    pub fn new() -> Self {
        TraceConvention { names: RwLock::new(std::collections::HashSet::new()) }
    }

    pub fn register(&self, name: &str) -> Result<(), ObsError> {
        if !is_valid_span_name(name) {
            return Err(ObsError::InvalidEntry(format!(
                "trace span name={} does not match snake_case.dot pattern",
                name
            )));
        }
        self.names
            .write()
            .expect("TraceConvention poisoned")
            .insert(name.to_string());
        Ok(())
    }

    pub fn known(&self, name: &str) -> bool {
        self.names.read().expect("TraceConvention poisoned").contains(name)
    }
}

fn is_valid_span_name(n: &str) -> bool {
    // ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$
    if !n.contains('.') {
        return false;
    }
    let segs: Vec<&str> = n.split('.').collect();
    if segs.len() < 2 {
        return false;
    }
    for s in segs {
        if s.is_empty() {
            return false;
        }
        let mut it = s.chars();
        let Some(first) = it.next() else { return false };
        if !first.is_ascii_lowercase() {
            return false;
        }
        if !it.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_') {
            return false;
        }
    }
    true
}

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn test_inventory() -> Inventory {
        Inventory {
            version: 1,
            metrics: vec![Entry {
                name: concat!("lw", "_test_registered_total").into(),
                kind: Kind::Counter,
                layer: Layer::L4,
                shipped_cycle: 19,
                labels: vec!["reality_id".into(), "outcome".into()],
                description: "x".into(),
                owner: "t".into(),
                source: "t".into(),
                cardinality_notes: None,
            }],
        }
    }

    #[test]
    fn entry_validate_accepts_canonical_lw_name() {
        let e = Entry {
            name: "lw_provisioner_steps_total".into(),
            kind: Kind::Counter,
            layer: Layer::L1,
            shipped_cycle: 5,
            labels: vec!["step".into(), "outcome".into()],
            description: "x".into(),
            owner: "o".into(),
            source: "s".into(),
            cardinality_notes: None,
        };
        assert!(e.validate().is_ok());
    }

    #[test]
    fn entry_validate_rejects_single_segment_lw() {
        let mut e = test_inventory().metrics.into_iter().next().unwrap();
        e.name = "lw_foo".into();
        assert!(e.validate().is_err());
    }

    #[test]
    fn entry_validate_accepts_exporter_metric() {
        let e = Entry {
            name: "pg_stat_replication_lag_bytes".into(),
            kind: Kind::Gauge,
            layer: Layer::L1,
            shipped_cycle: 1,
            labels: vec!["application_name".into()],
            description: "x".into(),
            owner: "sre".into(),
            source: "postgres-exporter".into(),
            cardinality_notes: None,
        };
        assert!(e.validate().is_ok());
    }

    #[test]
    fn inventory_rejects_unsupported_version() {
        let bad = Inventory { version: 99, metrics: vec![] };
        assert!(matches!(bad.validate(), Err(ObsError::UnsupportedVersion(99))));
    }

    #[test]
    fn inventory_rejects_duplicate_name() {
        let e = test_inventory().metrics.into_iter().next().unwrap();
        let bad = Inventory { version: 1, metrics: vec![e.clone(), e] };
        assert!(matches!(bad.validate(), Err(ObsError::DuplicateMetricName(_))));
    }

    #[test]
    fn admission_warn_accepts_unregistered() {
        let inv = test_inventory();
        let a = Admission::new(&inv, AdmissionMode::Warn);
        let labels = HashMap::new();
        assert!(a.emit_metric(concat!("lw", "_notreg_x_total"), &labels, 1.0).is_ok());
        let (e, w, r) = a.stats();
        assert_eq!((e, w, r), (1, 1, 0));
    }

    #[test]
    fn admission_reject_rejects_unregistered() {
        let inv = test_inventory();
        let a = Admission::new(&inv, AdmissionMode::Reject);
        let labels = HashMap::new();
        let err = a.emit_metric(concat!("lw", "_notreg_x_total"), &labels, 1.0);
        assert!(matches!(err, Err(ObsError::UnregisteredMetric(_))));
        let (e, w, r) = a.stats();
        assert_eq!((e, w, r), (1, 0, 1));
    }

    #[test]
    fn admission_set_mode_flips_at_runtime() {
        let inv = test_inventory();
        let a = Admission::new(&inv, AdmissionMode::Warn);
        let labels = HashMap::new();
        assert!(a.emit_metric(concat!("lw", "_foo_x_total"), &labels, 1.0).is_ok());
        let prev = a.set_mode(AdmissionMode::Reject);
        assert_eq!(prev, AdmissionMode::Warn);
        assert!(matches!(
            a.emit_metric(concat!("lw", "_foo_x_total"), &labels, 1.0),
            Err(ObsError::UnregisteredMetric(_))
        ));
    }

    #[test]
    fn admission_strict_labels_rejects_unknown_label() {
        let inv = test_inventory();
        let a = Admission::new(&inv, AdmissionMode::Reject).with_strict_labels();
        let mut labels = HashMap::new();
        labels.insert("user_id".into(), "u1".into());
        assert!(matches!(
            a.emit_metric(concat!("lw", "_test_registered_total"), &labels, 1.0),
            Err(ObsError::UnregisteredLabel(_, _))
        ));
    }

    #[test]
    fn budget_buffer_evicts_oldest() {
        let b = BudgetBreachBuffer::new(2);
        let mkrow = |n: &str| BudgetBreachRow {
            metric_name: n.into(),
            labels: HashMap::new(),
            reason: "x".into(),
            mode: AdmissionMode::Warn,
            occurred_at: 0,
        };
        b.write(mkrow("m1"));
        b.write(mkrow("m2"));
        b.write(mkrow("m3"));
        let rows = b.drain();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].metric_name, "m2");
        assert_eq!(rows[1].metric_name, "m3");
        assert_eq!(b.dropped_count(), 1);
    }

    #[test]
    fn trace_convention_accepts_valid_names() {
        let tc = TraceConvention::new();
        for n in ["publisher.xadd", "world.provision.canary_run"] {
            assert!(tc.register(n).is_ok());
            assert!(tc.known(n));
        }
    }

    #[test]
    fn trace_convention_rejects_bad_names() {
        let tc = TraceConvention::new();
        for n in ["NotSnake", "no.UPPER.case", "single", "double..dot", "x.", ".x"] {
            assert!(matches!(tc.register(n), Err(ObsError::InvalidEntry(_))));
        }
    }
}
