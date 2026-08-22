//! **The REFUSALS a verb row meets at BUILD** — everything an author may write
//! and the engine will not accept.
//!
//! Split out of `adding_a_verb_touches_zero_files.rs` at `IMP-D3`'s ceiling, and
//! the seam is the one `CMD-10` draws: that file asserts a verb RESOLVES with no
//! code, this one asserts what a verb may not SAY. They fail for different
//! reasons — the first when the seam breaks, the second when a refusal stops
//! refusing.
//!
//! Every case here is a message an author reads, so every assertion checks that
//! the message names the VERB and the reason — not just that something failed.

use ruleset_loader::{parse_layer, resolve, Layer, PROVING_GROUND_TOML};

/// **`CMD-10`'s owed bite, discharged.**
///
/// §9.4: *"for a concern classified vocabulary, author a member that sets an
/// authority-bearing field and assert the build or the engine REFUSES it. If no
/// such member can be constructed, V4 was not applied — it was asserted."*
///
/// Here is the member. Three of them, one per forbidden key, and each refusal
/// names the verb, the key and the reason — not *"unknown field"*, which is true
/// and no help, because the field is not unknown.
#[test]
fn a_verb_that_writes_an_authority_field_is_refused_by_name() {
    for (key, value) in [
        ("submitter_class", "\"host\""),
        ("may_submit_engine_verbs", "true"),
        ("pays_spend", "true"),
    ] {
        let src = format!(
            "[[verbs]]\nname = \"usurp\"\n{key} = {value}\n\
             effect_quantity = \"vitality\"\neffect_amount = 1\n"
        );
        let err = parse_layer(Layer::Reality, &src)
            .expect_err("an authority-bearing field must be REFUSED at the door");
        let msg = err.to_string();
        println!("CMD-10 V4  {key} -> {msg}");
        assert!(msg.contains(key), "the refusal must name the key: {msg}");
        assert!(msg.contains("usurp"), "the refusal must name the verb: {msg}");
        assert!(
            msg.len() > 120,
            "the refusal must carry the REASON, not just the name: {msg}"
        );
    }
}

/// A verb targeting another actor is refused while the offer registry is
/// unbuilt. Accepting it would ship a verb that works and is unauthorised.
#[test]
fn a_verb_targeting_another_actor_is_refused_until_the_offer_registry_exists() {
    let src = "[[verbs]]\nname = \"smite\"\ntarget = \"other\"\n\
               effect_quantity = \"vitality\"\neffect_amount = -5\n";
    let err = resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).unwrap(),
        parse_layer(Layer::Reality, src).unwrap(),
    ])
    .expect_err("CMD-11/CMD-12 are parked, so `other` has no authorised path");
    let msg = err.to_string();
    println!("offer registry  -> {msg}");
    assert!(msg.contains("smite") && msg.contains("offer registry"), "{msg}");
}

/// **The honest bound.** Sixteen verbs fit; the seventeenth is a version bump,
/// visible and costed, not a silent failure.
#[test]
fn the_seventeenth_verb_is_refused_rather_than_dropped() {
    let mut src = String::new();
    for i in 0..=ruleset_core::MAX_DECLARED_VERBS {
        src.push_str(&format!(
            "[[verbs]]\nname = \"v{i}\"\neffect_quantity = \"vitality\"\neffect_amount = 1\n\n"
        ));
    }
    let err = resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).unwrap(),
        parse_layer(Layer::Reality, &src).unwrap(),
    ])
    .expect_err("past the declared width is a REFUSAL, never a silent truncation");
    println!("width bound  -> {err}");
    assert!(err.to_string().contains("capacity"));
}

// ── the claim itself, mechanised ────────────────────────────────────────────

