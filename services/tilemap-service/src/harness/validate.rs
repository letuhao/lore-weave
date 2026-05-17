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
}
