//! The fold — substrate §5, and hub item 5.
//!
//! ```text
//! value(q) = clamp( floor(q),
//!                   ( base(q) + Σ flat(q) ) × max(0, 1000 + Σ pct(q)) / 1000,
//!                   ceiling(q) )
//! ```
//!
//! | term | |
//! |---|---|
//! | `q` | a **quantity ordinal** |
//! | `Σ flat` · `Σ pct` | contributions from modifier rows, **signed** |
//! | **percent is SUMMED, not chained** | order-independent by construction, and it kills exponential stacking. A chained product is order-dependent and needs a deterministic sort as a patch |
//! | `max(0, 1000 + Σ pct)` | **load-bearing** — it was once absent, and two −60 % debuffs gave a factor of −0.2 and a negative stat |
//! | arithmetic | **`i64` accumulator, exactly one division at emit** |
//! | `base(q)` | the actor's stored intrinsic value, which **begins** at the declaring plugin's declared initial value (hub §3.4b) |
//!
//! **This is `resolve_block` generalised from a fixed slot table to ordinals** —
//! the fold that has already been debugged, since the `max(0, …)` floor exists
//! because it was once missing.
//!
//! ## `floor(q)` and `ceiling(q)` — what this fold clamps with, and what it
//! deliberately does not consult
//!
//! Substrate §5 assigns the ceiling MODEL to whichever feature declares a
//! bounded quantity (`U-4`), and says the hub *"needs only that the clamp
//! exists"*. The clamp that exists here is the **representation's**: the
//! accumulator is `i64` and a quantity is one `i32`, so the emit saturates into
//! `i32`. That saturation is **not silent** — it is substrate §7's **CAPPED**,
//! and it appears in the report.
//!
//! **A correction, because an earlier version of this doc called the ceiling
//! model "UNWRITTEN" and that is FALSE against the tree.** `ruleset-core` — this
//! crate's own direct dependency — already ships a per-ordinal bound:
//! `ResourceDecl { quantity, min, base, ceiling: CeilingBinding, … }` in
//! `ruleset-core/src/resource/mod.rs`, held by `ResourceTable` over **the same
//! ordinal space** this fold addresses, carried by every `Ruleset`, and already
//! validated (`ResourceError::BadBounds` refuses a `base` outside `[min,
//! ceiling]`). What is true is narrower, and is what this fold does:
//!
//! > **the hub does not CONSULT it.** `HubRegistry` takes the initial value from
//! > the attaching plugin's own `QuantityDecl`, and the fold clamps with nothing
//! > but the `i32` emit.
//!
//! That is a deliberate refusal rather than an oversight: reconciling
//! `QuantityDecl` against `ResourceDecl` decides **what a pool is**, which is the
//! resource feature's question, and answering it from feature #1's chair is the
//! encroachment this round exists to stop. **The consequence is real and is
//! registered rather than hidden** — a reality can declare `ceiling: Fixed(1000)`
//! for a quantity and this fold will resolve it to 10 500 with no `Capped`
//! record. Seam `S-18`.
//!
//! A narrower clamp arriving through a *channel* is separately unwritten
//! (`U-2`: the shipped clamp is a two-pass ordered parameter pair with intersect
//! semantics and a floor-wins contradiction rule, and a `u8` ordinal cannot
//! express *"and also a clamp channel"*). Feature #1 registers that seam too;
//! it does not fill it.
//!
//! ## The order of operations, and the one limit it has
//!
//! 1. every submitted row is **checked** (`M-5`) — a bad row is REFUSED, the fold continues;
//! 2. **pass 1** resolves every present quantity from **modifier rows only**;
//! 3. **pass 2** turns each derivation into a contribution, reading its source quantity's **pass-1** value;
//! 4. **pass 3** re-resolves with both sets of contributions, and emits.
//!
//! **A derivation therefore reads a value that has no derived contributions in
//! it.** That is the shipped shape — `resolve_block` runs its modifier loop and
//! *then* derives `MoveRange` from the finalised `Speed` — and it makes the fold
//! total without a dependency solver. **A derivation of a derivation is not
//! expressible**, and that is stated rather than discovered: the feature that
//! needs one owns the question.
//!
//! ## Purity and totality (`M-6`)
//!
//! The neighbouring seam states this explicitly — `Domain::apply` *"MUST be
//! deterministic and total"* — so this fold does too. **No panic on any input:**
//! every multiply saturates, the one division is guarded by a submission-time
//! zero-divisor refusal *and* a runtime branch, and nothing here allocates a
//! key-ordered map or reads a clock. Same inputs, byte-identical outputs.

use ruleset_core::{MAX_DECLARED_QUANTITIES, ModifierOp, OpKind};

use crate::report::{CapSite, Capped, Contribution, Explanation, FoldReport, Refused, RowRef};

