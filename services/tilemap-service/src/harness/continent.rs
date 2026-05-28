//! Continent-scale measurement harness. Times `place_tilemap` at 256² and —
//! when a gateway client is supplied — runs the engine→L3-batched→L4 flow
//! against the live model, reporting generation timing + token cost. The L3
//! pass uses [`run_l3_batched`] so a continent's large object set is classified
//! in bounded per-zone batches.

use std::time::{Duration, Instant};

use loreweave_llm::{GatewayClient, ModelSource};
use uuid::Uuid;

use crate::engine::{place_tilemap_with_timings, PlacementStageTimings};
use crate::seed::derive_seed;
use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
use crate::types::tilemap::{GridSize, TilemapView};
use crate::types::treasure::TreasureTierSpec;
use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

use super::bootstrap::{build_l4_inputs, engine_placeholders};
use super::l4_retry::run_l4_with_retries;
use super::retry::{L3_BATCH_SIZE, run_l3_batched};
use super::style::{NarrationLanguage, NarrationVoice, NarrativeTone};

/// Offline (engine-only) continent-generation measurement.
///
/// `zones_elapsed` times `place_zones` alone (Penrose tiling + per-zone
/// fractalize — the area DEFERRED #016/#018 optimised); `modificator_timings`
/// is the per-modificator breakdown from
/// [`place_tilemap_with_timings`][crate::engine::place_tilemap_with_timings]
/// (DEFERRED #029 — narrows the modificator pipeline onto a specific placer).
/// `elapsed` is the full `place_tilemap` (place_zones + the modificator
/// pipeline).
#[derive(Debug)]
pub struct OfflineMeasurement {
    pub grid: GridSize,
    pub zone_count: usize,
    pub object_count: usize,
    pub road_segments: usize,
    pub river_segments: usize,
    pub zones_elapsed: Duration,
    pub modificator_timings: Vec<(String, Duration)>,
    pub elapsed: Duration,
}

/// Live engine→L3-batched→L4 measurement against the gateway.
#[derive(Debug)]
pub struct LiveMeasurement {
    pub l3_object_count: usize,
    pub l3_batch_size: usize,
    pub l3_llm_attempts: u32,
    pub l3_fallback_count: usize,
    pub l3_input_tokens: u32,
    pub l3_output_tokens: u32,
    pub l3_elapsed: Duration,
    pub l4_zone_count: usize,
    pub l4_llm_attempts: u32,
    pub l4_fallback_count: usize,
    pub l4_input_tokens: u32,
    pub l4_output_tokens: u32,
    pub l4_elapsed: Duration,
}

/// The 12-zone continent reality the measurement places: a `Hub` capital, a
/// chain of 8 `Wilderness` regions (each with a modest `treasure_tiers` entry —
/// density kept low so the live object set, hence the L3 batch count, stays
/// feasible), two `Sea` zones, and a `Portal`-reached `Forbidden` vault.
fn continent_template() -> TilemapTemplate {
    const REGIONS: usize = 8;
    let mk = |id: String, role: ZoneRole, connections: Vec<TemplateConnection>, treasure_tiers: Vec<TreasureTierSpec>| {
        ZoneSpec {
            zone_id: ZoneId(id),
            zone_role: role,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections,
            treasure_tiers,
            biome_selection_rules: None,
            inherit_treasure_from: None,
        }
    };

    let mut zones = vec![mk(
        "capital".to_string(),
        ZoneRole::Hub,
        vec![
            TemplateConnection::new(ZoneId("region_1".to_string()), PassageKind::Threshold),
            TemplateConnection::new(ZoneId("vault".to_string()), PassageKind::Portal),
        ],
        vec![],
    )];
    for i in 1..=REGIONS {
        let connections = if i < REGIONS {
            let kind = if i % 2 == 0 { PassageKind::Threshold } else { PassageKind::Open };
            vec![TemplateConnection::new(ZoneId(format!("region_{}", i + 1)), kind)]
        } else {
            vec![]
        };
        zones.push(mk(
            format!("region_{i}"),
            ZoneRole::Wilderness,
            connections,
            vec![TreasureTierSpec { min: 2000, max: 6000, density: 2 }],
        ));
    }
    zones.push(mk("inland_sea_a".to_string(), ZoneRole::Sea, vec![], vec![]));
    zones.push(mk("inland_sea_b".to_string(), ZoneRole::Sea, vec![], vec![]));
    zones.push(mk("vault".to_string(), ZoneRole::Forbidden, vec![], vec![]));

    TilemapTemplate {
        template_id: TilemapTemplateId("continent_measure_v1".to_string()),
        zones,
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
    }
}

