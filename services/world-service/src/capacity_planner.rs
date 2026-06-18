//! L1.C.3 — Capacity planner: shard allocator per R04 §12D.6.
//!
//! ## Contract
//!
//! Given the live capacity snapshot of N shards, pick the **least-full**
//! shard whose utilization is strictly below the FULL threshold (default
//! 95%). The WARNING threshold (default 80%) does NOT block allocation;
//! it only triggers an SRE alert (separate concern — emitted by the
//! Prometheus rules in L1.I, cycle 6).
//!
//! ## Determinism
//!
//! Ties (two shards with identical free capacity) are broken by `ShardId`
//! ascending. This is **deterministic**, NOT random — Q-L1A-3 audit rules
//! require allocation reasoning be reproducible from logs.
//!
//! ## Thresholds source
//!
//! `scripts/capacity-thresholds.yaml` (L1.C.7) is the canonical source.
//! The planner takes the parsed thresholds as a value; the YAML loader
//! ships with the deployment harness in cycle 7 (L1.L capacity gates).

use serde::{Deserialize, Serialize};

use crate::errors::ProvisionerError;

/// Opaque shard identifier — matches `reality_registry.db_host` substring.
/// Wrapped so we don't conflate it with any other string field.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ShardId(pub String);

impl ShardId {
    /// Construct from a `&str` for tests + call sites.
    pub fn new(s: impl Into<String>) -> Self {
        Self(s.into())
    }

    /// Borrow the inner string.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Per-shard capacity snapshot — read from `shard_utilization` table in
/// later cycles (L1.A.6 lands the table in cycle 7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ShardCapacity {
    /// Shard identifier (e.g. `pg-shard-0.internal`).
    pub shard_id: ShardId,
    /// Total reality slots provisioned on this shard (capacity).
    pub total_realities: u32,
    /// Live realities currently routed here.
    pub used_realities: u32,
}

impl ShardCapacity {
    /// Returns utilization as a fraction in `[0, 1]`. Returns 1.0 when
    /// `total_realities` is 0 (treat empty shard as "full" so the planner
    /// skips it rather than divide-by-zero — empty here means "not
    /// initialized for hosting", per R04 §12D.6).
    pub fn utilization(&self) -> f32 {
        if self.total_realities == 0 {
            return 1.0;
        }
        self.used_realities as f32 / self.total_realities as f32
    }

    /// Free slots remaining.
    pub fn free_slots(&self) -> u32 {
        self.total_realities.saturating_sub(self.used_realities)
    }

    /// Validates the snapshot — `used <= total`.
    pub fn validate(&self) -> Result<(), ProvisionerError> {
        if self.used_realities > self.total_realities {
            return Err(ProvisionerError::BadCapacity(format!(
                "shard {:?}: used={} > total={}",
                self.shard_id, self.used_realities, self.total_realities
            )));
        }
        Ok(())
    }
}

/// Per-cluster thresholds. Default = R04 §12D.6 defaults (80/95).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CapacityThresholds {
    /// Utilization fraction (0..1) that triggers SRE warning alerts.
    pub warning: f32,
    /// Utilization fraction (0..1) at or above which the planner refuses
    /// to allocate.
    pub full: f32,
}

impl Default for CapacityThresholds {
    fn default() -> Self {
        Self { warning: 0.80, full: 0.95 }
    }
}

impl CapacityThresholds {
    /// Validates the threshold pair (0 < warning < full <= 1.0).
    pub fn validate(&self) -> Result<(), ProvisionerError> {
        if !(0.0..=1.0).contains(&self.warning) || !(0.0..=1.0).contains(&self.full) {
            return Err(ProvisionerError::BadCapacity(format!(
                "thresholds out of [0,1]: warning={}, full={}",
                self.warning, self.full
            )));
        }
        if self.warning >= self.full {
            return Err(ProvisionerError::BadCapacity(format!(
                "warning ({}) must be strictly less than full ({})",
                self.warning, self.full
            )));
        }
        Ok(())
    }
}

/// L1.C.3 — capacity planner.
///
/// Stateless functional API — the planner takes the snapshot at call time
/// and returns the choice. State lives in `shard_utilization` (per-shard
/// row in meta DB, refreshed by the metrics-aggregation job in L1.I).
pub struct CapacityPlanner {
    /// Active thresholds (load from `scripts/capacity-thresholds.yaml`).
    pub thresholds: CapacityThresholds,
}

impl CapacityPlanner {
    /// Construct with explicit thresholds.
    pub fn new(thresholds: CapacityThresholds) -> Self {
        Self { thresholds }
    }

