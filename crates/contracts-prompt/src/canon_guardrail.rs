//! Canon guardrail — full implementation per L5.I.3 (RAID cycle 27).
//!
//! # Q-L5-5 LOCKED
//!
//! Roleplay-service / world-service call [`YamlGuardrail::check_proposed_write`]
//! (via the cycle-25 [`CanonGuardrail`] trait) BEFORE writing a proposed L3
//! event. Returns `Err(GuardrailViolation)` if the proposal conflicts with
//! L1 axiomatic canon.
//!
//! # Data-driven rules (NOT hardcoded)
//!
//! Rules ship in a YAML manifest (default location:
//! `contracts/canon/guardrail_rules.yaml`). Each rule binds:
//!
//! - `attribute_path_glob` — `world.climate`, `world.*`, `*.allegiance`, …
//! - `predicate` — one of `equals` | `equals_any` | `forbids_value` |
//!   `forbids_regex` | `numeric_range`
//! - `severity` — `block` (default) | `warn`
//! - `axiom_id` + `reason` — forensic identifiers carried in the violation
//!
//! The YAML loader is **strict** — unknown fields fail-fast at startup,
//! never silently disable enforcement.
//!
//! # Backwards-compat with cycle 25
//!
//! Implements `dp_kernel::canon_cache::CanonGuardrail`. Production swaps
//! `NoOpGuardrail` (cycle 25 placeholder) for [`YamlGuardrail`] with no
//! caller changes.

use std::collections::HashMap;

use dp_kernel::canon_cache::{CanonGuardrail, GuardrailProposal, GuardrailViolation};
use serde::Deserialize;

/// Predicate enum — the supported rule expression types. Versioned by
/// adding new variants (NEVER mutate existing variant shapes — would
/// silently break the YAML loader).
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Predicate {
    /// Proposal's value MUST equal the axiom value (exact match on the
    /// canonical JSON bytes after re-encoding).
    Equals {
        /// Axiom value the proposed write must equal.
        value: serde_json::Value,
    },
    /// Proposal's value MUST equal ONE OF the axiom values.
    EqualsAny {
        /// Allowed axiom values.
        values: Vec<serde_json::Value>,
    },
    /// Proposal's value MUST NOT equal any of the forbidden values.
    ForbidsValue {
        /// Disallowed values.
        values: Vec<serde_json::Value>,
    },
    /// Proposal's value (string) MUST NOT match the regex. Matched
    /// case-insensitively.
    ForbidsRegex {
        /// Forbidden pattern (substring match for V1; full regex left
        /// for a future variant when an explicit regex dep is added —
        /// `serde_yaml` already pulls a heavy graph; we keep the V1
        /// surface to substring to avoid further bloat).
        pattern: String,
    },
    /// Proposal's value (number) MUST be in `[min, max]` inclusive.
    NumericRange {
        /// Minimum allowed value (inclusive).
        min: f64,
        /// Maximum allowed value (inclusive).
        max: f64,
    },
}

/// Severity of a rule.
#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    /// Reject the proposal with `GuardrailViolation`.
    #[default]
    Block,
    /// Surface as a warning but DO NOT reject. V1 cycle-27 still returns
    /// `Ok(())` for warn — warnings ride a different channel (metrics)
    /// added in a downstream cycle.
    Warn,
}

/// One rule. Matches by `attribute_path_glob` then applies `predicate`.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    /// Stable identifier for the axiom this rule enforces. Carried in
    /// the violation `reason` for forensic / governance audit.
    pub axiom_id: String,
    /// Human-readable explanation. Carried in violation `reason`.
    pub reason: String,
    /// Attribute path glob. `world.climate` matches exact;
    /// `world.*` matches one path segment after `world.`;
    /// `*.allegiance` matches any one segment before `.allegiance`.
    /// `**` (double-star) is RESERVED for future hierarchy match.
    pub attribute_path_glob: String,
    /// Optional `book_id` restriction. When None, applies to all books.
    /// Use UUID for book-specific axioms.
    #[serde(default)]
    pub book_id: Option<uuid::Uuid>,
    /// The predicate.
    pub predicate: Predicate,
    /// Severity (defaults to `block`).
    #[serde(default)]
    pub severity: Severity,
}

