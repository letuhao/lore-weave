//! Engine-object bootstrap — runs the placement engine on a small reality,
//! drives the engine's **own placed objects** through the L3 retry loop, then
//! narrates the placed zones through the L4 retry loop (TMP_008b §5/§6).
//!
//! The objects are `place_tilemap`'s `object_placements` — treasures, guards,
//! monoliths, obstacles, ferries — the genuine engine→L3→L4 flow. Every placed
//! object kind is classified (including biome `Obstacle`s); each maps to an L3
//! `kind` label + a closed `suggested_canon_kind` set.

use std::collections::HashMap;

use loreweave_llm::{GatewayClient, ModelSource};
use uuid::Uuid;

use crate::engine::place_tilemap;
use crate::seed::derive_seed;
use crate::types::biome::BiomeObjectType;
use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::object::TilemapObjectKind;
use crate::types::template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
use crate::types::tilemap::{GridSize, TilemapView};
use crate::types::treasure::TreasureTierSpec;
use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

use super::keyphrase::extract_key_phrases;
use super::l4_prompt::ZoneNarrationInput;
use super::l4_retry::{L4Result, run_l4_with_retries};
use super::prompt::L3Placeholder;
use super::retry::{L3Result, run_l3_with_retries};
use super::style::{NarrationLanguage, NarrationVoice, NarrativeTone};

/// Result of [`bootstrap_small_reality`] — the placed tilemap, the L3
/// classification of the engine-placed objects, and the L4 zone narration.
#[derive(Debug)]
pub struct BootstrapReport {
    pub tilemap: TilemapView,
    pub l3: L3Result,
    pub l4: L4Result,
}

/// Run the small-reality bootstrap: place a 4-zone wuxia template via the
/// engine, then classify its **engine-placed** object set through the §5 retry
/// loop. `max_attempts` is the §5 per-batch retry cap (TMP-LLM-C-Q3: 3).
pub async fn bootstrap_small_reality(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    max_attempts: u32,
) -> crate::Result<BootstrapReport> {
    let template = bootstrap_template();
    let seed = derive_seed(
        "bootstrap_reality",
        "bootstrap_channel",
        &template.template_id.0,
        template.seed_offset,
    );
    let tilemap = place_tilemap(
        &template,
        ChannelId("bootstrap_channel".to_string()),
        ChannelTier::Country,
        GridSize { width: 48, height: 48 },
        seed,
    )?;

    // The L3 input is the engine's own placed objects (TMP_006/007/Phase E
    // output) — no fixture set.
    let placeholders = engine_placeholders(&tilemap);
    let book_canon_refs = vec![
        "lotus_sect_homeland_v1".to_string(),
        "western_forest_lore_v1".to_string(),
    ];
    let l3 = run_l3_with_retries(
        client,
        model_source,
        model_ref,
        user_id,
        &placeholders,
        &book_canon_refs,
        max_attempts,
    )
    .await?;

    let l4_inputs = build_l4_inputs(&tilemap, &placeholders, &l3);
    let l4 = run_l4_with_retries(
        client,
        model_source,
        model_ref,
        user_id,
        &l4_inputs,
        NarrationLanguage::En,
        NarrativeTone::Wuxia,
        NarrationVoice::SecondPerson,
        max_attempts,
    )
    .await?;

    Ok(BootstrapReport { tilemap, l3, l4 })
}

/// The L3 `kind` label for a placed-object kind — the PascalCase variant name.
/// Exhaustive `match` (no wildcard): a new `TilemapObjectKind` variant forces a
/// compile error here.
fn kind_label(kind: TilemapObjectKind) -> &'static str {
    match kind {
        TilemapObjectKind::Treasure => "Treasure",
        TilemapObjectKind::MonsterLair => "MonsterLair",
        TilemapObjectKind::Town => "Town",
        TilemapObjectKind::Mine => "Mine",
        TilemapObjectKind::Landmark => "Landmark",
        TilemapObjectKind::Monolith => "Monolith",
        TilemapObjectKind::Decoration => "Decoration",
        TilemapObjectKind::Obstacle => "Obstacle",
        TilemapObjectKind::Ferry => "Ferry",
    }
}