    /// Pick the **least-full** shard with capacity, breaking ties by
    /// `ShardId` ascending.
    ///
    /// Returns `Err(NoShardCapacity)` when EVERY shard is at or above
    /// `full`. Returns `Err(BadCapacity)` when a snapshot is malformed
    /// (used > total) or the thresholds are inverted.
    pub fn pick_shard<'a>(
        &self,
        shards: &'a [ShardCapacity],
    ) -> Result<&'a ShardCapacity, ProvisionerError> {
        self.thresholds.validate()?;
        if shards.is_empty() {
            return Err(ProvisionerError::NoShardCapacity);
        }
        for s in shards {
            s.validate()?;
        }
        // Filter out full shards.
        let mut eligible: Vec<&ShardCapacity> = shards
            .iter()
            .filter(|s| s.utilization() < self.thresholds.full)
            .collect();
        if eligible.is_empty() {
            return Err(ProvisionerError::NoShardCapacity);
        }
        // Sort by utilization ASC, tie-break by ShardId ASC (deterministic).
        eligible.sort_by(|a, b| {
            a.utilization()
                .partial_cmp(&b.utilization())
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.shard_id.cmp(&b.shard_id))
        });
        Ok(eligible[0])
    }

    /// Returns the subset of shards whose utilization is at or above the
    /// `warning` threshold. Used by the SRE alert path (out of band).
    pub fn warning_shards<'a>(&self, shards: &'a [ShardCapacity]) -> Vec<&'a ShardCapacity> {
        shards
            .iter()
            .filter(|s| s.utilization() >= self.thresholds.warning)
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shard(id: &str, used: u32, total: u32) -> ShardCapacity {
        ShardCapacity {
            shard_id: ShardId::new(id),
            used_realities: used,
            total_realities: total,
        }
    }

    #[test]
    fn picks_least_full_shard() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        let shards = vec![
            shard("pg-shard-0", 50, 100), // 0.50
            shard("pg-shard-1", 30, 100), // 0.30  ← least full
            shard("pg-shard-2", 80, 100), // 0.80
        ];
        let picked = p.pick_shard(&shards).expect("pick");
        assert_eq!(picked.shard_id.as_str(), "pg-shard-1");
    }

    #[test]
    fn breaks_ties_by_shard_id_ascending() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        // Both shards have identical 30% utilization; ID ascending wins.
        let shards = vec![
            shard("pg-shard-b", 30, 100),
            shard("pg-shard-a", 30, 100),
        ];
        let picked = p.pick_shard(&shards).expect("pick");
        assert_eq!(picked.shard_id.as_str(), "pg-shard-a");
    }

    #[test]
    fn refuses_when_all_shards_full() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        // All at 95% — full threshold by default.
        let shards = vec![
            shard("pg-shard-0", 95, 100),
            shard("pg-shard-1", 96, 100),
        ];
        let err = p.pick_shard(&shards).unwrap_err();
        assert!(matches!(err, ProvisionerError::NoShardCapacity));
    }

    #[test]
    fn refuses_when_no_shards() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        let err = p.pick_shard(&[]).unwrap_err();
        assert!(matches!(err, ProvisionerError::NoShardCapacity));
    }

    #[test]
    fn rejects_bad_threshold_pairs() {
        // warning >= full
        let p = CapacityPlanner::new(CapacityThresholds { warning: 0.95, full: 0.95 });
        let err = p.pick_shard(&[shard("pg-shard-0", 1, 10)]).unwrap_err();
        assert!(matches!(err, ProvisionerError::BadCapacity(_)));

        // out of range
        let p = CapacityPlanner::new(CapacityThresholds { warning: 1.5, full: 2.0 });
        let err = p.pick_shard(&[shard("pg-shard-0", 1, 10)]).unwrap_err();
        assert!(matches!(err, ProvisionerError::BadCapacity(_)));
    }

    #[test]
    fn rejects_overfull_snapshot() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        let err = p.pick_shard(&[shard("pg-shard-0", 105, 100)]).unwrap_err();
        assert!(matches!(err, ProvisionerError::BadCapacity(_)));
    }

    #[test]
    fn warning_shards_filter() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        let shards = vec![
            shard("a", 30, 100), // 0.30 < 0.80
            shard("b", 80, 100), // 0.80 >= 0.80 — warning
            shard("c", 90, 100), // 0.90 — warning
        ];
        let warn = p.warning_shards(&shards);
        assert_eq!(warn.len(), 2);
        assert_eq!(warn[0].shard_id.as_str(), "b");
        assert_eq!(warn[1].shard_id.as_str(), "c");
    }

    #[test]
    fn zero_total_treated_as_full() {
        let p = CapacityPlanner::new(CapacityThresholds::default());
        let shards = vec![shard("uninit", 0, 0)];
        let err = p.pick_shard(&shards).unwrap_err();
        assert!(matches!(err, ProvisionerError::NoShardCapacity));
    }
}
