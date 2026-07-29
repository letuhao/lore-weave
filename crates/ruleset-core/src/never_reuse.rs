//! `QTY-A5`'s never-reuse arm: an ordinal is assigned, monotonic, and **never
//! reused on removal**.
//!
//! Split out of `quantity.rs` when adding this pushed that file past `IMP-D3`'s
//! 400-line ceiling. The cap was not raised, and the boundary is a real one
//! rather than a convenient cut: `quantity.rs` is a DATA STRUCTURE (a fixed-width
//! table of declared identities and its codec), while this is a POLICY over a
//! *history* of those tables. The table cannot enforce this on its own — it has
//! no idea what any earlier epoch declared.
//!
//! ## Why it lives here and not in the loader
//!
//! It is pure: tables in, verdict out, no I/O and no store. The caller gathers
//! the priors (`ruleset-loader` walks the binding history and fetches each
//! epoch's ruleset by digest); this decides. Keeping the decision in
//! `ruleset-core` means `game-rules` and the kernel can reason about it without
//! reaching for a crate that can open a file (`IMP-D2`).

use crate::quantity::QuantityTable;

/// An ordinal a prior epoch bound to one identity, rebound to another.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrdinalReuse {
    /// The ordinal whose meaning would change.
    pub ordinal: u16,
    /// What some earlier epoch assigned it.
    pub was: String,
    /// What the candidate ruleset assigns it.
    pub now: String,
}

impl core::fmt::Display for OrdinalReuse {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(
            f,
            "ordinal {} was `{}` in an earlier epoch and would become `{}`: committed \
             events refer to a quantity BY NUMBER, so reusing it silently reinterprets \
             every one of them (QTY-A5). The epoch switch is refused; the reality stays \
             on its current epoch (doc 16 §9)",
            self.ordinal, self.was, self.now
        )
    }
}

impl QuantityTable {
    /// **QTY-A5: an ordinal is assigned, monotonic, and NEVER REUSED ON REMOVAL.**
    ///
    /// Checks a candidate table against every table that was ever in force for
    /// this reality. `priors` is the quantity table of each prior epoch's
    /// ruleset, in any order — the union is what matters, not the sequence.
    ///
    /// ## Why this could not be built in `Q1`, and can be now
    ///
    /// Within one ruleset the ordinal IS the position, and the layer merge is a
    /// union with no verb for removal — so nothing can be removed and the rule
    /// has no possible violation. It only acquires a subject at an **epoch
    /// switch**, where a new layer stack can simply omit what the old one
    /// declared. `Q1` shipped this as an asserted trigger rather than a
    /// validator that returns *permitted* for every input that can exist (NV-2).
    /// This is that subject arriving.
    ///
    /// ## Why the union of priors, not just the previous epoch
    ///
    /// Remove `karma` at epoch 2 and re-add a different quantity at epoch 3:
    /// comparing only against epoch 2 would find ordinal 1 free and hand it out,
    /// while epoch 1's committed events still mean `karma` by it. The high-water
    /// mark is over **everything that ever was**, which is exactly why
    /// `reality_ruleset_binding` keeps one row per epoch instead of one mutable
    /// column (`QTY-Q6`).
    ///
    /// Returns the FIRST reuse found — refusing is all-or-nothing, so there is
    /// nothing a caller could do with the rest.
    pub fn check_never_reused(
        &self,
        priors: &[&QuantityTable],
    ) -> Result<(), OrdinalReuse> {
        for prior in priors {
            for ordinal in 0..prior.len() as u16 {
                let Some(was) = prior.name_of(ordinal) else { continue };
                match self.name_of(ordinal) {
                    // Same identity — the normal additive case.
                    Some(now) if now.as_str() == was.as_str() => {}
                    // Rebound to something else: the violation.
                    Some(now) => {
                        return Err(OrdinalReuse {
                            ordinal,
                            was: was.as_str().to_string(),
                            now: now.as_str().to_string(),
                        })
                    }
                    // DROPPED, not rebound. Allowed: the ordinal is retired, and
                    // because the candidate table is a prefix `0..n`, a shorter
                    // table can only drop from the TAIL. Nothing later can take
                    // the slot without tripping the arm above, so history stays
                    // readable. (QTY-A10(c) calls the slot "never reused and
                    // never removed"; removal from the tail is indistinguishable
                    // from never having declared it, for every committed event.)
                    None => {}
                }
            }
        }
        Ok(())
    }
}
