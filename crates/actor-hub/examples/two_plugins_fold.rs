//! **A LIVE RUN of feature #1** — two plugins, attached to one actor, folded,
//! with the explain path and the resolved numbers printed.
//!
//! ## Why an example and not another test
//!
//! Every other exercise of this crate is a test, and a test **asserts its own
//! expectation**: it proves the code agrees with the author, and it prints
//! nothing a reader can check. This binary asserts nothing. It runs the public
//! surface and prints what came back, so the numbers are read off a real
//! process rather than off a claim about one.
//!
//! It compiles against **`actor_hub`'s public surface only**, exactly as a
//! plugin crate written next year would — the same standing as
//! `tests/adding_a_feature_touches_zero_files.rs`, which is why neither can be
//! satisfied by reaching inside `src/`.
//!
//! ## What it demonstrates, and what it deliberately does not
//!
//! Two plugins the hub has never heard of declare their own quantities and
//! their own fold layers, and **the second contributes to the first's
//! quantity** — which is the entire point of a fold: a treasure changes a
//! cultivator's qi without either author knowing the other. It also shows both
//! verbs of substrate §7 in one run — a **REFUSED** row and a **CAPPED**
//! value — because *nothing silent* is a property you can only see by looking
//! at the output.
//!
//! It does **not** show a quantity changing over time. Nothing in the hub
//! writes a quantity after `attach` initialises it (`S-15`); whatever does that
//! also decides what event records the change, and that belongs to the
//! declaring feature.

use actor_hub::{
    Actor, CapSite, ContributionBound, DerivationRow, EntityId, FoldLayer, HubRegistry,
    ModifierOp, ModifierRow, OpKind, PluginDecl, PluginOrdinal, QuantityDecl, QuantityOrdinal,
    RowRef,
};
use ruleset_core::QuantityTable;

fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).expect("ordinal within the declared width")
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).expect("plugin ordinal within the declared width")
}

/// The names exist HERE, in the plugin author's file. The hub is handed
/// ordinals and never learns any of them.
const NAMES: [&str; 4] = ["qi", "realm", "breath_rate", "carry_weight"];

fn name(o: QuantityOrdinal) -> &'static str {
    NAMES[o.index()]
}

