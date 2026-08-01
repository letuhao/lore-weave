//! S2 reference router/host — the thing SC-A7 says sim-core must NOT be.
//!
//! The kernel holds no registry of other islands; THIS does. It is the
//! in-process reference implementation of the §9 transport contract:
//! - a message sent during tick-window T is delivered at the T+1 tick
//!   boundary (+1 tick latency, SL-A10);
//! - a missing/dissolved target discards the message WITH a recorded
//!   reason (a dead letter), never an error.
//!
//! `commit-service` (S3) owns the production equivalent; this one exists so
//! multi-island semantics are testable and the in-process routing cost is
//! measurable (SL-Q9 baseline before real IPC at S4b).

use std::collections::BTreeMap;

use sim_core::{Domain, Island, IslandId, IslandMessage, Lane, StepStatus};

/// A message the router could not deliver, with why. Recorded, never thrown.
pub struct DeadLetter<D: Domain> {
    pub message: IslandMessage<D>,
    pub reason: &'static str,
}

pub struct Realm<D: Domain> {
    /// BTreeMap: iteration order is part of replay-observable behavior.
    islands: BTreeMap<IslandId, Island<D>>,
    /// Sent this tick-window; delivered at the next `tick_all`.
    mailbox: Vec<IslandMessage<D>>,
    pub dead_letters: Vec<DeadLetter<D>>,
}

impl<D: Domain> Realm<D> {
    pub fn new() -> Self {
        Self {
            islands: BTreeMap::new(),
            mailbox: Vec::new(),
            dead_letters: Vec::new(),
        }
    }

    pub fn insert(&mut self, island: Island<D>) {
        self.islands.insert(island.id, island);
    }

    /// Take an island out — the only way to dissolve it (dissolve consumes).
    pub fn remove(&mut self, id: IslandId) -> Option<Island<D>> {
        self.islands.remove(&id)
    }

    pub fn island(&self, id: IslandId) -> Option<&Island<D>> {
        self.islands.get(&id)
    }

    pub fn island_mut(&mut self, id: IslandId) -> Option<&mut Island<D>> {
        self.islands.get_mut(&id)
    }

    /// Queue a message. NOT delivered until the next `tick_all` — the +1
    /// tick latency is enforced here, not in the kernel.
    pub fn send(&mut self, msg: IslandMessage<D>) {
        self.mailbox.push(msg);
    }

    /// Deliver the mailbox (in send order), then tick every island by `dt`.
    /// Cross-island messages ride the Live lane in this reference host
    /// (arrivals/handoffs are player-visible; a production router may split).
    pub fn tick_all(&mut self, dt: u64) {
        for msg in std::mem::take(&mut self.mailbox) {
            match self.islands.get_mut(&msg.to) {
                // A poisoned island never steps again — delivering into it
                // maroons the message silently. Dead-letter it instead
                // (§9: discarded WITH a recorded reason, never an error).
                Some(isle) if !isle.is_poisoned() => {
                    isle.deliver(Lane::Live, msg);
                }
                Some(_) => self.dead_letters.push(DeadLetter {
                    message: msg,
                    reason: "poisoned island",
                }),
                None => self.dead_letters.push(DeadLetter {
                    message: msg,
                    reason: "unknown-or-dissolved island",
                }),
            }
        }
        for isle in self.islands.values_mut() {
            isle.tick(dt);
        }
    }

    /// Step every island until all are idle (or poisoned). Returns total
    /// steps. Round-robin over BTreeMap order — deterministic.
    pub fn step_all(&mut self) -> u64 {
        let mut steps = 0u64;
        loop {
            let mut progressed = false;
            for isle in self.islands.values_mut() {
                match isle.step() {
                    StepStatus::Processed(_) => {
                        steps += 1;
                        progressed = true;
                    }
                    StepStatus::Idle | StepStatus::Poisoned => {}
                }
            }
            if !progressed {
                return steps;
            }
        }
    }

    pub fn len(&self) -> usize {
        self.islands.len()
    }

    pub fn is_empty(&self) -> bool {
        self.islands.is_empty()
    }
}

impl<D: Domain> Default for Realm<D> {
    fn default() -> Self {
        Self::new()
    }
}