/// The closed `suggested_canon_kind` set the L3 classifier must pick from for a
/// given placed-object kind — **index 0 is the engine default** (the TMP_008b
/// §6 canonical-default fallback). Wuxia-flavoured to match the bootstrap
/// reality. For `Obstacle` this is the generic fallback list — a *tagged*
/// obstacle is routed through [`obstacle_suggestions`] instead (see
/// [`engine_placeholders`]).
fn suggested_canon_kind(kind: TilemapObjectKind) -> &'static [&'static str] {
    match kind {
        TilemapObjectKind::Treasure => &["BanditCache", "AbandonedCellar", "OldShrine"],
        TilemapObjectKind::MonsterLair => &["BanditCamp", "WolfDen", "ElvenWatcher"],
        TilemapObjectKind::Monolith => &["AncientWaygate", "JadePortalStone", "SpiritGate"],
        TilemapObjectKind::Obstacle => &["RockOutcrop", "TangledThicket", "FallenTimber"],
        TilemapObjectKind::Ferry => &["RiverFerry", "RopeBridgeCrossing", "FerrymanDock"],
        TilemapObjectKind::Landmark => &["AncientTree", "RuinedWell", "RobberShrine"],
        TilemapObjectKind::Town => &["MarketTown", "WalledCity", "TradingPost"],
        TilemapObjectKind::Mine => &["IronMine", "JadeQuarry", "SaltMine"],
        TilemapObjectKind::Decoration => &["WildFlowers", "MossyStones", "Brambles"],
    }
}

/// The closed `suggested_canon_kind` set for an `Obstacle`, keyed by its
/// `biome_object_type` (TMP_005 §2.1) — a mountain, a lake, and a tree get
/// distinct, biome-appropriate canonical kinds instead of one generic list, so
/// an L3 classification (and the §6 default, index 0) is semantically honest.
/// An untagged obstacle (`None` — engine obstacles are always tagged, so this
/// is defensive) falls back to the generic `Obstacle` list.
fn obstacle_suggestions(biome: Option<BiomeObjectType>) -> &'static [&'static str] {
    match biome {
        Some(BiomeObjectType::Mountain) => &["CraggyPeak", "JaggedRidge", "StoneSummit"],
        Some(BiomeObjectType::Tree) => &["AncientGrove", "GnarledPine", "ShadedCopse"],
        Some(BiomeObjectType::Lake) => &["StillTarn", "ReedyMere", "MistPool"],
        Some(BiomeObjectType::Crater) => &["ScorchedHollow", "MeteorScar", "SunkenPit"],
        Some(BiomeObjectType::Rock) => &["RockOutcrop", "BoulderField", "ShatteredScree"],
        Some(BiomeObjectType::Plant) => &["TangledThicket", "BrambleSnarl", "ThornBrake"],
        Some(BiomeObjectType::Structure) => &["RuinedWall", "TumbledShrine", "OldWatchpost"],
        Some(BiomeObjectType::Animal) => &["BeastTrail", "GrazingHerd", "PredatorRange"],
        Some(BiomeObjectType::Other) => &["StrangeFormation", "UnmarkedSite", "OddTerrain"],
        None => suggested_canon_kind(TilemapObjectKind::Obstacle),
    }
}

/// Derive the L3 placeholder set from the engine's own `object_placements` —
/// the genuine engine→L3 object flow. `obj_id`s are `obj_{i}` (1-based,
/// contiguous, matching the tool schema's `^obj_[0-9]+$`); `zone_id` is the
/// zone owning the object's `anchor`; suggestions are the per-kind closed set —
/// or, for an `Obstacle`, the per-`biome_object_type` set.
///
/// An object whose `anchor` lies in no zone (impossible — zones partition the
/// grid) is skipped defensively rather than panicking.
///
/// `pub(super)` — the continent measurement harness reuses it.
pub(super) fn engine_placeholders(tilemap: &TilemapView) -> Vec<L3Placeholder> {
    tilemap
        .object_placements
        .iter()
        .filter_map(|p| {
            let zone = tilemap.zones.iter().find(|z| z.assigned_tiles.get(p.anchor))?;
            Some((p, zone.zone_id.0.as_str()))
        })
        .enumerate()
        .map(|(i, (p, zone_id))| {
            let obj_id = format!("obj_{}", i + 1);
            let suggested = match p.kind {
                TilemapObjectKind::Obstacle => obstacle_suggestions(p.biome_object_type),
                other => suggested_canon_kind(other),
            };
            L3Placeholder::new(&obj_id, kind_label(p.kind), zone_id, suggested)
        })
        .collect()
}

