//! Smoke tests for Phase 0a tilemap-service: TMP-specific invariants.
//!
//! LLM gateway wire-format tests live in [`loreweave_llm`]'s
//! `tests/wire_format.rs` (the SDK owns its own contract; this service only
//! consumes it). These tests cover what's unique to tilemap-service:
//! - `TilemapView` JSON roundtrip
//! - `derive_seed` determinism (TMP-A4)
//! - `ChannelTier::Cell` excluded from tilemap generation (TMP-A1)
//! - `TilemapSeed` Display

use tilemap_service::seed::{TilemapSeed, derive_seed};
use tilemap_service::types::{
    ChannelId, ChannelTier, GridSize, TilemapTemplateId, TilemapView,
};

#[test]
fn tilemap_view_roundtrips_through_json() {
    let original = TilemapView::empty(
        ChannelId("country:song_china".to_string()),
        ChannelTier::Country,
        GridSize::COUNTRY_DEFAULT,
        TilemapTemplateId("wuxia_southern_song_v1".to_string()),
        0xDEAD_BEEF_CAFE_F00D,
    );

    let json = serde_json::to_string(&original).expect("serialize TilemapView");
    let parsed: TilemapView = serde_json::from_str(&json).expect("deserialize TilemapView");

    assert_eq!(original, parsed, "TilemapView roundtrip preserves equality");
}

#[test]
fn derive_seed_is_deterministic_across_calls() {
    let seed_1 = derive_seed("reality_a", "country_song_china", "wuxia_v1", 0);
    let seed_2 = derive_seed("reality_a", "country_song_china", "wuxia_v1", 0);
    assert_eq!(seed_1, seed_2, "TMP-A4: same inputs must produce same seed");
}

#[test]
fn derive_seed_differs_on_any_input_change() {
    let base = derive_seed("r", "c", "t", 0);
    assert_ne!(base, derive_seed("r_other", "c", "t", 0));
    assert_ne!(base, derive_seed("r", "c_other", "t", 0));
    assert_ne!(base, derive_seed("r", "c", "t_other", 0));
    assert_ne!(base, derive_seed("r", "c", "t", 1));
}

#[test]
fn channel_tier_cell_excluded_from_tilemap() {
    // TMP-A1: cell tier has no tilemap_view.
    assert!(!ChannelTier::Cell.generates_tilemap());
    assert!(ChannelTier::Continent.generates_tilemap());
    assert!(ChannelTier::Country.generates_tilemap());
    assert!(ChannelTier::District.generates_tilemap());
    assert!(ChannelTier::Town.generates_tilemap());
}

#[test]
fn tilemap_seed_display_is_hex() {
    assert_eq!(format!("{}", TilemapSeed(0)), "0x0000000000000000");
    assert_eq!(format!("{}", TilemapSeed(1)), "0x0000000000000001");
    let value: u64 = 0xDEAD_BEEF_CAFE_F00D;
    assert_eq!(
        format!("{}", TilemapSeed(value)),
        format!("0x{:016x}", value)
    );
}
