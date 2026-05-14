//! TMP-A4 deterministic seed derivation.
//!
//! Axiom: `seed = blake3(reality_id || channel_id || template_id || seed_offset)` →
//! byte-identical tilemap output across replays for the same inputs (satisfies
//! TDIL-A9 "replay determinism FREE V1"). See
//! [`docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md#6-determinism--seeding`].
//!
//! Blake3 chosen over sha256: faster + cryptographic + 256-bit output. The first
//! 8 bytes of the digest are folded down to a `u64` for use as the procedural
//! RNG seed.

use blake3::Hasher;
use serde::{Deserialize, Serialize};

/// Tilemap procedural-generation seed. Always derived via [`derive_seed`];
/// constructing directly with `TilemapSeed(0)` is allowed for fixtures but
/// breaks the determinism axiom if used in production.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct TilemapSeed(pub u64);

impl TilemapSeed {
    pub fn raw(self) -> u64 {
        self.0
    }
}

impl std::fmt::Display for TilemapSeed {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:#018x}", self.0)
    }
}

/// Derive the TMP-A4 deterministic seed.
///
/// Field ordering + the `|` separator are part of the contract — changing
/// either would invalidate every cached tilemap. Same inputs always produce
/// the same `TilemapSeed`.
pub fn derive_seed(
    reality_id: &str,
    channel_id: &str,
    template_id: &str,
    seed_offset: u64,
) -> TilemapSeed {
    let mut hasher = Hasher::new();
    hasher.update(reality_id.as_bytes());
    hasher.update(b"|");
    hasher.update(channel_id.as_bytes());
    hasher.update(b"|");
    hasher.update(template_id.as_bytes());
    hasher.update(b"|");
    hasher.update(&seed_offset.to_le_bytes());
    let digest = hasher.finalize();
    let bytes: [u8; 8] = digest.as_bytes()[..8]
        .try_into()
        .expect("blake3 digest has at least 32 bytes — slice of 8 cannot fail");
    TilemapSeed(u64::from_le_bytes(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn derive_seed_is_deterministic() {
        let a = derive_seed("reality_a", "country_song_china", "wuxia_v1", 0);
        let b = derive_seed("reality_a", "country_song_china", "wuxia_v1", 0);
        assert_eq!(a, b, "same inputs must produce the same seed (TMP-A4)");
    }

    #[test]
    fn derive_seed_differs_on_reality_change() {
        let a = derive_seed("reality_a", "ch", "t", 0);
        let b = derive_seed("reality_b", "ch", "t", 0);
        assert_ne!(a, b);
    }

    #[test]
    fn derive_seed_differs_on_channel_change() {
        let a = derive_seed("r", "channel_a", "t", 0);
        let b = derive_seed("r", "channel_b", "t", 0);
        assert_ne!(a, b);
    }

    #[test]
    fn derive_seed_differs_on_template_change() {
        let a = derive_seed("r", "ch", "template_a", 0);
        let b = derive_seed("r", "ch", "template_b", 0);
        assert_ne!(a, b);
    }

    #[test]
    fn derive_seed_differs_on_offset_change() {
        let a = derive_seed("r", "ch", "t", 0);
        let b = derive_seed("r", "ch", "t", 1);
        assert_ne!(a, b);
    }

    #[test]
    fn derive_seed_separator_prevents_field_boundary_collision() {
        let a = derive_seed("ab", "cd", "ef", 0);
        let b = derive_seed("a", "bcd", "ef", 0);
        assert_ne!(a, b, "separator byte must distinguish concatenations");
    }
}
