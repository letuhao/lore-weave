//! Deterministic single-threaded simulation executor (Path B — VOPR-style).
//!
//! ## Why not madsim (Path A)
//!
//! `dp-kernel` hard-links `sqlx` (`crates/dp-kernel/Cargo.toml`, non-optional).
//! madsim replaces `tokio` globally via a Cargo `[patch]` under `--cfg madsim`,
//! and `sqlx` is NOT on madsim's supported-driver list (madsim ships
//! `madsim-tokio-postgres`, not sqlx) — so any crate that transitively pulls
//! `dp-kernel` fails to build under the patch. See `README.md` §Decision for the
//! empirical record. Path B owns its scheduler instead: no tokio patch, no sqlx
//! wall, fully deterministic, and the SAME seed-reproducible property madsim
//! would give (TigerBeetle's VOPR is this same idea — madsim is merely one impl).
//!
//! ## How interleavings arise (the non-vacuity precondition)
//!
//! The kernel's in-sim async surface ([`crate::store::SimEventStore`]) is
//! reactor-free — every op is a `Mutex` lock with no IO `await`, so its future
//! resolves on first poll. Interleavings therefore exist ONLY where an actor
//! explicitly `[sim_yield]`s. Without yield points every future would complete
//! atomically on first poll and the sim would be vacuously single-path. The
//! Inc-1 gate (`crate::skeleton`) proves the yields actually interleave.

use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll, Waker};

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

/// A simulated task: a `'static` future driven to completion by [`Sim::run`].
/// Deliberately NOT `Send` — the executor is single-threaded by construction
/// (single-thread + seeded RNG is the whole source of determinism).
pub type SimTask = Pin<Box<dyn Future<Output = ()>>>;

/// A cooperative yield point. Returns `Pending` exactly once, handing control
/// back to the scheduler so a *different* task may run before this one resumes.
/// Place one between actor ops to expose them to interleaving.
pub fn sim_yield() -> SimYield {
    SimYield { yielded: false }
}

/// Future returned by [`sim_yield`]. Pending on the first poll, Ready after.
pub struct SimYield {
    yielded: bool,
}

impl Future for SimYield {
    type Output = ();
    fn poll(mut self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<()> {
        if self.yielded {
            Poll::Ready(())
        } else {
            self.yielded = true;
            Poll::Pending
        }
    }
}

/// The deterministic scheduler. A `seed` fixes the entire interleaving: same
/// seed ⇒ identical observable trace; different seed ⇒ (almost surely) a
/// different one.
pub struct Sim;

impl Sim {
    /// Run `tasks` to completion under a seed-determined interleaving. At each
    /// step the seeded RNG picks one not-yet-finished task and polls it once; a
    /// task that yields (`Pending`) stays runnable and may be re-picked.
    ///
    /// The executor returns nothing itself — the observable trace lives in the
    /// shared state the tasks mutate (e.g. [`crate::store::SimEventStore`]'s
    /// global append log).
    pub fn run(seed: u64, tasks: Vec<SimTask>) {
        let mut rng = ChaCha8Rng::seed_from_u64(seed);
        let mut tasks = tasks;
        // Indices of tasks not yet finished. `swap_remove` keeps this O(1) and
        // is itself deterministic (same seed ⇒ same removal sequence).
        let mut alive: Vec<usize> = (0..tasks.len()).collect();
        let waker = Waker::noop();
        let mut cx = Context::from_waker(waker);
        while !alive.is_empty() {
            let pick = rng.random_range(0..alive.len());
            let idx = alive[pick];
            match tasks[idx].as_mut().poll(&mut cx) {
                Poll::Ready(()) => {
                    alive.swap_remove(pick);
                }
                Poll::Pending => {}
            }
        }
    }
}