use crate::ordinal::QuantityOrdinal;
use crate::plugin_set::PluginSet;
use crate::registry::HubRegistry;
use crate::rows::{DerivationRow, ModifierRow};

/// The per-mille scale the percent channel is expressed on. One division, at
/// emit — substrate §5.
const PERMILLE: i64 = 1_000;

/// One quantity's two accumulator channels.
#[derive(Clone, Copy, Default)]
struct Channels {
    flat: i64,
    pct: i64,
}

impl Channels {
    /// Accumulate one contribution.
    ///
    /// **The `saturating_add`s here are defensive uniformity, NOT guards, and
    /// saying so is the point.** Both addends are `i32` widened into an `i64`
    /// accumulator, so overflowing one needs roughly **2^32 rows for a single
    /// quantity** — unreachable, and a cold-start review confirmed it by
    /// measurement: replacing both with `wrapping_add` leaves the whole suite
    /// green, and no input can redden it.
    ///
    /// A check that cannot fail must not be described as a check
    /// (`docs/standards/non-vacuity.md`, NV-1). What IS a real guard is the
    /// `saturating_mul` in [`resolve`] — `sum × factor` genuinely exceeds `i64`
    /// at three rows each way, and `the_accumulator_saturates_rather_than_wrapping`
    /// reds when it is weakened.
    fn add(&mut self, op: ModifierOp) {
        match op {
            ModifierOp::Flat(v) => self.flat = self.flat.saturating_add(v as i64),
            ModifierOp::Percent(v) => self.pct = self.pct.saturating_add(v as i64),
        }
    }
}

/// `(base + Σflat) × max(0, 1000 + Σpct) / 1000` — the formula, once, so the
/// three passes cannot drift apart.
///
/// **This function contains the fold's ONLY division**, which is what substrate
/// §5's *"exactly one division at emit"* constrains. A `DerivationRow` divides
/// too ([`crate::DerivationRow::amount`]) — that is the row's own ratio
/// `factor_milli / divisor`, computed *before* its result becomes a
/// contribution, and it is not a second division of the accumulator. Stated
/// because the two are easy to count as one violation.
fn resolve(base: i32, ch: Channels) -> Resolved {
    let factor = (PERMILLE + ch.pct).max(0);
    let sum = (base as i64).saturating_add(ch.flat);
    // Exactly ONE division, at emit. The multiply saturates first so an extreme
    // flat sum cannot wrap into the wrong sign — and the saturation is REPORTED,
    // because after it the true value is gone and any `wanted` derived from the
    // result understates it.
    let product = sum.saturating_mul(factor);
    let saturated = sum != 0 && factor != 0 && product / factor != sum;
    Resolved { value: product / PERMILLE, factor_milli: factor, saturated }
}

/// One quantity's resolution, with the fact that the accumulator saturated
/// carried alongside rather than inferred from the result — it cannot be
/// inferred, which is the defect this struct exists to fix.
#[derive(Clone, Copy)]
struct Resolved {
    value: i64,
    factor_milli: i64,
    saturated: bool,
}

/// Saturate the accumulator into the `i32` slot, reporting a CAP when it bites.
fn emit(q: QuantityOrdinal, r: Resolved, capped: &mut Vec<Capped>) -> i32 {
    if r.saturated {
        capped.push(Capped {
            quantity: q,
            site: CapSite::Accumulator,
            wanted: r.value,
            emitted: i32::MAX,
        });
    }
    let out = r.value.clamp(i32::MIN as i64, i32::MAX as i64) as i32;
    if out as i64 != r.value {
        capped.push(Capped { quantity: q, site: CapSite::Emit, wanted: r.value, emitted: out });
    }
    out
}

/// The intra-layer order (`M-13`): fold layer, then submitting plugin, then the
/// position the row was submitted at. Total, and it never compares two rows
/// equal — the submission index is unique per channel.
fn order_key(c: &Contribution) -> (u8, u8, usize) {
    let idx = match c.row {
        // Modifier rows are keyed below derivation rows at the same (layer,
        // plugin), because pass 2 produces derived contributions from pass-1
        // values and reading them after the literals is the shipped order.
        RowRef::Modifier(i) => i,
        RowRef::Derivation(i) => usize::MAX / 2 + i,
    };
    (c.fold_layer.get(), c.source.get(), idx)
}

