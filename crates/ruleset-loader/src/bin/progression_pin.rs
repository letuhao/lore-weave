//! `progression-pin` — S6. Where the bytes land.
//!
//! The sibling of `progression-validate`, and the difference between them is the
//! whole point of having two binaries:
//!
//! | | `progression-validate` | `progression-pin` |
//! |---|---|---|
//! | store | **throwaway**, removed after | the **real** one |
//! | leaves behind | nothing | the table, the labels, the ruleset |
//! | answers | *"would this be admitted?"* | *"admit it"* |
//!
//! A verdict that persisted would let a later load resolve a table nobody
//! approved; an admission that did not persist would be a no-op wearing a
//! success. One binary with a flag would make that distinction a runtime
//! argument, and the wrong value of it is silent in both directions.
//!
//! ## `--expect` is the property this binary exists for
//!
//! S5 recorded a `progression_digest` alongside a human's approval. S6 must pin
//! **that** digest and no other. Between the two there is a re-generation, a file
//! write and a process boundary — every one of which is a place for the bytes to
//! change, and none of which would announce it: the pin would succeed, the store
//! would hold a valid table, and the ruleset would carry a digest a human never
//! saw.
//!
//! So the expected digest is **required**, compared after resolution, and a
//! mismatch is a refusal that prints both. This is T8 (*the artifact cannot be
//! swapped*) at the one hop where the artifact leaves the database.
//!
//! ```text
//! progression-pin --store <dir> --expect <64-hex> <layer>=<path>
//! ```
//!
//! Exit 0 = pinned, 1 = refused, 2 = usage.

use std::path::{Path, PathBuf};

use ruleset_core::{LAW_VERSION, RULESET_SCHEMA_VERSION};
use ruleset_loader::{
    read_layer, resolve_and_pin, LabelStore, Layer, LoadError, ProgressionStore, RulesetStore,
};

fn layer_by_name(name: &str) -> Option<Layer> {
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
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\t', "\\t")
}

fn emit(ok: bool, findings: &[String], progression: Option<&str>, ruleset: Option<&str>) {
    println!("{{");
    println!("  \"pinned\": {ok},");
    println!("  \"engine_schema_version\": {RULESET_SCHEMA_VERSION},");
    println!("  \"engine_law_version\": {LAW_VERSION},");
    println!(
        "  \"progression_digest\": {},",
        progression.map(|d| format!("\"{d}\"")).unwrap_or_else(|| "null".into())
    );
    // The digest of the WHOLE ruleset, which is what actually moves when a
    // progression table is pinned — POC-1's exit criterion is "the ruleset digest
    // moves", not "a table appeared in a directory".
    println!(
        "  \"ruleset_digest\": {},",
        ruleset.map(|d| format!("\"{d}\"")).unwrap_or_else(|| "null".into())
    );
    println!("  \"findings\": [");
    for (i, f) in findings.iter().enumerate() {
        let comma = if i + 1 == findings.len() { "" } else { "," };
        println!("    \"{}\"{comma}", escape(f));
    }
    println!("  ]");
    println!("}}");
}

struct Args {
    store: PathBuf,
    expect: String,
    layers: Vec<(Layer, PathBuf)>,
}

fn parse(argv: &[String]) -> Result<Args, String> {
    let (mut store, mut expect, mut layers) = (None, None, Vec::new());
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--store" => {
                i += 1;
                store = Some(PathBuf::from(argv.get(i).ok_or("--store needs a path")?));
            }
            "--expect" => {
                i += 1;
                expect = Some(argv.get(i).ok_or("--expect needs a digest")?.clone());
            }
            other => {
                let (name, path) = other
                    .split_once('=')
                    .ok_or_else(|| format!("argument `{other}` is not <layer>=<path>"))?;
                let layer =
                    layer_by_name(name).ok_or_else(|| format!("unknown layer `{name}`"))?;
                layers.push((layer, PathBuf::from(path)));
            }
        }
        i += 1;
    }
    let expect = expect.ok_or(
        "--expect <64-hex> is REQUIRED. S5 recorded a digest beside a human's approval, and \
         S6 must pin that one; without it the pin would succeed on whatever the bytes happen \
         to resolve to and the ruleset would carry a digest nobody saw",
    )?;
    if expect.len() != 64 || !expect.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(format!("--expect `{expect}` is not a 64-hex digest"));
    }
    Ok(Args {
        store: store.ok_or("--store <dir> is required")?,
        expect: expect.to_ascii_lowercase(),
        layers,
    })
}

