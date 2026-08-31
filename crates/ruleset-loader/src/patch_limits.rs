//! `LIM-1` — **the authored `[limits]` block, and the fold that enforces it.**
//!
//! Its own file for the reason `patch_resource.rs` and `patch_verb.rs` are
//! theirs: one authored block, its parse shape and the arm that applies it,
//! within reading distance of each other. It is also the only block in
//! `RulesetPatch` that CONSTRAINS the others rather than contributing to them,
//! and that difference is worth a file boundary rather than a paragraph.
//!
//! Split out when adding it pushed `patch.rs` past `IMP-D3`'s 400-line ceiling.
//! Paid in a split rather than an allowlist row.

use ruleset_core::{Limits, OrdinalSpace, Ruleset};
use serde::Deserialize;

/// `LIM-1` — one layer's contribution to the reality's declared size.
///
/// **Every field `Option`, and an absent field is not zero.** A layer that
/// declares no `[limits]` block inherits whatever the layers below it declared,
/// and a stack that declares none anywhere runs at [`Limits::CAPACITY`] — which
/// is exactly the behaviour every manifest had before this block existed. That
/// default is `AUTHOR-1`'s call: a mandatory block on every preset would be a
/// cost paid by every author to serve the few who want a tighter bound.
///
/// **There is no `cues` key.** A cue space is derived from the verb limit
/// (`Limits::cues`) because every cue comes from a verb row and there is exactly
/// one per row. A key an author could set independently would be a number to
/// keep in step with another number, for no gain.
///
/// **There is no `plugins` key either**, and the reason is a boundary rather
/// than a convenience: a plugin is a compiled-in engine feature, not an authored
/// row, so a manifest declaring a plugin ceiling would be declaring a limit on
/// the binary it is running against.
#[derive(Debug, Clone, Copy, Default, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LimitsPatch {
    pub quantities: Option<u16>,
    pub resources: Option<u16>,
    pub verbs: Option<u16>,
}

impl LimitsPatch {
    /// This layer's value for `space`, if it declares one.
    ///
    /// EXHAUSTIVE destructuring: a new [`OrdinalSpace`] variant is a compile
    /// error here until it is given a key, which is what stops the register and
    /// the authored surface drifting apart — the exact drift that let a cue
    /// space ship with no bound at all.
    fn get(&self, space: OrdinalSpace) -> Option<u16> {
        let Self { quantities, resources, verbs } = self;
        match space {
            OrdinalSpace::Quantities => *quantities,
            OrdinalSpace::Resources => *resources,
            OrdinalSpace::Verbs => *verbs,
        }
    }
}


impl LimitsPatch {
    /// Apply this layer's declared sizes to the running fold.
    ///
    /// Called BEFORE the rows of its own layer (see `RulesetPatch::apply`), and
    /// that order is load-bearing: an author writes the block and the rows it
    /// governs in ONE file, so a layer that raises `verbs` to 24 and then
    /// declares its 20th verb has to see its own raise. Applying it after the
    /// rows would refuse the most natural thing anyone writes, and the bug would
    /// look like the limit "not working".
    pub(crate) fn fold_into(
        &self,
        limits: &mut Limits,
        base: &Ruleset,
    ) -> Result<(), ruleset_core::LimitError> {
        for space in OrdinalSpace::ALL {
            if let Some(value) = self.get(space) {
                limits.declare(space, value, declared_in(base, space))?;
            }
        }
        Ok(())
    }
}

/// How many rows of `space` the fold has accepted so far.
///
/// EXHAUSTIVE over [`OrdinalSpace`]: a new space is a compile error here until
/// it can answer this, which is what stops a limit being declarable for
/// something whose count nobody can read.
fn declared_in(base: &Ruleset, space: OrdinalSpace) -> usize {
    match space {
        OrdinalSpace::Quantities => base.quantities.len(),
        OrdinalSpace::Resources => base.resources.len(),
        OrdinalSpace::Verbs => base.verbs.len(),
    }
}
