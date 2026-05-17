//! L4 narration validation (TMP_008b §4.3 R1-R4), the §6 canonical-default
//! narration fallback, and the subset-retry helpers — mirroring the Phase-2 L3
//! `validate.rs`. Spec D1/D3/D4.

use std::collections::HashSet;

use serde::Deserialize;

use super::l4_prompt::ZoneNarrationInput;
use super::style::NarrationLanguage;

/// One narration parsed from the `submit_zone_narrations` tool-call arguments.
#[derive(Debug, Clone, Deserialize)]
pub struct L4Narration {
    pub zone_id: String,
    pub narration: String,
}

/// The parsed `submit_zone_narrations` argument object.
#[derive(Debug, Clone, Deserialize)]
pub struct L4ToolArguments {
    pub zone_narrations: Vec<L4Narration>,
}

/// A single L4 validation failure (TMP_008b §4.3).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum L4ValidationError {
    /// R1 — an input zone has no narration.
    MissingNarration { zone_id: String },
    /// R1 — an output narration's `zone_id` is not an input zone.
    UnknownZoneId { zone_id: String },
    /// R2 — a `zone_id` appears more than once in the output.
    DuplicateZoneId { zone_id: String },
    /// R3 — narration length outside `50..=2000` chars.
    BadLength { zone_id: String, chars: usize },
    /// R4 — narration script does not match the requested language.
    LanguageMismatch { zone_id: String, requested: String },
}

impl L4ValidationError {
    /// The `zone_id` this error is about — exhaustive `match`, no `_` wildcard
    /// (a future variant lacking a `zone_id` then fails to compile).
    pub fn zone_id(&self) -> &str {
        match self {
            Self::MissingNarration { zone_id }
            | Self::UnknownZoneId { zone_id }
            | Self::DuplicateZoneId { zone_id }
            | Self::BadLength { zone_id, .. }
            | Self::LanguageMismatch { zone_id, .. } => zone_id,
        }
    }

    /// One actionable retry line for [`format_l4_errors_for_retry`].
    fn retry_line(&self) -> String {
        match self {
            Self::MissingNarration { zone_id } => format!(
                "[MISSING-NARRATION] zone_id='{zone_id}' was not narrated. Add a narration."
            ),
            Self::UnknownZoneId { zone_id } => format!(
                "[UNKNOWN-ZONE] zone_id='{zone_id}' is not in this payload. Remove this entry."
            ),
            Self::DuplicateZoneId { zone_id } => format!(
                "[DUPLICATE-ZONE] zone_id='{zone_id}' appears twice. Keep only one entry."
            ),
            Self::BadLength { zone_id, chars } => format!(
                "[BAD-LENGTH] zone_id='{zone_id}': narration is {chars} chars. \
                 It must be 50-2000 characters."
            ),
            Self::LanguageMismatch { zone_id, requested } => format!(
                "[LANGUAGE-MISMATCH] zone_id='{zone_id}': narration is not in the \
                 requested language '{requested}'. Rewrite it in '{requested}'."
            ),
        }
    }
}

/// Narration character-count bounds (TMP_008b §3.3 / §4.3 R3).
const MIN_NARRATION_CHARS: usize = 50;
const MAX_NARRATION_CHARS: usize = 2000;

/// Whether `c` is a CJK-script character (the §4.3 R4 heuristic).
fn is_cjk_char(c: char) -> bool {
    matches!(c as u32,
        0x3400..=0x4DBF   // CJK Unified Ideographs Extension A
        | 0x4E00..=0x9FFF // CJK Unified Ideographs
        | 0x3040..=0x309F // Hiragana
        | 0x30A0..=0x30FF // Katakana
        | 0x1100..=0x11FF // Hangul Jamo
        | 0x3130..=0x318F // Hangul Compatibility Jamo
        | 0xAC00..=0xD7AF // Hangul Syllables
    )
}