/// Build the L4 zone-narration inputs from the placed zones + the L3 result
/// (spec D7): `terrain` from each `ZoneRuntime` (always populated), `l3_objects`
/// recovered by joining each `L3Classification.obj_id` back to its
/// `L3Placeholder.zone_id`. `pub(super)` — reused by the continent harness.
pub(super) fn build_l4_inputs(
    tilemap: &TilemapView,
    placeholders: &[L3Placeholder],
    l3: &L3Result,
) -> Vec<ZoneNarrationInput> {
    let obj_zone: HashMap<&str, &str> = placeholders
        .iter()
        .map(|p| (p.obj_id.as_str(), p.zone_id.as_str()))
        .collect();
    let mut objects_by_zone: HashMap<&str, Vec<String>> = HashMap::new();
    for c in &l3.classifications {
        if let Some(&zid) = obj_zone.get(c.obj_id.as_str()) {
            objects_by_zone.entry(zid).or_default().push(c.canon_kind.clone());
        }
    }
    tilemap
        .zones
        .iter()
        .map(|z| ZoneNarrationInput {
            zone_id: z.zone_id.0.clone(),
            terrain: z.terrain_type.tag().to_string(),
            l3_objects: objects_by_zone
                .get(z.zone_id.0.as_str())
                .cloned()
                .unwrap_or_default(),
        })
        .collect()
}

/// The 4-zone wuxia reality the bootstrap places. The two `Wilderness` zones
/// carry a `min ≥ 2000` treasure tier (so `TreasurePlacer` emits `Treasure`
/// piles + their `MonsterLair` guards), and a `Portal` connection reaches a
/// `Forbidden` vault (so `ConnectionsPlacer` places a `Monolith` pair) — the
/// engine then also fills biome `Obstacle`s. The result is a varied,
/// multi-kind object set for the L3 demo.
fn bootstrap_template() -> TilemapTemplate {
    fn zone(id: &str, role: ZoneRole, conns: &[(&str, PassageKind)]) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: role,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns
                .iter()
                .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
                .collect(),
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
        }
    }
    let mut template = TilemapTemplate {
        template_id: TilemapTemplateId("bootstrap_wuxia_v1".to_string()),
        zones: vec![
            zone(
                "jianghu_capital",
                ZoneRole::Hub,
                &[
                    ("western_wilds", PassageKind::Threshold),
                    ("forbidden_vault", PassageKind::Portal),
                ],
            ),
            zone(
                "western_wilds",
                ZoneRole::Wilderness,
                &[("lotus_grove", PassageKind::Open)],
            ),
            zone("lotus_grove", ZoneRole::Wilderness, &[]),
            zone("forbidden_vault", ZoneRole::Forbidden, &[]),
        ],
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
    };
    // TreasurePlacer only acts on zones with `treasure_tiers`; a `min ≥ 2000`
    // tier guarantees each pile is guarded, so the demo classifies Treasure
    // piles *and* MonsterLair guards.
    for z in &mut template.zones {
        if z.zone_role == ZoneRole::Wilderness {
            z.treasure_tiers = vec![TreasureTierSpec { min: 2000, max: 6000, density: 4 }];
        }
    }
    template
}

