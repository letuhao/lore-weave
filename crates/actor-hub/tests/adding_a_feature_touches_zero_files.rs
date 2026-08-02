//! **The acceptance test** — hub §6.
//!
//! > **Adding a feature must touch ZERO files in actor core.**
//! >
//! > Under this frame it is checkable, because a plugin that cannot add a field
//! > has nothing to touch.
//!
//! ## Why this test lives OUTSIDE `src/`
//!
//! It is an **integration** test: it compiles against `actor-hub`'s *public*
//! surface only, exactly as a plugin crate written next year would. A unit test
//! inside `src/` can reach `pub(crate)` items and would quietly prove a weaker
//! statement — that the hub can fold a plugin *it can see the insides of*.
//!
//! **The claim under test is a claim about a DIFF**: declaring a plugin,
//! attaching it, submitting its rows and reading its resolved numbers must all
//! be possible from here, with **no edit to any file under
//! `crates/actor-hub/src/`.** If a future change makes a plugin need a field in
//! the hub, this file stops compiling — which is the failure being visible
//! rather than a design being quietly abandoned.
//!
//! ## And the honest bound, asserted rather than claimed
//!
//! > **It holds UP TO THE DECLARED WIDTHS.** The 33rd plugin, and the plugin
//! > whose quantities exceed 32, **do** touch actor core — and that is a
//! > **version bump**, visible and costed, not a silent failure.
//!
//! The last test here is that bound: the 33rd plugin ordinal **cannot be
//! constructed**, so the failure is a refusal at the door rather than a plugin
//! that attaches and is silently never folded.

use actor_hub::{
    Actor, ContributionBound, DerivationRow, EntityId, FoldLayer, HubRegistry, MAX_PLUGINS,
    ModifierOp, ModifierRow, OpKind, PluginDecl, PluginOrdinal, QuantityDecl, QuantityOrdinal,
    RowRefusal,
};
use ruleset_core::QuantityTable;

fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).expect("ordinal within the declared width")
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).expect("plugin ordinal within the declared width")
}

/// A feature invented entirely here, in test code, by an author the hub has
/// never heard of.
///
/// It is a cultivation system: a `qi` pool, a `realm` tier index, and a
/// `breath_rate` derived from `realm`. **None of those words appear anywhere in
/// `crates/actor-hub/src/`** — the hub knows three ordinals, two fold layers and
/// nothing else.
struct Cultivation {
    ordinal: PluginOrdinal,
    qi: QuantityOrdinal,
    realm: QuantityOrdinal,
    breath_rate: QuantityOrdinal,
    /// The author's own layer names, which the engine never learns.
    base_layer: FoldLayer,
    treasure_layer: FoldLayer,
}

impl Cultivation {
    fn new() -> Self {
        Self {
            ordinal: p(0),
            qi: q(0),
            realm: q(1),
            breath_rate: q(2),
            base_layer: FoldLayer(10),
            treasure_layer: FoldLayer(40),
        }
    }

    fn decl(&self) -> PluginDecl {
        PluginDecl {
            ordinal: self.ordinal,
            quantities: vec![
                QuantityDecl { ordinal: self.qi, initial: 500 },
                QuantityDecl { ordinal: self.realm, initial: 3 },
                QuantityDecl { ordinal: self.breath_rate, initial: 1 },
            ],
            fold_layers: vec![self.base_layer, self.treasure_layer],
        }
    }
}

fn cultivation_reality() -> (Cultivation, HubRegistry) {
    let plugin = Cultivation::new();
    let table = QuantityTable::assign(&["qi", "realm", "breath_rate"]).unwrap();
    let registry = HubRegistry::build(&table, &[plugin.decl()]).unwrap();
    (plugin, registry)
}

