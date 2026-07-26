//! §4 core types — shapes verbatim from `14_sim_core_spec.md`, S1a slice.
//!
//! Deviations, both recorded in `docs/plans/2026-07-26-sim-core-s1a.md`:
//! - [`Violation`] is **non-generic** (`PreconditionKind` + `Option<EntityId>`)
//!   so [`DiscardReason`] (REC-63's closed enum) stays non-generic.
//! - Spec's `SmallVec<[Precondition; 4]>` is a plain `Vec` (zero-dep rule;
//!   revisit at the bench, not by guess).

use crate::domain::Domain;

/// Island identity. One island == one DP-A16 channel (CS-A1 finding).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct IslandId(pub u64);

/// Entity identity within a reality.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct EntityId(pub u64);

/// Idempotency key (I2). Maps to the platform `IdempotencyKey` triple at the
/// commit-service boundary (S3); inside the kernel it is opaque.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct InputId(pub u128);

/// Logical time, per island. Never wall-clock (TDIL-A9).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Tick(pub u64);

/// Ingress stamp — monotonic per island, assigned at admission (and at
/// admission ONLY; validation happens at step time, spec §5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Seq(pub u64);

/// Generation — bumped on lifecycle change. S1a compares; the bump-cascade
/// machinery is S1b.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Gen(pub u32);

/// Content digest of the resolved `RealityRuleset` this island runs under
/// (RLS-A13). Pinned at construction; the host stamps it into every emitted
/// event's envelope at the S3 boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RulesetDigest(pub [u8; 32]);

/// SL-A2 execution classes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Class {
    A,
    B,
    C,
}

/// Input producers — ALL treated as unpredictable (spec §4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Producer {
    PlayerInput,
    LlmDecision,
    ScriptDecision,
    Timer,
    Generator,
    CrossIsland,
    WorkerResult,
    WorldEvent,
    Admin,
    SessionLifecycle,
}

/// One admitted ingress item. `seq` is stamped by [`crate::Ingress::push`];
/// any caller-supplied value is overwritten there.
///
/// NOTE: `Clone`/`Debug` for the four generic types are MANUAL impls (bottom
/// of this file) — derives would demand `D: Clone`/`D: Debug` on the domain
/// marker itself instead of using the associated-type bounds.
pub struct QueuedInput<D: Domain> {
    pub seq: Seq,
    pub input_id: InputId,
    pub class: Class,
    pub source: Producer,
    pub payload: D::Payload,
    pub preconditions: Vec<Precondition<D>>,
    pub on_invalid: Fallback<D>,
    /// Island generation at ADMISSION (S1b, spec §7). Stamped by the island;
    /// a bump supersedes every item stamped older — O(1) cascade cancel with
    /// zero per-item inspection. PRESERVED across buffered repark so
    /// dissolution also cancels parked work.
    pub admitted_gen: Gen,
    /// SL-A4 deadline (logical). `now > deadline` at step ⇒ expiry, resolved
    /// through `on_invalid` (Substitute = the AGT-A2 "Defend" pattern).
    /// `Buffer` on expiry is coerced to Drop — retrying a dead item forever
    /// is never right.
    pub deadline: Option<Tick>,
}

/// Preconditions, re-validated at step time (spec §5). The island evaluates
/// the STRUCTURAL variants from generations it already tracks; the domain
/// evaluates only the SEMANTIC ones (`ResourceAtLeast`, and its own).
pub enum Precondition<D: Domain> {
    EntityAlive { id: EntityId, generation: Gen },
    EncounterActive { id: EntityId, generation: Gen },
    ActorEligible { id: EntityId, turn: Tick },
    ResourceAtLeast { id: EntityId, kind: D::ResKind, amount: i64 },
    IslandOwns { id: EntityId },
}

/// What to do when a precondition fails at step time.
///
/// `Notify`'s delivery is the host's `turn.outcome` frame (REC-64) — the
/// kernel records the reason; it does not own a transport.
pub enum Fallback<D: Domain> {
    Drop,
    Substitute(D::Payload),
    Notify(EntityId, DiscardReason),
    Buffer,
}

/// Per-item result. A duplicate or a failed precondition is a NORMAL recorded
/// outcome, never an error (spec §5).
pub enum Outcome<D: Domain> {
    Applied { events: Vec<D::Event> },
    Discarded { reason: DiscardReason },
    Buffered,
}

/// Discriminant of a [`Precondition`], for non-generic reporting.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PreconditionKind {
    EntityAlive,
    EncounterActive,
    ActorEligible,
    ResourceAtLeast,
    IslandOwns,
}

