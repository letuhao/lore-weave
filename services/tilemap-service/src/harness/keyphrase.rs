//! TMP_008b §10 — deterministic key-phrase extraction, run post-LLM on an L4
//! narration. V1 cut: frequency rank — no IDF corpus weighting, no KeyBERT
//! (§10 V2+). Deterministic: same narration ⇒ same phrases.

use std::collections::HashMap;

/// Stopwords dropped before ranking — the fixed inline set (spec D6).
const STOPWORDS: &[&str] = &[
    "the", "and", "for", "are", "was", "were", "its", "with", "this", "that",
    "from", "has", "had", "have", "not", "but", "you", "your", "they", "their",
    "them", "she", "her", "his", "him",
];

/// Extract up to `n` key phrases from `narration` (TMP_008b §10, spec D6).
///
/// Split on every non-alphanumeric character (Unicode-aware — accented Latin
/// such as Vietnamese tokenizes correctly), lowercase, drop tokens shorter than
/// 3 chars, all-digit tokens, and stopwords; count term frequency; rank by
/// `(count desc, first-appearance asc)` — a stable sort over first-appearance
/// order gives the tie-break for free. Fully deterministic.
///
/// V1 limitation: CJK text has no word spaces, so a CJK run is not split into
/// meaningful tokens — key-phrase quality for `Zh`/`Ja`/`Ko` is V2 (KeyBERT).
pub fn extract_key_phrases(narration: &str, n: usize) -> Vec<String> {
    // First-appearance order of kept terms + their frequencies.
    let mut order: Vec<String> = Vec::new();
    let mut counts: HashMap<String, usize> = HashMap::new();

    for raw in narration.split(|c: char| !c.is_alphanumeric()) {
        if raw.is_empty() {
            continue;
        }
        let tok = raw.to_lowercase();
        if tok.chars().count() < 3 {
            continue;
        }
        // All-digit tokens (bare numbers like `2026`) are not key phrases.
        if tok.chars().all(|c| c.is_numeric()) {
            continue;
        }
        if STOPWORDS.contains(&tok.as_str()) {
            continue;
        }
        if !counts.contains_key(&tok) {
            order.push(tok.clone());
        }
        *counts.entry(tok).or_insert(0) += 1;
    }

    // Stable sort by descending count — ties keep first-appearance order.
    let mut ranked = order;
    ranked.sort_by(|a, b| counts[b].cmp(&counts[a]));
    ranked.truncate(n);
    ranked
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "The ancient forest grew dark. The forest whispered. \
                          Ancient roots, ancient stone — year 2026.";

    #[test]
    fn ranks_by_frequency_with_first_appearance_tiebreak() {
        // counts: ancient=3, forest=2, then grew/dark/... =1 each.
        let phrases = extract_key_phrases(SAMPLE, 3);
        assert_eq!(phrases, ["ancient", "forest", "grew"]);
    }

    #[test]
    fn count_one_terms_keep_first_appearance_order() {
        // MED-1 — the `(count desc, first-appearance asc)` tie-break: the
        // count-1 tail must follow first-appearance order. A switch to an
        // unstable sort would break this (and pass `is_deterministic`).
        assert_eq!(
            extract_key_phrases(SAMPLE, 8),
            ["ancient", "forest", "grew", "dark", "whispered", "roots", "stone", "year"],
        );
    }

    #[test]
    fn is_deterministic() {
        assert_eq!(
            extract_key_phrases(SAMPLE, 5),
            extract_key_phrases(SAMPLE, 5),
        );
    }

    #[test]
    fn respects_n_and_can_return_fewer() {
        assert_eq!(extract_key_phrases(SAMPLE, 2).len(), 2);
        // "ab cd" — both tokens <3 chars → nothing kept.
        assert!(extract_key_phrases("ab cd", 5).is_empty());
    }

    #[test]
    fn accented_latin_words_survive_tokenization() {
        // Vietnamese (accented Latin) must not be shredded into sub-3-char
        // fragments — the Unicode-aware split keeps `rừng`/`nương` whole.
        let phrases = extract_key_phrases("rừng rừng nương xanh tươi", 3);
        assert!(phrases.contains(&"rừng".to_string()), "got {phrases:?}");
        assert!(phrases.contains(&"nương".to_string()), "got {phrases:?}");
    }

    #[test]
    fn excludes_stopwords_and_bare_digits() {
        let phrases = extract_key_phrases(SAMPLE, 20);
        assert!(!phrases.contains(&"the".to_string()), "stopword leaked");
        assert!(!phrases.contains(&"2026".to_string()), "bare number leaked");
        // a digit-bearing word like `tier3` keeps (it has [a-z]).
        let mixed = extract_key_phrases("tier3 tier3 zone", 5);
        assert!(mixed.contains(&"tier3".to_string()));
    }
}
