//! The BEHAVIOURAL half of the authorable-surface contract.
//!
//! `contracts/ruleset/authorable-surface.v1.yaml` is the derived statement of
//! what an author may declare (`G-S5a`). `scripts/authorable-surface-gate.py`
//! checks it against the SOURCE — every field of every patch type reachable from
//! `RulesetPatch` is listed, and nothing is listed that is not a field.
//!
//! That check can still be satisfied by a contract the loader would reject. It
//! compares names against names; it never asks the loader anything. So this file
//! asks:
//!
//! * a document containing **every** enumerated key **parses**;
//! * a key that is **not** enumerated is **refused**;
//! * every key the contract calls **refused** is refused **by name**, with the
//!   reason — not as "unknown field", which is the wrong answer twice.
//!
//! Two methods, one subject: `V.2`'s "a mechanical oracle by a DIFFERENT method
//! than the thing it checks". A field added and enumerated but mistyped passes
//! the source gate and fails here; a field added and never enumerated passes
//! here and fails the source gate.
//!
//! **This runs at the PARSE boundary on purpose.** `deny_unknown_fields` acts
//! during deserialization, and the two forbidden lists act on the permissive
//! first pass — so `parse_layer` is exactly the layer where "may an author write
//! this key?" is answered. Semantic validity (does the named quantity exist, is
//! the pair complete) belongs to `resolve`, is a different question, and would
//! only add ways for this test to fail for reasons that are not its subject.

use ruleset_loader::{Layer, LoadError, parse_layer};
use serde_yaml::Value;

const CONTRACT: &str = "../../contracts/ruleset/authorable-surface.v1.yaml";

fn contract() -> Value {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(CONTRACT);
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("REACH: cannot read the contract at {path:?}: {e}"));
    serde_yaml::from_str(&text).expect("the contract is valid YAML")
}

fn seq<'a>(v: &'a Value, key: &str) -> &'a Vec<Value> {
    v.get(key).and_then(Value::as_sequence).unwrap_or_else(|| panic!("`{key}:` is not a list"))
}

fn s(v: &Value, key: &str) -> String {
    v.get(key).and_then(Value::as_str).unwrap_or_default().to_string()
}

/// A parse-legal value for a declared type.
///
/// Deliberately crude: at the parse boundary the only thing that matters is that
/// the TOML scalar is of the right *shape*. A closed-set member is used where
/// the contract names one, so the document also happens to be semantically
/// plausible — but nothing here depends on that.
fn sample(field: &Value) -> String {
    let ty = s(field, "type");
    let bare = ty.trim_start_matches("Option<").trim_end_matches('>').to_string();
    if let Some(set) = field.get("closed_set").and_then(Value::as_sequence) {
        if let Some(first) = set.first().and_then(Value::as_str) {
            return format!("\"{first}\"");
        }
    }
    match bare.as_str() {
        "String" => "\"x\"".into(),
        "f64" => "1.0".into(),
        "[i32; SLOT_COUNT]" => "[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]".into(),
        _ => "1".into(),
    }
}

/// Render one section's fields as `key = value` lines, skipping any field whose
/// value is a nested table (those are emitted as their own header).
fn body(section: &Value, skip_nested: bool) -> String {
    let mut out = String::new();
    for f in seq(section, "fields") {
        if skip_nested && f.get("nested").is_some() {
            continue;
        }
        out.push_str(&format!("{} = {}\n", s(f, "key"), sample(f)));
    }
    out
}

fn nested_entry(doc: &Value, key: &str) -> Value {
    seq(doc, "nested")
        .iter()
        .find(|n| s(n, "key") == key)
        .unwrap_or_else(|| panic!("the contract references nested `{key}` and does not define it"))
        .clone()
}

/// A document declaring EVERY enumerated key.
fn maximal_document(doc: &Value) -> String {
    let sections = seq(doc, "sections");
    let mut root = String::new();
    let mut tables = String::new();

    for sec in sections {
        let key = s(sec, "key");
        // Root-level scalars must precede every table header — after a header,
        // TOML assigns following keys to that table.
        if sec.get("scalar_list").is_some() {
            root.push_str(&format!("{key} = [\"q1\"]\n"));
        } else if sec.get("list_of_tables").is_some() {
            tables.push_str(&format!("\n[[{key}]]\n{}", body(sec, true)));
            for f in seq(sec, "fields") {
                if let Some(n) = f.get("nested").and_then(Value::as_str) {
                    let nested = nested_entry(doc, n);
                    tables.push_str(&format!(
                        "\n[[{key}.{}]]\n{}",
                        s(f, "key"),
                        body(&nested, true)
                    ));
                }
            }
        } else {
            tables.push_str(&format!("\n[{key}]\n{}", body(sec, true)));
        }
    }
    format!("{root}{tables}")
}

