//! Inc-5 — tilemap determinism-DST.
//!
//! `place_tilemap` is synchronous + deterministic (TMP-A4: same
//! `(template, channel, tier, grid, seed)` ⇒ byte-identical `TilemapView`).
//! There is no concurrency to interleave, so madsim/the executor add nothing —
//! the honest DST here is a DETERMINISM corpus:
//!   - in-process: a sweep of seeds is byte-stable across repeated runs;
//!   - **cross-process**: a fresh process produces the SAME bytes (catches
//!     process-global nondeterminism — `HashMap` random-state / allocator
//!     addresses leaking into output — that an in-process repeat cannot).
//!
//! The existing `tilemap-service` test covers ONE in-process golden seed; this
//! adds the seed corpus, the cross-process leg, and a non-vacuity bite. The
//! engine (`place_tilemap`) is NOT modified — the bite lives entirely here
//! (review LOW-1).

use tilemap_service::engine::place_tilemap;
use tilemap_service::seed::TilemapSeed;
use tilemap_service::types::template::{
    TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec,
};
use tilemap_service::types::treasure::TreasureTierSpec;
use tilemap_service::types::zone::{PassageKind, ZoneId, ZoneRole};
use tilemap_service::types::{ChannelId, ChannelTier, GridSize, TerrainKind, TilemapView};

const SEEDS: u64 = 16;

fn zone(
    id: &str,
    role: ZoneRole,
    terrains: Vec<TerrainKind>,
    conns: &[(&str, PassageKind)],
) -> ZoneSpec {
    ZoneSpec {
        zone_id: ZoneId(id.to_string()),
        zone_role: role,
        size: 100,
        terrain_types: terrains,
        monster_strength: None,
        connections: conns
            .iter()
            .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
            .collect(),
        treasure_tiers: vec![],
        biome_selection_rules: None,
        inherit_treasure_from: None,
        biome_theme: None,
    }
}

/// A well-formed fixture (same shape as the engine's own determinism test).
fn fixture() -> TilemapTemplate {
    let mut template = TilemapTemplate {
        template_id: TilemapTemplateId("s10_determinism".to_string()),
        zones: vec![
            zone(
                "capital",
                ZoneRole::Wilderness,
                vec![TerrainKind::Grass],
                &[("crossroad", PassageKind::Threshold)],
            ),
            zone(
                "crossroad",
                ZoneRole::Hub,
                vec![],
                &[
                    ("frontier", PassageKind::Open),
                    ("rival", PassageKind::Portal),
                ],
            ),
            zone(
                "frontier",
                ZoneRole::Wilderness,
                vec![TerrainKind::Mountain],
                &[("rival", PassageKind::Adversarial)],
            ),
            zone("inland_sea", ZoneRole::Sea, vec![], &[]),
            zone("rival", ZoneRole::Forbidden, vec![], &[]),
        ],
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
        background_biome: None,
    };
    for z in &mut template.zones {
        if z.zone_role == ZoneRole::Wilderness {
            z.treasure_tiers = vec![TreasureTierSpec {
                min: 2000,
                max: 6000,
                density: 4,
            }];
        }
    }
    template
}

fn run(template: &TilemapTemplate, seed: u64) -> TilemapView {
    place_tilemap(
        template,
        ChannelId("ch_s10".to_string()),
        ChannelTier::Country,
        GridSize {
            width: 48,
            height: 48,
        },
        TilemapSeed(seed),
    )
    .expect("placement on the well-formed fixture must succeed")
}

/// FNV-1a/64 over a byte slice → hex. A small, dependency-free, deterministic
/// digest so cross-process comparison ships a short string, not a whole map.
fn fnv1a(bytes: &[u8]) -> String {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in bytes {
        h ^= *b as u64;
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("{h:016x}")
}

/// Canonical digest of `place_tilemap(seed)`. With `bite`, fold in a NON-seed
/// input (a per-call counter) so two runs of the same seed disagree — the
/// general "output depends on something other than the seed" nondeterminism
/// class. DETERMINISTIC (review LOW-3: no reliance on HashMap-order flake) so
/// the bite fires every time. The engine output itself is untouched.
pub fn digest(seed: u64, bite: bool) -> String {
    let view = run(&fixture(), seed);
    let json = serde_json::to_string(&view).expect("serialize view");
    let mut d = fnv1a(json.as_bytes());
    if bite {
        use std::sync::atomic::{AtomicU64, Ordering};
        static CALLS: AtomicU64 = AtomicU64::new(0);
        let n = CALLS.fetch_add(1, Ordering::SeqCst);
        d = fnv1a(format!("{d}|{n}").as_bytes());
    }
    d
}

/// In-process determinism: each seed in the corpus is byte-stable across two
/// runs. With `bite`, the injected nondeterminism MUST make the two runs differ.
pub fn check_inprocess(bite: bool) -> Result<String, String> {
    let seeds = crate::seed_sweep(SEEDS);
    if bite {
        // The bite must break byte-stability for at least one seed.
        for seed in 0..seeds {
            if digest(seed, true) != digest(seed, true) {
                return Ok(format!(
                    "bite fired: injected nondeterminism broke byte-stability at seed {seed} \
                     — the determinism gate HAS teeth"
                ));
            }
        }
        return Err(format!(
            "bite did NOT fire: digests stayed stable across {seeds} seeds despite injected \
             nondeterminism — the determinism gate is VACUOUS"
        ));
    }
    for seed in 0..seeds {
        let (a, b) = (digest(seed, false), digest(seed, false));
        if a != b {
            return Err(format!(
                "in-process NONDETERMINISM at seed {seed}: {a} != {b}"
            ));
        }
    }
    Ok(format!(
        "determinism OK (in-process): {seeds} seeds byte-stable across repeated runs"
    ))
}

/// Seeds the cross-process leg checks (kept small — each spawns a child).
pub const CROSS_PROCESS_SEEDS: [u64; 3] = [1, 7, 0xA11CE];
