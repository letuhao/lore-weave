//! The island — single-threaded inside, one DP-A16 channel, the unit of
//! parallelism (SL-A9). S1a: single island; cross-island messaging is S2.

use std::collections::BTreeMap;
use std::sync::Arc;

use crate::domain::Domain;
use crate::ingress::{Ingress, Lane};
use crate::rng::DetRng;
use crate::seen::{SeenSet, SeenWindow};
use crate::types::{
    DiscardReason, EntityId, Fallback, Gen, InputId, IslandId, Outcome, Precondition,
    PreconditionKind, QueuedInput, RulesetDigest, Seq, Tick, Violation,
};

/// Result of one `step()` call.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepStatus {
    /// Ingress empty — nothing done.
    Idle,
    /// Exactly one item processed (its admission stamp).
    Processed(Seq),
}

pub struct Island<D: Domain> {
    pub id: IslandId,
    tick: Tick,
    /// Structural registries — the generations sim-core itself tracks.
    /// `BTreeMap` everywhere: hash order must never enter replay state.
    entities: BTreeMap<EntityId, Gen>,
    encounters: BTreeMap<EntityId, Gen>,
    ingress: Ingress<D>,
    seen: SeenSet,
    state: D::State,
    /// RLS-A12: rules are held by `Arc`, NOT inside `State` — they never
    /// enter checkpoints, migration payloads or crash rebuilds.
    rules: Arc<D::Rules>,
    pub digest: RulesetDigest,
    rng: DetRng,
    /// Recorded outcomes, in processing order. Every item's fate is recorded;
    /// nothing is silent (CS-D5 discipline). Bounding is an S1b concern.
    outcomes: Vec<(Seq, Outcome<D>)>,
    externals: Vec<D::External>,
    /// Due-at-tick inputs; admitted (stamped) only when due.
    schedule: BTreeMap<Tick, Vec<(Lane, QueuedInput<D>)>>,
    /// `Fallback::Buffer` parking; re-offered at next `tick()` with original
    /// `Seq` preserved (spec §5.3).
    buffered: Vec<(Lane, QueuedInput<D>)>,
    /// InputIds currently in a buffered episode — `Buffered` is recorded once
    /// per episode, not once per re-park (finding 1). NOTE (finding 4,
    /// accepted): while buffered, an id is absent from `seen`, so a concurrent
    /// true duplicate can apply in its place; exactly-one-applies still holds.
    currently_buffered: std::collections::BTreeSet<InputId>,
}

impl<D: Domain> Island<D> {
    pub fn new(
        id: IslandId,
        seed: u64,
        rules: Arc<D::Rules>,
        digest: RulesetDigest,
        seen_window: SeenWindow,
        initial_state: D::State,
    ) -> Self {
        Self {
            id,
            tick: Tick(0),
            entities: BTreeMap::new(),
            encounters: BTreeMap::new(),
            ingress: Ingress::new(),
            seen: SeenSet::new(seen_window),
            state: initial_state,
            rules,
            digest,
            rng: DetRng::new(seed),
            outcomes: Vec::new(),
            externals: Vec::new(),
            schedule: BTreeMap::new(),
            buffered: Vec::new(),
            currently_buffered: std::collections::BTreeSet::new(),
        }
    }

    // ─── structural registry (S1a surface; the invalidation CASCADE is S1b) ───

    pub fn spawn_entity(&mut self, id: EntityId) -> Gen {
        let g = Gen(0);
        self.entities.insert(id, g);
        g
    }

    /// Bump an entity's generation — every in-flight input holding the old
    /// gen becomes stale and will discard at ITS step (never retroactively).
    pub fn bump_entity_gen(&mut self, id: EntityId) -> Option<Gen> {
        let g = self.entities.get_mut(&id)?;
        // Saturating: a wrap at u32::MAX would RESURRECT stale generations;
        // pinning at MAX makes everything stale-forever — the safe direction.
        *g = Gen(g.0.saturating_add(1));
        Some(*g)
    }

    pub fn despawn_entity(&mut self, id: EntityId) {
        self.entities.remove(&id);
    }

    pub fn entity_gen(&self, id: EntityId) -> Option<Gen> {
        self.entities.get(&id).copied()
    }

    pub fn start_encounter(&mut self, id: EntityId) -> Gen {
        let g = Gen(0);
        self.encounters.insert(id, g);
        g
    }

    pub fn end_encounter(&mut self, id: EntityId) {
        self.encounters.remove(&id);
    }

    // ─── admission (stamps Seq, validates NOTHING — spec §5) ───

    pub fn submit(&mut self, lane: Lane, input: QueuedInput<D>) -> Seq {
        self.ingress.push(lane, input)
    }

    /// Admit `input` when the island's logical clock reaches `due`.
    pub fn schedule_at(&mut self, due: Tick, lane: Lane, input: QueuedInput<D>) {
        self.schedule.entry(due).or_default().push((lane, input));
    }

    // ─── time (injected, never read — TDIL-A9) ───

    /// Advance logical time. Never blocks; Class A work + due timers only.
    ///
    /// HOST CONTRACT (finding 3): seen-set TTL eviction runs HERE, never on
    /// the per-item path — a host that steps without ever ticking leaks the
    /// seen-set even with a TTL window. Cell islands must tick periodically.
    pub fn tick(&mut self, dt: u64) {
        self.tick = Tick(self.tick.0.saturating_add(dt));

        // Due timers → admission (stamped now, validated at their step).
        let due: Vec<Tick> = self
            .schedule
            .range(..=self.tick)
            .map(|(t, _)| *t)
            .collect();
        for t in due {
            if let Some(items) = self.schedule.remove(&t) {
                for (lane, input) in items {
                    self.ingress.push(lane, input);
                }
            }
        }

        // Re-offer buffered items at the FRONT, original Seq preserved.
        // Reverse iteration keeps their relative order after push_front.
        for (lane, input) in self.buffered.drain(..).rev().collect::<Vec<_>>() {
            self.ingress.push_front_preserving_seq(lane, input);
        }

        // Eviction runs on the tick path, never the per-item path.
        self.seen.evict_expired(self.tick);
    }

