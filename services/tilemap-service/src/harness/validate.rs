//! L3 response validation — TMP_008b §4.1 rules R1-R5. The Phase 0b harness
//! runs these against the LLM's parsed tool-call output to MEASURE contract
//! conformance; the full per-object retry loop (TMP_008b §5) is Phase 2.

use std::collections::HashSet;

use serde::Deserialize;

use super::prompt::L3Placeholder;

/// One classification entry parsed from the `submit_zone_classifications`
/// tool-call arguments.
#[derive(Debug, Clone, Deserialize)]
pub struct L3Classification {
    pub obj_id: String,
    pub canon_kind: String,
    pub narrative_tag: String,
    #[serde(default)]
    pub canon_ref: Option<String>,
    #[serde(default)]
    pub rationale: Option<String>,
}

/// The parsed `submit_zone_classifications` argument object.
#[derive(Debug, Clone, Deserialize)]
pub struct L3ToolArguments {
    pub classifications: Vec<L3Classification>,
}

/// A single validation failure (TMP_008b §4.1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum L3ValidationError {
    /// R1 — an input obj_id never appeared in the output.
    MissingObjectClassification { obj_id: String },
    /// R1 — an output obj_id was not in the input.
    UnknownObjId { obj_id: String },
    /// R2 — an obj_id appeared more than once in the output.
    DuplicateObjId { obj_id: String },
    /// R3 — canon_kind not in that object's suggested_canon_kind list.
    CanonKindNotInSuggested {
        obj_id: String,
        received: String,
        allowed: Vec<String>,
    },
    /// R4 — canon_ref is non-null but not a known book_canon_refs entry.
    CanonRefNotFound { obj_id: String, received: String },
    /// R5 — narrative_tag fails the [a-z0-9_]{1,64} pattern.
    InvalidNarrativeTag { obj_id: String, received: String },
}

impl L3ValidationError {
    /// The `obj_id` this error is about.
    ///
    /// Exhaustive `match`, **no `_` wildcard** (spec D4) — a future variant
    /// lacking an `obj_id` is then a compile error, not a silent break of the
    /// retry loop's accept/narrow ground truth.
    pub fn obj_id(&self) -> &str {
        match self {
            Self::MissingObjectClassification { obj_id }
            | Self::UnknownObjId { obj_id }
            | Self::DuplicateObjId { obj_id }
            | Self::CanonKindNotInSuggested { obj_id, .. }
            | Self::CanonRefNotFound { obj_id, .. }
            | Self::InvalidNarrativeTag { obj_id, .. } => obj_id,
        }
    }

    /// One actionable retry line (TMP_008b §4.2) — the tag plus a concrete
    /// instruction. Used by [`format_errors_for_retry`].
    fn retry_line(&self) -> String {
        match self {
            Self::MissingObjectClassification { obj_id } => format!(
                "[MISSING] obj_id='{obj_id}' was not classified. Add a classification."
            ),
            Self::UnknownObjId { obj_id } => format!(
                "[UNKNOWN] obj_id='{obj_id}' was not in the input. Remove this entry."
            ),
            Self::DuplicateObjId { obj_id } => format!(
                "[DUPLICATE] obj_id='{obj_id}' appears twice. Keep only one entry."
            ),
            Self::CanonKindNotInSuggested {
                obj_id,
                received,
                allowed,
            } => format!(
                "[INVALID-CANON-KIND] obj_id='{obj_id}': canon_kind='{received}' is not in \
                 suggested_canon_kind={allowed:?}. Pick exactly one from that list."
            ),
            Self::CanonRefNotFound { obj_id, received } => format!(
                "[INVALID-CANON-REF] obj_id='{obj_id}': canon_ref='{received}' does not exist \
                 in book_canon_refs. Use a real ref from the list, or set canon_ref=null."
            ),
            Self::InvalidNarrativeTag { obj_id, received } => format!(
                "[INVALID-TAG] obj_id='{obj_id}': narrative_tag='{received}' has invalid \
                 characters. Use only lowercase letters, digits, underscores; max 64 chars."
            ),
        }
    }

