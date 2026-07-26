//! Two-lane ingress (SC-D1): `Live` (player-visible latency) drains strictly
//! before `Background`. Admission stamps `Seq` — and does NOTHING else; all
//! validation happens at step time (spec §5).

use std::collections::VecDeque;

use crate::domain::Domain;
use crate::types::{QueuedInput, Seq};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lane {
    Live,
    Background,
}

#[derive(Debug)]
pub struct Ingress<D: Domain> {
    live: VecDeque<QueuedInput<D>>,
    background: VecDeque<QueuedInput<D>>,
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
    pub fn push(&mut self, lane: Lane, mut input: QueuedInput<D>) -> Seq {
        let seq = Seq(self.next_seq);
        self.next_seq += 1;
        input.seq = seq;
        match lane {
            Lane::Live => self.live.push_back(input),
            Lane::Background => self.background.push_back(input),
        }
        seq
    }

    /// Re-offer a buffered input at the FRONT of its lane, PRESERVING its
    /// original `Seq` (spec §5.3: buffered intents keep their stamp).
    pub fn push_front_preserving_seq(&mut self, lane: Lane, input: QueuedInput<D>) {
        match lane {
            Lane::Live => self.live.push_front(input),
            Lane::Background => self.background.push_front(input),
        }
    }

    /// SC-D1: Live strictly first. Returns the lane the item came from —
    /// a buffered re-offer must go back to ITS lane (a Background item that
    /// jumped to Live on retry would be a priority inversion).
    pub fn pop(&mut self) -> Option<(Lane, QueuedInput<D>)> {
        if let Some(i) = self.live.pop_front() {
            return Some((Lane::Live, i));
        }
        self.background.pop_front().map(|i| (Lane::Background, i))
    }

    /// S2 dissolution: remove EVERYTHING, Live first (stable order for the
    /// transfer path — the successor re-admits in this order).
    pub fn drain_all(&mut self) -> Vec<(Lane, QueuedInput<D>)> {
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
