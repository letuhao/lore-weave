//! **Axis 2 — the declared verb, on a REAL stack.**
//!
//! A unit suite proves the substrate resolves. It cannot prove the fact reaches
//! the log, survives Postgres, and projects to the shape a browser reads — and
//! this repository has recorded four cross-service contract bugs that mock-only
//! coverage hid.
//!
//! So this drives the SAME sequence `bin/spine.rs` does, against a real
//! database:
//!
//! ```text
//! a submitted command  ->  admission (the real vocabulary + verb table)
//!                      ->  the island (the real domain, the real ruleset)
//!                      ->  EventEnvelope -> ChannelWriter::append  (real PG)
//!                      ->  read the row BACK from the log
//!                      ->  TurnOutcome::from_resolution            (the wire)
//! ```
//!
//! **Gated on `DECLARED_VERB_TEST_DATABASE_URL`**, and skipped-with-a-reason
//! when absent. `scripts/declared-verb-live-smoke.sh` sets it up. The DSN is
//! guarded before anything touches the server: a fixture may only point at a
//! database whose name announces itself as disposable, which is the rule an
//! unscoped `DELETE FROM books` broke once, against the real book DB.

use std::sync::Arc;

use commit_service::admission::{admit_t6, AdmissionOutcome, DedupCache};
use commit_service::combat::Side;
use commit_service::{
    Actor, CombatDomain, CombatEvent, CombatState, RealityRules, TurnOutcome, Vocabulary,
    COMBAT_V1_JSON,
};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use dp_kernel::envelope::EventEnvelope;
use sim_core::{EntityId, Island, IslandId, Lane, Outcome, RulesetEpoch, SeenWindow, StepStatus};
use sqlx::postgres::PgPoolOptions;
use sqlx::Row;
use uuid::Uuid;

/// The submitter. Any uuid — these suites are about admission, not identity.
/// Before `SEALED-SUBJECT` the proposal carried `"actor": 1` and admission
/// believed it; the SUBJECT is now a parameter the CALLER supplies.
const TEST_USER: &str = "7e57ab1e-0000-4000-8000-00000000ac70";

const DSN_VAR: &str = "DECLARED_VERB_TEST_DATABASE_URL";
const ACTOR: EntityId = EntityId(1);

/// Refuse a DSN whose database name does not announce itself as disposable.
/// Runs BEFORE anything touches the server.
fn guarded() -> Option<String> {
    let raw = std::env::var(DSN_VAR).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "scratch", "throwaway", "sandbox"].iter().any(|m| db.contains(m)),
        "{DSN_VAR} points at `{db}`, which carries no throwaway marker"
    );
    Some(raw)
}

/// A submitted command, in the wire shape a driver actually sends.
fn proposal(id: &str, tool: &str) -> String {
    serde_json::json!({
        "producer_service": "commit-service-live-smoke",
        "proposal_id": id,
        "target_channel": 1,
        "user_ref_id": TEST_USER,
        "candidates": [],
        "decision": { "tool": tool, "params": {} },
    })
    .to_string()
}

