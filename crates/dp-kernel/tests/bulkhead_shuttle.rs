//! W2.5 — shuttle model-check of the bulkhead ADMISSION algorithm
//! (closes D-S6-BULKHEAD-SHUTTLE).
//!
//! Lives in `tests/` (NOT in lib code) deliberately: the model uses the
//! `shuttle` dev-dependency, and dp-kernel has integration tests, so a
//! `#[cfg(shuttle)] mod` inside the lib would be compiled during the *normal*
//! lib build (under `--cfg shuttle`) where dev-deps are NOT linked. An
//! integration-test file is only ever built as a test target, with dev-deps
//! available. The whole file is `#![cfg(shuttle)]` so a normal `cargo test`
//! compiles an empty target.
//!
//! SCOPE (honest, per plan R1 + the S9 model-check precedent): the production
//! `Bulkhead` delegates its slot gate to `tokio::sync::Semaphore` +
//! `tokio::time::timeout`, which shuttle CANNOT intercept (it drives its own
//! executor + sync primitives). So this does NOT check the literal `Bulkhead`
//! struct — it model-checks the ADMISSION ALGORITHM it embodies: "never admit
//! more than `max` concurrently." A faithful async model-check of the literal
//! tokio bulkhead needs a tokio-aware checker (turmoil / a loom-async fork) —
//! tracked as D-W2-BULKHEAD-SHUTTLE-LITERAL. The bite proves the harness
//! actually explores interleavings and catches a real over-admission race, so
//! this is non-vacuous.
//!
//! Run: `RUSTFLAGS="--cfg shuttle" cargo test -p dp-kernel --test bulkhead_shuttle`
#![cfg(shuttle)]

use shuttle::sync::atomic::{AtomicUsize, Ordering::SeqCst};
use shuttle::sync::{Arc, Mutex};

const MAX: usize = 2;
const THREADS: usize = 3;

// CORRECT admission: the check + the increment happen under ONE lock, so the
// decision is atomic — exactly the guarantee tokio::Semaphore gives.
struct Correct {
    active: Mutex<usize>,
}
impl Correct {
    fn try_admit(&self) -> bool {
        let mut g = self.active.lock().unwrap();
        if *g < MAX {
            *g += 1;
            true
        } else {
            false
        }
    }
    fn release(&self) {
        *self.active.lock().unwrap() -= 1;
    }
}

// RACY admission (the bite): check then increment as SEPARATE atomic ops — the
// gap between the load and the fetch_add lets multiple callers all read "< MAX"
// before any commits, over-admitting.
struct Racy {
    active: AtomicUsize,
}
impl Racy {
    fn try_admit(&self) -> bool {
        if self.active.load(SeqCst) < MAX {
            // GAP — another thread can pass this check before we commit below.
            self.active.fetch_add(1, SeqCst);
            true
        } else {
            false
        }
    }
    fn release(&self) {
        self.active.fetch_sub(1, SeqCst);
    }
}

// `inside` is an independent, always-correct observer of how many callers are
// CONCURRENTLY in the admitted region — it measures what the gate actually let
// through, regardless of the gate's own (possibly broken) bookkeeping.
fn contend_correct() {
    let gate = Arc::new(Correct { active: Mutex::new(0) });
    let inside = Arc::new(AtomicUsize::new(0));
    let hs: Vec<_> = (0..THREADS)
        .map(|_| {
            let g = gate.clone();
            let ins = inside.clone();
            shuttle::thread::spawn(move || {
                if g.try_admit() {
                    let c = ins.fetch_add(1, SeqCst) + 1;
                    assert!(c <= MAX, "more than MAX concurrently admitted: {c}");
                    ins.fetch_sub(1, SeqCst);
                    g.release();
                }
            })
        })
        .collect();
    for h in hs {
        h.join().unwrap();
    }
}

fn contend_racy() {
    let gate = Arc::new(Racy { active: AtomicUsize::new(0) });
    let inside = Arc::new(AtomicUsize::new(0));
    let hs: Vec<_> = (0..THREADS)
        .map(|_| {
            let g = gate.clone();
            let ins = inside.clone();
            shuttle::thread::spawn(move || {
                if g.try_admit() {
                    let c = ins.fetch_add(1, SeqCst) + 1;
                    assert!(c <= MAX, "more than MAX concurrently admitted: {c}");
                    ins.fetch_sub(1, SeqCst);
                    g.release();
                }
            })
        })
        .collect();
    for h in hs {
        h.join().unwrap();
    }
}

/// PRIMARY: a correct gate NEVER lets more than MAX callers into the admitted
/// region at once. `check_random` samples thousands of schedules (bounded,
/// fast); an unbounded DFS over a 3-thread model is too large to run in CI.
#[test]
fn correct_admission_caps_concurrency() {
    shuttle::check_random(contend_correct, 5000);
}

/// BITE (non-vacuity): the racy gate's check→increment gap over-admits on some
/// schedule; shuttle finds it and the `c <= MAX` assertion panics.
/// `#[should_panic]` asserts shuttle caught it — a vacuous harness that did not
/// explore interleavings would NOT panic and this test would FAIL.
#[test]
#[should_panic]
fn bite_racy_admission_breaks_the_cap() {
    shuttle::check_random(contend_racy, 5000);
}
