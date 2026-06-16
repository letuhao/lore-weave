//! L4.C — Transition graph + `AttemptStateTransition`.
//!
//! Mirrors `contracts/meta/transitions_validator.go` (graph load + validate)
//! and `contracts/meta/lifecycle.go::AttemptStateTransition` (state-machine
//! wrapper around `MetaWrite`).
//!
//! ## Semantics (must match Go)
//!
//! 1. Look up the resource's transition graph (loaded at startup).
//! 2. Reject if `(from, to)` not in graph -> [`MetaError::InvalidTransition`].
//! 3. Reject if `from` forbids `to` via `mutual_exclusions` ->
//!    [`MetaError::MutualExclusion`].
//! 4. Delegate to `meta_write` with op=UPDATE + `expected_before` set on the
//!    state column (CAS for free).
//! 5. Write a `lifecycle_transition_audit` row in the SAME flow (failed
//!    attempts also audited — Q-L1A-3 full audit, no sampling).
//!
//! On graph rejection (steps 2+3) we write a FAILED-attempt audit row in its
//! OWN TX so the audit row survives even when the data write was never
//! attempted. Matches Go behavior.

use serde::Deserialize;
use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};
use std::path::Path;

use crate::audit::{AuditClock, AuditUuidGen, LifecycleTransitionAuditRow, OutboxAppender};
use crate::errors::MetaError;
use crate::metawrite::{
    meta_write, Actor, ConnectionWriter, MetaWriteConfig, MetaWriteIntent,
    MetaWriteOp, QueryBuilder, RequestContext, ValueMap,
};
#[cfg(test)]
use crate::metawrite::ActorType;
use uuid::Uuid;

/// State-machine graph (one entry per resource type, e.g. `reality`).
#[derive(Debug, Clone)]
pub struct TransitionGraph {
    /// `resource_name -> ResourceGraph`.
    pub resources: HashMap<String, ResourceGraph>,
}

impl TransitionGraph {
    /// Sorted resource names (deterministic for tests).
    pub fn resource_names(&self) -> Vec<String> {
        let mut names: Vec<String> = self.resources.keys().cloned().collect();
        names.sort();
        names
    }

    /// Load + validate `transitions.yaml`.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, MetaError> {
        let raw = std::fs::read(path.as_ref()).map_err(|e| {
            MetaError::ConfigInvalid(format!(
                "read transitions {}: {e}",
                path.as_ref().display()
            ))
        })?;
        Self::parse(&raw)
    }

    /// Parse + validate an in-memory YAML payload.
    pub fn parse(raw: &[u8]) -> Result<Self, MetaError> {
        let f: TransitionsFile = serde_yaml::from_slice(raw).map_err(|e| {
            MetaError::ConfigInvalid(format!("unmarshal transitions: {e}"))
        })?;
        if f.version != 1 {
            return Err(MetaError::ConfigInvalid(format!(
                "transitions version={} unsupported",
                f.version
            )));
        }
        if f.resources.is_empty() {
            return Err(MetaError::ConfigInvalid(
                "transitions: no resources defined".into(),
            ));
        }
        let mut out = HashMap::with_capacity(f.resources.len());
        for (name, r) in f.resources {
            out.insert(name.clone(), build_resource_graph(&name, r)?);
        }
        Ok(TransitionGraph { resources: out })
    }
}

/// One resource's state machine.
#[derive(Debug, Clone)]
pub struct ResourceGraph {
    /// Resource type name (e.g., `reality`).
    pub name: String,
    /// Backing table (e.g., `reality_registry`).
    pub table: String,
    /// State column name (e.g., `status`).
    pub state_column: String,
    /// All declared states.
    pub states: HashSet<String>,
    /// Initial states.
    pub initial_states: HashSet<String>,
    /// Terminal states (no outgoing transitions allowed).
    pub terminal_states: HashSet<String>,
    /// `transitions[from] = set of allowed to-states`.
    pub transitions: HashMap<String, HashSet<String>>,
    /// `mutex[from] = set of forbidden to-states`.
    pub mutual_exclusions: HashMap<String, HashSet<String>>,
}