/// The deterministic seed for the continent measurement.
fn continent_seed(template: &TilemapTemplate) -> crate::seed::TilemapSeed {
    derive_seed("continent_measure", "continent_channel", &template.template_id.0, template.seed_offset)
}

/// Place the continent at 256² and time it (AC-5). Returns the placed view so
/// the live measurement can reuse it.
pub fn measure_offline() -> crate::Result<(TilemapView, OfflineMeasurement)> {
    let template = continent_template();
    let grid = GridSize::CONTINENT_DEFAULT;
    let seed = continent_seed(&template);

    // Single-pass timed placement. `place_tilemap_with_timings` returns the
    // same view as `place_tilemap` plus per-stage durations — DEFERRED #029
    // makes the modificator-pipeline cost addressable by naming the dominant
    // placer. The total wall time is captured separately because
    // `PlacementStageTimings` only covers `place_zones` + per-modificator;
    // view assembly + serialisation overheads are tiny but real.
    let t0 = Instant::now();
    let (tilemap, stage) = place_tilemap_with_timings(
        &template,
        ChannelId("continent_channel".to_string()),
        ChannelTier::Country,
        grid,
        seed,
    )?;
    let elapsed = t0.elapsed();
    let PlacementStageTimings {
        place_zones: zones_elapsed,
        modificators: modificator_timings,
    } = stage;
    let offline = OfflineMeasurement {
        grid,
        zone_count: tilemap.zones.len(),
        object_count: tilemap.object_placements.len(),
        road_segments: tilemap.road_segments.len(),
        river_segments: tilemap.river_segments.len(),
        zones_elapsed,
        modificator_timings,
        elapsed,
    };
    Ok((tilemap, offline))
}

/// Run the live engine→L3-batched→L4 flow against the gateway and time each
/// stage (AC-6). Gateway-call failures are absorbed by the retry loops (every
/// object/zone still ends classified/narrated via the §6 fallback) — this
/// returns `Err` only on the loops' input-precondition, which engine output
/// never violates.
pub async fn measure_live(
    tilemap: &TilemapView,
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
) -> crate::Result<LiveMeasurement> {
    let placeholders = engine_placeholders(tilemap);
    let book_canon_refs: Vec<String> = Vec::new();

    let t_l3 = Instant::now();
    let l3 = run_l3_batched(
        client, model_source, model_ref, user_id,
        &placeholders, &book_canon_refs, 3, L3_BATCH_SIZE,
    )
    .await?;
    let l3_elapsed = t_l3.elapsed();

    let l4_inputs = build_l4_inputs(tilemap, &placeholders, &l3);
    let t_l4 = Instant::now();
    let l4 = run_l4_with_retries(
        client, model_source, model_ref, user_id,
        &l4_inputs,
        NarrationLanguage::En,
        NarrativeTone::Wuxia,
        NarrationVoice::SecondPerson,
        3,
    )
    .await?;
    let l4_elapsed = t_l4.elapsed();

    Ok(LiveMeasurement {
        l3_object_count: placeholders.len(),
        l3_batch_size: L3_BATCH_SIZE,
        l3_llm_attempts: l3.llm_attempts,
        l3_fallback_count: l3.fallback_count,
        l3_input_tokens: l3.input_tokens,
        l3_output_tokens: l3.output_tokens,
        l3_elapsed,
        l4_zone_count: l4_inputs.len(),
        l4_llm_attempts: l4.llm_attempts,
        l4_fallback_count: l4.fallback_count,
        l4_input_tokens: l4.input_tokens,
        l4_output_tokens: l4.output_tokens,
        l4_elapsed,
    })
}

/// Render the offline measurement as a human-readable block.
pub fn render_offline(m: &OfflineMeasurement) -> String {
    let modificators_total: Duration = m.modificator_timings.iter().map(|(_, d)| *d).sum();
    let mut per_mod = String::new();
    // Sort by descending wall time so the dominant placer is immediately
    // obvious — the whole point of DEFERRED #029.
    let mut sorted = m.modificator_timings.clone();
    sorted.sort_by(|a, b| b.1.cmp(&a.1));
    for (name, d) in &sorted {
        let pct = if modificators_total.as_nanos() > 0 {
            d.as_secs_f64() / modificators_total.as_secs_f64() * 100.0
        } else {
            0.0
        };
        per_mod.push_str(&format!(
            "   {name:<20} : {:>9.3} s  ({pct:>5.1} %)\n",
            d.as_secs_f64(),
        ));
    }
    format!(
        "── continent measurement — offline (engine-only) ────────\n\
         grid           : {}×{}\n\
         zones          : {}\n\
         objects placed : {}\n\
         road segments  : {}\n\
         river segments : {}\n\
         place_zones    : {:.3} s  (Penrose + fractalize — DEFERRED #016/#018)\n\
         modificators   : {:.3} s  (sum of per-stage below — DEFERRED #029)\n\
{per_mod}\
         place_tilemap  : {:.3} s  (total)\n\
         ─────────────────────────────────────────────────────────\n",
        m.grid.width, m.grid.height, m.zone_count, m.object_count,
        m.road_segments, m.river_segments,
        m.zones_elapsed.as_secs_f64(),
        modificators_total.as_secs_f64(),
        m.elapsed.as_secs_f64(),
    )
}