/// Fold an actor's attached plugins' contributions.
///
/// `base` comes from the actor's stored intrinsic values; a quantity whose
/// declaring plugin is not attached is ABSENT and is not folded at all.
pub fn fold(
    attached: PluginSet,
    stored: &[i32; MAX_DECLARED_QUANTITIES],
    registry: &HubRegistry,
    modifiers: &[ModifierRow],
    derivations: &[DerivationRow],
) -> FoldReport {
    let mut refused: Vec<Refused> = Vec::new();
    let mut capped: Vec<Capped> = Vec::new();

    // ── which quantities exist on this actor at all ──────────────────────────
    let mut present = [false; MAX_DECLARED_QUANTITIES];
    for raw in 0..MAX_DECLARED_QUANTITIES as u16 {
        if let Some(q) = QuantityOrdinal::new(raw) {
            present[q.index()] = registry.is_present(attached, q);
        }
    }

    // ── check every row once; a refused row contributes nothing (M-5) ────────
    let mut accepted_mods: Vec<(usize, &ModifierRow)> = Vec::new();
    for (i, row) in modifiers.iter().enumerate() {
        match registry.check_modifier(attached, row) {
            Ok(()) => accepted_mods.push((i, row)),
            Err(reason) => refused.push(Refused { row: RowRef::Modifier(i), reason }),
        }
    }
    let mut accepted_derivs: Vec<(usize, &DerivationRow)> = Vec::new();
    for (i, row) in derivations.iter().enumerate() {
        match registry.check_derivation(attached, row) {
            Ok(()) => accepted_derivs.push((i, row)),
            Err(reason) => refused.push(Refused { row: RowRef::Derivation(i), reason }),
        }
    }

    // ── pass 1 — modifier rows only ─────────────────────────────────────────
    let mut contributions: Vec<Vec<Contribution>> =
        (0..MAX_DECLARED_QUANTITIES).map(|_| Vec::new()).collect();
    let mut channels = [Channels::default(); MAX_DECLARED_QUANTITIES];

    for (i, row) in &accepted_mods {
        let slot = row.target.index();
        channels[slot].add(row.op);
        contributions[slot].push(Contribution {
            source: row.source,
            fold_layer: row.fold_layer,
            op: row.op,
            row: RowRef::Modifier(*i),
            derived_from: None,
        });
    }

    let mut pass1 = [0i32; MAX_DECLARED_QUANTITIES];
    for raw in 0..MAX_DECLARED_QUANTITIES as u16 {
        let Some(q) = QuantityOrdinal::new(raw) else { continue };
        if !present[q.index()] {
            continue;
        }
        let r = resolve(stored[q.index()], channels[q.index()]);
        // Pass-1 values are INTERMEDIATE — a cap here would be reported twice,
        // once now and once at the real emit, so the saturation is silent and
        // only the emit in pass 3 reports.
        pass1[q.index()] = r.value.clamp(i32::MIN as i64, i32::MAX as i64) as i32;
    }

    // ── pass 2 — derivations CONTRIBUTE, they never SET ──────────────────────
    for (i, row) in &accepted_derivs {
        let read = pass1[row.source_quantity.index()];
        let (op, clamp_site) = row.amount_reported(read);
        if let Some(site) = clamp_site {
            capped.push(Capped {
                quantity: row.target,
                site,
                wanted: row.raw_amount(read),
                emitted: op.value(),
            });
        }
        let slot = row.target.index();
        channels[slot].add(op);
        contributions[slot].push(Contribution {
            source: row.source,
            fold_layer: row.fold_layer,
            op,
            row: RowRef::Derivation(*i),
            derived_from: Some((row.source_quantity, read)),
        });
    }

    // ── pass 3 — emit ───────────────────────────────────────────────────────
    let mut values: [Option<i32>; MAX_DECLARED_QUANTITIES] = [None; MAX_DECLARED_QUANTITIES];
    let mut explanations = Vec::new();
    for raw in 0..MAX_DECLARED_QUANTITIES as u16 {
        let Some(q) = QuantityOrdinal::new(raw) else { continue };
        if !present[q.index()] {
            continue;
        }
        let ch = channels[q.index()];
        let base = stored[q.index()];
        let r = resolve(base, ch);
        let (pre_emit, factor_milli) = (r.value, r.factor_milli);
        let value = emit(q, r, &mut capped);
        values[q.index()] = Some(value);

        let mut applied = core::mem::take(&mut contributions[q.index()]);
        applied.sort_by_key(order_key);
        explanations.push(Explanation {
            quantity: q,
            base,
            contributions: applied,
            flat_sum: ch.flat,
            percent_sum: ch.pct,
            factor_milli,
            pre_emit,
            value,
        });
    }

    // Refusals are reported in submission order within each row kind, and
    // modifiers before derivations — deterministic, and independent of which
    // rows happened to be refused.
    FoldReport { values, refused, capped, explanations }
}

/// The op channels the fold knows about. If `OpKind` ever grows a third member,
/// [`Channels::add`]'s `match` is a compile error — but this states the
/// assumption where a reader of the fold will see it.
const _: () = assert!(OpKind::COUNT == 2, "the fold has exactly two accumulator channels");