#[test]
fn a_document_declaring_every_enumerated_key_parses() {
    let doc = contract();
    let toml_src = maximal_document(&doc);

    // REACH — a contract that parsed to nothing would render an empty document,
    // which parses fine and proves nothing at all.
    let lines = toml_src.lines().filter(|l| l.contains('=')).count();
    assert!(
        lines >= 40,
        "REACH: the generated document declares only {lines} key(s); the contract is not being \
         read.\n{toml_src}"
    );

    match parse_layer(Layer::Reality, &toml_src) {
        Ok(_) => {}
        Err(e) => panic!(
            "the loader REFUSED a document built entirely from the contract's own enumeration: \
             {e:?}\n\nThe contract promises an author these keys; the loader is the thing that \
             decides. One of them is wrong.\n\n--- generated ---\n{toml_src}"
        ),
    }
}

#[test]
fn a_key_the_contract_does_not_enumerate_is_refused_in_every_section() {
    let doc = contract();
    let mut checked = 0;
    for sec in seq(&doc, "sections") {
        let key = s(sec, "key");
        if sec.get("scalar_list").is_some() {
            continue; // a list of strings has no keys to misspell
        }
        let header = if sec.get("list_of_tables").is_some() {
            format!("[[{key}]]")
        } else {
            format!("[{key}]")
        };
        let src = format!("{header}\n{}not_a_real_key = 1\n", body(sec, true));
        let err = parse_layer(Layer::Reality, &src).err().unwrap_or_else(|| {
            panic!(
                "section `{key}` ACCEPTED an undeclared key. `deny_unknown_fields` is what makes \
                 the contract's enumeration complete rather than indicative — without it, a \
                 misspelled key silently does nothing and the author tunes a number that has no \
                 effect."
            )
        });
        let msg = format!("{err:?}");
        assert!(
            msg.contains("not_a_real_key"),
            "section `{key}` refused the key but the diagnostic does not name it: {msg}"
        );
        checked += 1;
    }
    assert!(checked >= 5, "REACH: only {checked} section(s) probed");
}

#[test]
fn every_key_the_contract_calls_refused_is_refused_by_name_with_its_reason() {
    let doc = contract();
    let block = doc.get("refused").expect("the contract declares `refused:`");
    let mut checked = 0;
    for entry in seq(block, "keys") {
        let key = s(entry, "key");
        let err = parse_layer(Layer::Reality, &format!("{key} = 1\n"))
            .err()
            .unwrap_or_else(|| panic!("`{key}` is documented as refused and the loader ACCEPTED it"));
        // The VARIANT, not the message text. `deny_unknown_fields` would also
        // produce an error mentioning the key — and that is precisely the wrong
        // answer, because the key is not unknown. It is very well known and
        // simply not the author's, which is why `forbidden.rs` refuses it by
        // name on a permissive first pass. Matching on the variant is what
        // distinguishes the two; matching on text cannot.
        assert!(
            matches!(err, LoadError::ForbiddenField { field, .. } if field == key),
            "`{key}` was not refused as a FORBIDDEN FIELD. If this is `Parse`, the by-name \
             refusal was skipped and serde answered 'unknown field' instead — true, and no help, \
             because the author is never told why they may never set it: {err:?}"
        );
        checked += 1;
    }
    assert!(checked >= 3, "REACH: only {checked} refused key(s) probed");
}

#[test]
fn every_key_refused_inside_a_verb_row_is_refused_by_name_with_the_verb() {
    let doc = contract();
    let block = doc.get("refused_in_verb_rows").expect("the contract declares it");
    let mut checked = 0;
    for entry in seq(block, "keys") {
        let key = s(entry, "key");
        let src = format!(
            "[[verbs]]\nname = \"strike\"\neffect_quantity = \"hp\"\neffect_amount = -1\n{key} = 1\n"
        );
        let err = parse_layer(Layer::Reality, &src)
            .err()
            .unwrap_or_else(|| panic!("a verb row carrying `{key}` was ACCEPTED"));

        // Match the VARIANT first. Asserting on message text alone was VACUOUS
        // here and biting proved it: with `refuse_authority_keys` removed, the
        // `deny_unknown_fields` fallback still produced an error containing both
        // the key AND the word "strike" — because `toml`'s error rendering
        // echoes the offending SOURCE SNIPPET, and the snippet contains
        // `name = "strike"`. The assertion passed on the document being quoted
        // back at it rather than on the refusal naming the verb.
        let LoadError::Verb { message, .. } = &err else {
            panic!(
                "a verb row carrying `{key}` was not refused by the per-row check. `CMD-10` V4 \
                 is enforced on the permissive pass so the author is told WHICH VERB; if this is \
                 `Parse`, that check was skipped and serde answered for it: {err:?}"
            )
        };
        assert!(message.contains(&key), "`{key}` refused without being named: {message}");
        assert!(
            message.contains("strike"),
            "the refusal of `{key}` does not name the VERB. An author with a dozen verbs is left \
             looking, which is why this list is separate from the top-level one: {message}"
        );
        checked += 1;
    }
    assert!(checked >= 3, "REACH: only {checked} verb-row refusal(s) probed");
}
