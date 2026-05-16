//! Phase 2 fixture-object bootstrap — runs the Phase 1 placement engine on a
//! small reality, then drives a **fixture** object set through the full L3
//! retry loop (TMP_008b §5/§6).
//!
//! The objects are fixture, not engine-placed: engine object placement is
//! TMP_006 (TreasurePlacer / ObjectManager), unbuilt. This demonstrates the
//! end-to-end L3 contract — `place_tilemap` → L3 retry loop → classified
//! result — not the engine→L3 object flow.

use loreweave_llm::{GatewayClient, ModelSource};
use uuid::Uuid;

use crate::engine::place_tilemap;
use crate::seed::derive_seed;
use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
use crate::types::tilemap::{GridSize, TilemapView};
use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

use super::prompt::L3Placeholder;
use super::retry::{L3Result, run_l3_with_retries};

/// Result of [`bootstrap_small_reality`] — the placed tilemap plus the L3
/// classification of the fixture object set.
#[derive(Debug)]
pub struct BootstrapReport {
    pub tilemap: TilemapView,
    pub l3: L3Result,
}

/// Run the small-reality bootstrap: place a 3-zone wuxia template via the
/// Phase 1 engine, then classify a fixture object set through the §5 retry
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

    let placeholders = bootstrap_placeholders();
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

    Ok(BootstrapReport { tilemap, l3 })
}

/// The hardcoded 3-zone wuxia reality the bootstrap places.
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
                .map(|(to, kind)| TemplateConnection {
                    to_zone: ZoneId(to.to_string()),
                    kind: *kind,
                })
                .collect(),
        }
    }
    TilemapTemplate {
        template_id: TilemapTemplateId("bootstrap_wuxia_v1".to_string()),
        zones: vec![
            zone(
                "jianghu_capital",
                ZoneRole::Hub,
                &[("western_wilds", PassageKind::Threshold)],
            ),
            zone(
                "western_wilds",
                ZoneRole::Wilderness,
                &[("lotus_grove", PassageKind::Open)],
            ),
            zone("lotus_grove", ZoneRole::Wilderness, &[]),
        ],
        seed_offset: 0,
    }
}

/// Fixture objects to classify — two per zone; `zone_id`s match
/// [`bootstrap_template`]'s zones.
fn bootstrap_placeholders() -> Vec<L3Placeholder> {
    let treasure = ["BanditCache", "AbandonedCellar", "OldShrine"];
    let lair = ["BanditCamp", "WolfDen", "ElvenWatcher"];
    let landmark = ["AncientTree", "RuinedWell", "RobberShrine"];
    vec![
        L3Placeholder::new("obj_1", "Treasure", "jianghu_capital", &treasure),
        L3Placeholder::new("obj_2", "Landmark", "jianghu_capital", &landmark),
        L3Placeholder::new("obj_3", "Treasure", "western_wilds", &treasure),
        L3Placeholder::new("obj_4", "MonsterLair", "western_wilds", &lair),
        L3Placeholder::new("obj_5", "MonsterLair", "lotus_grove", &lair),
        L3Placeholder::new("obj_6", "Landmark", "lotus_grove", &landmark),
    ]
}

/// Render a [`BootstrapReport`] as a human-readable block for the CLI.
pub fn render_bootstrap_report(r: &BootstrapReport) -> String {
    let mut s = String::from("── Phase 2 small-reality bootstrap ──────────────────────\n");
    s.push_str(&format!(
        "placement : {} zones, {}×{} grid\n",
        r.tilemap.zones.len(),
        r.tilemap.grid_size.width,
        r.tilemap.grid_size.height,
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
    s.push_str("─────────────────────────────────────────────────────────\n");
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bootstrap_placeholders_reference_template_zones() {
        // Every fixture object's zone_id must be a real zone in the template
        // (the bootstrap's only cross-component invariant testable offline).
        let template = bootstrap_template();
        let zone_ids: Vec<&str> = template
            .zones
            .iter()
            .map(|z| z.zone_id.0.as_str())
            .collect();
        for p in bootstrap_placeholders() {
            assert!(
                zone_ids.contains(&p.zone_id.as_str()),
                "fixture object {} references unknown zone {}",
                p.obj_id,
                p.zone_id,
            );
            assert!(!p.suggested_canon_kind.is_empty(), "{} has no suggested kinds", p.obj_id);
        }
    }

    #[test]
    fn bootstrap_placeholder_obj_ids_are_unique_and_well_formed() {
        let ps = bootstrap_placeholders();
        let mut ids: Vec<&str> = ps.iter().map(|p| p.obj_id.as_str()).collect();
        let count = ids.len();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), count, "duplicate obj_id in bootstrap placeholders");
        for p in &ps {
            assert!(
                p.obj_id.starts_with("obj_") && p.obj_id["obj_".len()..].chars().all(|c| c.is_ascii_digit()),
                "obj_id '{}' does not match ^obj_[0-9]+$",
                p.obj_id,
            );
        }
    }
}
