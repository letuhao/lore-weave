//! TMP_003 — the modificator pipeline: each generation step (terrain paint,
//! treasure place, …) is a [`Modificator`] with declared dependencies; the
//! [`ModificatorRegistry`] topologically sorts them (Kahn 1962) and runs them.
//!
//! Phase 1 builds the framework + runs it single-threaded (spec D6); the
//! thread-pool parallel mode (§4.2) is a later optimisation on a proven-
//! deterministic base.

pub mod modificator;
pub mod registry;

pub use modificator::{Modificator, ModificatorContext};
pub use registry::ModificatorRegistry;
