//! Construction and the rebuild boundary — `new`, `checkpoint`, `restore`,
//! `dissolve`, `is_quiescent`.
//!
//! `new` joined them when the RLS-I1 audit fix pushed `mod.rs` past its ceiling,
//! and the seam is better for it: everything here answers *"how does this island
//! come to be, and how does it stop being this island"*, none of it is on the
//! step path, and `new` and `restore` are the two constructors — they belong
//! within reading distance of each other.
//!
//! A CHILD module of `island` for the same reason as `epoch`: it reads the
//! parent's private fields directly, and a sibling would have forced them
//! `pub(crate)`.
//!
//! The seam is real rather than a line count. Everything here answers *"how
//! does this island stop being this island"* — snapshot it, rebuild it from a
//! snapshot, or consume it — and none of it is on the step path. Split out on
//! 2026-07-29 when `Q0b B2a` pushed `island.rs` past its recorded ceiling;
//! nothing changed in the move.

use std::collections::BTreeMap;
use std::sync::Arc;

use super::Island;
use crate::checkpoint::{Dissolution, IslandCheckpoint};
use crate::domain::Domain;
use crate::ingress::{Ingress, IngressItem, Lane};
use crate::metrics::IslandMetrics;
use crate::rng::DetRng;
use crate::seen::{SeenSet, SeenWindow};
use crate::types::{
    DissolutionReason, Gen, IslandId, QueuedInput, RulesetEpoch, RulesetMismatch, Tick,
};

impl<D: Domain> Island<D> {
    /// `epoch` is REQUIRED, and that is a correction rather than a shape.
    ///
    /// It used to default to `RulesetEpoch(1)`, and `load_reality` used to
    /// throw the binding's epoch away — so a reality durably bound at epoch 5
    /// produced an island claiming epoch 1, and `RLS-I1` monotonicity was
    /// computed against 1. A redelivered switch to epoch 3 would then be
    /// ACCEPTED, moving the island onto rules the reality had already moved
    /// past: the guard defeated by the constructor.
    ///
    /// Both decisions were individually correct — the binding carries the
    /// epoch, a brand-new reality starts at 1 — which is the `NV-4` shape and
    /// the reason this is a parameter now instead of a default. A caller that
    /// genuinely has a fresh reality passes `RulesetEpoch(1)` and says so.
    pub fn new(
        id: IslandId,
        seed: u64,
        epoch: RulesetEpoch,
        rules: Arc<D::Rules>,
        seen_window: SeenWindow,
        initial_state: D::State,
    ) -> Self {
        // RLS-A13 — DERIVED, never supplied. See `Domain::rules_digest`: a
        // digest handed in beside the rules is a pair nothing forces to agree.
        let digest = D::rules_digest(&rules);
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
            epoch,
            rng: DetRng::new(seed),
            outcomes: Vec::new(),
            externals: Vec::new(),
            schedule: BTreeMap::new(),
            buffered: Vec::new(),
            currently_buffered: std::collections::BTreeSet::new(),
            metrics: IslandMetrics::default(),
            island_gen: Gen(0),
            containment: true,
            in_step: false,
            poisoned: false,
            quarantine: Vec::new(),
        }
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
            epoch: self.epoch,
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
    ///
    /// # Refuses a rules/digest mismatch (RLS-A13)
    ///
    /// `Island::new` cannot be given a digest that disagrees with its rules —
    /// there is no digest argument. `restore` is the one place the two can
    /// still disagree, because the checkpoint carries a HISTORICAL digest and
    /// the caller supplies rules NOW. Continuing under rules the checkpoint's
    /// digest does not describe is silent replay divergence: the island keeps
    /// stepping, its events keep claiming the old pin, and nothing is wrong
    /// until an oracle disagrees months later — by which time the evidence is
    /// gone.
    ///
    /// So it is refused, loudly, which is what RLS-D12 already specifies for an
    /// engine that cannot honour a stored ruleset: **quarantine, never silently
    /// reinterpret.** The cost is real and worth stating — a node that cannot
    /// resolve the checkpoint's ruleset cannot adopt the island at all. That is
    /// the correct trade for a determinism-pinned system, and it is the shape
    /// F2 completes: once the immutable ruleset store exists, the caller looks
    /// the ruleset up BY `cp.digest` and the mismatch stops being reachable.
    ///
    /// **Today this is latent, not live** — `checkpoint`/`restore` are not on
    /// the durable recovery path (`recovery.rs` records the decision: replay
    /// from the committed log, *"persisting island checkpoints … is strictly
    /// more machinery"*), and nothing in production calls it. Which is exactly
    /// why it costs nothing to close now, and would be archaeology later.
    pub fn restore(
        cp: IslandCheckpoint<D>,
        rules: Arc<D::Rules>,
    ) -> Result<Self, RulesetMismatch> {
        let derived = D::rules_digest(&rules);
        if derived != cp.digest {
            return Err(RulesetMismatch { checkpoint: cp.digest, supplied: derived });
        }
        Ok(Self {
            id: cp.id,
            tick: cp.tick,
            entities: cp.entities,
            encounters: cp.encounters,
            ingress: Ingress::with_next_seq(cp.next_seq),
            seen: cp.seen,
            state: cp.state,
            rules,
            // Equal to `D::rules_digest(&rules)` by the check above — the
            // stored one is used so the field's PROVENANCE stays the
            // checkpoint, not a re-derivation that would mask a future bug in
            // the guard itself.
            digest: cp.digest,
            epoch: cp.epoch,
            rng: cp.rng,
            outcomes: Vec::new(),
            externals: Vec::new(),
            schedule: BTreeMap::new(),
            buffered: Vec::new(),
            currently_buffered: std::collections::BTreeSet::new(),
            metrics: IslandMetrics::default(),
            island_gen: cp.island_gen,
            containment: true,
            in_step: false,
            poisoned: false,
            quarantine: Vec::new(),
        })
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
                (lane, IngressItem::Input(i))
            }));
        }
        pending.extend(
            std::mem::take(&mut self.buffered)
                .into_iter()
                .map(|(lane, i)| (lane, IngressItem::Input(i))),
        );

        let total = pending.len() as u64;
        // A POISONED island never transfers pending work regardless of the
        // reason the host picked — §10.1 says a dead island's pending is
        // LOST, and migrating a queue out of a corrupted context would
        // launder it (review-impl S2 finding 3).
        // A PENDING EPOCH SWITCH IS NEVER TRANSFERRED, and that is a decision
        // rather than an omission. `transfers_pending` hands work to a
        // successor island, and a successor is rebuilt from the checkpoint —
        // which already carries the epoch. Carrying the switch too would
        // deliver it to an island that either already has that epoch (refused,
        // noisily, on a path where nobody is listening) or is a genuinely
        // different island of the same reality, whose epoch is not this
        // island's to move. It is COUNTED as discarded, never dropped
        // silently; the host re-issues the switch against whatever islands are
        // live, which is the same thing it had to do for the ones that never
        // received it.
        let transferable: Vec<(Lane, QueuedInput<D>)> = if reason.transfers_pending()
            && !self.poisoned
        {
            pending
                .into_iter()
                .filter(|(_, i)| i.admitted_gen() == self.island_gen)
                .filter_map(|(lane, i)| i.into_input().map(|i| (lane, i)))
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
            // A dissolved island's checkpoint carries its epoch for the same
            // reason `checkpoint()` does: the transfer target rebuilds from
            // this, and an island that arrives at epoch 1 would accept a
            // replay of a switch it has already applied.
            epoch: self.epoch,
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
}
