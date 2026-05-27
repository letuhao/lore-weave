//! TMP_005 §2 — the biome type family. A [`BiomeSet`] groups visually-consistent
//! obstacle templates; [`BiomeSelectionRules`] parameterizes how `ObstaclePlacer`
//! picks biomes per zone (Phase B).
//!
//! V1+30d cut: `factions` / `alignments` on a [`BiomeSet`] are schema-reserved —
//! the engine library leaves both empty, so the §4.1 filter passes every zone.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

use crate::types::object_template::TilemapObjectTemplate;
use crate::types::tile::TerrainKind;

/// Stable biome identifier (e.g. `"grassland_pines"`).
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct BiomeId(pub String);

/// TMP_005 §2.1 — the 9 obstacle-object kinds. `Ord` so it can key the
/// deterministic [`BiomeSelection`] map.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BiomeObjectType {
    Mountain,
    Tree,
    Lake,
    Crater,
    Rock,
    Plant,
    Structure,
    Animal,
    Other,
}

/// TMP_005 §2.1 — which map level a biome may spawn on. V1+30d: all `Surface`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BiomeLevel {
    Surface,
    Underground,
    Both,
}

/// TMP_005 §2.1 — V2+ alignment scoping. V1+30d: schema-reserved, unused.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Alignment {
    Good,
    Neutral,
    Evil,
}

/// TMP_005 §2.2 — selection priority band. `First` picks before `Normal` before
/// `Last`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BiomePriority {
    First,
    Normal,
    Last,
}

/// TMP_005 §2.1 — a group of visually-consistent obstacle templates that share
/// a terrain + object-type + level scope.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BiomeSet {
    pub biome_id: BiomeId,
    /// Terrains this biome may spawn on.
    pub terrain_types: BTreeSet<TerrainKind>,
    pub level: BiomeLevel,
    /// V2+ faction scoping (faction id strings). V1+30d: empty ⇒ all factions
    /// pass the §4.1 filter.
    #[serde(default)]
    pub factions: BTreeSet<String>,
    /// V2+ alignment scoping. V1+30d: empty ⇒ all alignments pass.
    #[serde(default)]
    pub alignments: BTreeSet<Alignment>,
    pub object_type: BiomeObjectType,
    /// 4-10 visually-consistent object templates (TMP_005 §2.1).
    pub templates: Vec<TilemapObjectTemplate>,
}

/// TMP_005 §2.2 — author-tunable biome-selection rules. `use_engine_default`
/// true ⇒ ignore `rules`, use the engine defaults.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BiomeSelectionRules {
    pub use_engine_default: bool,
    #[serde(default)]
    pub rules: Vec<BiomeSelectionRule>,
}

/// TMP_005 §2.2 — one ordered selection rule: pick `count_min..=count_max` sets
/// of `object_type`, in `priority` order, optionally `xor_with` a paired type.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BiomeSelectionRule {
    pub object_type: BiomeObjectType,
    pub count_min: u8,
    pub count_max: u8,
    /// Pick this type XOR the paired type (e.g. `Lake` xor `Crater`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub xor_with: Option<BiomeObjectType>,
    pub priority: BiomePriority,
}

/// The per-zone biome-selection result — selected `BiomeId`s grouped by
/// `BiomeObjectType` (TMP_005 §4.1). `BTreeMap` for deterministic iteration.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct BiomeSelection {
    pub by_type: BTreeMap<BiomeObjectType, Vec<BiomeId>>,
}

impl BiomeSelection {
    /// The biomes selected for `object_type` (empty slice if none).
    pub fn of_type(&self, object_type: BiomeObjectType) -> &[BiomeId] {
        self.by_type.get(&object_type).map_or(&[], Vec::as_slice)
    }

    /// Record `biome` under `object_type`.
    pub fn push(&mut self, object_type: BiomeObjectType, biome: BiomeId) {
        self.by_type.entry(object_type).or_default().push(biome);
    }

    /// Whether any biome of any type was selected.
    pub fn is_empty(&self) -> bool {
        self.by_type.values().all(Vec::is_empty)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn biome_selection_groups_by_object_type() {
        let mut sel = BiomeSelection::default();
        assert!(sel.is_empty());
        sel.push(BiomeObjectType::Tree, BiomeId("oak_pine".to_string()));
        sel.push(BiomeObjectType::Tree, BiomeId("bamboo".to_string()));
        sel.push(BiomeObjectType::Rock, BiomeId("granite".to_string()));
        assert!(!sel.is_empty());
        assert_eq!(sel.of_type(BiomeObjectType::Tree).len(), 2);
        assert_eq!(sel.of_type(BiomeObjectType::Rock).len(), 1);
        assert!(sel.of_type(BiomeObjectType::Mountain).is_empty());
    }

    #[test]
    fn biome_set_serde_round_trip() {
        let set = BiomeSet {
            biome_id: BiomeId("grassland_pines".to_string()),
            terrain_types: BTreeSet::from([TerrainKind::Grass]),
            level: BiomeLevel::Surface,
            factions: BTreeSet::new(),
            alignments: BTreeSet::new(),
            object_type: BiomeObjectType::Tree,
            templates: vec![],
        };
        let back: BiomeSet = serde_json::from_str(&serde_json::to_string(&set).unwrap()).unwrap();
        assert_eq!(set, back);
    }

    #[test]
    fn biome_selection_rules_serde_round_trip() {
        // AC-8 — `BiomeSelectionRules` / `BiomeSelectionRule` survive JSON,
        // including both the `Some` and `None` cases of `xor_with` (which
        // carries `#[serde(default, skip_serializing_if = "Option::is_none")]`).
        let rules = BiomeSelectionRules {
            use_engine_default: false,
            rules: vec![
                BiomeSelectionRule {
                    object_type: BiomeObjectType::Lake,
                    count_min: 0,
                    count_max: 1,
                    xor_with: Some(BiomeObjectType::Crater),
                    priority: BiomePriority::First,
                },
                BiomeSelectionRule {
                    object_type: BiomeObjectType::Tree,
                    count_min: 1,
                    count_max: 2,
                    xor_with: None,
                    priority: BiomePriority::Normal,
                },
            ],
        };
        let back: BiomeSelectionRules =
            serde_json::from_str(&serde_json::to_string(&rules).unwrap()).unwrap();
        assert_eq!(rules, back);
        // The `use_engine_default: true` shape (empty `rules`) also round-trips.
        let defaulted = BiomeSelectionRules { use_engine_default: true, rules: vec![] };
        let back2: BiomeSelectionRules =
            serde_json::from_str(&serde_json::to_string(&defaulted).unwrap()).unwrap();
        assert_eq!(defaulted, back2);
    }
}
