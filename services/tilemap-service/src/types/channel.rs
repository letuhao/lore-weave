//! Channel identity + tier — mirrors MAP_001 `MapKind` (5 V1 closed enum)
//! and DP-K1 `ChannelId`.
//!
//! Per TMP-A1, **Cell tier is excluded** from any `tilemap_view` — CSC_001
//! is authoritative for the in-scene 16×16 interior. tilemap-service only
//! generates tile data for the four non-cell tiers.

use serde::{Deserialize, Serialize};

/// Stable channel identity. Phase 0a is a string newtype — Phase 2 will swap
/// in the real DP-K1 `ChannelId` once the Rust DP SDK exists.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ChannelId(pub String);

impl std::fmt::Display for ChannelId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

/// The closed `MapKind` set (doc 36 `SPG-A3`), replacing `MAP_001`'s retired
/// five-rung `MapKind` ladder.
///
/// ⚠ RENAMED 2026-08-22 — `SPG-R1` retired `MapKind` on 2026-07-30 and
/// `SPG-R14` supplies the mapping. **It is a REMAP, not a rename:** the ladder's
/// five rungs become three kinds plus recursion, because `MapKind::Region` is
/// itself recursive and the middle rungs were three DEPTHS rather than three
/// kinds.
///
/// ```text
///   Continent · Country · District  ->  Region   (nesting)
///   Town                            ->  Locale   (SPG-R9: it carries the tilemap)
///   Cell                            ->  Domain   (SPG-R5; CSC_001 owns the interior)
/// ```
///
/// The variant set is the one `0024_map_layout`'s `map_layout_kind_closed` CHECK
/// accepts, so the service and the database spell a kind the same way. `Vessel`
/// is reserved in doc 36 and absent here for the same reason it is absent from
/// that CHECK: a kind the engine cannot interpret should not be writable.
///
/// ## The old spellings still DESERIALISE, and that is a rule rather than a kindness
///
/// A wire vocabulary change that cannot read what it previously wrote is a
/// data-loss event. `SDF-A12` states the general form -- *retire a decoder,
/// never delete it* -- and DataFixerUpper is the proof at scale: its fix chain
/// is never pruned, which is why a 2011 Minecraft world still loads.
///
/// So each absorbed rung carries a `#[serde(alias)]`. Aliases are
/// DESERIALISE-ONLY: emission is always the new spelling, so the wire moves
/// forward while every payload already written keeps reading. **Measured, not
/// assumed: removing them reds
/// `pre_phase_e_view_json_deserializes_without_road_or_river_segments`, a test
/// that exists to assert exactly this and which caught the omission the first
/// time this enum was remapped.**
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MapKind {
    /// Root of a coordinate space.
    Universe,
    /// A planet or plane.
    World,
    /// A geographic subdivision of a `World`; RECURSIVE.
    ///
    /// The three aliases are the retired ladder rungs this kind absorbed
    /// (`SPG-R14`). They are DESERIALISE-ONLY: serde emits `region` and accepts
    /// the old spellings, so a payload written before 2026-08-22 still reads.
    #[serde(alias = "continent", alias = "country", alias = "district")]
    Region,
    /// The tilemap-bearing kind (`SPG-R9`). Was `town`.
    #[serde(alias = "town")]
    Locale,
    /// An interior. Excluded from tilemap generation (`TMP-A1`). Was `cell`.
    #[serde(alias = "cell")]
    Domain,
    /// A corridor between nodes (`SPG-A13`).
    Passage,
    /// An ephemeral tactical grid.
    Arena,
}

impl MapKind {
    /// `true` for kinds that generate a `tilemap_view`.
    ///
    /// ⚠ REWRITTEN AS A POSITIVE LIST, and the reason is the whole risk of this
    /// remap. It used to read `!matches!(self, MapKind::Domain)` — correct
    /// ONLY because the closed set had five members and four of them were
    /// tilemap-bearing. Widening to seven makes a negation silently claim that
    /// `Universe`, `Passage` and `Arena` bear tilemaps, which is false for all
    /// three. **A predicate whose correctness depends on the SIZE of a closed
    /// set breaks the moment the set changes, and it breaks quietly.**
    pub fn generates_tilemap(self) -> bool {
        matches!(self, MapKind::Region | MapKind::Locale)
    }
}
