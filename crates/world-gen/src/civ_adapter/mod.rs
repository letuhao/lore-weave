//! Civilization adapter — exposes a `flatworld::FlatWorld` through the
//! same `(centers, neighbors, biomes, climate, river_flux, is_coast,
//! elevation, sea_level)` interface that System-A's civilization stack
//! ([`crate::political`], [`crate::settlement`], [`crate::routes`],
//! [`crate::culture`], [`crate::feature`]) consumes.
//!
//! ## Module layout
//!
//! | Module | Responsibility |
//! |--------|----------------|
//! | [`mesh`] | `CivView` struct; flat `build_civ_view`; ocean augment; sphere projection; biome / climate translation; elevation quantiser |
//! | [`pipeline`] | Convenience builders chaining System-A's mesh-agnostic stages (`extract_features` / `build_political` / `build_settlement` / `build_routes` / `build_culture` / `build_hydrology_view`) — all sphere-projected per HIGH-1 |
//! | [`naming`] | Synthetic deterministic naming (Ship 7) + LLM-driven naming via `TextProvider` (Ship 7b) |
//! | [`render`] | Political-map PNG + SVG export with feature labels (Ship 8) |
//! | [`bundle`] | `CivBundle` Serialize/Deserialize + blake3 `content_hash` + JSON round-trip helpers (Ship 9) |
//!
//! The legacy single-file `civ_adapter.rs` (sessions 80-92) was split
//! into this folder in session 93 — no logic change, purely a layout
//! refactor for review readability.
//!
//! ## Strategy
//!
//! PO chose Approach A (feature-complete flatworld first, then 3D
//! mapping). Strategy step 2 (sphere mesh adapter) shipped in session
//! 91 and was made the default for all pipeline convenience functions
//! in session 92 after the /review-impl HIGH-1 finding.

pub mod bundle;
pub mod mesh;
pub mod naming;
pub mod pipeline;
pub mod render;

// Re-export the public surface so existing callers
// (`crate::civ_adapter::*`) keep compiling.

pub use bundle::{bundle_civ, compute_civ_hash, verify_civ_hash, CivBundle};
pub use mesh::{
    augment_with_ocean, build_civ_view, build_civ_view_spherical, derive_climate_zone,
    elevation_to_u16, koppen_to_biome_kind, project_to_sphere, CivView,
};
pub use naming::{apply_synthetic_names, name_civ_via_llm};
pub use pipeline::{
    build_culture, build_hydrology_view, build_political, build_routes, build_settlement,
    extract_features,
};
pub use render::{render_civ_political_png, render_civ_svg};
