//! The island — single-threaded inside, one DP-A16 channel, the unit of
//! parallelism (SL-A9). S1a: single island; cross-island messaging is S2.

use std::collections::BTreeMap;
use std::sync::Arc;

use crate::checkpoint::{Dissolution, IslandCheckpoint};
use crate::domain::Domain;
use crate::ingress::{Ingress, Lane};
use crate::metrics::IslandMetrics;
use crate::rng::DetRng;
use crate::seen::{SeenSet, SeenWindow};
use crate::types::{
    Class, DiscardReason, DissolutionReason, EntityId, Fallback, Gen, InputId, IslandId,
    IslandMessage, Outcome, Precondition, PreconditionKind, Producer, QueuedInput, RulesetDigest,
    Seq, Tick, Violation,
};

/// Result of one `step()` call.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepStatus {
    /// Ingress empty — nothing done.
    Idle,
    /// Exactly one item processed (its admission stamp).
    Processed(Seq),
    /// S1b: a previous `apply` panicked; the island refuses further work
    /// until the host rebuilds it (SC-A8 poison-not-resume).
    Poisoned,
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
    /// S1b island generation (spec §7). Items are stamped at admission; a
    /// bump supersedes everything stamped older, O(1).
    island_gen: Gen,
    /// S1b panic containment (SC-A8/A9). `containment=false` lets panics
    /// propagate (chaos-harness mode per spec §10.4 — surfacing beats
    /// swallowing in tests).
    containment: bool,
    poisoned: bool,
    /// Quarantined poison-pill inputs (≤1 in V1: first quarantine poisons).
    quarantine: Vec<QueuedInput<D>>,
    /// InputIds currently in a buffered episode — `Buffered` is recorded once
    /// per episode, not once per re-park (finding 1). NOTE (finding 4,
    /// accepted): while buffered, an id is absent from `seen`, so a concurrent
    /// true duplicate can apply in its place; exactly-one-applies still holds.
    currently_buffered: std::collections::BTreeSet<InputId>,
    metrics: IslandMetrics,
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
            metrics: IslandMetrics::default(),
            island_gen: Gen(0),
            containment: true,
            poisoned: false,
            quarantine: Vec::new(),
        }
    }

    // ─── structural registry (S1a surface; the invalidation CASCADE is S1b) ───

    /// Spawning over an id this island ALREADY tracks bumps its generation
    /// (same rule as `arrive` — review-impl S2 finding 2): re-inserting at
    /// Gen(0) would RESURRECT old-epoch refs pinned to Gen(0).
    pub fn spawn_entity(&mut self, id: EntityId) -> Gen {
        let g = match self.entities.get(&id) {
            Some(prev) => Gen(prev.0.saturating_add(1)),
            None => Gen(0),
        };
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

    /// Same anti-resurrection rule as `spawn_entity`.
    pub fn start_encounter(&mut self, id: EntityId) -> Gen {
        let g = match self.encounters.get(&id) {
            Some(prev) => Gen(prev.0.saturating_add(1)),
            None => Gen(0),
        };
        self.encounters.insert(id, g);
        g
    }

    pub fn end_encounter(&mut self, id: EntityId) {
        self.encounters.remove(&id);
    }

    /// Chaos-harness mode: panics PROPAGATE instead of poisoning (spec
    /// §10.4 — "do NOT catch in sim/debug builds"). Default is containment ON.
    pub fn set_containment(&mut self, on: bool) {
        self.containment = on;
    }

    /// S1b — the O(1) invalidation cascade (spec §7): every item admitted
    /// under an older generation discards as `Superseded` at its pop, with
    /// no queue walk. Their input_ids are NOT burned in `seen`, so a
    /// re-submission after the bump processes normally.
    pub fn bump_island_gen(&mut self) -> Gen {
        self.island_gen = Gen(self.island_gen.0.saturating_add(1));
        self.metrics.island_gen_bumps += 1;
        self.island_gen
    }

    pub fn is_poisoned(&self) -> bool {
        self.poisoned
    }

    pub fn quarantined(&self) -> &[QueuedInput<D>] {
        &self.quarantine
    }

    // ─── admission (stamps Seq + island_gen, validates NOTHING — spec §5) ───

    pub fn submit(&mut self, lane: Lane, mut input: QueuedInput<D>) -> Seq {
        input.admitted_gen = self.island_gen;
        let seq = self.ingress.push(lane, input);
        IslandMetrics::gauge_peak(&mut self.metrics.peak_ingress_depth, self.ingress.len());
        seq
    }

    /// Admit `input` when the island's logical clock reaches `due`.
    pub fn schedule_at(&mut self, due: Tick, lane: Lane, input: QueuedInput<D>) {
        self.schedule.entry(due).or_default().push((lane, input));
    }

    /// S2 §9 — accept a cross-island message. `delivery_id` becomes the
    /// `input_id`, so exactly-once (I8) IS the existing I2 seen-set dedup —
    /// a router redelivery discards as `Duplicate`, recorded like any other.
    /// The +1-tick latency lives in the ROUTER (it delivers at the target's
    /// next tick boundary); the kernel just admits.
    ///
    /// `from`/`causality` are NOT retained here — the ROUTER is the audit
    /// point for cross-island provenance (it sees every message; the kernel
    /// sees only what was delivered). A message arrives with no
    /// preconditions, so its payload must be TOTAL/defensive in `apply`
    /// (same bar as a `Substitute` fallback).
    pub fn deliver(&mut self, lane: Lane, msg: IslandMessage<D>) -> Seq {
        self.metrics.cross_island_delivered += 1;
        self.submit(lane, QueuedInput {
            seq: Seq(u64::MAX), // overwritten at admission
            input_id: msg.delivery_id,
            class: Class::B,
            source: Producer::CrossIsland,
            payload: msg.payload,
            preconditions: Vec::new(),
            on_invalid: Fallback::Drop,
            admitted_gen: self.island_gen, // re-stamped in submit anyway
            deadline: None,
        })
    }

    // ─── S2 handoff (SL-A12: EntityDeparted → EntityArrived) ───

    /// Remove `id` from this island and return its portable state. The
    /// registry entry is removed BEFORE any message can exist, so
    /// entity-in-exactly-one-island is structural, not a protocol promise.
    /// In-flight inputs referencing it now fail `EntityAlive`/`IslandOwns`
    /// at their step (S1a machinery, unchanged).
    pub fn depart(&mut self, id: EntityId) -> Option<(Gen, D::Portable)> {
        let generation = self.entities.remove(&id)?;
        Some((generation, D::extract(&mut self.state, id)))
    }

    /// Install a departed entity. Arriving over an entity this island already
    /// owns bumps its generation (the old epoch's refs go stale) — arrivals
    /// never silently merge.
    pub fn arrive(&mut self, id: EntityId, portable: D::Portable) -> Gen {
        let generation = match self.entities.get(&id) {
            Some(g) => Gen(g.0.saturating_add(1)),
            None => Gen(0),
        };
        self.entities.insert(id, generation);
        D::install(&mut self.state, id, portable);
        generation
    }

    // ─── S2 checkpoint / restore / dissolve (spec §10.1 / §10.5) ───

    /// Snapshot everything needed to rebuild a stepping-identical island.
    /// Pending work is EXCLUDED by contract (§10.5 loss table). A speed
    /// optimisation for Class B (the event log is the recovery truth,
    /// SC-A10); load-bearing for Class A ephemera (RTM-Q4).
    ///
    /// Returns `None` on a POISONED island — its state may be half-mutated
    /// (SC-A8), and a checkpoint of it restored later would smuggle the
    /// corruption past the poison flag. Post-panic forensics go through
    /// `dissolve(Unresponsive)`, whose checkpoint field is explicitly
    /// labelled last-known-state.
    pub fn checkpoint(&self) -> Option<IslandCheckpoint<D>>
    where
        D::State: Clone,
    {
        if self.poisoned {
            return None;
        }
        Some(IslandCheckpoint {
            id: self.id,
            tick: self.tick,
            island_gen: self.island_gen,
            digest: self.digest,
            entities: self.entities.clone(),
            encounters: self.encounters.clone(),
            state: self.state.clone(),
            rng: self.rng.clone(),
            seen: self.seen.clone(),
            next_seq: self.ingress.next_seq(),
        })
    }

    /// Rebuild from a checkpoint: stepping-identical to the island at
    /// `checkpoint()` time — same rng position, same seen-set (bus redelivery
    /// dedups), same generations, continuing `Seq` stamps. Fresh metrics
    /// (cumulative telemetry is the HOST's aggregation concern), empty
    /// queues (§10.5), containment on, not poisoned.
    pub fn restore(cp: IslandCheckpoint<D>, rules: Arc<D::Rules>) -> Self {
        Self {
            id: cp.id,
            tick: cp.tick,
            entities: cp.entities,
            encounters: cp.encounters,
            ingress: Ingress::with_next_seq(cp.next_seq),
            seen: cp.seen,
            state: cp.state,
            rules,
            digest: cp.digest,
            rng: cp.rng,
            outcomes: Vec::new(),
            externals: Vec::new(),
            schedule: BTreeMap::new(),
            buffered: Vec::new(),
            currently_buffered: std::collections::BTreeSet::new(),
            metrics: IslandMetrics::default(),
            island_gen: cp.island_gen,
            containment: true,
            poisoned: false,
            quarantine: Vec::new(),
        }
    }

    /// Dissolve, CONSUMING the island — "Gone" is unrepresentable by move
    /// semantics, not a runtime flag. The §10.1 policy: transfer-class
    /// reasons carry current-generation pending work in `transferable`;
    /// everything else (and every stale-generation item) is counted
    /// discarded. Quarantined pills ride their own field, NEVER
    /// `transferable` (SC-A9 — replaying one is the infinite crash loop).
    pub fn dissolve(mut self, reason: DissolutionReason) -> Dissolution<D> {
        let mut pending = self.ingress.drain_all();
        for (_, items) in std::mem::take(&mut self.schedule) {
            // Scheduled items were never admitted — stamp them into the
            // current epoch so a transfer target treats them as fresh.
            pending.extend(items.into_iter().map(|(lane, mut i)| {
                i.admitted_gen = self.island_gen;
                (lane, i)
            }));
        }
        pending.append(&mut self.buffered);

        let total = pending.len() as u64;
        // A POISONED island never transfers pending work regardless of the
        // reason the host picked — §10.1 says a dead island's pending is
        // LOST, and migrating a queue out of a corrupted context would
        // launder it (review-impl S2 finding 3).
        let transferable: Vec<(Lane, QueuedInput<D>)> = if reason.transfers_pending()
            && !self.poisoned
        {
            pending
                .into_iter()
                .filter(|(_, i)| i.admitted_gen == self.island_gen)
                .collect()
        } else {
            Vec::new()
        };
        let discarded_pending = total - transferable.len() as u64;

        let checkpoint = IslandCheckpoint {
            id: self.id,
            tick: self.tick,
            island_gen: self.island_gen,
            digest: self.digest,
            entities: self.entities,
            encounters: self.encounters,
            state: self.state,
            rng: self.rng,
            seen: self.seen,
            next_seq: self.ingress.next_seq(),
        };

        Dissolution {
            reason,
            transferable,
            discarded_pending,
            checkpoint,
            quarantined: self.quarantine,
            outcomes: self.outcomes,
            metrics: self.metrics,
            was_poisoned: self.poisoned,
        }
    }

    /// SC-A3 — a host must only `dissolve(Migrating)` a quiescent island
    /// (encounters migrate between turns; cells when drained).
    pub fn is_quiescent(&self) -> bool {
        self.ingress.is_empty() && self.buffered.is_empty() && self.schedule.is_empty()
    }

    // ─── time (injected, never read — TDIL-A9) ───

    /// Advance logical time. Never blocks; Class A work + due timers only.
    ///
    /// HOST CONTRACT (finding 3): seen-set TTL eviction runs HERE, never on
    /// the per-item path — a host that steps without ever ticking leaks the
    /// seen-set even with a TTL window. Cell islands must tick periodically.
    pub fn tick(&mut self, dt: u64) {
        // SC-A8: poisoned = NEVER resumed — firing timers and reparking
        // buffered items is work (review-impl S2 finding 6).
        if self.poisoned {
            return;
        }
        self.tick = Tick(self.tick.0.saturating_add(dt));
        self.metrics.ticks += 1;

        // Due timers → admission (stamped now, validated at their step).
        let due: Vec<Tick> = self
            .schedule
            .range(..=self.tick)
            .map(|(t, _)| *t)
            .collect();
        for t in due {
            if let Some(items) = self.schedule.remove(&t) {
                for (lane, mut input) in items {
                    // Stamped at FIRE time — a scheduled item outliving a
                    // dissolution belongs to the new epoch.
                    input.admitted_gen = self.island_gen;
                    self.ingress.push(lane, input);
                    self.metrics.scheduled_fired += 1;
                }
            }
        }

        // Re-offer buffered items at the FRONT, original Seq preserved.
        // Reverse iteration keeps their relative order after push_front.
        for (lane, input) in self.buffered.drain(..).rev().collect::<Vec<_>>() {
            self.ingress.push_front_preserving_seq(lane, input);
        }

        // Eviction runs on the tick path, never the per-item path.
        self.metrics.seen_evictions += self.seen.evict_expired(self.tick);
    }

    // ─── the step function (spec §5, verbatim semantics) ───

    /// Process exactly ONE ingress item, atomically (SL-A9 per-item atomicity).
    pub fn step(&mut self) -> StepStatus {
        if self.poisoned {
            return StepStatus::Poisoned;
        }
        let Some((lane, item)) = self.ingress.pop() else {
            return StepStatus::Idle;
        };
        let seq = item.seq;
        self.metrics.steps_processed += 1;

        // S1b §7 — generation gate FIRST, before the seen-set: a superseded
        // item must not burn its input_id (re-submit after invalidation is
        // legitimate), and this is the O(1) half of the cascade.
        if item.admitted_gen != self.island_gen {
            self.currently_buffered.remove(&item.input_id);
            self.metrics.discarded_superseded += 1;
            self.record(seq, Outcome::Discarded { reason: DiscardReason::Superseded });
            return StepStatus::Processed(seq);
        }

        // I2 — idempotency. A duplicate is a normal recorded outcome.
        if !self.seen.insert(item.input_id, self.tick) {
            self.metrics.discarded_duplicate += 1;
            self.record(seq, Outcome::Discarded {
                reason: DiscardReason::Duplicate,
            });
            return StepStatus::Processed(seq);
        }
        IslandMetrics::gauge_peak(&mut self.metrics.peak_seen_len, self.seen.len());

        // S1b SL-A4 — deadline, resolved through the declared fallback.
        // AFTER the seen-set, deliberately (review-impl S2 finding 1): expiry
        // is a FINAL outcome, so it must burn the input_id — otherwise a
        // redelivery re-expires and a `Substitute` fallback COMMITS TWICE,
        // and a duplicate of an already-applied input whose deadline has
        // since passed would misreport as Expired instead of Duplicate.
        // (The gen gate stays BEFORE seen: a cascade cancel is "never
        // happened", not a final outcome — re-submit is legitimate there.)
        if let Some(d) = item.deadline
            && self.tick > d
        {
            self.resolve_expiry(lane, item);
            return StepStatus::Processed(seq);
        }

        // Preconditions re-validated NOW, never at admission.
        match self.check_all(&item) {
            Ok(()) => {
                self.currently_buffered.remove(&item.input_id);
                match self.apply_contained(&item) {
                    Ok(events) => {
                        self.metrics.applied += 1;
                        self.externals.extend(D::externals(&events));
                        self.record(seq, Outcome::Applied { events });
                    }
                    Err(()) => {
                        // SC-A8/A9: poison, quarantine the pill, record —
                        // half-mutated state is never observable because no
                        // further step runs.
                        self.poisoned = true;
                        self.metrics.quarantined += 1;
                        self.record(seq, Outcome::Discarded {
                            reason: DiscardReason::Quarantined,
                        });
                        self.quarantine.push(item);
                    }
                }
            }
            Err(violation) => self.resolve_fallback(lane, item, violation),
        }
        StepStatus::Processed(seq)
    }

    /// S1b SC-A8: containment boundary. `AssertUnwindSafe` is sound HERE
    /// because every Err path poisons the island before returning — the
    /// possibly-half-mutated state can never be observed by another step.
    fn apply_contained(&mut self, item: &QueuedInput<D>) -> Result<Vec<D::Event>, ()> {
        if self.containment {
            let state = &mut self.state;
            let rules = &self.rules;
            let rng = &mut self.rng;
            std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                D::apply(state, rules, item, rng)
            }))
            .map_err(|_| ())
        } else {
            Ok(D::apply(&mut self.state, &self.rules, item, &mut self.rng))
        }
    }

    /// S1b SL-A4 expiry: resolved through the declared fallback; `Buffer`
    /// coerces to Drop (retrying a dead item forever is never right).
    fn resolve_expiry(&mut self, _lane: Lane, item: QueuedInput<D>) {
        let seq = item.seq;
        self.currently_buffered.remove(&item.input_id);
        match item.on_invalid.clone() {
            Fallback::Substitute(payload) => {
                let sub = QueuedInput { payload, preconditions: Vec::new(), ..item };
                match self.apply_contained(&sub) {
                    Ok(events) => {
                        self.metrics.applied += 1;
                        self.metrics.substituted += 1;
                        self.externals.extend(D::externals(&events));
                        self.record(seq, Outcome::Applied { events });
                    }
                    Err(()) => {
                        self.poisoned = true;
                        self.metrics.quarantined += 1;
                        self.record(seq, Outcome::Discarded {
                            reason: DiscardReason::Quarantined,
                        });
                        // The SUBSTITUTE is quarantined, not the original —
                        // it is the object that panicked, which is what the
                        // operator reviews (accepted, review-impl finding 7).
                        self.quarantine.push(sub);
                    }
                }
            }
            _ => {
                self.metrics.discarded_expired += 1;
                self.record(seq, Outcome::Discarded { reason: DiscardReason::Expired });
            }
        }
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
                self.metrics.discarded_precondition += 1;
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
                match self.apply_contained(&sub) {
                    Ok(events) => {
                        self.metrics.applied += 1;
                        self.metrics.substituted += 1;
                        self.externals.extend(D::externals(&events));
                        self.record(seq, Outcome::Applied { events });
                    }
                    Err(()) => {
                        self.poisoned = true;
                        self.metrics.quarantined += 1;
                        self.record(seq, Outcome::Discarded {
                            reason: DiscardReason::Quarantined,
                        });
                        self.quarantine.push(sub);
                    }
                }
            }
            Fallback::Notify(_entity, _declared) => {
                // Delivery is the host's `turn.outcome` frame (REC-64). The
                // kernel records the ACTUAL violation — the caller-declared
                // reason is a presentation hint and must never overwrite the
                // audit record (review-impl finding 2: a client could declare
                // `Expired` over a real EntityAlive failure and falsify the log).
                self.metrics.discarded_precondition += 1;
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
                    self.metrics.buffered_episodes += 1;
                    self.record(seq, Outcome::Buffered);
                } else {
                    self.metrics.rebuffer_cycles += 1;
                }
                // Re-offer on the item's OWN lane (review finding 1: the
                // prior hardcoded Live was a priority inversion for
                // Background items).
                self.buffered.push((lane, item));
                IslandMetrics::gauge_peak(&mut self.metrics.peak_buffered_len, self.buffered.len());
            }
        }
    }

    fn record(&mut self, seq: Seq, outcome: Outcome<D>) {
        self.outcomes.push((seq, outcome));
        IslandMetrics::gauge_peak(&mut self.metrics.peak_outcomes_len, self.outcomes.len());
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

    pub fn seen_len(&self) -> usize {
        self.seen.len()
    }

    pub fn buffered_len(&self) -> usize {
        self.buffered.len()
    }

    /// The kernel's observability surface — deterministic counters + peak
    /// gauges. The HOST emits these as real telemetry (DP-R8); tests assert
    /// they agree with the outcome log (a drift = a silent outcome path).
    pub fn metrics(&self) -> &IslandMetrics {
        &self.metrics
    }

    /// Drain effects that must LEAVE the island (SC-A4). sim-core never
    /// writes anything external itself (AGT-A6 / DP-A6).
    pub fn drain_proposals(&mut self) -> Vec<D::External> {
        std::mem::take(&mut self.externals)
    }
}