/// §4.3 R4 — a confident script mismatch between `narration` and `language`.
/// A narration with too few alphabetic chars to classify is NOT flagged (R3
/// length already covers degenerate text).
fn language_mismatch(narration: &str, language: NarrationLanguage) -> bool {
    let alpha = narration.chars().filter(|c| c.is_alphabetic()).count();
    if alpha < 10 {
        return false;
    }
    let cjk = narration.chars().filter(|&c| is_cjk_char(c)).count();
    let cjk_ratio = cjk as f64 / alpha as f64;
    // A dead-band — flag only a *confident* script mismatch (spec R-B), so a
    // Latin narration that legitimately quotes a minority CJK passage (or vice
    // versa) is not false-flagged into an unnecessary retry / fallback.
    if language.is_cjk() {
        cjk_ratio < 0.15 // a CJK language but the text is barely CJK
    } else {
        cjk_ratio > 0.85 // a Latin-script language but the text is mostly CJK
    }
}

/// Run TMP_008b §4.3 rules R1-R4 against a parsed L4 response.
pub fn validate_l4(
    narrations: &[L4Narration],
    inputs: &[ZoneNarrationInput],
    language: NarrationLanguage,
) -> Vec<L4ValidationError> {
    let mut errors = Vec::new();

    let input_ids: HashSet<&str> = inputs.iter().map(|i| i.zone_id.as_str()).collect();
    let output_ids: HashSet<&str> = narrations.iter().map(|n| n.zone_id.as_str()).collect();

    // R1 — every input zone narrated; no unknown output zone.
    for i in inputs {
        if !output_ids.contains(i.zone_id.as_str()) {
            errors.push(L4ValidationError::MissingNarration {
                zone_id: i.zone_id.clone(),
            });
        }
    }
    for n in narrations {
        if !input_ids.contains(n.zone_id.as_str()) {
            errors.push(L4ValidationError::UnknownZoneId {
                zone_id: n.zone_id.clone(),
            });
        }
    }

    // R2 — no duplicate zone_id.
    let mut seen: HashSet<&str> = HashSet::new();
    for n in narrations {
        if !seen.insert(n.zone_id.as_str()) {
            errors.push(L4ValidationError::DuplicateZoneId {
                zone_id: n.zone_id.clone(),
            });
        }
    }

    let mut content_checked: HashSet<&str> = HashSet::new();
    for n in narrations {
        // A duplicate zone_id is already flagged by R2; validate content
        // (R3/R4) against the first occurrence only — a repeat would emit
        // duplicate, self-contradictory retry lines.
        if !content_checked.insert(n.zone_id.as_str()) {
            continue;
        }
        // R3 — length 50..=2000 chars.
        let chars = n.narration.chars().count();
        if !(MIN_NARRATION_CHARS..=MAX_NARRATION_CHARS).contains(&chars) {
            errors.push(L4ValidationError::BadLength {
                zone_id: n.zone_id.clone(),
                chars,
            });
        }
        // R4 — language match (heuristic).
        if language_mismatch(&n.narration, language) {
            errors.push(L4ValidationError::LanguageMismatch {
                zone_id: n.zone_id.clone(),
                requested: language.tag().to_string(),
            });
        }
    }

    errors
}

/// TMP_008b §4.2-analogue retry message for L4 (spec D1). Empty error slice →
/// `""`; non-empty → the reframed subset-retry preamble as the first line, a
/// blank line, then one `[TAG] …` line per error.
pub fn format_l4_errors_for_retry(errors: &[L4ValidationError]) -> String {
    if errors.is_empty() {
        return String::new();
    }
    let mut msg = String::from(
        "Your previous narration of the zones below failed validation. \
         Previously-valid narrations are already saved — re-narrate ONLY the \
         zones in this payload.\n\n",
    );
    for err in errors {
        msg.push_str(&err.retry_line());
        msg.push('\n');
    }
    msg
}

