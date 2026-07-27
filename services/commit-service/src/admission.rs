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

use sim_core::{Admitted, Class, EntityId, Fallback, Gen, InputId, Producer, QueuedInput, Seq};

use crate::domain::CombatDomain;
use crate::producer::ProducerRegistry;
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
}

// `event_category` is deliberately ABSENT (PID-D5). It used to ride the wire
// and SELECT THE VALIDATOR SUBSET, so a proposal could elect its own trust
// tier — an LLM-originated message writing "T1" skipped the entire LLM-safety
// stage set. The category is now derived from the verified producer
// (`producer::ProducerRegistry::verify_and_derive`). A field that is not on
// the wire cannot be forged; the same reason `TurnSubmit` carries no `actor`
// (CWC-D3).

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
    /// Validated → an [`Admitted`] ingress token for the island (CS-A3: from
    /// here it is an ordinary input under SC-A1 re-validation).
    ///
    /// IAS-D3 — carrying the TOKEN rather than a bare `QueuedInput` makes
    /// this module the sole minter in the service: `Island::submit` accepts
    /// nothing else, and `Admitted`'s field is private, so a caller cannot
    /// assemble one. Feeding the island now requires having called admission,
    /// which is a property of the type rather than of reviewer attention.
    Admitted(Box<Admitted<CombatDomain>>),
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

/// The EVT category a proposal declares. `15` §7b.2's three origin classes:
/// the LLM's proposal runs the FULL pipeline; the player's runs the reduced
/// player subset (the player is NOT an EVT-A7 trusted producer —
/// commit-service validates on their behalf).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Category {
    /// EVT-T6 Proposal — LLM output.
    T6,
    /// EVT-T1 Submitted — player input via the gateway/room.
    T1,
}

impl Category {
    // `parse(&str) -> Category` USED to live here and is deliberately gone.
    // Its only caller read `event_category` off the wire, and a string→tier
    // mapping sitting available is an invitation to re-add the field. The
    // category now has exactly one source: `verify_and_derive` (PID-D3).

    /// The per-category stage table (plan D4). The distinction is the point:
    /// **`Skip` = this category declares the stage inapplicable; `NotRun` =
    /// the stage is owed and unbuilt.** Collapsing them would hide real debt
    /// behind a legitimate-looking absence — the whole reason D6 records
    /// stages at all.
    fn stage_verdicts(self) -> &'static [(&'static str, bool)] {
        match self {
            // (stage, applicable?) — applicable ⇒ NotRun (owed), else Skip.
            Self::T6 => &[
                ("capability", true),
                ("a5-intent", true),
                ("a6-sanitize", true),
                ("structural-validators", true),
                ("lex", true),
                ("heresy", true),
                ("a6-output", true),
                ("canon-drift", true),
                ("causal-ref-integrity", true),
                ("world-rule", true),
            ],
            // The player's tool-call is not LLM OUTPUT, so the A5/A6 and
            // canon-drift stages do not apply to it; world-rule, capability
            // and free-text sanitisation do.
            Self::T1 => &[
                ("capability", true),
                ("a5-intent", false),
                ("a6-sanitize", false),
                ("structural-validators", true),
                ("lex", true),
                ("heresy", true),
                ("a6-output", false),
                ("canon-drift", false),
                ("causal-ref-integrity", true),
                ("world-rule", true),
                ("free-text-sanitisation", true),
            ],
        }
    }
}

/// Run the T6 (LLM-proposal) admission subset over one bus message body.
pub fn admit_t6(
    raw_json: &str,
    vocab: &Vocabulary,
    dedup: &mut DedupCache,
) -> AdmissionRecord {
    // Back-compat entry point for callers that do not sign (tests, the POC
    // runner). Trusts the caller to have established identity out-of-band.
    admit_signed(raw_json, None, &ProducerRegistry::new(), vocab, dedup)
}