fn run(a: &Args) -> (bool, Vec<String>, Option<String>, Option<String>) {
    let mut sources = Vec::new();
    for (layer, path) in &a.layers {
        match read_layer(*layer, Path::new(path)) {
            Ok(s) => sources.push(s),
            Err(e) => return (false, vec![e.to_string()], None, None),
        }
    }
    if sources.is_empty() {
        return (false, vec!["no layers given".into()], None, None);
    }

    // ── pass 1: resolve into a SCRATCH store to learn the digest ────────────
    //
    // `resolve_and_pin` PERSISTS the table before it returns, so the `--expect`
    // comparison cannot come after a resolution against the real store: a
    // mismatch would already have written a table nobody approved into the store
    // a reality resolves from. That is exactly the class `progression-validate`'s
    // throwaway store exists to prevent, and the first version of this binary
    // let it through on the sibling — proven by running a mismatched pin against
    // an empty store and finding `<digest>.prog` and `<digest>.labels.toml` in it
    // afterwards.
    //
    // So: resolve into scratch, compare, and only then resolve into the real
    // store. The second pass is the same deterministic code over the same bytes,
    // so it costs a little work and buys the property that the real store is
    // never touched by a run that is going to refuse.
    let scratch_root = std::env::temp_dir().join(format!("progpin-{}", std::process::id()));
    let scratch = RulesetStore::new(&scratch_root);
    let got = {
        let sp = ProgressionStore::beside(&scratch);
        let sl = LabelStore::beside(&scratch);
        let probe = match resolve_and_pin(&sources, &sp, &sl) {
            Ok(r) => r,
            Err(LoadError::ProgressionInvalid(v)) => {
                let _ = std::fs::remove_dir_all(&scratch_root);
                return (false, v.iter().map(|f| f.to_string()).collect(), None, None);
            }
            Err(e) => {
                let _ = std::fs::remove_dir_all(&scratch_root);
                return (false, vec![e.to_string()], None, None);
            }
        };
        let d = probe.progression.map(|d| d.to_hex());
        let _ = std::fs::remove_dir_all(&scratch_root);
        match d {
            Some(d) => d,
            None => {
                return (
                    false,
                    vec!["the resolved ruleset carries NO progression digest, so there is \
                          nothing to pin. An empty layer set resolves to the engine \
                          default, which is admissible and progression-less - refused \
                          rather than recorded as a successful pin of nothing"
                        .into()],
                    None,
                    None,
                )
            }
        }
    };

    // T8, at the one hop where the artifact leaves the database.
    if got != a.expect {
        return (
            false,
            vec![format!(
                "digest mismatch: the approved candidate names {} and these bytes resolve \
                 to {}. Between S5 and here sit a re-generation, a file write and a \
                 process boundary; a pin that accepted the difference would put a digest \
                 in the ruleset that no human ever saw. The real store was NOT touched",
                a.expect, got
            )],
            Some(got),
            None,
        );
    }

    // ── pass 2: the real admission ──────────────────────────────────────────
    let rules = RulesetStore::new(&a.store);
    let prog = ProgressionStore::beside(&rules);
    let labels = LabelStore::beside(&rules);
    let ruleset = match resolve_and_pin(&sources, &prog, &labels) {
        Ok(r) => r,
        Err(e) => return (false, vec![e.to_string()], Some(got), None),
    };

    match rules.put(&ruleset) {
        Ok(rd) => (true, Vec::new(), Some(got), Some(rd.to_hex())),
        Err(e) => (false, vec![e.to_string()], Some(got), None),
    }
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.is_empty() || argv[0] == "--help" {
        eprintln!(
            "progression-pin --store <dir> --expect <64-hex> <layer>=<path> …\n\
             \n\
             ADMITS a validated progression table into a REAL content-addressed store and\n\
             reports the ruleset digest it produced. The sibling `progression-validate`\n\
             answers \"would this be admitted?\" against a throwaway store and leaves\n\
             nothing behind; this one answers \"admit it\".\n\
             \n\
             --expect is REQUIRED and is compared after resolution (T8): S6 pins the digest\n\
             a human approved at S5, or nothing.\n\
             \n\
             Exit 0 = pinned, 1 = refused."
        );
        std::process::exit(2);
    }

    let args = match parse(&argv) {
        Ok(a) => a,
        Err(e) => {
            emit(false, &[e], None, None);
            std::process::exit(2);
        }
    };

    let (ok, findings, prog, rules) = run(&args);
    emit(ok, &findings, prog.as_deref(), rules.as_deref());
    std::process::exit(if ok { 0 } else { 1 });
}