/// Render a [`BootstrapReport`] as a human-readable block for the CLI.
pub fn render_bootstrap_report(r: &BootstrapReport) -> String {
    let mut s = String::from("── small-reality bootstrap (L3 → L4) ────────────────────\n");
    s.push_str(&format!(
        "placement : {} zones, {}×{} grid, {} object(s) placed\n",
        r.tilemap.zones.len(),
        r.tilemap.grid_size.width,
        r.tilemap.grid_size.height,
        r.tilemap.object_placements.len(),
    ));
    s.push_str(&format!(
        "L3 loop   : {} object(s), {} gateway attempt(s), {} canonical-default fallback(s)\n",
        r.l3.classifications.len(),
        r.l3.llm_attempts,
        r.l3.fallback_count,
    ));
    let mut classifications = r.l3.classifications.clone();
    classifications.sort_by(|a, b| a.obj_id.cmp(&b.obj_id));
    for c in &classifications {
        s.push_str(&format!(
            "  {}: canon_kind={} tag={}\n",
            c.obj_id, c.canon_kind, c.narrative_tag,
        ));
    }
    s.push_str(&format!(
        "L4 loop   : {} narration(s), {} gateway attempt(s), {} canonical-default fallback(s)\n",
        r.l4.narrations.len(),
        r.l4.llm_attempts,
        r.l4.fallback_count,
    ));
    let mut narrations = r.l4.narrations.clone();
    narrations.sort_by(|a, b| a.zone_id.cmp(&b.zone_id));
    for n in &narrations {
        // §10 deterministic key-phrase extraction over each narration.
        let phrases = extract_key_phrases(&n.narration, 5);
        s.push_str(&format!(
            "  {}: {} chars, key_phrases=[{}]\n",
            n.zone_id,
            n.narration.chars().count(),
            phrases.join(", "),
        ));
    }
    s.push_str("─────────────────────────────────────────────────────────\n");
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::seed::TilemapSeed;

    /// Place the bootstrap reality at a fixed seed.
    fn placed() -> TilemapView {
        place_tilemap(
            &bootstrap_template(),
            ChannelId("bootstrap_test".to_string()),
            ChannelTier::Country,
            GridSize { width: 48, height: 48 },
            TilemapSeed(0xB00757),
        )
        .expect("the bootstrap template must place")
    }

    /// All nine `TilemapObjectKind` variants.
    const ALL_KINDS: [TilemapObjectKind; 9] = [
        TilemapObjectKind::Treasure,
        TilemapObjectKind::MonsterLair,
        TilemapObjectKind::Town,
        TilemapObjectKind::Mine,
        TilemapObjectKind::Landmark,
        TilemapObjectKind::Monolith,
        TilemapObjectKind::Decoration,
        TilemapObjectKind::Obstacle,
        TilemapObjectKind::Ferry,
    ];

    /// All nine `BiomeObjectType` variants.
    const ALL_BIOME_TYPES: [BiomeObjectType; 9] = [
        BiomeObjectType::Mountain,
        BiomeObjectType::Tree,
        BiomeObjectType::Lake,
        BiomeObjectType::Crater,
        BiomeObjectType::Rock,
        BiomeObjectType::Plant,
        BiomeObjectType::Structure,
        BiomeObjectType::Animal,
        BiomeObjectType::Other,
    ];

    #[test]
    fn every_object_kind_maps_to_a_label_and_suggestions() {
        // AC-2 — every kind (incl. Obstacle) has a label + non-empty closed set.
        for kind in ALL_KINDS {
            assert!(!kind_label(kind).is_empty(), "{kind:?} has no label");
            assert!(
                !suggested_canon_kind(kind).is_empty(),
                "{kind:?} has no suggested_canon_kind",
            );
        }
    }

    #[test]
    fn obstacle_suggestions_total_over_all_biome_types() {
        // AC-8 — every BiomeObjectType (and the untagged None case) maps to a
        // non-empty obstacle suggestion list.
        assert!(!obstacle_suggestions(None).is_empty(), "untagged obstacle has no suggestions");
        for biome in ALL_BIOME_TYPES {
            assert!(
                !obstacle_suggestions(Some(biome)).is_empty(),
                "{biome:?} has no obstacle suggestions",
            );
        }
    }

    #[test]
    fn obstacle_suggestions_are_distinct_per_biome_type() {
        // AC-8 — a mountain, a lake, and a tree get *different* suggestion
        // lists (the biome routing is real, not a single generic list).
        let mountain = obstacle_suggestions(Some(BiomeObjectType::Mountain));
        let lake = obstacle_suggestions(Some(BiomeObjectType::Lake));
        let tree = obstacle_suggestions(Some(BiomeObjectType::Tree));
        assert_ne!(mountain, lake, "mountain and lake share a suggestion list");
        assert_ne!(mountain, tree, "mountain and tree share a suggestion list");
        assert_ne!(lake, tree, "lake and tree share a suggestion list");
    }

    #[test]
    fn engine_placeholders_are_well_formed_and_zone_resolved() {
        // AC-1/AC-3/AC-4 — placeholders derive from object_placements; obj_ids
        // contiguous 1-based and well-formed; zone_id is a real placed zone.
        let tilemap = placed();
        let phs = engine_placeholders(&tilemap);
        assert!(!phs.is_empty(), "the enriched template must place objects");

        let zone_ids: Vec<&str> = tilemap.zones.iter().map(|z| z.zone_id.0.as_str()).collect();
        for (i, p) in phs.iter().enumerate() {
            assert_eq!(p.obj_id, format!("obj_{}", i + 1), "obj_id must be contiguous 1-based");
            assert!(
                p.obj_id.starts_with("obj_")
                    && p.obj_id["obj_".len()..].chars().all(|c| c.is_ascii_digit()),
                "obj_id '{}' does not match ^obj_[0-9]+$",
                p.obj_id,
            );
            assert!(
                zone_ids.contains(&p.zone_id.as_str()),
                "placeholder {} references unknown zone {}",
                p.obj_id,
                p.zone_id,
            );
            assert!(!p.kind.is_empty(), "{} has an empty kind label", p.obj_id);
            assert!(!p.suggested_canon_kind.is_empty(), "{} has no suggestions", p.obj_id);
        }
    }

    #[test]
    fn engine_placeholder_zone_matches_the_objects_anchor_owner() {
        // AC-3 — each placeholder's zone_id is the zone whose assigned_tiles
        // contains the placed object's anchor, in object_placements order.
        let tilemap = placed();
        let phs = engine_placeholders(&tilemap);
        // engine_placeholders skips no object here (every anchor is zoned), so
        // the placeholder list is index-aligned with object_placements.
        assert_eq!(phs.len(), tilemap.object_placements.len());
        for (p, placement) in phs.iter().zip(&tilemap.object_placements) {
            let owner = tilemap
                .zones
                .iter()
                .find(|z| z.assigned_tiles.get(placement.anchor))
                .expect("every placed object's anchor lies in a zone");
            assert_eq!(p.zone_id, owner.zone_id.0, "{} zone mismatch", p.obj_id);
            assert_eq!(p.kind, kind_label(placement.kind), "{} kind mismatch", p.obj_id);
        }
    }

    #[test]
    fn obstacle_placeholders_carry_biome_keyed_suggestions() {
        // AC-8 — on real engine output, each Obstacle placeholder's suggestion
        // list is keyed to that obstacle's biome_object_type, and ObstaclePlacer
        // reliably emits a Mountain (its §2.3 count-1 rule) so the mountain list
        // is genuinely exercised.
        let tilemap = placed();
        let phs = engine_placeholders(&tilemap);
        // `Vec<String>` vs the `&[&str]` literal lists — compare as &str.
        let same = |got: &[String], want: &[&str]| -> bool {
            got.iter().map(String::as_str).eq(want.iter().copied())
        };
        // engine_placeholders skips nothing here, so it is index-aligned.
        let obstacles: Vec<_> = phs
            .iter()
            .zip(&tilemap.object_placements)
            .filter(|(_, placement)| placement.kind == TilemapObjectKind::Obstacle)
            .collect();
        assert!(!obstacles.is_empty(), "the bootstrap template places obstacles");
        for (p, placement) in &obstacles {
            assert!(
                same(&p.suggested_canon_kind, obstacle_suggestions(placement.biome_object_type)),
                "{} ({:?}) did not get its biome-keyed suggestions",
                p.obj_id,
                placement.biome_object_type,
            );
        }
        assert!(
            obstacles.iter().any(|(p, _)| same(
                &p.suggested_canon_kind,
                obstacle_suggestions(Some(BiomeObjectType::Mountain)),
            )),
            "no Mountain obstacle — the biome-keyed routing went untested on real output",
        );
    }

    #[test]
    fn bootstrap_template_places_treasure_lair_obstacle_and_monolith() {
        // AC-5 — the enriched template yields a varied object set: treasure +
        // guards (treasure_tiers), obstacles (ObstaclePlacer), and a Monolith
        // pair (the jianghu_capital→forbidden_vault Portal connection).
        let tilemap = placed();
        for want in [
            TilemapObjectKind::Treasure,
            TilemapObjectKind::MonsterLair,
            TilemapObjectKind::Obstacle,
            TilemapObjectKind::Monolith,
        ] {
            assert!(
                tilemap.object_placements.iter().any(|p| p.kind == want),
                "the bootstrap template placed no {want:?}",
            );
        }
    }

    #[test]
    fn engine_placeholders_are_deterministic() {
        // AC-7 — a fixed seed yields the same placeholder set. L3Placeholder
        // has no PartialEq, so compare projected tuples (REVIEW-DESIGN R1).
        let proj = |tilemap: &TilemapView| -> Vec<(String, String, String, Vec<String>)> {
            engine_placeholders(tilemap)
                .into_iter()
                .map(|p| (p.obj_id, p.kind, p.zone_id, p.suggested_canon_kind))
                .collect()
        };
        assert_eq!(proj(&placed()), proj(&placed()));
    }
}