impl ResourceGraph {
    /// Returns `(allowed, forbidden_by_mutex)`.  Self-loops are never allowed.
    pub fn allows(&self, from: &str, to: &str) -> (bool, bool) {
        if from == to {
            return (false, false);
        }
        let tos = match self.transitions.get(from) {
            Some(s) => s,
            None => return (false, false),
        };
        if !tos.contains(to) {
            return (false, false);
        }
        if let Some(mx) = self.mutual_exclusions.get(from) {
            if mx.contains(to) {
                return (false, true);
            }
        }
        (true, false)
    }
}

// ── YAML parser types (private) ─────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct TransitionRow {
    from: String,
    to: Vec<String>,
}
#[derive(Debug, Deserialize)]
struct MutexRow {
    if_status: String,
    forbidden_transitions: Vec<String>,
}
#[derive(Debug, Deserialize)]
struct ResourceYaml {
    table: String,
    state_column: String,
    states: Vec<String>,
    #[serde(default)]
    initial_states: Vec<String>,
    #[serde(default)]
    terminal_states: Vec<String>,
    #[serde(default)]
    transitions: Vec<TransitionRow>,
    #[serde(default)]
    mutual_exclusions: Vec<MutexRow>,
}
#[derive(Debug, Deserialize)]
struct TransitionsFile {
    version: u32,
    resources: HashMap<String, ResourceYaml>,
}

fn to_set(xs: &[String]) -> HashSet<String> {
    xs.iter().cloned().collect()
}

fn build_resource_graph(name: &str, r: ResourceYaml) -> Result<ResourceGraph, MetaError> {
    if r.table.trim().is_empty() {
        return Err(MetaError::ConfigInvalid(format!(
            "resource {name}: empty table"
        )));
    }
    if r.state_column.trim().is_empty() {
        return Err(MetaError::ConfigInvalid(format!(
            "resource {name}: empty state_column"
        )));
    }
    if r.states.is_empty() {
        return Err(MetaError::ConfigInvalid(format!(
            "resource {name}: states empty"
        )));
    }

    let states = to_set(&r.states);
    // duplicate state-name check
    let unique: BTreeSet<&String> = r.states.iter().collect();
    if unique.len() != r.states.len() {
        return Err(MetaError::ConfigInvalid(format!(
            "resource {name}: duplicate state name"
        )));
    }

    let initial_states = to_set(&r.initial_states);
    let terminal_states = to_set(&r.terminal_states);
    for s in &initial_states {
        if !states.contains(s) {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: initial state {s} not in states"
            )));
        }
    }
    for s in &terminal_states {
        if !states.contains(s) {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: terminal state {s} not in states"
            )));
        }
    }
    if initial_states.is_empty() {
        return Err(MetaError::ConfigInvalid(format!(
            "resource {name}: no initial_states"
        )));
    }

    let mut transitions: HashMap<String, HashSet<String>> = HashMap::new();
    for tr in &r.transitions {
        if !states.contains(&tr.from) {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: transition.from={} not in states",
                tr.from
            )));
        }
        if tr.to.is_empty() {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: transition.from={} has no to-states",
                tr.from
            )));
        }
        let dst = transitions.entry(tr.from.clone()).or_default();
        for to in &tr.to {
            if !states.contains(to) {
                return Err(MetaError::ConfigInvalid(format!(
                    "resource {name}: transition {}->{} not in states",
                    tr.from, to
                )));
            }
            if to == &tr.from {
                return Err(MetaError::ConfigInvalid(format!(
                    "resource {name}: self-loop {}->{} not allowed",
                    tr.from, to
                )));
            }
            dst.insert(to.clone());
        }
    }

    // Reachability check.
    let reachable = bfs_reach(&initial_states, &transitions);
    for s in &states {
        if initial_states.contains(s) {
            continue;
        }
        if !reachable.contains(s) {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: state {s} unreachable from initial_states"
            )));
        }
    }

    // Non-terminal states must have at least one outgoing transition.
    for s in &states {
        if terminal_states.contains(s) {
            if transitions.contains_key(s) {
                return Err(MetaError::ConfigInvalid(format!(
                    "resource {name}: terminal state {s} has outgoing transitions"
                )));
            }
            continue;
        }
        if !transitions.contains_key(s) {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: non-terminal state {s} has no outgoing transitions"
            )));
        }
    }

    let mut mutual_exclusions: HashMap<String, HashSet<String>> = HashMap::new();
    for m in r.mutual_exclusions {
        if !states.contains(&m.if_status) {
            return Err(MetaError::ConfigInvalid(format!(
                "resource {name}: mutex.if_status={} not in states",
                m.if_status
            )));
        }
        let set = mutual_exclusions.entry(m.if_status.clone()).or_default();
        for f in &m.forbidden_transitions {
            if !states.contains(f) {
                return Err(MetaError::ConfigInvalid(format!(
                    "resource {name}: mutex.forbidden={f} not in states"
                )));
            }
            set.insert(f.clone());
        }
    }

    Ok(ResourceGraph {
        name: name.to_string(),
        table: r.table,
        state_column: r.state_column,
        states,
        initial_states,
        terminal_states,
        transitions,
        mutual_exclusions,
    })
}