#[tokio::test]
async fn a_declared_verb_reaches_the_log_and_the_wire() -> anyhow::Result<()> {
    let Some(dsn) = guarded() else {
        // `SKIP` first, then the reason. The prefix is what
        // `scripts/live-suites.py` reads to tell "did nothing" from "passed" —
        // without it the runner reports this suite as a PASS on a run where it
        // never connected. This line announced only "live infra unavailable",
        // a THIRD spelling of skip in a tree that already had two, and
        // `live-suite-registry-gate` red on it.
        eprintln!(
            "SKIP declared_verb_live — live infra unavailable: {DSN_VAR} is unset. \
             Run scripts/declared-verb-live-smoke.sh"
        );
        return Ok(());
    };

    // ── the reality, through the REAL loader ────────────────────────────────
    let rules = Arc::new(RealityRules::proving_ground());
    let verb = rules.rules().verbs.ordinal_of("gather").expect("the shipped preset declares it");
    let decl = *rules.rules().verbs.get(verb).unwrap();
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON)?;
    assert!(!vocab.contains("gather"), "the tool manifest must NOT know it — the table must");

    let reality = Uuid::new_v4();
    let channel = 1i64;
    let pool = PgPoolOptions::new().max_connections(4).connect(&dsn).await?;
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(channel)).await?;
    let writer = ChannelWriter::new(Arc::new(pool.clone()), reality, lease);

    let mut state = CombatState { session_seed: 0x5EED, ..Default::default() };
    state.actors.insert(ACTOR, Actor::spawn(&rules, ACTOR, Side::A));
    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(channel as u64),
        0x0A11_11FE_u64,
        RulesetEpoch(1),
        Arc::clone(&rules),
        SeenWindow::Unbounded,
        state,
    );
    isle.spawn_entity(ACTOR);

    let mut dedup = DedupCache::new(std::time::Duration::from_secs(300));
    let mut aggregate_version = 0u64;
    let mut turn = 0u64;

    // Drive the verb until its declared `focus` runs out, then once more. The
    // last submission is the REFUSAL — `CMD-5`'s other half, and the one a
    // happy-path-only smoke would never reach.
    let uses = rules.rules().resources.by_role(ruleset_core::EngineRole::None).unwrap().base;
    let mut committed: Vec<(i64, String, serde_json::Value)> = Vec::new();

    for i in 0..=uses {
        let raw = proposal(&format!("p-{i}"), "gather");
        let admitted = match admit_t6(&raw, ACTOR, &vocab, &rules.rules().verbs, &mut dedup).outcome {
            AdmissionOutcome::Admitted(input) => input,
            other => panic!("a declared verb must be ADMITTED, got {other:?}"),
        };
        let input_id = admitted.input().input_id;
        isle.submit(Lane::Live, *admitted);
        while !matches!(isle.step(), StepStatus::Idle | StepStatus::Poisoned) {}

        // Everything the island resolved since the last drain, committed the
        // way the spine commits it.
        let outcomes: Vec<_> = isle.outcomes().to_vec();
        for (seq, outcome) in outcomes.iter().skip(committed.len()) {
            let applied = matches!(outcome, Outcome::Applied { .. });
            if applied {
                turn += 1;
            }
            aggregate_version += 1;
            let env = EventEnvelope {
                event_id: Uuid::new_v4(),
                event_type: if applied { "turn.resolved".into() } else { "turn.discarded".into() },
                event_version: 1,
                aggregate_id: format!("enc-{channel}"),
                aggregate_type: "combat_session".into(),
                aggregate_version,
                reality_id: reality,
                occurred_at: commit_service::hostclock::now_rfc3339(),
                recorded_at: commit_service::hostclock::now_rfc3339(),
                payload: serde_json::json!({
                    "island_seq": seq.0.to_string(),
                    "events": match outcome {
                        Outcome::Applied { events } => serde_json::to_value(events)?,
                        _ => serde_json::json!([]),
                    },
                }),
                metadata: Some(serde_json::json!({
                    "event_category": "T6",
                    "input_id": input_id.0.to_string(),
                    "turn_number": turn.to_string(),
                })),
                // RLS-A13 — the pin is DERIVED from the island that produced it.
                ruleset_digest: Some(isle.digest.to_hex()),
            };
            let appended = writer.append(&env, &serde_json::json!([])).await?;
            committed.push((appended.channel_event_id, env.event_type.clone(), env.payload.clone()));
        }
        // One action per turn is the ENGINE's budget; the boundary refills it.
        isle.submit(
            Lane::Live,
            sim_core::Admitted::unchecked(sim_core::QueuedInput {
                seq: sim_core::Seq(u64::MAX),
                input_id: sim_core::InputId(10_000 + i as u128),
                class: sim_core::Class::B,
                source: sim_core::Producer::ScriptDecision,
                payload: commit_service::CombatPayload::EndTurn,
                preconditions: vec![],
                on_invalid: sim_core::Fallback::Drop,
                admitted_gen: sim_core::Gen(0),
                deadline: None,
            }),
        );
        while !matches!(isle.step(), StepStatus::Idle | StepStatus::Poisoned) {}
    }

    // ── A2.1 — read the facts BACK from Postgres, not from memory ───────────
    let rows = sqlx::query(
        "SELECT channel_event_id, event_type, payload, ruleset_digest \
         FROM events WHERE reality_id = $1 ORDER BY aggregate_version ASC",
    )
    .bind(reality)
    .fetch_all(&pool)
    .await?;
    assert!(!rows.is_empty(), "the log is empty — nothing was committed");

    let mut acted = None;
    let mut refused = None;
    for r in &rows {
        let id: i64 = r.get("channel_event_id");
        let ty: String = r.get("event_type");
        let payload: serde_json::Value = r.get("payload");
        let digest: Option<String> = r.try_get("ruleset_digest").unwrap_or(None);
        println!(
            "A2.1  channel_event_id={id}  type={ty}  pin={}  payload={}",
            digest.as_deref().unwrap_or("<none>"),
            payload
        );
        for e in payload["events"].as_array().cloned().unwrap_or_default() {
            match e["type"].as_str() {
                Some("acted") => acted = Some((id, e.clone())),
                Some("refused") => refused = Some((id, e.clone())),
                _ => {}
            }
        }
        assert!(digest.is_some(), "RLS-A13 — every committed fact carries its pin");
    }

    // ── A2.1 — the applied fact, with the CUE (`CMD-4`) ─────────────────────
    let (acted_id, acted_ev) = acted.expect("a declared verb commits an `acted` fact");
    println!("A2.1  APPLIED  channel_event_id={acted_id}  {acted_ev}");
    assert_eq!(acted_ev["verb"].as_u64(), Some(verb as u64));
    assert_eq!(
        acted_ev["cue"].as_u64(),
        Some(decl.cue as u64),
        "CMD-4 — the declared cue ordinal survived the round trip through Postgres"
    );
    assert_eq!(acted_ev["actor"].as_str(), Some(ACTOR.0.to_string().as_str()), "CWC-A2 decimal string");
    // **The NUMBERS, not only the identifiers.** The first version of this smoke
    // asserted `verb` and `cue` and nothing else — so a fact carrying a
    // fabricated `left` for a quantity the actor does not hold would have passed
    // it unchanged, which is exactly the defect a cold-start reviewer found in
    // the substrate. The three fields below are what makes this a check on what
    // HAPPENED rather than on what was labelled.
    assert_eq!(
        acted_ev["quantity"].as_u64(),
        Some(decl.effect.quantity as u64),
        "the fact must name the quantity the DECLARATION names"
    );
    assert_eq!(acted_ev["delta"].as_i64(), Some(decl.effect.amount as i64));
    let left = acted_ev["left"].as_i64().expect("left is a number");
    let (min, ceiling) = rules.pool_bounds(decl.effect.quantity).expect("a declared pool");
    assert!(
        (i64::from(min)..=i64::from(ceiling)).contains(&left),
        "left={left} is outside the pool's declared bounds [{min}, {ceiling}] — the clamp          did not run, or the fact is about a quantity the actor does not hold"
    );

    // ── A2.2 — the REFUSAL, with its reason ordinal (`CMD-5`) ───────────────
    let (refused_id, refused_ev) = refused.expect(
        "the refusal path must commit a fact — a substrate that only proves its happy path \
         has proved half of CMD-5",
    );
    println!("A2.2  REFUSED  channel_event_id={refused_id}  {refused_ev}");
    assert_eq!(refused_ev["reason"].as_str(), Some("requirement_unmet"));

    // ── A2.3 — the CUE channel: the same facts, projected to the wire ───────
    let narration: Vec<String> = serde_json::from_value::<Vec<CombatEvent>>(
        rows.iter()
            .find(|r| r.get::<i64, _>("channel_event_id") == acted_id)
            .map(|r| r.get::<serde_json::Value, _>("payload")["events"].clone())
            .unwrap(),
    )?
    .iter()
    .map(|e| serde_json::to_string(e).unwrap())
    .collect();
    let wire = TurnOutcome::from_resolution(acted_id, turn, true, narration, None);
    let wire_json = serde_json::to_value(&wire)?;
    println!("A2.3  WIRE  {wire_json}");
    assert_eq!(wire_json["channel_event_id"], acted_id.to_string(), "CWC-A2 decimal string");
    // PARSED, not substring-matched. `TurnOutcome`'s narration is a Vec<String>
    // of serialized facts, so the cue arrives JSON-escaped inside a JSON string
    // — and a `contains("\"cue\":1")` on the outer rendering fails against a
    // payload that carries it perfectly well. Matching the shape instead of the
    // spelling is also what stops this passing on a coincidence.
    let first: serde_json::Value =
        serde_json::from_str(wire_json["detail"]["events"][0].as_str().unwrap())?;
    assert_eq!(
        first["cue"].as_u64(),
        Some(decl.cue as u64),
        "CMD-4 — the cue must reach the client payload: {wire_json}"
    );
    assert_eq!(first["type"].as_str(), Some("acted"));

    Ok(())
}