/// Root manifest shape (YAML).
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RuleSet {
    /// Manifest format version (currently 1).
    pub version: u32,
    /// Rules in declaration order. First matching rule wins.
    pub rules: Vec<Rule>,
}

/// Load + parse errors. Fail-fast — production NEVER silently disables
/// the guardrail.
#[derive(Debug, thiserror::Error)]
pub enum RuleSetLoadError {
    #[error("canon_guardrail: read manifest: {0}")]
    Io(#[from] std::io::Error),
    #[error("canon_guardrail: parse YAML: {0}")]
    Parse(#[from] serde_yaml::Error),
    #[error("canon_guardrail: unsupported manifest version {got} (expected 1)")]
    UnsupportedVersion { got: u32 },
    #[error("canon_guardrail: empty rule set (must declare at least one rule)")]
    Empty,
    #[error("canon_guardrail: duplicate axiom_id {0:?}")]
    DuplicateAxiomId(String),
    #[error("canon_guardrail: rule {axiom_id:?} has empty attribute_path_glob")]
    EmptyGlob { axiom_id: String },
}

impl RuleSet {
    /// Parses a YAML manifest from the supplied bytes.
    pub fn parse(bytes: &[u8]) -> Result<Self, RuleSetLoadError> {
        let raw: Self = serde_yaml::from_slice(bytes)?;
        raw.validate()
    }

    /// Loads a YAML manifest from disk.
    pub fn load(path: impl AsRef<std::path::Path>) -> Result<Self, RuleSetLoadError> {
        let bytes = std::fs::read(path)?;
        Self::parse(&bytes)
    }

    /// Structural validations.
    fn validate(self) -> Result<Self, RuleSetLoadError> {
        if self.version != 1 {
            return Err(RuleSetLoadError::UnsupportedVersion { got: self.version });
        }
        if self.rules.is_empty() {
            return Err(RuleSetLoadError::Empty);
        }
        let mut seen = HashMap::with_capacity(self.rules.len());
        for r in &self.rules {
            if r.attribute_path_glob.trim().is_empty() {
                return Err(RuleSetLoadError::EmptyGlob {
                    axiom_id: r.axiom_id.clone(),
                });
            }
            if seen.insert(r.axiom_id.clone(), ()).is_some() {
                return Err(RuleSetLoadError::DuplicateAxiomId(r.axiom_id.clone()));
            }
        }
        Ok(self)
    }
}

/// Production guardrail impl — drives a [`RuleSet`].
///
/// `Send + Sync` — safe to share across threads (RuleSet is immutable
/// after load).
pub struct YamlGuardrail {
    rules: RuleSet,
}

impl YamlGuardrail {
    /// Constructs from an in-memory rule set.
    pub fn new(rules: RuleSet) -> Self {
        Self { rules }
    }

    /// Number of rules loaded (for SRE metrics + smoke tests).
    pub fn rule_count(&self) -> usize {
        self.rules.rules.len()
    }

    fn match_first(&self, proposal: &GuardrailProposal) -> Option<&Rule> {
        for r in &self.rules.rules {
            if !glob_match(&r.attribute_path_glob, &proposal.attribute_path) {
                continue;
            }
            if let Some(scoped_book) = r.book_id {
                if scoped_book != proposal.book_id {
                    continue;
                }
            }
            return Some(r);
        }
        None
    }
}

impl CanonGuardrail for YamlGuardrail {
    fn check_proposed_write(
        &self,
        proposal: &GuardrailProposal,
    ) -> Result<(), GuardrailViolation> {
        let Some(rule) = self.match_first(proposal) else {
            // No matching rule → allow (open-by-default for unmapped
            // attribute paths; rules MUST be explicit per Q-L5-5).
            return Ok(());
        };
        if matches!(rule.severity, Severity::Warn) {
            // V1: warnings ride a side-channel; do not block.
            return Ok(());
        }
        if predicate_satisfied(&rule.predicate, &proposal.proposed_value) {
            Ok(())
        } else {
            Err(GuardrailViolation {
                book_id: proposal.book_id,
                attribute_path: proposal.attribute_path.clone(),
                proposed_value: proposal.proposed_value.clone(),
                reason: format!("[{}] {}", rule.axiom_id, rule.reason),
            })
        }
    }
}

/// Evaluates a predicate against the proposed value bytes.
///
/// Returns `true` when the proposal SATISFIES the axiom (i.e. is allowed);
/// `false` when it conflicts.
fn predicate_satisfied(pred: &Predicate, proposed: &[u8]) -> bool {
    // Decode the proposed bytes ONCE.
    let proposed_json: serde_json::Value = match serde_json::from_slice(proposed) {
        Ok(v) => v,
        Err(_) => {
            // Malformed proposal bytes can't be evaluated → treat as
            // violation (fail-closed; the guardrail must NEVER allow a
            // proposal it cannot parse).
            return false;
        }
    };
    match pred {
        Predicate::Equals { value } => json_eq(value, &proposed_json),
        Predicate::EqualsAny { values } => values.iter().any(|v| json_eq(v, &proposed_json)),
        Predicate::ForbidsValue { values } => !values.iter().any(|v| json_eq(v, &proposed_json)),
        Predicate::ForbidsRegex { pattern } => match proposed_json.as_str() {
            Some(s) => !contains_ci(s, pattern),
            // Non-string proposals are vacuously allowed for forbids_regex
            // (the rule is irrelevant to non-string values).
            None => true,
        },
        Predicate::NumericRange { min, max } => match proposed_json.as_f64() {
            Some(n) => n >= *min && n <= *max,
            None => false,
        },
    }
}

/// Canonical JSON equality — normalizes via re-encode so trailing
/// whitespace etc. don't cause false negatives.
fn json_eq(a: &serde_json::Value, b: &serde_json::Value) -> bool {
    let aa = serde_json::to_string(a).unwrap_or_default();
    let bb = serde_json::to_string(b).unwrap_or_default();
    aa == bb
}

/// Case-insensitive substring match.
fn contains_ci(haystack: &str, needle: &str) -> bool {
    haystack.to_lowercase().contains(&needle.to_lowercase())
}

/// Glob match for attribute paths. Supports:
///   - exact: `world.climate`
///   - single-segment wildcard: `world.*` (matches `world.climate`,
///     `world.geography` but NOT `world.climate.zone`)
///   - prefix wildcard: `*.allegiance` (matches `faction.allegiance`,
///     `npc.allegiance`)
///   - both ends: `*.allegiance.*` (not commonly used; V1 supports it
///     for completeness)
///
/// `**` (double-star, hierarchical) is reserved for future use; treated
/// as a literal in V1 (won't match anything realistic).
pub fn glob_match(glob: &str, path: &str) -> bool {
    let glob_parts: Vec<&str> = glob.split('.').collect();
    let path_parts: Vec<&str> = path.split('.').collect();
    if glob_parts.len() != path_parts.len() {
        return false;
    }
    for (g, p) in glob_parts.iter().zip(path_parts.iter()) {
        if *g == "*" {
            continue;
        }
        if g != p {
            return false;
        }
    }
    true
}

// ─────────────────────────────────────────────────────────────────────────
// Tests.
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    fn proposal(attr: &str, value: &[u8]) -> GuardrailProposal {
        GuardrailProposal {
            reality_id: Uuid::new_v4(),
            book_id: Uuid::new_v4(),
            attribute_path: attr.to_string(),
            proposed_value: value.to_vec(),
            source_event_type: "l3.event.recorded".to_string(),
        }
    }

    #[test]
    fn glob_match_exact() {
        assert!(glob_match("world.climate", "world.climate"));
        assert!(!glob_match("world.climate", "world.geography"));
        assert!(!glob_match("world.climate", "world.climate.zone"));
    }

    #[test]
    fn glob_match_single_segment_wildcard() {
        assert!(glob_match("world.*", "world.climate"));
        assert!(glob_match("world.*", "world.geography"));
        assert!(!glob_match("world.*", "faction.allegiance"));
        assert!(!glob_match("world.*", "world.climate.zone"));
    }

    #[test]
    fn glob_match_prefix_wildcard() {
        assert!(glob_match("*.allegiance", "faction.allegiance"));
        assert!(glob_match("*.allegiance", "npc.allegiance"));
        assert!(!glob_match("*.allegiance", "faction.banner"));
    }

    #[test]
    fn parse_rejects_version_zero() {
        let yaml = "version: 0\nrules: []\n";
        match RuleSet::parse(yaml.as_bytes()) {
            Err(RuleSetLoadError::UnsupportedVersion { got: 0 }) => {}
            other => panic!("expected UnsupportedVersion, got {other:?}"),
        }
    }

    #[test]
    fn parse_rejects_empty() {
        let yaml = "version: 1\nrules: []\n";
        match RuleSet::parse(yaml.as_bytes()) {
            Err(RuleSetLoadError::Empty) => {}
            other => panic!("expected Empty, got {other:?}"),
        }
    }

    #[test]
    fn parse_rejects_duplicate_axiom() {
        let yaml = r#"
version: 1
rules:
  - axiom_id: A
    reason: x
    attribute_path_glob: world.climate
    predicate:
      kind: equals
      value: "arid"
  - axiom_id: A
    reason: y
    attribute_path_glob: world.geography
    predicate:
      kind: equals
      value: "mountain"
"#;
        match RuleSet::parse(yaml.as_bytes()) {
            Err(RuleSetLoadError::DuplicateAxiomId(a)) if a == "A" => {}
            other => panic!("expected DuplicateAxiomId, got {other:?}"),
        }
    }

    #[test]
    fn parse_rejects_unknown_field() {
        let yaml = r#"
version: 1
rules:
  - axiom_id: A
    reason: x
    attribute_path_glob: world.climate
    predicate:
      kind: equals
      value: "arid"
    BOGUS_FIELD: 42
"#;
        match RuleSet::parse(yaml.as_bytes()) {
            Err(RuleSetLoadError::Parse(_)) => {}
            other => panic!("expected Parse error, got {other:?}"),
        }
    }

    #[test]
    fn parse_rejects_empty_glob() {
        let yaml = r#"
version: 1
rules:
  - axiom_id: A
    reason: x
    attribute_path_glob: ""
    predicate:
      kind: equals
      value: "arid"
"#;
        match RuleSet::parse(yaml.as_bytes()) {
            Err(RuleSetLoadError::EmptyGlob { axiom_id }) if axiom_id == "A" => {}
            other => panic!("expected EmptyGlob, got {other:?}"),
        }
    }

    fn rules_yaml_basic() -> &'static str {
        r#"
version: 1
rules:
  - axiom_id: A1_climate_immutable
    reason: world.climate is L1 axiomatic — cannot be modified
    attribute_path_glob: world.climate
    predicate:
      kind: equals
      values:
        - "arid"
        - "temperate"
        - "polar"
    severity: block
  - axiom_id: A1_climate_immutable
    reason: dup test  # would dup but axiom_ids are unique
    attribute_path_glob: world.geography
    predicate:
      kind: equals
      value: "mountain"
"#
    }