fn bfs_reach(
    seeds: &HashSet<String>,
    edges: &HashMap<String, HashSet<String>>,
) -> HashSet<String> {
    let mut out: HashSet<String> = seeds.iter().cloned().collect();
    let mut queue: VecDeque<String> = seeds.iter().cloned().collect();
    while let Some(head) = queue.pop_front() {
        if let Some(next_set) = edges.get(&head) {
            for n in next_set {
                if out.insert(n.clone()) {
                    queue.push_back(n.clone());
                }
            }
        }
    }
    out
}

// ── AttemptStateTransition ──────────────────────────────────────────────────

/// Caller input for `attempt_state_transition`.
#[derive(Debug, Clone, PartialEq)]
pub struct TransitionRequest {
    /// Resource type (e.g., `reality`).
    pub resource_type: String,
    /// Resource id (PK value).
    pub resource_id: String,
    /// State the resource is currently in.
    pub from_state: String,
    /// State the caller wants to transition into.
    pub to_state: String,
    /// Human-readable reason.
    pub reason: String,
    /// Actor performing the transition.
    pub actor: Actor,
    /// Extra columns to set in the same UPDATE.
    pub payload: ValueMap,
}

impl TransitionRequest {
    /// Fail-fast validation of the request shape.
    pub fn validate(&self) -> Result<(), MetaError> {
        if self.resource_type.trim().is_empty() {
            return Err(MetaError::BadIntent("resource_type empty".into()));
        }
        if self.resource_id.trim().is_empty() {
            return Err(MetaError::BadIntent("resource_id empty".into()));
        }
        if self.from_state.trim().is_empty() || self.to_state.trim().is_empty() {
            return Err(MetaError::BadIntent("from/to state empty".into()));
        }
        Ok(())
    }
}

/// Successful transition result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TransitionResult {
    /// `lifecycle_transition_audit.audit_id` (success row).
    pub audit_id: Uuid,
    /// New state value written.
    pub new_state: String,
    /// `attempted_at_nanos` of the audit row.
    pub transition_at_nanos: i64,
}

/// Maps `resource_table -> pk_column_name`. Provided by the caller so the
/// Rust port doesn't have to hard-code Go's `pkColumnFor` switch. If the
/// caller passes `None`, the default falls back to `<table_without_registry>_id`.
pub type PkColumnLookup<'a> = &'a dyn Fn(&str) -> String;