/// Admit a proposal whose producer identity is PROVEN (PID-A2..A4).
///
/// `sig_hex` is the sibling stream field; `registry` maps a producer to its
/// key and its category. An empty registry means "identity not enforced" —
/// the pre-PID behaviour, kept only so unsigned in-process callers still work
/// while producers are migrated. A NON-empty registry is default-DENY.
pub fn admit_signed(
    raw_json: &str,
    sig_hex: Option<&str>,
    registry: &ProducerRegistry,
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

    // ── PID-A4: producer identity, BEFORE dedup ──
    //
    // First because everything after it is work done for a caller whose
    // identity is unestablished — and, more sharply, because the dedup triple
    // CONTAINS `producer_service`: deduping on an unverified identity lets a
    // forger evict a real proposal from the window by claiming its name.
    let category = if registry.is_empty() {
        stages.push(("producer-identity", Verdict::Skip));
        Category::T6
    } else {
        match registry.verify_and_derive(&proposal.producer_service, raw_json.as_bytes(), sig_hex) {
            Ok(cat) => {
                stages.push(("producer-identity", Verdict::Pass));
                cat
            }
            Err(e) => {
                stages.push(("producer-identity", Verdict::Fail(e.to_string())));
                return AdmissionRecord {
                    stages,
                    outcome: AdmissionOutcome::Rejected {
                        stage: "producer-identity",
                        reason: e.to_string(),
                    },
                };
            }
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

    // ── the category's declared stage table: NotRun (owed) vs Skip
    //    (declared inapplicable). Never silent, either way (D6/D4).
    for (stage, applicable) in category.stage_verdicts() {
        stages.push((stage, if *applicable { Verdict::NotRun } else { Verdict::Skip }));
    }

    AdmissionRecord {
        stages,
        outcome: AdmissionOutcome::Admitted(Box::new(Admitted::admit(QueuedInput {
            seq: Seq(u64::MAX), // stamped at island admission
            input_id: input_id_for(&triple),
            class: Class::B,
            source: match category {
                Category::T1 => Producer::PlayerInput,
                Category::T6 => Producer::LlmDecision,
            },
            payload,
            // IAS-D2/A3 — admission emits OBLIGATIONS, not just a verdict.
            // Both are checkable entirely from island state at step time, so
            // they carry no outside-observed snapshot that could go stale
            // between here and there (the generation-stamped variants need a
            // caller that holds the island; these deliberately do not).
            preconditions: vec![
                sim_core::Precondition::IslandOwns { id: EntityId(proposal.actor) },
                sim_core::Precondition::ResourceAtLeast {
                    id: EntityId(proposal.actor),
                    kind: crate::domain::CombatResource::TurnSlot,
                    amount: 1,
                },
            ],
            // IAS-D6 — DROP, not Substitute, and the distinction is
            // load-bearing. AGT-A2's substitute exists for an *unusable LLM
            // decision*: the model said something nonsensical, so play a safe
            // default. A turn-economy violation is a different failure — the
            // actor is not confused, it is out of budget — and substituting
            // there MINTS the very action the gate just refused. (Measured:
            // with Substitute, 99 refused spam strikes came back as 99 free
            // Defends. The gate held and the exploit survived it.)
            //
            // Nothing is lost: a vocabulary-invalid decision is rejected at
            // admission and never reaches the island, so the only
            // preconditions that can fail in-loop are IslandOwns and the turn
            // slot — both of which must drop. The AGT-A2 fallback is issued
            // by the HOST on an admission rejection instead.
            on_invalid: Fallback::Drop,
            admitted_gen: Gen(0), // re-stamped by Island::submit
            deadline: None,
        }))),
    }
}

/// IAS-D6 — the HOST's turn boundary, minted here so that `admission` remains
/// the single place in the service that can produce an [`Admitted`] token.
///
/// This is engine authority, not a driver action: `CombatPayload::EndTurn` has
/// no tool in the vocabulary, so no player, LLM or script can request one. It
/// carries no preconditions because refilling is unconditional — a turn ends
/// whether or not anyone used theirs.
/// `turn_seq` MUST advance per boundary. A constant `input_id` here made the
/// island's I2 dedup discard every turn-end after the first as a `Duplicate`,
/// so slots refilled once and then never again — the turn economy silently
/// became "one action per encounter". Caught by the refill test, which is the
/// reason that test exists: asserting only that spam is blocked would have
/// passed with the game frozen.
pub fn admit_engine_turn_end(turn_seq: u64) -> Admitted<CombatDomain> {
    Admitted::admit(QueuedInput {
        seq: Seq(u64::MAX),
        // High namespace: proposal ids are 128-bit blake3 hashes of the
        // EVT-L3 triple, so a collision with one is not a practical concern.
        input_id: InputId(u128::MAX - turn_seq as u128),
        class: Class::B,
        source: Producer::WorldEvent,
        payload: crate::domain::CombatPayload::EndTurn,
        preconditions: vec![],
        on_invalid: Fallback::Drop,
        admitted_gen: Gen(0),
        deadline: None,
    })
}
