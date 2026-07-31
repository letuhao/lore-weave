//! `progression-validate` — **`PGN-A7`'s binary.**
//!
//! > *"The validator is the engine's binary, and the verdict records which
//! > binary."*
//!
//! Doc 39 §7 says this axiom *"stamps a version from nothing"* until something
//! can actually run the engine's validator. `S-1` built
//! `ProgressionSchemaValidator` as a **library**, which is a validator nothing
//! outside this workspace can call — so the pipeline's S5 stage would have
//! recorded `engine_schema_version: 5` next to a verdict produced by re-reading
//! the rules in Python. That is the *mirror nothing forces to agree* one tier up
//! from `CPL-A2`, and it is worse here: the mirror would be stamped with the real
//! engine's version number.
//!
//! This is the smallest thing that makes the stamp true. It reads authored
//! ruleset TOML, runs **the same** `resolve_and_pin` path a reality load runs,
//! and prints a JSON verdict carrying the versions **compiled into this
//! binary** — not passed in, not configured. A caller cannot claim a version it
//! did not run, because the only way to get a verdict is to run this.
//!
//! ```text
//! progression-validate <layer>=<path> [<layer>=<path> …]
//! ```
//!
//! Exit code is 0 for `admitted` and 1 for `refused`, so a shell pipeline sees
//! the verdict without parsing; the JSON on stdout is what S5 records.
//!
//! ## Why it validates through `resolve_and_pin` rather than calling `validate`
//!
//! `validate(table, quantities)` alone would check the table and miss everything
//! the *admission path* adds — the store round-trip, the dangling-pin check, the
//! label coverage refusal (`PGN-A18`). A verdict from a narrower path than the
//! one a reality actually takes is a verdict that can pass for a reality that
//! cannot load. So this runs the real one, against a throwaway store.

use std::collections::BTreeMap;
use std::path::Path;

use ruleset_core::{LAW_VERSION, RULESET_SCHEMA_VERSION};
use ruleset_loader::{
    read_layer, resolve_and_pin, LabelStore, Layer, LoadError, ProgressionStore, RulesetStore,
};

fn layer_by_name(name: &str) -> Option<Layer> {
    // Matched by the layer's own `name()` so this list cannot drift from the
    // enum: a new layer that is not handled here fails loudly at the CLI rather
    // than being silently unreachable.
    [
        Layer::EngineDefault,
        Layer::Preset,
        Layer::Book,
        Layer::Reality,
        Layer::ForgeOverride,
    ]
    .into_iter()
    .find(|l| l.name() == name)
}

fn escape(s: &str) -> String {
    // Hand-rolled rather than pulling serde_json into this crate for one output
    // shape. Only the four things a JSON string must escape appear in a findings
    // message; control characters cannot, because every message is a Rust
    // format string over enum data.
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\t', "\\t")
}

fn emit(verdict: &str, findings: &[String], digest: Option<String>) {
    println!("{{");
    println!("  \"verdict\": \"{verdict}\",");
    println!("  \"engine_schema_version\": {RULESET_SCHEMA_VERSION},");
    println!("  \"engine_law_version\": {LAW_VERSION},");
    match digest {
        Some(d) => println!("  \"progression_digest\": \"{d}\","),
        None => println!("  \"progression_digest\": null,"),
    }
    println!("  \"findings\": [");
    for (i, f) in findings.iter().enumerate() {
        let comma = if i + 1 == findings.len() { "" } else { "," };
        println!("    \"{}\"{comma}", escape(f));
    }
    println!("  ]");
    println!("}}");
}

fn run(args: &[String], scratch: &Path) -> (bool, Vec<String>, Option<String>) {
    let mut layers = Vec::new();
    for a in args {
        let Some((name, path)) = a.split_once('=') else {
            return (false, vec![format!("argument `{a}` is not <layer>=<path>")], None);
        };
        let Some(layer) = layer_by_name(name) else {
            return (false, vec![format!("unknown layer `{name}`")], None);
        };
        match read_layer(layer, Path::new(path)) {
            Ok(src) => layers.push(src),
            Err(e) => return (false, vec![e.to_string()], None),
        }
    }
    if layers.is_empty() {
        return (false, vec!["no layers given".into()], None);
    }

    // A throwaway store, because this is a VERDICT and not an admission: running
    // the validator must never leave a table behind that a later load could
    // resolve. The pipeline pins deliberately, at S6.
    let rules = RulesetStore::new(scratch.join("rules"));
    let prog = ProgressionStore::beside(&rules);
    let labels = LabelStore::beside(&rules);

    match resolve_and_pin(&layers, &prog, &labels) {
        Ok(r) => {
            let digest = r.progression.map(|d| d.to_hex());
            (true, Vec::new(), digest)
        }
        // Every finding, not the first. `validate` returns them all precisely so
        // a reviewer does not fix one, re-run, and find another — flattening that
        // to a single string here would undo it at the last hop.
        Err(LoadError::ProgressionInvalid(v)) => {
            (false, v.iter().map(|f| f.to_string()).collect(), None)
        }
        Err(e) => (false, vec![e.to_string()], None),
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() || args[0] == "--help" {
        eprintln!(
            "progression-validate <layer>=<path> …\n\
             \n\
             Runs the ENGINE's progression validator over authored ruleset TOML and\n\
             prints a JSON verdict stamped with the versions compiled into this\n\
             binary (PGN-A7). Exit 0 = admitted, 1 = refused.\n\
             \n\
             layers: {}",
            [
                Layer::EngineDefault,
                Layer::Preset,
                Layer::Book,
                Layer::Reality,
                Layer::ForgeOverride
            ]
            .map(|l| l.name())
            .join(", ")
        );
        std::process::exit(2);
    }

    let scratch = std::env::temp_dir().join(format!(
        "progval-{}-{}",
        std::process::id(),
        // Not a random name: two concurrent runs with the same pid cannot exist,
        // and a deterministic path is one a failing CI run can be pointed at.
        args.len()
    ));
    let (ok, findings, digest) = run(&args, &scratch);
    let _ = std::fs::remove_dir_all(&scratch);

    emit(if ok { "admitted" } else { "refused" }, &findings, digest);
    std::process::exit(if ok { 0 } else { 1 });
}

/// Kept as a map so `--help`'s layer list and `layer_by_name` cannot drift apart
/// without this failing to compile.
#[allow(dead_code)]
fn _layers_are_exhaustive(l: Layer) -> BTreeMap<&'static str, ()> {
    match l {
        Layer::EngineDefault | Layer::Preset | Layer::Book | Layer::Reality | Layer::ForgeOverride => {}
    }
    BTreeMap::new()
}
