//! TMP_008b §11 — closed style enums for L4 narration. Open authoring would
//! require a Forge AdminAction to add a variant (schema-additive per TMP-A8);
//! the closed set stops the LLM emitting unsupported tone/language strings.

use serde::{Deserialize, Serialize};

/// Narrative tone (TMP_008b §11). V2+ extensions are schema-additive.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NarrativeTone {
    Xianxia,
    Wuxia,
    HistFiction,
    Scifi,
    Modern,
    Fantasy,
    UrbanFantasy,
    Horror,
}

impl NarrativeTone {
    /// Stable lowercase tag for the L4 prompt.
    pub fn tag(self) -> &'static str {
        match self {
            Self::Xianxia => "xianxia",
            Self::Wuxia => "wuxia",
            Self::HistFiction => "hist_fiction",
            Self::Scifi => "scifi",
            Self::Modern => "modern",
            Self::Fantasy => "fantasy",
            Self::UrbanFantasy => "urban_fantasy",
            Self::Horror => "horror",
        }
    }
}

/// Narration output language (TMP_008b §11).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NarrationLanguage {
    Vi,
    En,
    Zh,
    Ja,
    Ko,
}

impl NarrationLanguage {
    /// Stable lowercase tag for the L4 prompt + the §4.3 R4 check.
    pub fn tag(self) -> &'static str {
        match self {
            Self::Vi => "vi",
            Self::En => "en",
            Self::Zh => "zh",
            Self::Ja => "ja",
            Self::Ko => "ko",
        }
    }

    /// Whether this language is written in a CJK script — the §4.3 R4
    /// language-detection heuristic checks the CJK-codepoint ratio for these.
    pub fn is_cjk(self) -> bool {
        matches!(self, Self::Zh | Self::Ja | Self::Ko)
    }
}

/// Narration grammatical voice (TMP_008b §11). Default V1+30d: `SecondPerson`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NarrationVoice {
    SecondPerson,
    ThirdPerson,
    Omniscient,
}

impl NarrationVoice {
    /// Stable lowercase tag for the L4 prompt.
    pub fn tag(self) -> &'static str {
        match self {
            Self::SecondPerson => "second_person",
            Self::ThirdPerson => "third_person",
            Self::Omniscient => "omniscient",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tags_are_stable_snake_case() {
        assert_eq!(NarrativeTone::Wuxia.tag(), "wuxia");
        assert_eq!(NarrativeTone::UrbanFantasy.tag(), "urban_fantasy");
        assert_eq!(NarrationLanguage::Vi.tag(), "vi");
        assert_eq!(NarrationVoice::SecondPerson.tag(), "second_person");
    }

    #[test]
    fn cjk_languages_are_flagged() {
        assert!(NarrationLanguage::Zh.is_cjk());
        assert!(NarrationLanguage::Ja.is_cjk());
        assert!(NarrationLanguage::Ko.is_cjk());
        assert!(!NarrationLanguage::Vi.is_cjk());
        assert!(!NarrationLanguage::En.is_cjk());
    }

    #[test]
    fn language_serde_round_trip() {
        let json = serde_json::to_string(&NarrationLanguage::Zh).unwrap();
        assert_eq!(json, "\"zh\"");
        let back: NarrationLanguage = serde_json::from_str(&json).unwrap();
        assert_eq!(back, NarrationLanguage::Zh);
    }
}
