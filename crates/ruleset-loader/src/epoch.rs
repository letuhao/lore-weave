//! `Q0b B1b` — an epoch switch, and the one check that can refuse it.
//!
//! ## Why this is not a method on `BindingStore`
//!
//! [`BindingStore::activate_epoch`] appends a row. It enforces nothing, and it
//! must not: the refusal needs the *rulesets* of every prior epoch, which live
//! in the content store, which the binding seam has no business reaching. A
//! storage trait that had to load rulesets to append a row would be a storage
//! trait that depends on everything.
//!
//! So the layering is: **the store is durable, this module is the law.**
//!
//! ## What the law is
//!
//! > **`QTY-A5`** — ordinals are assigned, monotonic, live inside the hashed
//! > ruleset, and **are never reused**.
//!
//! `Q1` shipped the first three clauses and deliberately left the fourth with no
//! subject: within one ruleset an ordinal *is* its position and the layer merge
//! is a union with no verb for removal, so nothing could violate it. **An epoch
//! switch is what gives it a subject** — a new layer stack can simply omit what
//! the old one declared, freeing an ordinal to mean something else.
//!
//! The check runs against **every prior epoch**, not the current one. That is
//! the whole reason `reality_ruleset_binding` is one row per epoch and closed
//! `QTY-Q6` with an append-only history instead of a mutable column: an ordinal
//! freed at epoch 2 is still meant by epoch 1's committed events, and checking
//! only against epoch 2 finds it free and hands it out.
//!
//! ## The policy on a violation: REFUSE (PO decision, 2026-07-29)
//!
//! The alternatives were *refuse the switch* or *accept and renumber*. Renumbering
//! is not available: the ordinals are inside the hashed bytes, so renumbering
//! produces a different digest for the same rules and every committed event
//! keeps referring to the old numbers regardless. Refusing leaves the reality on
//! its current epoch — which is a working reality, not a broken one — and the
//! operator edits the layer stack and tries again.

use ruleset_core::{OrdinalReuse, QuantityTable, RulesetDigest};

use crate::binding::{BindingError, BindingStore, RealityBinding};
use crate::store::{RulesetStore, StoreError};

/// Why an epoch switch did not happen.
#[derive(Debug)]
pub enum EpochSwitchError {
    /// The binding could not be read or appended.
    Binding(BindingError),
    /// The content store could not be read.
    Store(StoreError),
    /// A ruleset a prior epoch is bound to is **not in the store**.
    ///
    /// Not merely "a read failed": it means the never-reuse check cannot be
    /// computed, because the ordinals of that epoch are unknown. Proceeding
    /// would be a check that silently examined fewer epochs than it claims —
    /// so the switch is refused instead. **This is the one branch that turns a
    /// missing file into a refusal rather than a warning**, and it is
    /// deliberate: a partial history is indistinguishable from a clean one to
    /// everything downstream.
    PriorRulesetMissing { epoch: u32, digest: String },
    /// The new ruleset is not in the store — `put` it first.
    NewRulesetMissing { digest: String },
    /// `QTY-A5`: an ordinal would change meaning.
    OrdinalReused(OrdinalReuse),
}

impl core::fmt::Display for EpochSwitchError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Binding(e) => write!(f, "epoch switch: {e}"),
            Self::Store(e) => write!(f, "epoch switch: {e}"),
            Self::PriorRulesetMissing { epoch, digest } => write!(
                f,
                "epoch {epoch} is bound to ruleset {digest}, which is NOT in the content \
                 store. The QTY-A5 never-reuse check is computed over every prior epoch \
                 and cannot be computed without it, so the switch is refused rather than \
                 run against a partial history - a check that silently examines fewer \
                 epochs than it claims is worse than no check"
            ),
            Self::NewRulesetMissing { digest } => write!(
                f,
                "the ruleset being switched TO ({digest}) is not in the content store: \
                 store it before binding to it, or the reality would be bound to bytes \
                 that do not exist"
            ),
            Self::OrdinalReused(e) => write!(f, "{e}"),
        }
    }
}

impl From<BindingError> for EpochSwitchError {
    fn from(e: BindingError) -> Self {
        Self::Binding(e)
    }
}

impl From<StoreError> for EpochSwitchError {
    fn from(e: StoreError) -> Self {
        Self::Store(e)
    }
}

/// The quantity tables of every epoch this reality has ever been bound to.
///
/// Separate from [`activate_reality_epoch`] because it is the expensive half and
/// the interesting half: a caller that wants to *ask* whether a switch would be
/// permitted (a Forge preview, a dry run) needs the priors without the append.
pub fn prior_quantity_tables(
    bindings: &dyn BindingStore,
    store: &RulesetStore,
    reality_id: &str,
) -> Result<Vec<QuantityTable>, EpochSwitchError> {
    let mut out = Vec::new();
    for b in bindings.history(reality_id)? {
        // A digest that is not 64 hex is a corrupt BINDING, not a missing
        // ruleset — the file store is hand-editable and both conditions refuse,
        // so it would be easy to fold them. Don't: `PriorRulesetMissing` tells
        // an operator to restore bytes, which is the wrong instruction when the
        // row itself is the damaged thing.
        let digest = parse_hex(&b.digest).ok_or_else(|| {
            EpochSwitchError::Binding(BindingError::BadDigest(b.digest.clone()))
        })?;
        let rules = store.get(&digest)?.ok_or(EpochSwitchError::PriorRulesetMissing {
            epoch: b.epoch,
            digest: b.digest.clone(),
        })?;
        out.push(rules.quantities);
    }
    Ok(out)
}

/// Switch a reality to `digest`, refusing if it would reuse an ordinal.
///
/// Order matters and is the reason this reads the way it does: **the check runs
/// before the append**, so a refused switch leaves the binding table untouched
/// and the reality on a working epoch. An append-then-validate would have to
/// delete a row from a table whose entire guarantee is that rows are never
/// deleted.
pub fn activate_reality_epoch(
    bindings: &dyn BindingStore,
    store: &RulesetStore,
    reality_id: &str,
    digest: &RulesetDigest,
    reason: &str,
) -> Result<RealityBinding, EpochSwitchError> {
    // Refuse an unbound reality HERE as well as in the store. The store's check
    // is the durable one; this one exists so the error is `NotBound` rather than
    // an empty-priors vector that would make every switch trivially permitted —
    // a check whose scope silently became empty is the NV-3 shape.
    if bindings.load(reality_id)?.is_none() {
        return Err(BindingError::NotBound { reality_id: reality_id.to_string() }.into());
    }

    let next = store
        .get(digest)?
        .ok_or_else(|| EpochSwitchError::NewRulesetMissing { digest: digest.to_hex() })?;

    let priors = prior_quantity_tables(bindings, store, reality_id)?;
    let refs: Vec<&QuantityTable> = priors.iter().collect();
    if let Err(reuse) = next.quantities.check_never_reused(&refs) {
        return Err(EpochSwitchError::OrdinalReused(reuse));
    }

    Ok(bindings.activate_epoch(reality_id, digest, reason)?)
}

fn parse_hex(hex: &str) -> Option<RulesetDigest> {
    if hex.len() != 64 {
        return None;
    }
    let mut out = [0u8; 32];
    for (i, b) in out.iter_mut().enumerate() {
        *b = u8::from_str_radix(hex.get(i * 2..i * 2 + 2)?, 16).ok()?;
    }
    Some(RulesetDigest(out))
}