/// Split an L4 response into accepted narrations + validation errors, validated
/// against the requested `subset` (spec D1/D3). A narration is accepted iff its
/// `zone_id` is in `subset` AND no error names it — an out-of-subset narration
/// is never accepted, so it cannot overwrite a previously-saved narration.
pub fn partition_l4_response(
    subset: &[ZoneNarrationInput],
    response: &[L4Narration],
    language: NarrationLanguage,
) -> (Vec<L4Narration>, Vec<L4ValidationError>) {
    let errors = validate_l4(response, subset, language);
    let failed: HashSet<&str> = errors.iter().map(|e| e.zone_id()).collect();
    let subset_ids: HashSet<&str> = subset.iter().map(|i| i.zone_id.as_str()).collect();
    let accepted = response
        .iter()
        .filter(|n| {
            subset_ids.contains(n.zone_id.as_str()) && !failed.contains(n.zone_id.as_str())
        })
        .cloned()
        .collect();
    (accepted, errors)
}

/// TMP_008b §6 — the deterministic terminal fallback for a zone the LLM never
/// narrated validly. A fixed ~100-char template, so it is always ≥50 chars
/// (R3 lower bound holds by construction); truncated to 2000 chars for the
/// upper bound. NOT re-validated — it is the terminal "always playable" answer.
pub fn canonical_default_narration(input: &ZoneNarrationInput) -> L4Narration {
    let text = format!(
        "The region known as {} stretches across {} terrain. Its tale awaits \
         the telling. (Engine-default narration.)",
        input.zone_id, input.terrain,
    );
    L4Narration {
        zone_id: input.zone_id.clone(),
        narration: text.chars().take(MAX_NARRATION_CHARS).collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn zone(id: &str) -> ZoneNarrationInput {
        ZoneNarrationInput {
            zone_id: id.to_string(),
            terrain: "forest".to_string(),
            l3_objects: vec![],
        }
    }

    fn narr(id: &str, text: &str) -> L4Narration {
        L4Narration {
            zone_id: id.to_string(),
            narration: text.to_string(),
        }
    }

    /// A valid-length (≥50-char) English narration.
    fn good_text() -> String {
        "You step into a still forest where old pines crowd the narrow path.".to_string()
    }

    #[test]
    fn clean_response_has_no_errors() {
        let inputs = [zone("a"), zone("b")];
        let response = [narr("a", &good_text()), narr("b", &good_text())];
        let errors = validate_l4(&response, &inputs, NarrationLanguage::En);
        assert!(errors.is_empty(), "errors = {errors:?}");
    }

    #[test]
    fn flags_missing_unknown_duplicate_badlength() {
        let inputs = [zone("a"), zone("b"), zone("c")];
        let response = [
            narr("a", &good_text()),
            narr("a", &good_text()), // duplicate of a
            narr("z", &good_text()), // unknown zone z
            narr("c", "too short"),  // c's only narration — R3 BadLength
            // b missing entirely
        ];
        let errors = validate_l4(&response, &inputs, NarrationLanguage::En);
        assert!(errors.contains(&L4ValidationError::MissingNarration { zone_id: "b".into() }));
        assert!(errors.contains(&L4ValidationError::UnknownZoneId { zone_id: "z".into() }));
        assert!(errors.contains(&L4ValidationError::DuplicateZoneId { zone_id: "a".into() }));
        assert!(
            errors.iter().any(|e| matches!(
                e, L4ValidationError::BadLength { zone_id, .. } if zone_id == "c"
            )),
            "c's short narration must flag BadLength",
        );
    }

    #[test]
    fn duplicate_zone_content_rules_are_not_double_flagged() {
        // HIGH-2 — a zone repeated with a bad-length narration yields exactly
        // ONE BadLength (first occurrence) + ONE DuplicateZoneId, never two
        // BadLength lines (which would be self-contradictory retry context).
        let inputs = [zone("a")];
        let response = [narr("a", "short"), narr("a", "short")];
        let errors = validate_l4(&response, &inputs, NarrationLanguage::En);
        assert_eq!(
            errors.iter().filter(|e| matches!(e, L4ValidationError::BadLength { .. })).count(),
            1,
            "content rules run once per zone, not per occurrence",
        );
        assert_eq!(
            errors.iter().filter(|e| matches!(e, L4ValidationError::DuplicateZoneId { .. })).count(),
            1,
        );
    }

    #[test]
    fn mixed_script_does_not_false_flag_r4() {
        // MED-2 — a mostly-English narration quoting a short CJK passage is
        // within the R4 dead-band, so it is NOT flagged for an `En` reality.
        let inputs = [zone("a")];
        let text = "You enter the old hall where a faded couplet hangs: 月明 — \
                    and the lanterns sway over a long and quiet wooden floor.";
        let response = [narr("a", text)];
        let errors = validate_l4(&response, &inputs, NarrationLanguage::En);
        assert!(
            !errors.iter().any(|e| matches!(e, L4ValidationError::LanguageMismatch { .. })),
            "a minority CJK quote must not false-flag an English narration",
        );
    }

    #[test]
    fn flags_language_mismatch() {
        // An English narration requested as Chinese → R4 mismatch.
        let inputs = [zone("a")];
        let response = [narr("a", &good_text())];
        let errors = validate_l4(&response, &inputs, NarrationLanguage::Zh);
        assert!(errors.iter().any(|e| matches!(
            e,
            L4ValidationError::LanguageMismatch { zone_id, .. } if zone_id == "a"
        )));
        // ...and no mismatch when English is requested.
        assert!(validate_l4(&response, &inputs, NarrationLanguage::En).is_empty());
    }

    #[test]
    fn format_l4_errors_empty_is_empty_string() {
        assert_eq!(format_l4_errors_for_retry(&[]), "");
    }

    #[test]
    fn format_l4_errors_first_line_is_the_preamble() {
        let errors = vec![L4ValidationError::MissingNarration { zone_id: "b".into() }];
        let msg = format_l4_errors_for_retry(&errors);
        let first = msg.lines().next().unwrap();
        assert!(first.contains("failed validation"), "first line not the preamble: {first}");
        assert!(!first.contains("[MISSING"), "first line must be the preamble");
        assert!(msg.contains("[MISSING-NARRATION] zone_id='b'"));
    }

    #[test]
    fn partition_narrows_to_the_failing_subset() {
        let subset = [zone("a"), zone("b")];
        let response = [narr("a", &good_text()), narr("b", "short")];
        let (accepted, errors) = partition_l4_response(&subset, &response, NarrationLanguage::En);
        let ids: Vec<&str> = accepted.iter().map(|n| n.zone_id.as_str()).collect();
        assert_eq!(ids, ["a"], "only the valid zone is accepted");
        assert!(!errors.is_empty());
    }

    #[test]
    fn partition_ignores_out_of_subset_narrations() {
        // The accept side rejects an out-of-subset zone — a later attempt
        // re-emitting an already-accepted zone cannot overwrite saved work.
        let subset = [zone("a")];
        let response = [
            narr("a", &good_text()),
            narr("b", &good_text()), // 'b' is not in the subset
        ];
        let (accepted, _errors) = partition_l4_response(&subset, &response, NarrationLanguage::En);
        let ids: Vec<&str> = accepted.iter().map(|n| n.zone_id.as_str()).collect();
        assert_eq!(ids, ["a"], "out-of-subset zone 'b' must not be accepted");
    }

    #[test]
    fn canonical_default_is_deterministic_and_r3_valid_for_shortest_zone_id() {
        // AC-5 — a 1-char zone_id still yields a ≥50-char narration.
        let input = ZoneNarrationInput {
            zone_id: "z".to_string(),
            terrain: String::new(),
            l3_objects: vec![],
        };
        let a = canonical_default_narration(&input);
        let b = canonical_default_narration(&input);
        assert_eq!(a.narration, b.narration);
        assert_eq!(a.zone_id, "z");
        let chars = a.narration.chars().count();
        assert!((MIN_NARRATION_CHARS..=MAX_NARRATION_CHARS).contains(&chars), "len {chars}");
    }
}