/// The whole loop, from the outside: declare, attach, contribute, fold, read.
#[test]
fn a_feature_the_hub_has_never_heard_of_declares_attaches_and_folds() {
    let (plugin, registry) = cultivation_reality();

    let mut actor = Actor::new(EntityId(7));
    actor.attach(&registry, plugin.ordinal).unwrap();

    // Hub §3.4b — every quantity begins at the plugin's OWN declared value.
    assert_eq!(actor.quantity(&registry, plugin.qi), Some(500));
    assert_eq!(actor.quantity(&registry, plugin.realm), Some(3));

    // A treasure the author invented, expressed purely as data.
    let rows = [
        ModifierRow {
            target: plugin.qi,
            op: ModifierOp::Flat(200),
            source: plugin.ordinal,
            fold_layer: plugin.treasure_layer,
        },
        ModifierRow {
            target: plugin.qi,
            op: ModifierOp::Percent(300),
            source: plugin.ordinal,
            fold_layer: plugin.treasure_layer,
        },
    ];
    // `breath_rate` derived from `realm`, at a ratio a per-mille factor alone
    // could not express.
    let derivations = [DerivationRow {
        target: plugin.breath_rate,
        source_quantity: plugin.realm,
        op: OpKind::Flat,
        factor_milli: 7,
        divisor: 3,
        bound: Some(ContributionBound { min: 0, max: 100 }),
        source: plugin.ordinal,
        fold_layer: plugin.base_layer,
    }];

    let out = actor.fold(&registry, &rows, &derivations);

    // (500 + 200) × 1300 / 1000 = 910
    assert_eq!(out.value(plugin.qi), Some(910));
    // 1 + (3 × 7 / 3) = 1 + 7 = 8
    assert_eq!(out.value(plugin.breath_rate), Some(8));
    assert!(out.refused.is_empty());
    assert!(out.capped.is_empty());
}

/// The explain path works from outside too — a plugin author can answer *"why
/// is this number 910"* without reading the hub's source.
#[test]
fn the_author_can_explain_its_own_number_from_the_public_surface() {
    let (plugin, registry) = cultivation_reality();
    let mut actor = Actor::new(EntityId(7));
    actor.attach(&registry, plugin.ordinal).unwrap();

    let rows = [ModifierRow {
        target: plugin.qi,
        op: ModifierOp::Flat(200),
        source: plugin.ordinal,
        fold_layer: plugin.treasure_layer,
    }];
    let out = actor.fold(&registry, &rows, &[]);
    let e = out.explain(plugin.qi).expect("qi was folded");

    assert_eq!(e.base, 500);
    assert_eq!(e.flat_sum, 200);
    assert_eq!(e.contributions.len(), 1);
    assert_eq!(e.contributions[0].source, plugin.ordinal);
    assert_eq!(e.contributions[0].op, ModifierOp::Flat(200));
    assert_eq!((e.base as i64 + e.flat_sum) * e.factor_milli / 1000, e.pre_emit);
}

/// A SECOND feature, added without touching the first one or the hub. This is
/// the property the whole plugin frame exists for.
#[test]
fn a_second_feature_is_added_without_touching_the_first() {
    let first = Cultivation::new();
    // Feature #2, invented here: a body-refinement system owning one quantity
    // and introducing its own fold layer.
    let second = PluginDecl {
        ordinal: p(1),
        quantities: vec![QuantityDecl { ordinal: q(3), initial: 40 }],
        fold_layers: vec![FoldLayer(20)],
    };

    let table = QuantityTable::assign(&["qi", "realm", "breath_rate", "bone_strength"]).unwrap();
    let registry = HubRegistry::build(&table, &[first.decl(), second.clone()]).unwrap();

    let mut actor = Actor::new(EntityId(9));
    actor.attach(&registry, first.ordinal).unwrap();
    actor.attach(&registry, second.ordinal).unwrap();

    // Feature #2 may contribute to its OWN quantity...
    let own = ModifierRow {
        target: q(3),
        op: ModifierOp::Flat(10),
        source: second.ordinal,
        fold_layer: FoldLayer(20),
    };
    // ...and, at a layer it declared, to feature #1's quantity as well — which
    // is the point of a shared ordinal space: the hub does not know or care
    // which plugin a quantity "belongs" to when a contribution arrives.
    let cross = ModifierRow {
        target: first.qi,
        op: ModifierOp::Percent(100),
        source: second.ordinal,
        fold_layer: FoldLayer(20),
    };

    let out = actor.fold(&registry, &[own, cross], &[]);
    assert_eq!(out.value(q(3)), Some(50));
    assert_eq!(out.value(first.qi), Some(550));
}