    fn rules_yaml_for_test() -> &'static str {
        r#"
version: 1
rules:
  - axiom_id: A1_climate_arid
    reason: world.climate is L1 axiomatic — must be 'arid'
    attribute_path_glob: world.climate
    predicate:
      kind: equals
      value: "arid"
  - axiom_id: A2_allegiance_forbidden
    reason: forbidden allegiance values
    attribute_path_glob: faction.allegiance
    predicate:
      kind: forbids_value
      values:
        - "chaos"
        - "anarchy"
  - axiom_id: A3_population_range
    reason: city population must be 0..10000000
    attribute_path_glob: region.*
    predicate:
      kind: numeric_range
      min: 0.0
      max: 10000000.0
  - axiom_id: A4_no_profanity
    reason: lore must not contain profanity tokens
    attribute_path_glob: lore.intro
    predicate:
      kind: forbids_regex
      pattern: "badword"
  - axiom_id: A5_equals_any
    reason: rule.combat must be one of allowed schemes
    attribute_path_glob: rule.combat
    predicate:
      kind: equals_any
      values:
        - "d20"
        - "fudge"
"#
    }

    #[test]
    fn parse_basic_yaml() {
        let _ = RuleSet::parse(rules_yaml_basic().as_bytes())
            .expect_err("expected duplicate axiom rejection");
    }

    #[test]
    fn yaml_guardrail_allows_matching_equals() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);
        assert_eq!(g.rule_count(), 5);

        // world.climate = "arid" → allowed.
        let p = proposal("world.climate", b"\"arid\"");
        g.check_proposed_write(&p).expect("arid allowed");
    }

    #[test]
    fn yaml_guardrail_rejects_violating_equals() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        // world.climate = "tropical" → rejected.
        let p = proposal("world.climate", b"\"tropical\"");
        let err = g.check_proposed_write(&p).expect_err("tropical rejected");
        assert!(err.reason.contains("A1_climate_arid"), "violation reason missing axiom_id: {err:?}");
    }

    #[test]
    fn yaml_guardrail_rejects_forbids_value() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        let p = proposal("faction.allegiance", b"\"chaos\"");
        let err = g.check_proposed_write(&p).expect_err("chaos rejected");
        assert!(err.reason.contains("A2_allegiance_forbidden"));

        // Allowed value.
        let p = proposal("faction.allegiance", b"\"law\"");
        g.check_proposed_write(&p).expect("law allowed");
    }

    #[test]
    fn yaml_guardrail_numeric_range() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        let p = proposal("region.population", b"5000000");
        g.check_proposed_write(&p).expect("within range");

        let p = proposal("region.population", b"99999999");
        let err = g.check_proposed_write(&p).expect_err("out of range");
        assert!(err.reason.contains("A3_population_range"));
    }

    #[test]
    fn yaml_guardrail_forbids_regex_case_insensitive() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        let p = proposal("lore.intro", b"\"This is BADWORD content\"");
        let err = g.check_proposed_write(&p).expect_err("badword rejected (CI)");
        assert!(err.reason.contains("A4_no_profanity"));

        let p = proposal("lore.intro", b"\"This is clean content\"");
        g.check_proposed_write(&p).expect("clean allowed");
    }

    #[test]
    fn yaml_guardrail_equals_any() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        let p = proposal("rule.combat", b"\"d20\"");
        g.check_proposed_write(&p).expect("d20 allowed");

        let p = proposal("rule.combat", b"\"d6\"");
        let err = g.check_proposed_write(&p).expect_err("d6 not in allowed set");
        assert!(err.reason.contains("A5_equals_any"));
    }

    #[test]
    fn yaml_guardrail_unmapped_path_allowed() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        // No rule matches `random.unmapped.path` → allowed.
        let p = proposal("random.unmapped.path", b"\"anything\"");
        g.check_proposed_write(&p).expect("unmapped path allowed");
    }

    #[test]
    fn yaml_guardrail_warn_severity_does_not_block_v1() {
        let yaml = r#"
version: 1
rules:
  - axiom_id: WARN_ONLY
    reason: warn-only rule
    attribute_path_glob: world.climate
    predicate:
      kind: equals
      value: "arid"
    severity: warn
"#;
        let rs = RuleSet::parse(yaml.as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);
        let p = proposal("world.climate", b"\"tropical\"");
        g.check_proposed_write(&p).expect("warn does not block in V1");
    }

    #[test]
    fn malformed_proposed_bytes_fail_closed() {
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g = YamlGuardrail::new(rs);

        let p = proposal("world.climate", b"not-valid-json");
        let _err = g.check_proposed_write(&p).expect_err("fail-closed on malformed");
    }

    #[test]
    fn backwards_compat_with_cycle25_trait() {
        // Cycle 25 wired the trait into RPC handlers using
        // `dp_kernel::canon_cache::CanonGuardrail`. Cycle 27 swaps the
        // concrete impl. This test asserts the swap works by binding
        // YamlGuardrail as `Box<dyn CanonGuardrail>`.
        let rs = RuleSet::parse(rules_yaml_for_test().as_bytes()).unwrap();
        let g: Box<dyn CanonGuardrail> = Box::new(YamlGuardrail::new(rs));
        let p = proposal("world.climate", b"\"arid\"");
        g.check_proposed_write(&p).expect("trait-object call works");
    }
}