/// Render the live measurement as a human-readable block.
pub fn render_live(m: &LiveMeasurement) -> String {
    let batches = m.l3_object_count.div_ceil(m.l3_batch_size.max(1));
    format!(
        "── continent measurement — live (engine→L3-batched→L4) ──\n\
         L3 objects     : {} ({} per-zone batch(es), cap {})\n\
         L3 attempts    : {}  fallbacks: {}\n\
         L3 tokens      : input={} output={}\n\
         L3 elapsed     : {:.2} s\n\
         L4 zones       : {}\n\
         L4 attempts    : {}  fallbacks: {}\n\
         L4 tokens      : input={} output={}\n\
         L4 elapsed     : {:.2} s\n\
         ─────────────────────────────────────────────────────────\n",
        m.l3_object_count, batches, m.l3_batch_size,
        m.l3_llm_attempts, m.l3_fallback_count,
        m.l3_input_tokens, m.l3_output_tokens, m.l3_elapsed.as_secs_f64(),
        m.l4_zone_count, m.l4_llm_attempts, m.l4_fallback_count,
        m.l4_input_tokens, m.l4_output_tokens, m.l4_elapsed.as_secs_f64(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::place_tilemap;

    #[test]
    fn continent_template_has_the_expected_zone_mix() {
        let t = continent_template();
        assert_eq!(t.zones.len(), 12, "1 Hub + 8 Wilderness + 2 Sea + 1 Forbidden");
        let role_count = |r: ZoneRole| t.zones.iter().filter(|z| z.zone_role == r).count();
        assert_eq!(role_count(ZoneRole::Hub), 1);
        assert_eq!(role_count(ZoneRole::Wilderness), 8);
        assert_eq!(role_count(ZoneRole::Sea), 2);
        assert_eq!(role_count(ZoneRole::Forbidden), 1);
        // The capital reaches the Forbidden vault by a Portal (⇒ a Monolith).
        let capital = t.zones.iter().find(|z| z.zone_id.0 == "capital").unwrap();
        assert!(
            capital.connections.iter().any(|c| c.kind == PassageKind::Portal),
            "the capital must have a Portal connection to the vault",
        );
        // Every Wilderness region carries a treasure tier.
        for z in t.zones.iter().filter(|z| z.zone_role == ZoneRole::Wilderness) {
            assert!(!z.treasure_tiers.is_empty(), "{} has no treasure tier", z.zone_id.0);
        }
    }

    #[test]
    fn continent_template_places_deterministically() {
        // Place at a small grid — a full 256² is the runtime `measure` job,
        // far too slow for a unit test (the #016/#018 O(n²) placement cost).
        // Grid size does not affect the template-shape properties under test.
        let template = continent_template();
        let grid = GridSize { width: 48, height: 48 };
        let seed = continent_seed(&template);
        let place = || {
            place_tilemap(
                &template,
                ChannelId("continent_channel".to_string()),
                ChannelTier::Country,
                grid,
                seed,
            )
            .expect("the continent template must place")
        };
        let a = place();
        assert_eq!(a.zones.len(), 12);
        assert_eq!(a, place(), "continent placement is deterministic (TMP-A4)");
    }

    #[test]
    fn engine_placeholders_cover_the_placed_continent_objects() {
        // The L3 input derives from the placed continent's object set.
        let template = continent_template();
        let grid = GridSize { width: 48, height: 48 };
        let tilemap = place_tilemap(
            &template,
            ChannelId("continent_channel".to_string()),
            ChannelTier::Country,
            grid,
            continent_seed(&template),
        )
        .expect("places");
        let phs = engine_placeholders(&tilemap);
        assert!(!phs.is_empty(), "the continent places objects to classify");
        assert_eq!(phs.len(), tilemap.object_placements.len(), "one placeholder per object");
    }
}
