//! Admission — commit-service's gate between the bus and the island
//! (CS-A2: "commit-service owns admission; sim-core owns resolution").
//!
//! S3a implements the stages that exist and **records `NotRun` for every
//! registered stage that doesn't** (plan D6 — the conformance-runner verdict
//! discipline; a skipped stage is a declared absence in the RECORD, never a
//! silent bypass). Stage list = `_boundaries/03_validator_pipeline_slots.md`;
//! per-category subsets = `15_commit_service.md` §7b.2 (their registration
//! rides the REC-53 bundle).

use std::collections::BTreeMap;
use std::time::{Duration, Instant};

use sim_core::{Class, EntityId, Fallback, Gen, InputId, Producer, QueuedInput, Seq};

use crate::domain::CombatDomain;
use crate::vocabulary::Vocabulary;

/// Per-stage verdict — {pass|fail|notrun|skip}, the S1-runner contract.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Verdict {
    Pass,
    Fail(String),
    /// Stage is registered but not built yet — recorded, never silent.
    NotRun,
    /// Stage doesn't apply to this category (declared subset).
    Skip,
}

/// A T6 proposal as carried on the bus (flat fields → parsed).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Proposal {
    /// EVT-L3 idempotency triple, parts 1..3.
    pub producer_service: String,
    pub proposal_id: String,
    pub target_channel: i64,
    /// The AGT-A6 Decision this proposal carries (executes nothing).
    pub decision: serde_json::Value,
    /// Acting entity (island-side id).
    pub actor: u64,
    /// Offered candidates at decision time — (entity id, token) pairs; the
    /// validation set for `strike.target` (THR-A4 / REC-79).
    pub candidates: Vec<(u64, String)>,
    #[serde(default = "default_category")]
    pub event_category: String,
}

fn default_category() -> String {
    "T6".into()
}

/// EVT-L3 dedup cache — commit-service-owned, 60 s TTL (bus layer; the
/// kernel seen-set stays the second, step-time layer).
pub struct DedupCache {
    ttl: Duration,
    seen: BTreeMap<(String, String, i64), Instant>,
}

impl DedupCache {
    pub fn new(ttl: Duration) -> Self {
        Self { ttl, seen: BTreeMap::new() }
    }

    /// Returns false iff the triple is a live duplicate.
    pub fn insert(&mut self, key: (String, String, i64)) -> bool {
        let now = Instant::now();
        self.seen.retain(|_, t| now.duration_since(*t) < self.ttl);
        match self.seen.get(&key) {
            Some(_) => false,
            None => {
                self.seen.insert(key, now);
                true
            }
        }
    }

    pub fn len(&self) -> usize {
        self.seen.len()
    }

    pub fn is_empty(&self) -> bool {
        self.seen.is_empty()
    }
}

/// The admission record: every registered stage's verdict + the outcome.
/// CS-A4: both rejection kinds are recorded; neither is silent.
#[derive(Debug)]
pub struct AdmissionRecord {
    pub stages: Vec<(&'static str, Verdict)>,
    pub outcome: AdmissionOutcome,
}

#[derive(Debug)]
pub enum AdmissionOutcome {
    /// Validated → a stamped ingress item for the island (CS-A3: from here
    /// it is an ordinary input under SC-A1 re-validation).
    Admitted(Box<QueuedInput<CombatDomain>>),
    /// EVT-V4-class rejection at a named stage. Ack-on-reject (EVT-L2) —
    /// the proposal is resolved, never retried.
    Rejected { stage: &'static str, reason: String },
}

/// sim-core `InputId` = 128-bit hash of the EVT-L3 triple (the documented
/// S3 hook, `sim-core/src/types.rs:19-22`).
pub fn input_id_for(triple: &(String, String, i64)) -> InputId {
    let mut h = blake3::Hasher::new();
    h.update(triple.0.as_bytes());
    h.update(b"\x00");
    h.update(triple.1.as_bytes());
    h.update(b"\x00");
    h.update(&triple.2.to_le_bytes());
    let bytes = h.finalize();
    let mut b16 = [0u8; 16];
    b16.copy_from_slice(&bytes.as_bytes()[..16]);
    InputId(u128::from_le_bytes(b16))
}

/// Run the T6 (LLM-proposal) admission subset over one bus message body.
pub fn admit_t6(
    raw_json: &str,
    vocab: &Vocabulary,
    dedup: &mut DedupCache,
) -> AdmissionRecord {
    let mut stages: Vec<(&'static str, Verdict)> = Vec::new();

    // ── stage 0: schema ──
    let proposal: Proposal = match serde_json::from_str(raw_json) {
        Ok(p) => {
            stages.push(("schema", Verdict::Pass));
            p
        }
        Err(e) => {
            stages.push(("schema", Verdict::Fail(e.to_string())));
            return AdmissionRecord {
                stages,
                outcome: AdmissionOutcome::Rejected { stage: "schema", reason: e.to_string() },
            };
        }
    };

    // ── hot-path gate: idempotency (EVT-L3 triple) ──
    let triple = (
        proposal.producer_service.clone(),
        proposal.proposal_id.clone(),
        proposal.target_channel,
    );
    if !dedup.insert(triple.clone()) {
        stages.push(("idempotency", Verdict::Fail("duplicate within window".into())));
        return AdmissionRecord {
            stages,
            outcome: AdmissionOutcome::Rejected {
                stage: "idempotency",
                reason: format!("duplicate proposal {} within dedup window", proposal.proposal_id),
            },
        };
    }
    stages.push(("idempotency", Verdict::Pass));

    // ── decision validation against the closed vocabulary (the schema
    //    stage of the DECISION itself — AGT-A2; REC-79 id/state split) ──
    let candidates: Vec<(EntityId, String)> = proposal
        .candidates
        .iter()
        .map(|(id, tok)| (EntityId(*id), tok.clone()))
        .collect();
    let tool = proposal
        .decision
        .get("tool")
        .and_then(|t| t.as_str())
        .unwrap_or_default()
        .to_string();
    let params = proposal
        .decision
        .get("params")
        .cloned()
        .unwrap_or(serde_json::json!({}));
    let payload = match vocab.validate(
        EntityId(proposal.actor),
        &tool,
        &params.to_string(),
        &candidates,
    ) {
        Ok(p) => {
            stages.push(("decision-vocabulary", Verdict::Pass));
            p
        }
        Err(reject) => {
            stages.push(("decision-vocabulary", Verdict::Fail(reject.to_string())));
            return AdmissionRecord {
                stages,
                outcome: AdmissionOutcome::Rejected {
                    stage: "decision-vocabulary",
                    reason: reject.to_string(),
                },
            };
        }
    };

    // ── registered-but-unbuilt stages: recorded NotRun, in pipeline order ──
    for stage in [
        "capability",
        "a5-intent",
        "a6-sanitize",
        "structural-validators",
        "lex",
        "heresy",
        "a6-output",
        "canon-drift",
        "causal-ref-integrity",
        "world-rule",
    ] {
        stages.push((stage, Verdict::NotRun));
    }

    AdmissionRecord {
        stages,
        outcome: AdmissionOutcome::Admitted(Box::new(QueuedInput {
            seq: Seq(u64::MAX), // stamped at island admission
            input_id: input_id_for(&triple),
            class: Class::B,
            source: Producer::LlmDecision,
            payload,
            preconditions: vec![],
            on_invalid: Fallback::Substitute(vocab.fallback_payload(EntityId(proposal.actor))),
            admitted_gen: Gen(0), // re-stamped by Island::submit
            deadline: None,
        })),
    }
}