/// A quantity whose declaring plugin is not attached is **ABSENT, not zero** —
/// checked from outside, because this is the distinction a plugin author most
/// easily gets wrong.
#[test]
fn a_detached_features_quantities_vanish_rather_than_reading_zero() {
    let (plugin, registry) = cultivation_reality();
    let mut actor = Actor::new(EntityId(7));

    assert_eq!(actor.quantity(&registry, plugin.qi), None);
    actor.attach(&registry, plugin.ordinal).unwrap();
    assert_eq!(actor.quantity(&registry, plugin.qi), Some(500));
    actor.detach(plugin.ordinal).unwrap();
    assert_eq!(actor.quantity(&registry, plugin.qi), None);

    let out = actor.fold(&registry, &[], &[]);
    assert_eq!(out.value(plugin.qi), None);
    assert!(out.explanations.is_empty());
}

/// `U-7` from the outside: a plugin ships a row for a layer it forgot to
/// declare, and the row is REFUSED with a reason rather than landing in an
/// order nothing defines.
#[test]
fn a_row_for_an_undeclared_layer_is_refused_with_its_reason() {
    let (plugin, registry) = cultivation_reality();
    let mut actor = Actor::new(EntityId(7));
    actor.attach(&registry, plugin.ordinal).unwrap();

    let forgot = ModifierRow {
        target: plugin.qi,
        op: ModifierOp::Flat(9_999),
        source: plugin.ordinal,
        fold_layer: FoldLayer(77),
    };
    let out = actor.fold(&registry, &[forgot], &[]);

    assert_eq!(out.value(plugin.qi), Some(500), "the refused row contributed nothing");
    assert_eq!(out.refused.len(), 1);
    assert_eq!(out.refused[0].reason, RowRefusal::UndeclaredFoldLayer { layer: 77 });
}

/// **The honest bound, asserted rather than claimed** (hub §6). The 33rd plugin
/// touches actor core — and the shape of that touch is a **refusal at
/// construction**, not a plugin that attaches and is silently never folded.
#[test]
fn the_thirty_third_plugin_is_a_refusal_not_a_silent_failure() {
    assert_eq!(MAX_PLUGINS, 32);
    assert!(PluginOrdinal::new(31).is_some(), "the 32nd plugin fits");
    assert!(
        PluginOrdinal::new(32).is_none(),
        "the 33rd plugin must be unconstructible — raising the ceiling is a VERSION BUMP, \
         and this assertion is what makes it visible instead of silent"
    );

    // The same bound on the quantity side, from the public surface.
    assert!(QuantityOrdinal::new(31).is_some());
    assert!(QuantityOrdinal::new(32).is_none());
}

// DELETED: `the_public_surface_names_no_feature_vocabulary`.
//
// It bound five known-good items and claimed to prove the hub's public surface
// names no feature vocabulary. A review measured what that is worth: adding
// `pub struct Hp;` to the crate left it **green**. Its scope was a hand-written
// list, which `docs/standards/non-vacuity.md` NV-3 calls default-uncovered — it
// says nothing about an item added tomorrow, and an item added tomorrow is the
// entire failure mode.
//
// It is deleted rather than repaired because the honest version is not a test:
// the property is *"no name in the public surface belongs to a feature"*, and
// deciding whether a name is a feature's is a reading, not a predicate. The
// tests ABOVE carry the load — they are written against the public surface only,
// and a feature-shaped item appearing in the hub would show up as a name they
// did not need to use. A green test that proves nothing is worse than an absent
// one, because it reports coverage.
