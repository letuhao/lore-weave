//! contracts-prompt — RAID cycle 27 L5.I.3.
//!
//! Full implementation of the cycle-25 `dp-kernel::canon_cache::CanonGuardrail`
//! trait (Q-L5-5 LOCKED). Production roleplay-service / world-service binds
//! [`canon_guardrail::YamlGuardrail`] (or any other concrete impl in this
//! crate) in place of the `NoOpGuardrail` placeholder shipped in cycle 25.
//!
//! # Why a separate crate
//!
//! The cycle-25 interface lives in `dp-kernel` to keep the core dependency
//! surface small. The full implementation needs:
//!
//! - YAML loader (`serde_yaml`) — not needed by every dp-kernel consumer.
//! - Rule predicate evaluation that grows over time without rebuilding
//!   the kernel.
//! - A separate test surface (rule fixtures, axiom samples).
//!
//! Pulling these into `dp-kernel` would expand its dep graph for every
//! kernel consumer. Splitting keeps the kernel slim.
//!
//! # Backwards-compatibility (Q-L5-5)
//!
//! Cycle 25 shipped the trait + `NoOpGuardrail` + `StubRejectGuardrail`.
//! Cycle 27 adds full impls — the trait signature is UNCHANGED:
//!
//! ```ignore
//! trait CanonGuardrail: Send + Sync {
//!     fn check_proposed_write(&self, proposal: &GuardrailProposal)
//!         -> Result<(), GuardrailViolation>;
//! }
//! ```
//!
//! Production wiring replaces `NoOpGuardrail` with [`canon_guardrail::YamlGuardrail`]
//! transparently — no caller code changes.

pub mod canon_guardrail;

pub use canon_guardrail::{
    Predicate, Rule, RuleSet, RuleSetLoadError, YamlGuardrail,
};

// Re-export the cycle-25 dp-kernel surface so consumers can import a single
// crate (contracts-prompt) without also depending on dp-kernel directly.
pub use dp_kernel::canon_cache::{
    CanonGuardrail, CanonValue, GuardrailProposal, GuardrailViolation, NoOpGuardrail,
    StubRejectGuardrail,
};
