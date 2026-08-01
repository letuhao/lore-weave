//! Two-lane ingress (SC-D1): `Live` (player-visible latency) drains strictly
//! before `Background`. Admission stamps `Seq` — and does NOTHING else; all
//! validation happens at step time (spec §5).

use std::collections::VecDeque;
use std::sync::Arc;

use crate::domain::Domain;
use crate::types::{Gen, QueuedInput, RulesetEpoch, Seq};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lane {
    Live,
    Background,
}

/// What sits in a lane: ordinary domain work, or a kernel control item.
///
/// ## Why the queue needed a second shape
///
/// `RLS-A14` — *a ruleset epoch switch enters each affected island as an
/// **ordinary ingress item***. `QueuedInput` cannot carry one: it holds a
/// `D::Payload`, and a ruleset switch is not something the domain has an
/// opinion about. Giving it a payload variant would push a kernel concern into
/// every domain's vocabulary, including the ones that will never switch.
///
/// ## What the ORDERING buys, and it is not what it first looks like
///
/// The obvious reading is *"items ahead of the switch run under the old rules,
/// items behind it under the new"* — and the second half is the interesting
/// one, because it is only safe for a reason stated three lines up in this
/// file: **admission stamps `Seq` and does nothing else; every precondition is
/// re-validated at STEP time** (spec §5). So an item queued before the switch
/// and stepped after it is checked against the rules in force *at its step*,
/// not the ones in force when it was admitted.
///
/// That is why the ordered path does **not** bump the island generation, while
/// [`Island::activate_epoch`](crate::Island::activate_epoch) — the out-of-band
/// host call, which has no position in the queue — must. The bump was `B2a`'s
/// conservative answer to a question ordering answers properly.
pub enum IngressItem<D: Domain> {
    Input(QueuedInput<D>),
    /// `RLS-A14`. Carries the resolved rules rather than a digest to look up:
    /// the island has no store to look anything up in (`IMP-D2` — the kernel
    /// reaches no I/O), so the host resolves and hands over the `Arc`.
    EpochSwitch {
        seq: Seq,
        epoch: RulesetEpoch,
        rules: Arc<D::Rules>,
        /// Stamped like any other item so a dissolution cancels a pending
        /// switch too. A switch that survived an island's death and applied to
        /// its successor would move a *different* island's epoch.
        admitted_gen: Gen,
    },
}

impl<D: Domain> IngressItem<D> {
    pub fn seq(&self) -> Seq {
        match self {
            Self::Input(i) => i.seq,
            Self::EpochSwitch { seq, .. } => *seq,
        }
    }

    fn set_seq(&mut self, s: Seq) {
        match self {
            Self::Input(i) => i.seq = s,
            Self::EpochSwitch { seq, .. } => *seq = s,
        }
    }

    pub fn admitted_gen(&self) -> Gen {
        match self {
            Self::Input(i) => i.admitted_gen,
            Self::EpochSwitch { admitted_gen, .. } => *admitted_gen,
        }
    }

    pub fn set_admitted_gen(&mut self, g: Gen) {
        match self {
            Self::Input(i) => i.admitted_gen = g,
            Self::EpochSwitch { admitted_gen, .. } => *admitted_gen = g,
        }
    }

    /// The domain input, if this is one. Named `into_input` rather than
    /// `unwrap_input`: a control item is not an error case, and every caller
    /// that only handles inputs must say what it does with the other arm.
    pub fn into_input(self) -> Option<QueuedInput<D>> {
        match self {
            Self::Input(i) => Some(i),
            Self::EpochSwitch { .. } => None,
        }
    }
}

// Manual impls for the same reason `QueuedInput` has them: a derive would
// demand `D: Clone` / `D: Debug` on the domain marker instead of using the
// associated-type bounds.
impl<D: Domain> Clone for IngressItem<D> {
    fn clone(&self) -> Self {
        match self {
            Self::Input(i) => Self::Input(i.clone()),
            Self::EpochSwitch { seq, epoch, rules, admitted_gen } => Self::EpochSwitch {
                seq: *seq,
                epoch: *epoch,
                rules: Arc::clone(rules),
                admitted_gen: *admitted_gen,
            },
        }
    }
}

impl<D: Domain> core::fmt::Debug for IngressItem<D> {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Input(i) => f.debug_tuple("Input").field(i).finish(),
            // The rules are NOT printed: `D::Rules` has no Debug bound, and a
            // resolved ruleset in a log line is noise measured in kilobytes.
            Self::EpochSwitch { seq, epoch, admitted_gen, .. } => f
                .debug_struct("EpochSwitch")
                .field("seq", seq)
                .field("epoch", epoch)
                .field("admitted_gen", admitted_gen)
                .finish_non_exhaustive(),
        }
    }
}

#[derive(Debug)]
pub struct Ingress<D: Domain> {
    live: VecDeque<IngressItem<D>>,
    background: VecDeque<IngressItem<D>>,
    next_seq: u64,
}

impl<D: Domain> Ingress<D> {
    pub fn new() -> Self {
        Self {
            live: VecDeque::new(),
            background: VecDeque::new(),
            next_seq: 0,
        }
    }

    /// Admit an input: stamp the next monotonic `Seq` (overwriting any
    /// caller-supplied value) and enqueue. Returns the stamp.
    pub fn push(&mut self, lane: Lane, mut item: IngressItem<D>) -> Seq {
        let seq = Seq(self.next_seq);
        self.next_seq += 1;
        item.set_seq(seq);
        match lane {
            Lane::Live => self.live.push_back(item),
            Lane::Background => self.background.push_back(item),
        }
        seq
    }

    /// Re-offer a buffered input at the FRONT of its lane, PRESERVING its
    /// original `Seq` (spec §5.3: buffered intents keep their stamp).
    pub fn push_front_preserving_seq(&mut self, lane: Lane, item: IngressItem<D>) {
        match lane {
            Lane::Live => self.live.push_front(item),
            Lane::Background => self.background.push_front(item),
        }
    }

    /// SC-D1: Live strictly first. Returns the lane the item came from —
    /// a buffered re-offer must go back to ITS lane (a Background item that
    /// jumped to Live on retry would be a priority inversion).
    pub fn pop(&mut self) -> Option<(Lane, IngressItem<D>)> {
        if let Some(i) = self.live.pop_front() {
            return Some((Lane::Live, i));
        }
        self.background.pop_front().map(|i| (Lane::Background, i))
    }

    /// S2 dissolution: remove EVERYTHING, Live first (stable order for the
    /// transfer path — the successor re-admits in this order).
    pub fn drain_all(&mut self) -> Vec<(Lane, IngressItem<D>)> {
        let mut out = Vec::with_capacity(self.len());
        out.extend(self.live.drain(..).map(|i| (Lane::Live, i)));
        out.extend(self.background.drain(..).map(|i| (Lane::Background, i)));
        out
    }

    /// S2 checkpoint: the next stamp this ingress would assign. Restored via
    /// [`Ingress::with_next_seq`] so post-restore stamps never collide with
    /// pre-checkpoint ones in host logs.
    pub fn next_seq(&self) -> u64 {
        self.next_seq
    }

    pub fn with_next_seq(next_seq: u64) -> Self {
        Self {
            live: VecDeque::new(),
            background: VecDeque::new(),
            next_seq,
        }
    }

    pub fn len(&self) -> usize {
        self.live.len() + self.background.len()
    }

    pub fn is_empty(&self) -> bool {
        self.live.is_empty() && self.background.is_empty()
    }
}

impl<D: Domain> Default for Ingress<D> {
    fn default() -> Self {
        Self::new()
    }
}
