//! S2 — island checkpoint + dissolution result (spec §10.1/§10.5).
//!
//! DESIGN RULE (mirrors metrics-are-data): **a checkpoint is data; encoding
//! is the host's job.** The kernel stays zero-dep — it hands the host a plain
//! struct of everything needed to rebuild a stepping-identical island, and
//! the host (commit-service, S3) chooses the wire/disk format.
//!
//! **Pending work is deliberately EXCLUDED** — §10.5's loss table is the
//! contract: buffered intents are lost (player re-issues), in-flight LLM
//! decisions self-heal via the deadline fallback, bus-borne input redelivers
//! via PEL and dedups against the restored seen-set.

use std::collections::BTreeMap;

use crate::domain::Domain;
use crate::ingress::Lane;
use crate::metrics::IslandMetrics;
use crate::rng::DetRng;
use crate::seen::SeenSet;
use crate::types::{
    DissolutionReason, EntityId, Gen, IslandId, Outcome, QueuedInput, RulesetDigest, RulesetEpoch, Seq, Tick,
};

/// Everything needed to rebuild a stepping-identical island: domain state,
/// structural registries, rng position, seen-set, island generation, logical
/// clock, and the next `Seq` stamp (post-restore stamps must not collide
/// with pre-checkpoint ones in host logs).
pub struct IslandCheckpoint<D: Domain> {
    pub id: IslandId,
    pub tick: Tick,
    pub island_gen: Gen,
    pub digest: RulesetDigest,
    /// RLS-I1 — carried across a rebuild, or `restore` would silently reset an
    /// island that had reached epoch 3 back to 1 and let an already-applied
    /// switch re-apply. A monotonic counter that does not survive the one
    /// operation that reconstructs the counter is not monotonic.
    pub epoch: RulesetEpoch,
    pub entities: BTreeMap<EntityId, Gen>,
    pub encounters: BTreeMap<EntityId, Gen>,
    pub state: D::State,
    pub rng: DetRng,
    pub seen: SeenSet,
    pub next_seq: u64,
}

impl<D: Domain> Clone for IslandCheckpoint<D>
where
    D::State: Clone,
{
    fn clone(&self) -> Self {
        Self {
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
            next_seq: self.next_seq,
        }
    }
}

impl<D: Domain> core::fmt::Debug for IslandCheckpoint<D>
where
    D::State: core::fmt::Debug,
{
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.debug_struct("IslandCheckpoint")
            .field("id", &self.id)
            .field("tick", &self.tick)
            .field("island_gen", &self.island_gen)
            .field("entities", &self.entities)
            .field("encounters", &self.encounters)
            .field("state", &self.state)
            .field("next_seq", &self.next_seq)
            .finish_non_exhaustive()
    }
}

/// What `Island::dissolve` hands back. The island itself is CONSUMED — a
/// dissolved ("Gone") island is structurally unrepresentable, not a runtime
/// flag: the host's map loses it by ownership transfer, so no
/// "submitted to a gone island" code path can exist.
pub struct Dissolution<D: Domain> {
    pub reason: DissolutionReason,
    /// Pending work that travels with the island — ONLY for
    /// [`DissolutionReason::transfers_pending`] reasons, ONLY items of the
    /// current generation (already-superseded items die here, counted below).
    pub transferable: Vec<(Lane, QueuedInput<D>)>,
    /// Pending items dropped by the §10.1 policy (discard-class reason, or
    /// stale-generation items under a transfer-class reason).
    pub discarded_pending: u64,
    /// Final rebuild source. For a POISONED island this is the last-known
    /// state and MUST only feed `Unresponsive`/`Failed` recovery flows — the
    /// host rebuilds from its own durable checkpoint/event log (SC-A10).
    pub checkpoint: IslandCheckpoint<D>,
    /// SC-A9: quarantined poison pills. NEVER in `transferable`, NEVER
    /// re-queued — replaying one is the infinite crash loop. Operator review.
    pub quarantined: Vec<QueuedInput<D>>,
    /// The unflushed outcome log, for the host to persist.
    pub outcomes: Vec<(Seq, Outcome<D>)>,
    pub metrics: IslandMetrics,
    pub was_poisoned: bool,
}