fn main() {
    // ── Two authors, neither of whom edited actor-hub ────────────────────
    let cultivation = p(0);
    let equipment = p(1);

    let (qi, realm, breath_rate, carry_weight) = (q(0), q(1), q(2), q(3));

    // Each author names its own layers. The engine orders by the ordinal and
    // never learns what "treasure" means.
    let (base, gear, treasure) = (FoldLayer(10), FoldLayer(30), FoldLayer(40));

    let table = QuantityTable::assign(&NAMES).expect("a declared quantity table");
    let registry = HubRegistry::build(
        &table,
        &[
            PluginDecl {
                ordinal: cultivation,
                quantities: vec![
                    QuantityDecl { ordinal: qi, initial: 500 },
                    QuantityDecl { ordinal: realm, initial: 3 },
                    QuantityDecl { ordinal: breath_rate, initial: 1 },
                ],
                fold_layers: vec![base, treasure],
            },
            PluginDecl {
                ordinal: equipment,
                quantities: vec![QuantityDecl { ordinal: carry_weight, initial: 100 }],
                fold_layers: vec![gear],
            },
        ],
    )
    .expect("two well-formed plugin declarations");

    // ── One actor ────────────────────────────────────────────────────────
    let mut actor = Actor::new(EntityId(7));
    println!("actor {:?}  existence={:?}", EntityId(7), actor.existence());
    println!("  before attach, every quantity is ABSENT, not zero:");
    for o in [qi, realm, breath_rate, carry_weight] {
        println!("    {:<13} {:?}", name(o), actor.quantity(&registry, o));
    }

    actor.attach(&registry, cultivation).expect("cultivation attaches");
    println!("\n  attach(cultivation) — its OWN declared initial values appear:");
    for o in [qi, realm, breath_rate, carry_weight] {
        println!("    {:<13} {:?}", name(o), actor.quantity(&registry, o));
    }

    actor.attach(&registry, equipment).expect("equipment attaches");
    println!("\n  attach(equipment) — and only its own:");
    for o in [qi, realm, breath_rate, carry_weight] {
        println!("    {:<13} {:?}", name(o), actor.quantity(&registry, o));
    }

    // ── Contributions: DATA, from two different authors ───────────────────
    let modifiers = [
        // Equipment reaches into cultivation's quantity. Neither author knows
        // the other; both know an ordinal.
        ModifierRow { target: qi, op: ModifierOp::Flat(200), source: equipment, fold_layer: gear },
        ModifierRow {
            target: qi,
            op: ModifierOp::Percent(300),
            source: equipment,
            fold_layer: treasure,
        },
        // A row naming a layer NOBODY declared — substrate §7's REFUSED verb.
        ModifierRow {
            target: carry_weight,
            op: ModifierOp::Flat(50),
            source: equipment,
            fold_layer: FoldLayer(99),
        },
        // A flat contribution large enough that the i32 emit must clamp —
        // substrate §7's CAPPED verb.
        ModifierRow {
            target: carry_weight,
            op: ModifierOp::Flat(i32::MAX),
            source: equipment,
            fold_layer: gear,
        },
        ModifierRow {
            target: carry_weight,
            op: ModifierOp::Percent(1000),
            source: equipment,
            fold_layer: gear,
        },
    ];

    // `breath_rate` derived from `realm` at 7/3 — a ratio no per-mille factor
    // alone can express, which is why `divisor` is on the row (`U-6`).
    let derivations = [DerivationRow {
        target: breath_rate,
        source_quantity: realm,
        op: OpKind::Flat,
        factor_milli: 7,
        divisor: 3,
        bound: Some(ContributionBound { min: 0, max: 100 }),
        source: cultivation,
        fold_layer: base,
    }];

    let out = actor.fold(&registry, &modifiers, &derivations);

    // ── What came back ───────────────────────────────────────────────────
    println!("\n── resolved ─────────────────────────────────────────────");
    for o in [qi, realm, breath_rate, carry_weight] {
        println!("    {:<13} {:?}", name(o), out.value(o));
    }

    println!("\n── the explain path ─────────────────────────────────────");
    for e in &out.explanations {
        println!(
            "  {} : base {} → flat {:+} → percent {:+} (factor {}/1000) → pre-emit {} → {}",
            name(e.quantity),
            e.base,
            e.flat_sum,
            e.percent_sum,
            e.factor_milli,
            e.pre_emit,
            e.value
        );
        for c in &e.contributions {
            let from = match c.derived_from {
                Some((src, v)) => format!("  derived from {} = {}", name(src), v),
                None => String::new(),
            };
            println!(
                "      plugin {:?} at layer {:?} {:?} [{:?}]{}",
                c.source.get(),
                c.fold_layer.get(),
                c.op,
                c.row,
                from
            );
        }
    }

    println!("\n── nothing silent ───────────────────────────────────────");
    println!("  REFUSED ({}):", out.refused.len());
    for r in &out.refused {
        let idx = match r.row {
            RowRef::Modifier(i) => format!("modifier row {i}"),
            RowRef::Derivation(i) => format!("derivation row {i}"),
        };
        println!("    {idx:<16} {:?}", r.reason);
    }
    println!("  CAPPED ({}):", out.capped.len());
    for c in &out.capped {
        let site = match c.site {
            CapSite::Accumulator => "accumulator",
            CapSite::Emit => "emit",
            CapSite::DerivedAmount => "derived-amount",
            CapSite::DerivedBound => "derived-bound",
        };
        println!(
            "    {:<13} at {site:<12} wanted {} → emitted {}",
            name(c.quantity),
            c.wanted,
            c.emitted
        );
    }

    // ── And what the hub never did ───────────────────────────────────────
    println!("\n── the boundary, visible in what did NOT happen ──────────");
    println!("  the hub folded {} contribution(s) across 3 layers without",
             out.explanations.iter().map(|e| e.contributions.len()).sum::<usize>());
    println!("  reading one layer's MEANING: it ordered by the ordinal, and the");
    println!("  names above live in this file, never in crates/actor-hub/src.");
}