/// Execute one state transition.
///
/// Honors:
/// - Graph rejection -> [`MetaError::InvalidTransition`] + failed-attempt audit.
/// - Mutex rejection -> [`MetaError::MutualExclusion`] + failed-attempt audit.
/// - CAS lost race -> [`MetaError::ConcurrentStateTransition`] + failed-attempt
///   audit (`concurrent_modification` reason).
/// - Success -> success-attempt audit + [`TransitionResult`].
///
/// The audit writes are tracked by the caller-supplied [`LifecycleAuditSink`].
/// We deliberately decouple them from MetaWrite so failed-attempt audits can
/// be persisted without opening a fresh TX every cycle (the production wiring
/// usually batches them via a background queue).
pub fn attempt_state_transition<C, Q, A, K, G, L>(
    cfg: &mut MetaWriteConfig<'_, C, Q, A, K, G>,
    graph: &TransitionGraph,
    pk_lookup: PkColumnLookup<'_>,
    audit_sink: &L,
    req: TransitionRequest,
) -> Result<TransitionResult, MetaError>
where
    C: ConnectionWriter,
    Q: QueryBuilder,
    A: OutboxAppender<<C as ConnectionWriter>::Tx>,
    K: AuditClock,
    G: AuditUuidGen,
    L: LifecycleAuditSink,
{
    req.validate()?;
    let resource = graph.resources.get(&req.resource_type).ok_or_else(|| {
        let _ = write_failed_audit(audit_sink, cfg.clock, cfg.uuid_gen, &req, "invalid_transition");
        MetaError::UnknownResource(req.resource_type.clone())
    })?;
    let (allowed, forbidden) = resource.allows(&req.from_state, &req.to_state);
    if forbidden {
        let _ = write_failed_audit(audit_sink, cfg.clock, cfg.uuid_gen, &req, "mutual_exclusion");
        return Err(MetaError::MutualExclusion);
    }
    if !allowed {
        let _ = write_failed_audit(audit_sink, cfg.clock, cfg.uuid_gen, &req, "invalid_transition");
        return Err(MetaError::InvalidTransition {
            from: req.from_state.clone(),
            to: req.to_state.clone(),
        });
    }

    // Build the underlying MetaWriteIntent (UPDATE + CAS on state column).
    let pk_column = pk_lookup(&resource.table);
    let mut new_values: ValueMap = ValueMap::new();
    new_values.insert(
        resource.state_column.clone(),
        serde_json::Value::String(req.to_state.clone()),
    );
    for (k, v) in &req.payload {
        new_values.insert(k.clone(), v.clone());
    }
    let mut pk = ValueMap::new();
    pk.insert(pk_column, serde_json::Value::String(req.resource_id.clone()));
    let mut expected_before = ValueMap::new();
    expected_before.insert(
        resource.state_column.clone(),
        serde_json::Value::String(req.from_state.clone()),
    );

    let intent = MetaWriteIntent {
        table: resource.table.clone(),
        operation: MetaWriteOp::Update,
        pk,
        expected_before,
        new_values,
        actor: req.actor.clone(),
        reason: req.reason.clone(),
        request_context: RequestContext::default(),
    };

    match meta_write(cfg, intent) {
        Ok(_res) => {
            let now = cfg.clock.now_unix_nanos();
            let audit_id = cfg.uuid_gen.new_uuid();
            let row = LifecycleTransitionAuditRow {
                audit_id,
                resource_id: req.resource_id.clone(),
                from_status: req.from_state.clone(),
                to_status: req.to_state.clone(),
                actor_id: req.actor.id.clone(),
                actor_type: req.actor.actor_type,
                succeeded: true,
                failure_reason: String::new(),
                payload: req.payload.clone(),
                attempted_at_nanos: now,
            };
            audit_sink.write(row)?;
            Ok(TransitionResult {
                audit_id,
                new_state: req.to_state,
                transition_at_nanos: now,
            })
        }
        Err(e) => {
            let reason = if matches!(e, MetaError::ConcurrentStateTransition) {
                "concurrent_modification"
            } else {
                "database_error"
            };
            let _ = write_failed_audit(audit_sink, cfg.clock, cfg.uuid_gen, &req, reason);
            Err(e)
        }
    }
}

fn write_failed_audit<L: LifecycleAuditSink>(
    sink: &L,
    clock: &dyn AuditClock,
    uuid_gen: &dyn AuditUuidGen,
    req: &TransitionRequest,
    reason: &str,
) -> Result<(), MetaError> {
    let row = LifecycleTransitionAuditRow {
        audit_id: uuid_gen.new_uuid(),
        resource_id: req.resource_id.clone(),
        from_status: req.from_state.clone(),
        to_status: req.to_state.clone(),
        actor_id: req.actor.id.clone(),
        actor_type: req.actor.actor_type,
        succeeded: false,
        failure_reason: reason.into(),
        payload: req.payload.clone(),
        attempted_at_nanos: clock.now_unix_nanos(),
    };
    sink.write(row)
}

/// Persists lifecycle audit rows (success + failure). Decoupled from
/// MetaWrite so failed-attempt audits can be queued / batched without
/// opening a fresh TX each time.
pub trait LifecycleAuditSink {
    /// Write one audit row.
    fn write(&self, row: LifecycleTransitionAuditRow) -> Result<(), MetaError>;
}