    // ─── the step function (spec §5, verbatim semantics) ───

    /// Process exactly ONE ingress item, atomically (SL-A9 per-item atomicity).
    pub fn step(&mut self) -> StepStatus {
        let Some((lane, item)) = self.ingress.pop() else {
            return StepStatus::Idle;
        };
        let seq = item.seq;

        // I2 — idempotency. A duplicate is a normal recorded outcome.
        if !self.seen.insert(item.input_id, self.tick) {
            self.record(seq, Outcome::Discarded {
                reason: DiscardReason::Duplicate,
            });
            return StepStatus::Processed(seq);
        }

        // Preconditions re-validated NOW, never at admission.
        match self.check_all(&item) {
            Ok(()) => {
                self.currently_buffered.remove(&item.input_id);
                let events = D::apply(&mut self.state, &self.rules, &item, &mut self.rng);
                self.externals.extend(D::externals(&events));
                self.record(seq, Outcome::Applied { events });
            }
            Err(violation) => self.resolve_fallback(lane, item, violation),
        }
        StepStatus::Processed(seq)
    }

    /// Structural preconditions from island registries; semantic ones
    /// delegated to the domain (spec §4.0 split).
    fn check_all(&self, item: &QueuedInput<D>) -> Result<(), Violation> {
        for p in &item.preconditions {
            match p {
                Precondition::EntityAlive { id, generation } => {
                    if self.entities.get(id) != Some(generation) {
                        return Err(Violation {
                            kind: PreconditionKind::EntityAlive,
                            entity: Some(*id),
                        });
                    }
                }
                Precondition::EncounterActive { id, generation } => {
                    if self.encounters.get(id) != Some(generation) {
                        return Err(Violation {
                            kind: PreconditionKind::EncounterActive,
                            entity: Some(*id),
                        });
                    }
                }
                Precondition::ActorEligible { id, turn } => {
                    // Eligible once the island clock has reached the actor's turn.
                    if self.tick < *turn {
                        return Err(Violation {
                            kind: PreconditionKind::ActorEligible,
                            entity: Some(*id),
                        });
                    }
                }
                Precondition::IslandOwns { id } => {
                    if !self.entities.contains_key(id) {
                        return Err(Violation {
                            kind: PreconditionKind::IslandOwns,
                            entity: Some(*id),
                        });
                    }
                }
                sem @ Precondition::ResourceAtLeast { .. } => {
                    D::check(&self.state, &self.rules, sem)?;
                }
            }
        }
        Ok(())
    }

    fn resolve_fallback(&mut self, lane: Lane, item: QueuedInput<D>, violation: Violation) {
        let seq = item.seq;
        match item.on_invalid.clone() {
            Fallback::Drop => {
                self.currently_buffered.remove(&item.input_id);
                self.record(seq, Outcome::Discarded {
                    reason: DiscardReason::PreconditionFailed(violation),
                });
            }
            Fallback::Substitute(payload) => {
                // The substitute is the domain's DECLARED safe alternative —
                // applied with no preconditions of its own (it must be total).
                let sub = QueuedInput {
                    payload,
                    preconditions: Vec::new(),
                    ..item
                };
                let events = D::apply(&mut self.state, &self.rules, &sub, &mut self.rng);
                self.externals.extend(D::externals(&events));
                self.record(seq, Outcome::Applied { events });
            }
            Fallback::Notify(_entity, _declared) => {
                // Delivery is the host's `turn.outcome` frame (REC-64). The
                // kernel records the ACTUAL violation — the caller-declared
                // reason is a presentation hint and must never overwrite the
                // audit record (review-impl finding 2: a client could declare
                // `Expired` over a real EntityAlive failure and falsify the log).
                self.record(seq, Outcome::Discarded {
                    reason: DiscardReason::PreconditionFailed(violation),
                });
            }
            Fallback::Buffer => {
                // Must not collide with itself on re-offer.
                self.seen.forget(&item.input_id);
                // Record Buffered only on ENTRY into the buffered state —
                // a re-buffer cycle (re-offer → still ineligible → re-park)
                // must not append a new outcome each tick, or one stuck
                // input grows the log without bound (review-impl finding 1).
                if !self.currently_buffered.contains(&item.input_id) {
                    self.currently_buffered.insert(item.input_id);
                    self.record(seq, Outcome::Buffered);
                }
                // Re-offer on the item's OWN lane (review finding 1: the
                // prior hardcoded Live was a priority inversion for
                // Background items).
                self.buffered.push((lane, item));
            }
        }
    }

    fn record(&mut self, seq: Seq, outcome: Outcome<D>) {
        self.outcomes.push((seq, outcome));
    }

    // ─── read surface (host + tests) ───

    pub fn now(&self) -> Tick {
        self.tick
    }

    pub fn state(&self) -> &D::State {
        &self.state
    }

    pub fn outcomes(&self) -> &[(Seq, Outcome<D>)] {
        &self.outcomes
    }

    pub fn ingress_len(&self) -> usize {
        self.ingress.len()
    }

    /// Drain effects that must LEAVE the island (SC-A4). sim-core never
    /// writes anything external itself (AGT-A6 / DP-A6).
    pub fn drain_proposals(&mut self) -> Vec<D::External> {
        std::mem::take(&mut self.externals)
    }
}
