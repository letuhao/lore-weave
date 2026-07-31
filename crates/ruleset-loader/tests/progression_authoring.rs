//! `PGN-R2b` — a reality AUTHORS its progression, and it survives
//! TOML → fold → validate → store → pin.
//!
//! The exit criterion is the last test: 《寒潭劍錄》's three systems, written the
//! way an author would write them, ending as a digest on a `Ruleset`.

use ruleset_core::{BodyOrSoul, CapRule, CurveKind, ProgressionType};
use ruleset_loader::{parse_layer, resolve, resolve_and_pin, Layer, LoadError, ProgressionStore};

fn store(name: &str) -> ProgressionStore {
    let d = std::env::temp_dir().join(format!("lw-prog-auth-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    ProgressionStore::new(d)
}

fn reality(toml: &str) -> Result<(ruleset_core::Ruleset, ProgressionStore), LoadError> {
    let s = store(&format!("{:x}", toml.len()));
    let layer = parse_layer(Layer::Reality, toml)?;
    let r = resolve_and_pin(&[layer], &s)?;
    Ok((r, s))
}

fn err(toml: &str) -> LoadError {
    let s = store("err");
    let layer = parse_layer(Layer::Reality, toml).expect("parses");
    resolve_and_pin(&[layer], &s).expect_err("must refuse")
}

// ── the headline ────────────────────────────────────────────────────────────

/// **The slice's exit criterion.** 《寒潭劍錄》's three systems as an author
/// writes them: 內功 a staged ladder, 劍術 a skill deriving from 悟性, 悟性 an
/// attribute that follows the SOUL. Ends as a digest on the ruleset and a table
/// in the store.
#[test]
fn the_wuxia_book_three_systems_survive_toml_to_pin() {
    let (r, s) = reality(
        r#"
        quantities = ["internal_energy", "swordsmanship", "comprehension"]

        [[progression_kinds]]
        quantity = "internal_energy"
        type = "stage"
        curve = "stage"
        cap = "tier_based"
        initial_tier = 0
        [[progression_kinds.tiers]]
        tier_max = 100
        [[progression_kinds.tiers]]
        tier_max = 300
        breakthrough = "author_only"

        [[progression_kinds]]
        quantity = "comprehension"
        type = "attribute"
        body_or_soul = "soul"
        curve = "linear"
        rate = 1.0
        cap = "soft_cap"
        cap_value = 100
        initial_value = 10

        [[progression_kinds]]
        quantity = "swordsmanship"
        type = "skill"
        curve = "log"
        base_rate = 1.5
        difficulty = 1.2
        cap = "soft_cap"
        cap_value = 1000
        derives_from = "comprehension"
        derive_factor = 0.05
        "#,
    )
    .expect("the book's own systems must load");

    let digest = r.progression.expect("the ruleset carries a pin");
    let table = s.get(&digest).unwrap().expect("and the store has the bytes");
    assert_eq!(table.len(), 3);

    let ie = table.for_quantity(r.quantities.ordinal_of("internal_energy").unwrap()).unwrap();
    assert_eq!(ie.progression_type, ProgressionType::Stage);
    assert_eq!(ie.tiers.len(), 2);
    assert_eq!(ie.cap_rule, CapRule::TierBased);

    let wx = table.for_quantity(r.quantities.ordinal_of("comprehension").unwrap()).unwrap();
    assert_eq!(wx.body_or_soul, BodyOrSoul::Soul, "悟性 follows the SOUL");

    let js = table.for_quantity(r.quantities.ordinal_of("swordsmanship").unwrap()).unwrap();
    // RLS-A7: `1.5` in the file is 1500 in the bytes. Floats never reach the digest.
    assert_eq!(js.curve, CurveKind::Log { base_rate_milli: 1500, difficulty_milli: 1200 });
    let d = js.derives_from.expect("劍術 derives from 悟性");
    assert_eq!(d.source_quantity, r.quantities.ordinal_of("comprehension").unwrap());
    assert_eq!(d.rate_factor_milli, 50, "0.05 normalizes to 50 milli-units");
}

// ── the refusal that keeps `resolve` honest ─────────────────────────────────

/// `resolve` has no store, and a progression kind folds into a TABLE. Dropping
/// the rows would lose the author's whole ladder with the run staying green —
/// the `QTY-Q5` class this tier exists to refuse.
#[test]
fn resolve_without_a_store_refuses_rather_than_dropping_the_rows() {
    let layer = parse_layer(
        Layer::Reality,
        r#"
        quantities = ["qi"]
        [[progression_kinds]]
        quantity = "qi"
        type = "attribute"
        curve = "linear"
        cap = "unbounded"
        "#,
    )
    .expect("parses");
    let e = resolve(&[layer]).expect_err("resolve cannot pin");
    let msg = format!("{e}");
    assert!(matches!(e, LoadError::ProgressionNeedsStore { kinds: 1, .. }), "{msg}");
    assert!(msg.contains("resolve_and_pin"), "the refusal must name the call that works: {msg}");
    assert!(msg.contains("staying green"), "and say what it is refusing to do: {msg}");
}

// ── closed sets, every one refused BY NAME ──────────────────────────────────

fn base(extra: &str) -> String {
    format!("quantities = [\"qi\"]\n[[progression_kinds]]\nquantity = \"qi\"\n{extra}\n")
}

#[test]
fn an_unknown_type_is_refused_with_the_legal_values() {
    let e = err(&base("type = \"levelup\"\ncurve = \"linear\"\ncap = \"unbounded\""));
    assert!(format!("{e}").contains("Legal: attribute, skill, stage"), "{e}");
}

#[test]
fn an_unknown_body_or_soul_is_refused_and_says_why_it_matters() {
    let e = err(&base(
        "type = \"skill\"\nbody_or_soul = \"mind\"\ncurve = \"linear\"\ncap = \"unbounded\"",
    ));
    let msg = format!("{e}");
    assert!(msg.contains("Legal: body, soul, both"), "{msg}");
    assert!(
        msg.contains("wrong person"),
        "guessing this moves a character's abilities to the wrong body on a xuyên không \
         transfer, and the message must say so: {msg}"
    );
}

/// `soft_cap` and `hard_cap` are OPPOSITES — one is a slow grind past the
/// ceiling, the other refuses training at it. The message says so, because an
/// author who gets the other one spends an afternoon on it.
#[test]
fn an_unknown_cap_rule_names_the_opposites() {
    let e = err(&base("type = \"skill\"\ncurve = \"linear\"\ncap = \"capped\""));
    assert!(format!("{e}").contains("OPPOSITES"), "{e}");
}

#[test]
fn a_cap_without_its_value_is_refused_rather_than_defaulted() {
    let e = err(&base("type = \"skill\"\ncurve = \"linear\"\ncap = \"soft_cap\""));
    let msg = format!("{e}");
    assert!(msg.contains("needs a `cap_value`"), "{msg}");
    assert!(msg.contains("both are wrong to guess"), "{msg}");
}

#[test]
fn a_cap_value_on_a_rule_that_cannot_use_one_is_refused_not_ignored() {
    let e = err(&base(
        "type = \"skill\"\ncurve = \"linear\"\ncap = \"unbounded\"\ncap_value = 10",
    ));
    assert!(format!("{e}").contains("silently ignored"), "{e}");
}

/// **`PGN-A20` reaches the author.** `at_max_plus` is the variant a wuxia book
/// most wants — 寒潭, a pill, a sealed room — and every one of its fields is a
/// cross-element reference to a module that does not exist. The refusal names
/// what is missing rather than pretending the variant is unknown.
#[test]
fn at_max_plus_is_refused_with_the_reason_it_does_not_exist() {
    let e = err(&base(
        "type = \"stage\"\ncurve = \"stage\"\ncap = \"tier_based\"\ninitial_tier = 0\n\
         [[progression_kinds.tiers]]\ntier_max = 10\nbreakthrough = \"at_max_plus\"",
    ));
    let msg = format!("{e}");
    assert!(msg.contains("cross-element reference"), "{msg}");
    assert!(msg.contains("PGN-A20"), "{msg}");
    assert!(msg.contains("a place"), "the owning modules must be named: {msg}");
}

/// A `NaN` rate that became `0` would be a kind that never trains, and the
/// author would have no way to see why.
#[test]
fn a_non_finite_rate_is_refused() {
    let e = err(&base("type = \"skill\"\ncurve = \"linear\"\nrate = -1.0\ncap = \"unbounded\""));
    assert!(format!("{e}").contains("finite non-negative"), "{e}");
}

// ── the ruleset it is authored against ──────────────────────────────────────

#[test]
fn a_kind_for_an_undeclared_quantity_is_refused() {
    let e = err("quantities = [\"qi\"]\n[[progression_kinds]]\nquantity = \"mana\"\ntype = \"skill\"\ncurve = \"linear\"\ncap = \"unbounded\"\n");
    assert!(format!("{e}").contains("does not declare"), "{e}");
}

#[test]
fn deriving_from_an_undeclared_quantity_is_refused_not_dropped() {
    let e = err(&base(
        "type = \"skill\"\ncurve = \"linear\"\ncap = \"unbounded\"\nderives_from = \"nowhere\"",
    ));
    assert!(format!("{e}").contains("never arrives"), "{e}");
}

/// **`CPL-A2` / `PGN-A7`** — the engine's own validator runs BEFORE the store,
/// so a table that could never load never gets a content address.
#[test]
fn an_inadmissible_table_never_reaches_the_store() {
    let s = store("novalidate");
    let layer = parse_layer(
        Layer::Reality,
        // Stage curve with an absolute cap — PROG_001 §5.5 forbids the pair.
        "quantities = [\"qi\"]\n[[progression_kinds]]\nquantity = \"qi\"\ntype = \"stage\"\n\
         curve = \"stage\"\ncap = \"hard_cap\"\ncap_value = 10\ninitial_tier = 0\n\
         [[progression_kinds.tiers]]\ntier_max = 10\n",
    )
    .expect("parses");
    let e = resolve_and_pin(&[layer], &s).expect_err("the matrix must refuse this");
    assert!(matches!(e, LoadError::ProgressionInvalid(_)), "{e}");
    assert!(format!("{e}").contains("cap_curve_invalid"), "{e}");
    // The store must be EMPTY. The first draft of this assertion checked that
    // the EMPTY table's path did not exist — which is true whatever the code
    // does, so it could never fail. `NV-2`, the subject cannot vary, caught by
    // the bite-test: reordering store-before-validate left it green. Counting
    // what is actually on disk is a subject that varies.
    let written: Vec<_> = std::fs::read_dir(s.path_for(&table_digest_probe()).parent().unwrap())
        .map(|d| d.flatten().map(|e| e.file_name()).collect())
        .unwrap_or_default();
    assert!(written.is_empty(), "an inadmissible table was stored anyway: {written:?}");
}

// ── the fold ────────────────────────────────────────────────────────────────

/// `RLS-A16` — the engine default ships engine vocabulary, not world content. A
/// progression kind below the preset floor would be inherited by every reality
/// on this binary without any of them asking, and `QTY-A10(c)` means they could
/// never remove it.
#[test]
fn a_kind_below_the_preset_floor_is_refused() {
    let s = store("floor");
    let layer = parse_layer(
        Layer::EngineDefault,
        "quantities = [\"qi\"]\n[[progression_kinds]]\nquantity = \"qi\"\ntype = \"skill\"\n\
         curve = \"linear\"\ncap = \"unbounded\"\n",
    )
    .expect("parses");
    let e = resolve_and_pin(&[layer], &s).expect_err("engine_default may not declare content");
    assert!(matches!(e, LoadError::BelowFloor { field: "progression_kinds", .. }), "{e}");
}

/// **Digests do not union.** Two layers each carrying a 32-byte content address
/// have nothing to merge — the union happens over the TABLES, while the rows are
/// still rows, and exactly one table is stored at the end. A higher layer's row
/// for the same quantity REPLACES the lower one's.
#[test]
fn a_higher_layer_replaces_a_lower_layers_row_and_one_table_is_stored() {
    let s = store("fold");
    let preset = parse_layer(
        Layer::Preset,
        "quantities = [\"qi\", \"sword\"]\n\
         [[progression_kinds]]\nquantity = \"qi\"\ntype = \"skill\"\ncurve = \"linear\"\n\
         cap = \"soft_cap\"\ncap_value = 10\n",
    )
    .unwrap();
    let world = parse_layer(
        Layer::Reality,
        "[[progression_kinds]]\nquantity = \"qi\"\ntype = \"skill\"\ncurve = \"linear\"\n\
         cap = \"soft_cap\"\ncap_value = 999\n\
         [[progression_kinds]]\nquantity = \"sword\"\ntype = \"skill\"\ncurve = \"linear\"\n\
         cap = \"unbounded\"\n",
    )
    .unwrap();

    let r = resolve_and_pin(&[world, preset], &s).expect("folds");
    let t = s.get(&r.progression.unwrap()).unwrap().unwrap();
    assert_eq!(t.len(), 2, "two kinds, not three - the qi rows folded into one");
    let qi = t.for_quantity(r.quantities.ordinal_of("qi").unwrap()).unwrap();
    assert_eq!(
        qi.cap_rule,
        CapRule::SoftCap { cap: 999 },
        "the higher layer won"
    );
}

#[test]
fn declaring_no_progression_leaves_the_pin_none() {
    let s = store("nokinds");
    let layer = parse_layer(Layer::Reality, "quantities = [\"qi\"]\n").unwrap();
    let r = resolve_and_pin(&[layer], &s).unwrap();
    assert_eq!(r.progression, None, "`None` is the spelling, never an empty table's digest");
}

/// A digest whose only job is to give `path_for` a parent directory to read.
/// Never stored, never compared — it is a path probe, not a pin.
fn table_digest_probe() -> ruleset_core::ProgressionDigest {
    ruleset_core::ProgressionTable::EMPTY.digest()
}