/// **`CMD-6`, as a CHECK rather than a comment.**
///
/// `substrate.rs`'s own header says *"If either appears, the acceptance test is
/// false and the substrate has become the thing it replaced."* **Nothing checked
/// it.** A cold-start reviewer's sharpest finding was that every test above
/// would stay green if someone added `match verb { 0 => …, _ => … }` tomorrow —
/// so the load-bearing claim of `M2` was prose sitting under a file named for
/// it.
///
/// This reads the source at RUNTIME, which is the same call
/// `TestOpenAPIRouteConformance` makes for the contract-first rule: a check that
/// is compiled in cannot see the file it is about.
///
/// It is narrow on purpose. It does not try to understand Rust; it looks for the
/// two shapes a per-verb branch can take — a `match` whose scrutinee is the verb
/// ordinal, and a comparison of it against a literal — which is exactly the
/// discriminator `hub-vocabulary-gate` settled on one contract down, for the
/// same reason: *an ordinal is an ADDRESS; comparing one against a LITERAL asks
/// "is this the address I mean", which is a name.*
#[test]
fn the_substrate_never_branches_on_a_verb() {
    const CORE: &[&str] = &[
        "src/domain/substrate.rs",
        "src/domain/binding.rs",
        "src/domain/law.rs",
    ];
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut findings = Vec::new();

    for rel in CORE {
        let src = std::fs::read_to_string(root.join(rel))
            .unwrap_or_else(|e| panic!("command core file {rel} is unreadable: {e}"));
        for (i, line) in src.lines().enumerate() {
            let code = line.split("//").next().unwrap_or("").trim();
            if code.is_empty() {
                continue;
            }
            let branches_on_verb = code.starts_with("match verb")
                || code.contains("match verb {")
                || code.contains("matches!(verb")
                || (code.contains("verb ==") && code.split("verb ==").nth(1)
                    .is_some_and(|r| r.trim_start().starts_with(|c: char| c.is_ascii_digit())))
                || (code.contains("verb !=") && code.split("verb !=").nth(1)
                    .is_some_and(|r| r.trim_start().starts_with(|c: char| c.is_ascii_digit())));
            if branches_on_verb {
                findings.push(format!("{rel}:{}: {code}", i + 1));
            }
        }
    }

    assert!(
        findings.is_empty(),
        "command core branches on a verb ordinal, so `adding a verb touches zero files` is \
         FALSE — the substrate has become the `match` it replaced (CMD-6):\n  {}",
        findings.join("\n  ")
    );
    println!("CMD-6  {} command-core file(s) scanned; none branches on a verb", CORE.len());
}

/// **The cue space is PER-REALITY and BOUNDED** — sealed by the PO 2026-08-06.
///
/// `M2` shipped `cue: u16` with no width constant, no repin log and no argument,
/// twelve lines from a constant carrying all three. Nothing caught it because
/// nothing counted ordinal spaces — which is what `AF-8` had already reported
/// about `RefKindMask` and nobody acted on.
///
/// The width is DERIVED from `MAX_DECLARED_VERBS`, not chosen: every cue comes
/// from a verb row and there is exactly one per row, so a reality with N verbs
/// cannot need an (N+1)th distinct cue.
#[test]
fn a_cue_past_the_declared_space_is_refused() {
    let over = ruleset_core::MAX_DECLARED_CUES;
    let src = format!(
        "[[verbs]]\nname = \"loud\"\ncue = {over}\n\
         effect_quantity = \"vitality\"\neffect_amount = 1\n"
    );
    let err = resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).unwrap(),
        parse_layer(Layer::Reality, &src).unwrap(),
    ])
    .expect_err("a cue outside the reality's cue space must be refused at BUILD");
    let msg = err.to_string();
    println!("cue bound  -> {msg}");
    assert!(msg.contains("loud") && msg.contains("cue"), "{msg}");

    // …and the last legal one is accepted, so the bound is a BOUND and not a ban.
    let ok = format!(
        "[[verbs]]\nname = \"quiet\"\ncue = {}\n\
         effect_quantity = \"vitality\"\neffect_amount = 1\n",
        over - 1
    );
    resolve(&[
        parse_layer(Layer::Preset, PROVING_GROUND_TOML).unwrap(),
        parse_layer(Layer::Reality, &ok).unwrap(),
    ])
    .expect("the highest legal cue is legal — otherwise this is an off-by-one, not a bound");

    // The DERIVATION, asserted. When a non-verb emitter arrives this equality
    // stops being true and must be changed HERE, once, with a reason — which is
    // the loud version of a silent widening.
    assert_eq!(
        ruleset_core::MAX_DECLARED_CUES,
        ruleset_core::MAX_DECLARED_VERBS,
        "the cue space is DERIVED from the verb space because every cue comes from a verb \
         row. If something other than a verb now emits a cue, change the derivation and \
         say why"
    );
}