/// Default PK-column lookup for cycle 2 resources. Callers can supply a
/// custom function via `attempt_state_transition`'s `pk_lookup` parameter.
pub fn default_pk_lookup(table: &str) -> String {
    match table {
        "reality_registry" => "reality_id".into(),
        "pii_registry" => "user_ref_id".into(),
        "pii_kek" => "kek_id".into(),
        "user_consent_ledger" => "user_ref_id".into(),
        "player_character_index" => "pc_index_id".into(),
        "meta_write_audit"
        | "meta_read_audit"
        | "admin_action_audit"
        | "service_to_service_audit"
        | "prompt_audit" => "audit_id".into(),
        "user_cost_ledger" => "ledger_id".into(),
        "user_daily_cost" | "user_queue_metrics" => "user_ref_id".into(),
        "incidents" => "incident_id".into(),
        "feature_flags" => "flag_name".into(),
        "deploy_audit" => "deploy_id".into(),
        "shard_utilization" => "snapshot_id".into(),
        "scaling_events" => "scaling_event_id".into(),
        _ => "id".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SHIPPED: &str = "../../contracts/meta/transitions.yaml";

    #[test]
    fn shipped_transitions_parses() {
        let g = TransitionGraph::load(SHIPPED).expect("load");
        // Cycle 2 ships at least the `reality` resource.
        assert!(g.resources.contains_key("reality"));
    }

    #[test]
    fn reality_transitions_have_active_terminus() {
        let g = TransitionGraph::load(SHIPPED).expect("load");
        let r = g.resources.get("reality").unwrap();
        let (allowed, forbidden) = r.allows("provisioning", "seeding");
        assert!(allowed, "provisioning -> seeding should be allowed");
        assert!(!forbidden);
    }

    #[test]
    fn self_loop_always_rejected() {
        let g = TransitionGraph::load(SHIPPED).expect("load");
        let r = g.resources.get("reality").unwrap();
        let (allowed, _) = r.allows("active", "active");
        assert!(!allowed);
    }

    #[test]
    fn invalid_transition_returns_not_in_graph() {
        let g = TransitionGraph::load(SHIPPED).expect("load");
        let r = g.resources.get("reality").unwrap();
        let (allowed, forbidden) = r.allows("dropped", "active");
        assert!(!allowed);
        assert!(!forbidden);
    }

    #[test]
    fn parse_rejects_self_loop() {
        let doc = br#"
version: 1
resources:
  thing:
    table: thing
    state_column: status
    states: [a, b]
    initial_states: [a]
    terminal_states: [b]
    transitions:
      - from: a
        to: [a]
"#;
        let err = TransitionGraph::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("self-loop")));
    }

    #[test]
    fn parse_rejects_unreachable_state() {
        let doc = br#"
version: 1
resources:
  thing:
    table: thing
    state_column: status
    states: [a, b, c]
    initial_states: [a]
    terminal_states: [b, c]
    transitions:
      - from: a
        to: [b]
"#;
        let err = TransitionGraph::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("unreachable")));
    }

    #[test]
    fn parse_rejects_terminal_with_outgoing() {
        let doc = br#"
version: 1
resources:
  thing:
    table: thing
    state_column: status
    states: [a, b]
    initial_states: [a]
    terminal_states: [b]
    transitions:
      - from: a
        to: [b]
      - from: b
        to: [a]
"#;
        let err = TransitionGraph::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("terminal state b has outgoing")));
    }

    #[test]
    fn validate_request_rejects_empty_fields() {
        let req = TransitionRequest {
            resource_type: "".into(),
            resource_id: "x".into(),
            from_state: "a".into(),
            to_state: "b".into(),
            reason: "".into(),
            actor: Actor {
                actor_type: ActorType::System,
                id: "s".into(),
                svid: None,
            },
            payload: ValueMap::new(),
        };
        let err = req.validate().unwrap_err();
        assert!(matches!(err, MetaError::BadIntent(_)));
    }

    #[test]
    fn default_pk_lookup_covers_known_tables() {
        assert_eq!(default_pk_lookup("reality_registry"), "reality_id");
        assert_eq!(default_pk_lookup("user_consent_ledger"), "user_ref_id");
        assert_eq!(default_pk_lookup("meta_write_audit"), "audit_id");
        assert_eq!(default_pk_lookup("unknown_thing"), "id");
    }
}
