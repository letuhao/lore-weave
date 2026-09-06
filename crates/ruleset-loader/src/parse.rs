//! Reading ONE layer document — the two-pass parse and every refusal it makes.
//!
//! Split out of `lib.rs` at `IMP-D3`'s ceiling when `M2` added the verb-row
//! refusal. The seam is real and not a line-count dodge: everything here is
//! about ONE document (does it parse, does it declare a key that is not the
//! author's), while `resolve` is about the STACK (floors, fold order,
//! validation of the merged result). They fail for different reasons and their
//! diagnostics name different things.

use std::path::Path;

use crate::layer::Layer;
use crate::patch::RulesetPatch;
use crate::{LayerSource, LoadError};

/// Parse a TOML layer document.
///
/// **Two passes over one parse (S1a).** The document becomes a `toml::Value`
/// first so the `Forbidden` keys can be refused with a diagnostic that names
/// the field and the reason, *before* `deny_unknown_fields` gets to answer
/// "unknown field" — which is the wrong answer to a key that is very well
/// known and simply not the author's to set.
///
/// The rejected alternative was adding `schema_version`/`law_version` to
/// `RulesetPatch` so the validator could see them. That would make
/// `missing_fields`' totality check demand them in `engine_default.toml`:
/// **adding a field so it can be declared, in order to refuse declaring it.**
pub fn parse_layer(layer: Layer, toml_src: &str) -> Result<LayerSource, LoadError> {
    // Pass 1 — a permissive `Value`, ONLY to answer "does this document declare a
    // forbidden key?". Nothing is built from it.
    let doc: toml::Value =
        toml::from_str(toml_src).map_err(|source| LoadError::Parse { layer, source })?;
    // `as_table()` on a parsed TOML root cannot be `None` — the format has no
    // other root shape. Written as an explicit refusal rather than
    // `if let Some(t) = … {}` because that form makes the failure case **skip
    // the check silently**: if the assumption ever stopped holding, every
    // forbidden key would be quietly admitted and the gate would report nothing.
    // A guard whose else-branch is "do nothing" is not a guard.
    let table = doc.as_table().ok_or(LoadError::NotATable { layer })?;
    for (field, reason) in ruleset_core::FORBIDDEN_KEYS {
        if table.contains_key(*field) {
            return Err(LoadError::ForbiddenField { layer, field, reason });
        }
    }
    // `M2` / `CMD-10` V4 — the same refusal one level in, on every `[[verbs]]`
    // row. It runs HERE, on the permissive `Value`, for the reason the top-level
    // check does: `deny_unknown_fields` would answer "unknown field", which is
    // true and no help, because the field is not unknown. It is very well known
    // and simply not the author's to set.
    if let Some(rows) = table.get("verbs").and_then(|v| v.as_array()) {
        for row in rows {
            let Some(t) = row.as_table() else { continue };
            let name = t.get("name").and_then(|n| n.as_str()).unwrap_or("<unnamed>");
            crate::patch_verb::VerbPatch::refuse_authority_keys(t, name)
                .map_err(|e| LoadError::Verb { layer, message: e.to_string() })?;
        }
    }

    // Pass 2 — deserialize from the STRING, not from `doc`.
    //
    // **This costs a second parse and buys back the error spans.** Deserializing
    // the already-parsed `Value` looked free and silently destroyed every
    // diagnostic in this path: `toml`'s spans live on the source text, so
    // `Value -> T` reports
    //
    //     unknown field `max_hitt`, expected one of ... in `combat`
    //
    // where parsing the string reports
    //
    //     TOML parse error at line 4, column 1
    //       |
    //     4 | max_hitt = 9
    //       | ^^^^^^^^
    //
    // The module doc above justifies `deny_unknown_fields` by *"turning twenty
    // minutes of confusion into one line of diagnostic"* — so losing the line
    // number defeats the reason the refusal exists. Nothing caught it either:
    // `a_misspelled_key_is_refused_not_ignored` only asserts the key NAME is in
    // the message, which stayed true. `a_bad_key_is_reported_with_its_LINE` now
    // pins the span itself.
    //
    // The cost is one extra parse of a small file on the COLD path — layers are
    // resolved once at reality creation (RLS-A3 early binding), never in a step.
    let patch: RulesetPatch =
        toml::from_str(toml_src).map_err(|source| LoadError::Parse { layer, source })?;
    Ok(LayerSource { layer, patch })
}

/// Read a layer document from disk.
pub fn read_layer(layer: Layer, path: &Path) -> Result<LayerSource, LoadError> {
    let src = std::fs::read_to_string(path).map_err(|source| LoadError::Io { layer, source })?;
    parse_layer(layer, &src)
}
