//! `resolve_block` — the DF7-A3 layered resolution, and the clamps around it.

use ruleset_core::{StatRules, StatSlot};

use super::block::StatBlock;
use super::modifier::{Clamp, ModifierOp, ModifierSource, StatModifier};

/// Intersect EVERY clamp declared for `slot`, returning `(min, max)`.
///
/// **XST-D8 (fixed 2026-07-28).** This was `clamps.iter().find(|c| c.slot == slot)`,
/// which takes the **first** clamp and discards the rest — so two content packs
/// both clamping `MaxHp` had their winner decided by `Vec` position, i.e. by
/// **load order**, reintroducing order-dependence through the back door of the
/// one mechanism advertised as order-independent (DF7-A5).
///
/// Intersection is order-independent *by construction*: `max` and `min` are both
/// commutative and associative, so shuffling the slice cannot change the result.
/// That is what makes the shuffle test in this module non-vacuous.
fn intersect_clamps(slot: StatSlot, clamps: &[Clamp]) -> Option<(i32, i32)> {
    let mut acc: Option<(i32, i32)> = None;
    for c in clamps.iter().filter(|c| c.slot == slot) {
        acc = Some(match acc {
            None => (c.min, c.max),
            Some((lo, hi)) => (lo.max(c.min), hi.min(c.max)),
        });
    }
    acc.map(|(lo, hi)| {
        // Contradictory declarations (`[50,100]` ∩ `[200,300]`) leave an EMPTY
        // range, and `i32::clamp` PANICS when min > max. The floor wins, which
        // is deterministic and never panics.
        //
        // DEFERRED past F2, with the reason. The loader validates the RULESET,
        // and clamps are not ruleset fields — they arrive per-actor from
        // equipment, status and world rules, which are content the loader never
        // sees. The refusal belongs wherever those clamps get declared, which
        // does not exist yet. Refusing here at RUNTIME instead is the wrong
        // trade: it would kill a live encounter over an author's contradiction.
        // This runtime rule exists so a contradiction degrades predictably, not
        // so contradictions are acceptable.
        (lo, hi.max(lo))
    })
}

/// Resolve a block from its inputs — a pure function (DF7-A2), in the locked
/// layer order (DF7-A3):
///
/// ```text
/// base → archetype → progression → equipment flat → status flat
///      → Σ percent (all sources) → slot clamp → LEX CLAMP (last)
/// ```
///
/// **The Lex clamp runs last and that ordering is a recorded correction.** The
/// first DRAFT ran `Lex → slot` reasoning that "an author clamp cannot escape a
/// world rule" — which is backwards: whichever clamp runs last wins, so a slot
/// clamp whose `min` exceeds the Lex ceiling would raise the value *back
/// through* it (DF07_002 EC-1). A world rule is never escapable, therefore it
/// is applied last.
///
/// All arithmetic is i64 milli-units with a single emit-time division —
/// DF7-A4.
pub fn resolve_block(
    archetype: &StatBlock,
    modifiers: &[StatModifier],
    slot_clamps: &[Clamp],
    lex_clamps: &[Clamp],
    rules: &StatRules,
) -> StatBlock {
    // Zeroed, not defaults: the loop below `set`s EVERY slot, so the starting
    // values are dead. Starting from the defaults would look like they matter
    // and hide a future slot the loop stops covering.
    let mut out = StatBlock::zeroed();

    for slot in StatSlot::ALL {
        // base → archetype
        let mut flat: i64 = archetype.get(slot) as i64;

        // Flat layers, in source order. Iterating the ORDERED source list
        // rather than the modifier list keeps the result independent of the
        // order modifiers happen to arrive in.
        //
        // XST-D7: this iterates ALL SIX sources. It previously iterated three.
        for source in ModifierSource::ALL {
            for m in modifiers.iter().filter(|m| m.slot == slot && m.source == source) {
                if let ModifierOp::Flat(v) = m.op {
                    flat += v as i64;
                }
            }
        }

        // Σ percent across ALL sources, summed not chained (DF7-A5).
        let pct: i64 = modifiers
            .iter()
            .filter(|m| m.slot == slot)
            .filter_map(|m| match m.op {
                ModifierOp::Percent(v) => Some(v as i64),
                _ => None,
            })
            .sum();

        // Exactly one division, at emit. `(base+flat) × max(0, 1000+Σpct) / 1000`.
        //
        // XST-D1 (fixed 2026-07-28) — the `max(0, …)` is DF07_002 **EC-2**, an
        // already-found, already-fixed SPEC defect that this implementation
        // reintroduced by writing the formula from the axiom list instead of
        // from the edge-case document. Without it, `Σpct = −1200` (two −60%
        // debuffs, ordinary play in a debuff-dense reality) yields a factor of
        // −0.2 and a **negative StrikePower**. AC-DF7-17 names this exact
        // mutation: *"drop the max(0, …) on factor → yields a negative stat."*
        // −100% is the floor; further debuffs are absorbed.
        let factor = (1000 + pct).max(0);
        let value = flat.saturating_mul(factor) / 1000;
        let mut value = value.clamp(i32::MIN as i64, i32::MAX as i64) as i32;

        // Author clamp, then world rule — in that order, see above.
        value = apply_clamps(value, slot, slot_clamps, lex_clamps);
        out.set(slot, value);
    }

    // Speed feeds the derivation, so MoveRange can only be derived once the
    // loop has finalised Speed.
    //
    // XST-D6 (fixed 2026-07-28) — the derivation used to be the LAST statement,
    // overwriting MoveRange with its own `clamp(1, tuning.max_move)` and
    // **discarding the Lex ceiling**. A Lex clamp of `max = 2` on MoveRange
    // produced 5. The Lex-clamp-last property is a recorded correction
    // (DF07_002 EC-1) with a dedicated test — and that test covers
    // `StrikePower`, so nothing covered the one slot where the invariant was
    // actually broken. Deriving and THEN re-clamping restores DF7-A3: a world
    // rule is applied last and is therefore inescapable.
    out.derive_move_range(rules);
    let mr = StatSlot::MoveRange;
    let ranged = apply_clamps(out.get(mr), mr, slot_clamps, lex_clamps);
    out.set(mr, ranged);

    out
}

/// Author clamp, then world rule — the DF7-A3 order, in one place so both the
/// per-slot loop and the `MoveRange` derivation cannot drift apart (XST-D6).
fn apply_clamps(value: i32, slot: StatSlot, slot_clamps: &[Clamp], lex_clamps: &[Clamp]) -> i32 {
    let mut value = value;
    if let Some((lo, hi)) = intersect_clamps(slot, slot_clamps) {
        value = value.clamp(lo, hi);
    }
    if let Some((lo, hi)) = intersect_clamps(slot, lex_clamps) {
        value = value.clamp(lo, hi);
    }
    value
}