    /// Human-readable one-liner for the measurement report.
    pub fn describe(&self) -> String {
        match self {
            Self::MissingObjectClassification { obj_id } => {
                format!("[MISSING] obj_id='{obj_id}' was not classified")
            }
            Self::UnknownObjId { obj_id } => {
                format!("[UNKNOWN] obj_id='{obj_id}' was not in the input")
            }
            Self::DuplicateObjId { obj_id } => {
                format!("[DUPLICATE] obj_id='{obj_id}' appears more than once")
            }
            Self::CanonKindNotInSuggested {
                obj_id,
                received,
                allowed,
            } => format!(
                "[INVALID-CANON-KIND] obj_id='{obj_id}': '{received}' not in {allowed:?}"
            ),
            Self::CanonRefNotFound { obj_id, received } => {
                format!("[INVALID-CANON-REF] obj_id='{obj_id}': '{received}' not a known ref")
            }
            Self::InvalidNarrativeTag { obj_id, received } => {
                format!("[INVALID-TAG] obj_id='{obj_id}': '{received}' is not snake_case ≤64")
            }
        }
    }
}

/// True when `tag` is non-empty, ≤64 chars, and only `[a-z0-9_]` (TMP_008b §4.1 R5).
fn is_valid_narrative_tag(tag: &str) -> bool {
    !tag.is_empty()
        && tag.len() <= 64
        && tag
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

/// Run TMP_008b §4.1 rules R1-R5 against a parsed L3 response.
pub fn validate_l3(
    classifications: &[L3Classification],
    placeholders: &[L3Placeholder],
    book_canon_refs: &[String],
) -> Vec<L3ValidationError> {
    let mut errors = Vec::new();

    let input_ids: HashSet<&str> = placeholders.iter().map(|p| p.obj_id.as_str()).collect();
    let output_ids: HashSet<&str> = classifications.iter().map(|c| c.obj_id.as_str()).collect();

    // R1 — every input obj_id must appear; no extra output ids.
    for p in placeholders {
        if !output_ids.contains(p.obj_id.as_str()) {
            errors.push(L3ValidationError::MissingObjectClassification {
                obj_id: p.obj_id.clone(),
            });
        }
    }
    for c in classifications {
        if !input_ids.contains(c.obj_id.as_str()) {
            errors.push(L3ValidationError::UnknownObjId {
                obj_id: c.obj_id.clone(),
            });
        }
    }

    // R2 — no duplicate obj_id in the output.
    let mut seen: HashSet<&str> = HashSet::new();
    for c in classifications {
        if !seen.insert(c.obj_id.as_str()) {
            errors.push(L3ValidationError::DuplicateObjId {
                obj_id: c.obj_id.clone(),
            });
        }
    }

    for c in classifications {
        let placeholder = placeholders.iter().find(|p| p.obj_id == c.obj_id);

        // R3 — canon_kind ∈ that object's suggested_canon_kind.
        if let Some(p) = placeholder {
            if !p.suggested_canon_kind.contains(&c.canon_kind) {
                errors.push(L3ValidationError::CanonKindNotInSuggested {
                    obj_id: c.obj_id.clone(),
                    received: c.canon_kind.clone(),
                    allowed: p.suggested_canon_kind.clone(),
                });
            }
        }

        // R4 — canon_ref null OR a known book_canon_refs entry.
        if let Some(ref_id) = &c.canon_ref {
            if !book_canon_refs.contains(ref_id) {
                errors.push(L3ValidationError::CanonRefNotFound {
                    obj_id: c.obj_id.clone(),
                    received: ref_id.clone(),
                });
            }
        }

        // R5 — narrative_tag pattern + length.
        if !is_valid_narrative_tag(&c.narrative_tag) {
            errors.push(L3ValidationError::InvalidNarrativeTag {
                obj_id: c.obj_id.clone(),
                received: c.narrative_tag.clone(),
            });
        }
    }

    errors
}

/// TMP_008b §4.2 — render validation errors as a structured per-object retry
/// message for the LLM. Spec D3 output shape: an empty slice yields `""`; a
/// non-empty slice yields the reframed subset-retry preamble as the **first
/// line**, a blank line, then one actionable `[TAG] …` line per error. The
/// function owns the whole message — the caller passes it verbatim.
pub fn format_errors_for_retry(errors: &[L3ValidationError]) -> String {
    if errors.is_empty() {
        return String::new();
    }
    // Reframed for subset retries (spec D3) — §4.2's "keep all other entries
    // unchanged" assumed the full object set; this loop re-sends only the
    // failing subset, so the preamble must not reference absent objects.
    let mut msg = String::from(
        "Your previous classification of the objects below failed validation. \
         Previously-valid classifications are already saved — re-classify ONLY \
         the objects in this payload.\n\n",
    );
    for err in errors {
        msg.push_str(&err.retry_line());
        msg.push('\n');
    }
    msg
}

/// Split an L3 response into accepted classifications + validation errors,
/// validated against the requested `subset` (spec D4 — the per-object
/// accept/narrow core of the §5 retry loop).
///
/// A classification is **accepted** iff it is a member of `subset` and no
/// validation error names its `obj_id`. A response entry whose `obj_id` is not
/// in `subset` is reported as `UnknownObjId` by `validate_l3` and never
/// accepted — so `accepted` only ever contains subset members.
pub fn partition_response(
    subset: &[L3Placeholder],
    response: &[L3Classification],
    book_canon_refs: &[String],
) -> (Vec<L3Classification>, Vec<L3ValidationError>) {
    let errors = validate_l3(response, subset, book_canon_refs);
    let failed: HashSet<&str> = errors.iter().map(|e| e.obj_id()).collect();
    let subset_ids: HashSet<&str> = subset.iter().map(|p| p.obj_id.as_str()).collect();
    let accepted = response
        .iter()
        .filter(|c| {
            subset_ids.contains(c.obj_id.as_str()) && !failed.contains(c.obj_id.as_str())
        })
        .cloned()
        .collect();
    (accepted, errors)
}

/// TMP_008b §6 — the deterministic engine fallback for an object the LLM never
/// classified validly. Always produces a schema-valid `L3Classification` (its
/// `canon_kind` is in `suggested_canon_kind`, its `narrative_tag` is valid
/// snake_case, `canon_ref` is null) so the tilemap is playable even at 100 %
/// LLM failure.
///
/// `canon_kind` is the engine default — `suggested_canon_kind[0]`. The caller
/// MUST ensure that list is non-empty; the §5 retry loop checks this
/// precondition once at entry (spec D1/D5) so this indexing cannot panic.
pub fn canonical_default_classification(p: &L3Placeholder) -> L3Classification {
    L3Classification {
        obj_id: p.obj_id.clone(),
        canon_kind: p.suggested_canon_kind[0].clone(),
        narrative_tag: generate_default_tag(p),
        canon_ref: None,
        rationale: Some(
            "Canonical default (LLM failed validation after max retries)".to_string(),
        ),
    }
}

/// Deterministic narrative tag for a canonical-default classification —
/// `"{kind}_{zone}_default"`, each component lowercased and stripped to
/// `[a-z0-9_]`, the whole capped at 64 chars so it always passes the §4.1 R5
/// `narrative_tag` check.
fn generate_default_tag(p: &L3Placeholder) -> String {
    let kind = sanitize_tag_component(&p.kind);
    let zone = sanitize_tag_component(&p.zone_id);
    format!("{kind}_{zone}_default").chars().take(64).collect()
}

/// Lowercase `s` and map every character outside `[a-z0-9_]` to `_`.
fn sanitize_tag_component(s: &str) -> String {
    s.chars()
        .map(|c| {
            let c = c.to_ascii_lowercase();
            if c.is_ascii_alphanumeric() || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::harness::prompt::fixture_placeholders;

    fn ok_classification(obj_id: &str, kind: &str, tag: &str) -> L3Classification {
        L3Classification {
            obj_id: obj_id.to_string(),
            canon_kind: kind.to_string(),
            narrative_tag: tag.to_string(),
            canon_ref: None,
            rationale: None,
        }
    }

    #[test]
    fn clean_response_has_no_errors() {
        let p = fixture_placeholders();
        let classifications = vec![
            ok_classification("obj_1", "BanditCache", "hidden_bandit_cache"),
            ok_classification("obj_2", "BanditCamp", "forest_bandit_camp"),
            ok_classification("obj_3", "AncientTree", "lotus_sect_elder_tree"),
        ];
        let errors = validate_l3(&classifications, &p, &[]);
        assert!(errors.is_empty(), "errors = {errors:?}");
    }

    #[test]
    fn detects_missing_unknown_duplicate_badkind_badtag() {
        let p = fixture_placeholders();
        let classifications = vec![
            ok_classification("obj_1", "BanditCache", "ok_tag"),
            // obj_1 duplicated
            ok_classification("obj_1", "BanditCache", "ok_tag"),
            // bad canon_kind for obj_2
            ok_classification("obj_2", "LavaLair", "ok_tag"),
            // unknown obj id + bad tag
            ok_classification("obj_99", "Whatever", "Bad Tag!"),
            // obj_3 missing entirely
        ];
        let errors = validate_l3(&classifications, &p, &[]);
        assert!(errors.contains(&L3ValidationError::MissingObjectClassification {
            obj_id: "obj_3".into()
        }));
        assert!(errors.contains(&L3ValidationError::UnknownObjId {
            obj_id: "obj_99".into()
        }));
        assert!(errors.contains(&L3ValidationError::DuplicateObjId {
            obj_id: "obj_1".into()
        }));
        assert!(
            errors
                .iter()
                .any(|e| matches!(e, L3ValidationError::CanonKindNotInSuggested { obj_id, .. } if obj_id == "obj_2"))
        );
        assert!(
            errors
                .iter()
                .any(|e| matches!(e, L3ValidationError::InvalidNarrativeTag { obj_id, .. } if obj_id == "obj_99"))
        );
    }

    #[test]
    fn canon_ref_must_be_known() {
        let p = fixture_placeholders();
        let mut c = ok_classification("obj_1", "BanditCache", "tag");
        c.canon_ref = Some("nonexistent_ref".to_string());
        let errors = validate_l3(
            &[c],
            &p,
            &["lotus_sect_homeland_v1".to_string()],
        );
        assert!(errors.contains(&L3ValidationError::CanonRefNotFound {
            obj_id: "obj_1".into(),
            received: "nonexistent_ref".into(),
        }));
    }

    #[test]
    fn obj_id_returns_the_id_for_all_six_variants() {
        // AC-11 — every variant carries an obj_id; the accessor is total.
        let variants = [
            L3ValidationError::MissingObjectClassification { obj_id: "a".into() },
            L3ValidationError::UnknownObjId { obj_id: "b".into() },
            L3ValidationError::DuplicateObjId { obj_id: "c".into() },
            L3ValidationError::CanonKindNotInSuggested {
                obj_id: "d".into(),
                received: "X".into(),
                allowed: vec![],
            },
            L3ValidationError::CanonRefNotFound {
                obj_id: "e".into(),
                received: "r".into(),
            },
            L3ValidationError::InvalidNarrativeTag {
                obj_id: "f".into(),
                received: "T".into(),
            },
        ];
        let ids: Vec<&str> = variants.iter().map(|e| e.obj_id()).collect();
        assert_eq!(ids, ["a", "b", "c", "d", "e", "f"]);
    }

    #[test]
    fn format_errors_for_retry_empty_is_empty_string() {
        // AC-1 — total function: no errors ⇒ no "had errors" preamble.
        assert_eq!(format_errors_for_retry(&[]), "");
    }

    #[test]
    fn format_errors_for_retry_first_line_is_the_preamble() {
        // AC-1 — first line is the reframed subset-retry preamble, not an error.
        let errors = vec![
            L3ValidationError::MissingObjectClassification { obj_id: "obj_2".into() },
            L3ValidationError::InvalidNarrativeTag {
                obj_id: "obj_5".into(),
                received: "Bad Tag".into(),
            },
        ];
        let msg = format_errors_for_retry(&errors);
        let first = msg.lines().next().unwrap();
        assert!(first.contains("failed validation"), "first line not the preamble: {first}");
        assert!(!first.contains("[MISSING]"), "first line must be the preamble");
        assert!(msg.contains("[MISSING] obj_id='obj_2'"));
        assert!(msg.contains("[INVALID-TAG] obj_id='obj_5'"));
    }

    #[test]
    fn partition_response_accepts_all_when_clean() {
        let p = fixture_placeholders();
        let response = vec![
            ok_classification("obj_1", "BanditCache", "hidden_cache"),
            ok_classification("obj_2", "BanditCamp", "forest_camp"),
            ok_classification("obj_3", "AncientTree", "elder_tree"),
        ];
        let (accepted, errors) = partition_response(&p, &response, &[]);
        assert_eq!(accepted.len(), 3);
        assert!(errors.is_empty(), "errors = {errors:?}");
    }

    #[test]
    fn partition_response_narrows_to_the_failing_subset() {
        // Two invalid, one valid → only the valid object is accepted (spec D4).
        let p = fixture_placeholders();
        let response = vec![
            ok_classification("obj_1", "BanditCache", "ok_tag"),
            ok_classification("obj_2", "LavaLair", "ok_tag"), // R3: not suggested
            ok_classification("obj_3", "AncientTree", "Bad Tag!"), // R5: bad tag
        ];
        let (accepted, errors) = partition_response(&p, &response, &[]);
        let accepted_ids: Vec<&str> = accepted.iter().map(|c| c.obj_id.as_str()).collect();
        assert_eq!(accepted_ids, ["obj_1"]);
        assert!(!errors.is_empty());
    }

    #[test]
    fn partition_response_ignores_out_of_subset_entries() {
        // subset = obj_1 only; the LLM also returns obj_99 (never requested).
        let p = vec![fixture_placeholders().into_iter().next().unwrap()];
        let response = vec![
            ok_classification("obj_1", "BanditCache", "ok_tag"),
            ok_classification("obj_99", "Whatever", "ok_tag"),
        ];
        let (accepted, _errors) = partition_response(&p, &response, &[]);
        let ids: Vec<&str> = accepted.iter().map(|c| c.obj_id.as_str()).collect();
        assert_eq!(ids, ["obj_1"], "out-of-subset obj_99 must not be accepted");
    }

    #[test]
    fn canonical_default_uses_the_first_suggested_kind() {
        // AC-5 — canon_kind is the engine default = suggested_canon_kind[0].
        let p = &fixture_placeholders()[0]; // obj_1, suggested[0] == BanditCache
        let d = canonical_default_classification(p);
        assert_eq!(d.obj_id, "obj_1");
        assert_eq!(d.canon_kind, "BanditCache");
        assert_eq!(d.canon_ref, None);
        assert!(d.rationale.is_some());
    }

    #[test]
    fn canonical_default_is_deterministic() {
        // AC-5 — same placeholder ⇒ byte-identical classification.
        let p = &fixture_placeholders()[1];
        let a = canonical_default_classification(p);
        let b = canonical_default_classification(p);
        assert_eq!(a.obj_id, b.obj_id);
        assert_eq!(a.canon_kind, b.canon_kind);
        assert_eq!(a.narrative_tag, b.narrative_tag);
    }

    #[test]
    fn canonical_default_classification_passes_validation() {
        // The fallback output must itself be schema-valid (its whole point).
        let placeholders = fixture_placeholders();
        let defaults: Vec<_> = placeholders
            .iter()
            .map(canonical_default_classification)
            .collect();
        let errors = validate_l3(&defaults, &placeholders, &[]);
        assert!(errors.is_empty(), "fallback output failed validation: {errors:?}");
    }

    #[test]
    fn generate_default_tag_is_valid_snake_case() {
        // Even a messy kind/zone string yields an R5-valid narrative_tag.
        let p = L3Placeholder {
            obj_id: "obj_1".into(),
            kind: "Monster Lair!".into(),
            zone_id: "Zone-A".into(),
            suggested_canon_kind: vec!["X".into()],
        };
        let tag = generate_default_tag(&p);
        assert!(is_valid_narrative_tag(&tag), "tag '{tag}' is not valid");
        assert_eq!(tag, "monster_lair__zone_a_default");
    }
}