/// A failed check. Non-generic on purpose (plan deviation 1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Violation {
    pub kind: PreconditionKind,
    pub entity: Option<EntityId>,
}

// ─── Manual Clone/Debug for the generic types (associated-type bounds, not
//     `D: Clone`/`D: Debug` — see QueuedInput note) ───

impl<D: Domain> Clone for QueuedInput<D> {
    fn clone(&self) -> Self {
        Self {
            seq: self.seq,
            input_id: self.input_id,
            class: self.class,
            source: self.source,
            payload: self.payload.clone(),
            preconditions: self.preconditions.clone(),
            on_invalid: self.on_invalid.clone(),
            admitted_gen: self.admitted_gen,
            deadline: self.deadline,
        }
    }
}

impl<D: Domain> core::fmt::Debug for QueuedInput<D> {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.debug_struct("QueuedInput")
            .field("seq", &self.seq)
            .field("input_id", &self.input_id)
            .field("class", &self.class)
            .field("source", &self.source)
            .field("payload", &self.payload)
            .field("preconditions", &self.preconditions)
            .field("on_invalid", &self.on_invalid)
            .field("admitted_gen", &self.admitted_gen)
            .field("deadline", &self.deadline)
            .finish()
    }
}

impl<D: Domain> Clone for Precondition<D> {
    fn clone(&self) -> Self {
        match self {
            Self::EntityAlive { id, generation } => Self::EntityAlive { id: *id, generation: *generation },
            Self::EncounterActive { id, generation } => Self::EncounterActive { id: *id, generation: *generation },
            Self::ActorEligible { id, turn } => Self::ActorEligible { id: *id, turn: *turn },
            Self::ResourceAtLeast { id, kind, amount } => Self::ResourceAtLeast {
                id: *id,
                kind: *kind,
                amount: *amount,
            },
            Self::IslandOwns { id } => Self::IslandOwns { id: *id },
        }
    }
}

impl<D: Domain> core::fmt::Debug for Precondition<D> {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::EntityAlive { id, generation } => {
                f.debug_struct("EntityAlive").field("id", id).field("generation", generation).finish()
            }
            Self::EncounterActive { id, generation } => {
                f.debug_struct("EncounterActive").field("id", id).field("generation", generation).finish()
            }
            Self::ActorEligible { id, turn } => {
                f.debug_struct("ActorEligible").field("id", id).field("turn", turn).finish()
            }
            Self::ResourceAtLeast { id, kind, amount } => f
                .debug_struct("ResourceAtLeast")
                .field("id", id)
                .field("kind", kind)
                .field("amount", amount)
                .finish(),
            Self::IslandOwns { id } => f.debug_struct("IslandOwns").field("id", id).finish(),
        }
    }
}

impl<D: Domain> Clone for Fallback<D> {
    fn clone(&self) -> Self {
        match self {
            Self::Drop => Self::Drop,
            Self::Substitute(p) => Self::Substitute(p.clone()),
            Self::Notify(e, r) => Self::Notify(*e, r.clone()),
            Self::Buffer => Self::Buffer,
        }
    }
}

impl<D: Domain> core::fmt::Debug for Fallback<D> {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Drop => write!(f, "Drop"),
            Self::Substitute(p) => f.debug_tuple("Substitute").field(p).finish(),
            Self::Notify(e, r) => f.debug_tuple("Notify").field(e).field(r).finish(),
            Self::Buffer => write!(f, "Buffer"),
        }
    }
}

impl<D: Domain> Clone for Outcome<D> {
    fn clone(&self) -> Self {
        match self {
            Self::Applied { events } => Self::Applied { events: events.clone() },
            Self::Discarded { reason } => Self::Discarded { reason: reason.clone() },
            Self::Buffered => Self::Buffered,
        }
    }
}

impl<D: Domain> core::fmt::Debug for Outcome<D> {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Applied { events } => f.debug_struct("Applied").field("events", events).finish(),
            Self::Discarded { reason } => {
                f.debug_struct("Discarded").field("reason", reason).finish()
            }
            Self::Buffered => write!(f, "Buffered"),
        }
    }
}

/// REC-63's closed enum — referenced throughout doc 14, enumerated here.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DiscardReason {
    /// I2 seen-set hit.
    Duplicate,
    /// SC-A1 step-time re-validation miss.
    PreconditionFailed(Violation),
    /// Generational invalidation (S1b activates the cascade).
    Superseded,
    /// Deadline passed before step (SL-A4).
    Expired,
    /// The input's `apply` PANICKED; the item is quarantined and the island
    /// poisoned (SC-A9). Fifth variant added at S1b — amends the REC-63
    /// four-variant note (flagged in the reconciliation register).
    Quarantined,
}
