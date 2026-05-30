//! V2 data model — runtime registry container + loader.
//!
//! Loads `TerrainKindDef` / `ObjectKindDef` registry definitions from
//! embedded TOML (default registry) or from a file path (per-book
//! registries). Engine + placer look up tags here at world-gen time.
//!
//! See:
//! - [`crate::types::primitive`] — closed-primitive engine enums
//! - [`crate::types::registry`] — `TerrainKindDef`, `ObjectKindDef`,
//!   `RegistryRef`, property bag conventions
//! - ADR `docs/specs/2026-05-26-data-model-v2-registry-footprint.md` §2.3

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::types::biome_theme::BiomeThemeDef;
use crate::types::primitive::ObjectPrimitive;
use crate::types::registry::{ObjectKindDef, RegistryRef, TerrainKindDef};
use crate::types::tile::TerrainKind;

/// Errors surfaced by registry loading + validation.
#[derive(Debug)]
pub enum RegistryError {
    /// Failed to read the registry file from disk.
    Io(std::io::Error),
    /// TOML parse failure with line/column context.
    Parse(toml::de::Error),
    /// Schema violation — e.g. duplicate `id`, empty registry, invalid
    /// id format, zero footprint, walkability mask length mismatch.
    Validation(String),
}

impl std::fmt::Display for RegistryError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "registry io: {e}"),
            Self::Parse(e) => write!(f, "registry parse: {e}"),
            Self::Validation(msg) => write!(f, "registry validation: {msg}"),
        }
    }
}

impl std::error::Error for RegistryError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(e) => Some(e),
            Self::Parse(e) => Some(e),
            Self::Validation(_) => None,
        }
    }
}

impl From<std::io::Error> for RegistryError {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}

impl From<toml::de::Error> for RegistryError {
    fn from(e: toml::de::Error) -> Self {
        Self::Parse(e)
    }
}

/// id format check: must start with `[a-z]`, then any of `[a-z0-9_:.-]*`.
/// Matches the ADR §2.1.1 convention without pulling in the `regex`
/// crate as a dependency.
///
/// `pub(crate)` so [`crate::types::biome_theme`] can validate
/// [`BiomeThemeDef::id`] with the same rule that gates terrain + object
/// ids — keeps id-format invariants consistent across the registry.
pub(crate) fn is_valid_id(id: &str) -> bool {
    let mut chars = id.chars();
    match chars.next() {
        Some(c) if c.is_ascii_lowercase() => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '_' | ':' | '.' | '-'))
}

/// TMP-Q1 chunk B — biome-key validation. Every entry in an
/// `ObjectKindDef.biomes` list MUST be a `TerrainKind::tag()` value
/// (snake_case). Enumerated against the `TerrainKind` enum directly so
/// adding a future variant fails the registry-load until the literal
/// is mirrored here.
///
/// TMP-Q2 chunk A — also called by [`BiomeThemeDef::validate`] to gate
/// the `terrain` tag in each `BiomeMixEntry`. Same closed-set rule so a
/// future `TerrainKind` variant fails both places at once.
pub(crate) fn is_valid_biome_key(key: &str) -> bool {
    matches!(
        key,
        "grass"
            | "forest"
            | "mountain"
            | "water"
            | "sand"
            | "snow"
            | "swamp"
            | "road"
            | "rough"
            | "subterranean"
    )
}

/// Wire-shape for a TOML registry file. Combines terrain + object kinds
/// + metadata into a single document — easier per-book editing than two
/// separate files.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegistryFile {
    /// `[registry]` table — id + version metadata.
    pub registry: RegistryRef,
    /// `[[terrain]]` array of inline tables.
    #[serde(default)]
    pub terrain: Vec<TerrainKindDef>,
    /// `[[object]]` array of inline tables.
    #[serde(default)]
    pub object: Vec<ObjectKindDef>,
    /// TMP-Q2 chunk A — `[[biome]]` array of inline tables.
    /// `#[serde(default)]` keeps pre-Q2 per-book registry files loading
    /// without a `[[biome]]` section (the biome-theme pass is opt-in
    /// via [`crate::types::template::TilemapTemplate::background_biome`]
    /// / [`crate::types::template::ZoneSpec::biome_theme`]).
    #[serde(default)]
    pub biome: Vec<BiomeThemeDef>,
}

/// In-memory tag-keyed registry. Cheap clone (Arc would be nicer at
/// scale but the registry is small + cloned rarely).
#[derive(Debug, Clone)]
pub struct Registry {
    reference: RegistryRef,
    terrain_by_tag: HashMap<String, TerrainKindDef>,
    object_by_tag: HashMap<String, ObjectKindDef>,
    /// TMP-Q1 chunk B — index: biome key (snake_case `TerrainKind::tag()`)
    /// → decoration tags applicable in that biome. BTreeMap (not HashMap)
    /// for deterministic iteration: the DecorationPlacer's per-zone RNG
    /// stream samples this map and order must be stable across runs.
    /// Built at `from_file` time from every `ObjectKindDef` whose
    /// `primitive` is `Decoration` — bucketed once per biome listed in
    /// the kind's `biomes` field. Within each bucket, refs are sorted by
    /// `kind_id` for the same determinism reason.
    decoration_by_biome: BTreeMap<String, Vec<DecorationRef>>,
    /// TMP-Q2 chunk A — id → [`BiomeThemeDef`] lookup. BTreeMap (not
    /// HashMap) for the same determinism rationale as `decoration_by_biome`:
    /// chunk-B `BiomeThemePainter` iterates over this when emitting
    /// per-biome statistics + (future) palette previews, and the iteration
    /// order must be stable across runs.
    biome_by_id: BTreeMap<String, BiomeThemeDef>,
}

/// TMP-Q1 chunk B — denormalized decoration entry stored in the
/// per-biome index. Carries the placement-time fields the
/// `DecorationPlacer` reads (kind_id for lookup, density_weight for
/// weighted random selection, min_spacing for the Chebyshev gate).
#[derive(Debug, Clone, PartialEq)]
pub struct DecorationRef {
    pub kind_id: String,
    pub density_weight: f32,
    pub min_spacing: u32,
}

/// TMP-Q5 — validation hook for `RegistryRef.zone_role_colors`.
///
/// V1: no constraint (every u32 is a valid 24-bit color packed into
/// the low bits; alpha bits are ignored at render time). The function
/// exists as a reserved extension point so future constraints (alpha-
/// bit reserved, contrast-vs-foundation check, per-role hue family)
/// land without an API churn at `Registry::from_file` AND without
/// risking accidental deletion as bare dead code (MED-1 from
/// chunk-A /review-impl).
fn validate_zone_role_colors(
    _colors: &Option<crate::types::registry::ZoneRoleColors>,
) -> Result<(), RegistryError> {
    // V1 no-op. Future constraints land here.
    Ok(())
}

impl Registry {
    /// Build from a parsed registry file, validating:
    /// - at least one terrain + one object kind
    /// - every id matches `^[a-z][a-z0-9_:.-]*$`
    /// - no duplicate ids within terrain or within object
    /// - every footprint has area > 0
    /// - every `Mask` walkability matches its object's footprint area
    pub fn from_file(file: RegistryFile) -> Result<Self, RegistryError> {
        if file.terrain.is_empty() {
            return Err(RegistryError::Validation(
                "registry must define at least one terrain kind".into(),
            ));
        }
        if file.object.is_empty() {
            return Err(RegistryError::Validation(
                "registry must define at least one object kind".into(),
            ));
        }
        // TMP-Q5 — validate per-book zone_role_colors if declared.
        // Delegated to a named function so the seam is delete-resistant
        // (MED-1 from chunk-A /review-impl): a cleanup sweep that
        // removes a bare `let _ = colors;` no-op block is too easy;
        // a named function call with documented intent makes it
        // explicit that this is a reserved validation extension point.
        validate_zone_role_colors(&file.registry.zone_role_colors)?;
        let mut terrain_by_tag = HashMap::with_capacity(file.terrain.len());
        for def in file.terrain {
            if !is_valid_id(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "invalid terrain id {:?}: must match ^[a-z][a-z0-9_:.-]*$",
                    def.id
                )));
            }
            if terrain_by_tag.contains_key(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "duplicate terrain id {:?}",
                    def.id
                )));
            }
            terrain_by_tag.insert(def.id.clone(), def);
        }
        let mut object_by_tag = HashMap::with_capacity(file.object.len());
        for def in file.object {
            if !is_valid_id(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "invalid object id {:?}: must match ^[a-z][a-z0-9_:.-]*$",
                    def.id
                )));
            }
            if def.footprint.area() == 0 {
                return Err(RegistryError::Validation(format!(
                    "object {:?} footprint area must be > 0 (got width={}, height={})",
                    def.id, def.footprint.width, def.footprint.height
                )));
            }
            if let Some(crate::types::registry::WalkabilityPattern::Mask(mask)) =
                &def.walkability_pattern
            {
                let expected = def.footprint.area() as usize;
                if mask.len() != expected {
                    return Err(RegistryError::Validation(format!(
                        "object {:?} walkability_pattern mask length {} does not match footprint area {}",
                        def.id,
                        mask.len(),
                        expected
                    )));
                }
            }
            // TMP-Q1 chunk B — biome + density_weight validation runs for
            // EVERY object kind (MED-1: silent skip on non-decoration kinds
            // hides author errors). Even an obstacle with biomes = ["dessert"]
            // typo gets caught here.
            //
            // Duplicate biome keys in a single def's list (MED-3) are also
            // rejected — silently double-listing in the index would over-
            // weight the tag in chunk-C's weighted sample.
            let mut seen_biomes: std::collections::HashSet<&str> =
                std::collections::HashSet::with_capacity(def.biomes.len());
            for biome in &def.biomes {
                if !is_valid_biome_key(biome) {
                    return Err(RegistryError::Validation(format!(
                        "object {:?} lists unknown biome {:?}: must be a \
                         TerrainKind::tag() value (grass, forest, mountain, water, \
                         sand, snow, swamp, road, rough, subterranean)",
                        def.id, biome
                    )));
                }
                if !seen_biomes.insert(biome.as_str()) {
                    return Err(RegistryError::Validation(format!(
                        "object {:?} biomes list contains duplicate key {:?}",
                        def.id, biome
                    )));
                }
            }
            // MED-2 — density_weight must be finite + positive so chunk C's
            // weighted-sample `rng.gen_range(0.0..total)` never panics on
            // NaN/Inf and never silently never-picks on negative.
            if !def.density_weight.is_finite() || def.density_weight <= 0.0 {
                return Err(RegistryError::Validation(format!(
                    "object {:?} density_weight must be finite + positive, got {}",
                    def.id, def.density_weight
                )));
            }
            if object_by_tag.contains_key(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "duplicate object id {:?}",
                    def.id
                )));
            }
            object_by_tag.insert(def.id.clone(), def);
        }

        // TMP-Q1 chunk B — build the per-biome decoration index. Walks
        // `object_by_tag` in sorted-id order (collected into a Vec first)
        // so the index Vecs are deterministic regardless of HashMap's
        // internal iteration order. Validation already happened in the
        // outer loop above (MED-1/2/3 from chunk-B /review-impl); this
        // step is pure projection of validated state into the index.
        let mut decoration_by_biome: BTreeMap<String, Vec<DecorationRef>> = BTreeMap::new();
        let mut sorted_object_ids: Vec<&String> = object_by_tag.keys().collect();
        sorted_object_ids.sort_unstable();
        for id in sorted_object_ids {
            let def = &object_by_tag[id];
            if def.primitive != ObjectPrimitive::Decoration {
                continue;
            }
            for biome in &def.biomes {
                decoration_by_biome
                    .entry(biome.clone())
                    .or_default()
                    .push(DecorationRef {
                        kind_id: def.id.clone(),
                        density_weight: def.density_weight,
                        min_spacing: def.min_spacing,
                    });
            }
        }

        // TMP-Q2 chunk A — validate + index biome themes. Empty
        // `file.biome` is allowed (registries without a `[[biome]]`
        // section); the chunk-B placer early-returns when the lookup
        // misses.
        let mut biome_by_id: BTreeMap<String, BiomeThemeDef> = BTreeMap::new();
        for def in file.biome {
            if !is_valid_id(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "invalid biome id {:?}: must match ^[a-z][a-z0-9_:.-]*$",
                    def.id
                )));
            }
            if biome_by_id.contains_key(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "duplicate biome id {:?}",
                    def.id
                )));
            }
            def.validate().map_err(|e| {
                RegistryError::Validation(format!("biome {:?}: {e}", def.id))
            })?;
            biome_by_id.insert(def.id.clone(), def);
        }

        Ok(Self {
            reference: file.registry,
            terrain_by_tag,
            object_by_tag,
            decoration_by_biome,
            biome_by_id,
        })
    }

    /// Parse + validate from a TOML string.
    pub fn from_toml_str(toml_text: &str) -> Result<Self, RegistryError> {
        let file: RegistryFile = toml::from_str(toml_text)?;
        Self::from_file(file)
    }

    /// Read + parse from a filesystem path.
    pub fn load_from_path(path: &Path) -> Result<Self, RegistryError> {
        let text = std::fs::read_to_string(path)?;
        Self::from_toml_str(&text)
    }

    /// Load the embedded default registry (covers all current 10
    /// terrain + 18 object kinds under `lw:` namespace). Backward-
    /// compat anchor for V1.2 wire shape during V2 transition.
    pub fn load_default() -> Result<Self, RegistryError> {
        Self::from_toml_str(DEFAULT_REGISTRY_TOML)
    }

    /// Reference identifier embedded in TilemapView responses so the
    /// frontend can detect mismatched registry assumptions.
    pub fn reference(&self) -> &RegistryRef {
        &self.reference
    }

    /// Look up a terrain kind by tag. `None` for unknown tags — engine
    /// callers should fall back to a sentinel (e.g. `lw:void` if
    /// rendering, or treat as `TerrainPrimitive::Land` for permissive
    /// placer behavior).
    pub fn get_terrain(&self, tag: &str) -> Option<&TerrainKindDef> {
        self.terrain_by_tag.get(tag)
    }

    /// Look up an object kind by tag.
    pub fn get_object(&self, tag: &str) -> Option<&ObjectKindDef> {
        self.object_by_tag.get(tag)
    }

    pub fn terrain_tags(&self) -> impl Iterator<Item = &str> {
        self.terrain_by_tag.keys().map(String::as_str)
    }

    pub fn object_tags(&self) -> impl Iterator<Item = &str> {
        self.object_by_tag.keys().map(String::as_str)
    }

    pub fn terrain_count(&self) -> usize {
        self.terrain_by_tag.len()
    }

    pub fn object_count(&self) -> usize {
        self.object_by_tag.len()
    }

    /// TMP-Q2 chunk A — look up a biome theme by id. Returns `None` for
    /// ids not declared in the registry (chunk-B placer treats as a
    /// silent no-op for that zone / background — the field is opt-in
    /// and an unknown id is recoverable, not a panic).
    pub fn get_biome(&self, id: &str) -> Option<&BiomeThemeDef> {
        self.biome_by_id.get(id)
    }

    /// TMP-Q2 chunk A — declared biome theme ids in BTreeMap (sorted)
    /// order. Used by introspection tests + future inspector UIs.
    pub fn biome_ids(&self) -> impl Iterator<Item = &str> {
        self.biome_by_id.keys().map(String::as_str)
    }

    /// TMP-Q2 chunk A — number of biome themes in this registry.
    /// Pre-Q2 registries (no `[[biome]]` section) report 0.
    pub fn biome_count(&self) -> usize {
        self.biome_by_id.len()
    }

    /// TMP-Q1 chunk B — decorations registered for `terrain`'s biome.
    /// `terrain.tag()` is the snake_case key (e.g. `Grass → "grass"`,
    /// `Subterranean → "subterranean"`) used by the `decoration_by_biome`
    /// index. Returns `&[]` for biomes with no decorations declared
    /// (defensive — DecorationPlacer skips the zone silently). Order
    /// within a biome's slice is deterministic (sorted by `kind_id` at
    /// `from_file` time).
    pub fn decorations_for_terrain(&self, terrain: TerrainKind) -> &[DecorationRef] {
        self.decoration_by_biome
            .get(terrain.tag())
            .map(Vec::as_slice)
            .unwrap_or(&[])
    }

    /// TMP-Q1 chunk B — total slice-entry count across all biome buckets
    /// (a tag listed in N biomes counts N times). General-purpose
    /// introspection of the index; not the same as "number of unique
    /// decoration kinds" (use `object_tags` filtered by primitive for
    /// that count).
    pub fn decoration_index_size(&self) -> usize {
        self.decoration_by_biome.values().map(Vec::len).sum()
    }

    /// TMP-Q1 chunk B — biome keys that have at least one decoration
    /// declared. Iteration is deterministic (BTreeMap order). General-
    /// purpose introspection; chunk-C placer uses `decorations_for_terrain`.
    pub fn decoration_biome_keys(&self) -> impl Iterator<Item = &str> {
        self.decoration_by_biome.keys().map(String::as_str)
    }

    /// V2 — build the `terrain_vocabulary` for V1 wire-shape compatibility.
    /// Indexed by the `u8` values written into `TilemapView.terrain_layer`:
    /// `[0]` is a `lw:void` sentinel, `[1..=10]` are the V1 `TerrainKind`
    /// variants. For each V1 kind, consults this registry for the canonical
    /// tag (e.g. `lw:grass`); per-book registries that override `lw:` entries
    /// produce a different primitive while keeping the same tag. Falls back
    /// to the static `TerrainKind::v2_cell()` defaults when an entry is
    /// absent — keeping wire shape compatible even for partial registries.
    pub fn build_default_terrain_vocabulary(&self) -> Vec<crate::types::tile::TerrainCell> {
        use crate::types::tile::TerrainKind;
        let mut vocab = Vec::with_capacity(11);
        vocab.push(crate::types::tile::TerrainCell {
            primitive: crate::types::primitive::TerrainPrimitive::Void,
            tag: "lw:void".to_string(),
        });
        for kind in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let default_cell = kind.v2_cell();
            let cell = match self.get_terrain(&default_cell.tag) {
                Some(def) => crate::types::tile::TerrainCell {
                    primitive: def.primitive,
                    tag: default_cell.tag,
                },
                None => default_cell,
            };
            vocab.push(cell);
        }
        vocab
    }

    /// V2 — resolve the (primitive, footprint, tag) triple for a placed object.
    /// First derives the canonical `lw:` tag from `(kind, biome_obj_type)` via
    /// the static `v2_defaults` helper, then looks it up in this registry. If
    /// the registry overrides the entry (per-book registries), uses the
    /// override; otherwise falls back to the static defaults. The drift-
    /// prevention test (`v2_defaults_match_default_registry`) guarantees the
    /// default registry's entry agrees with the static helper, so default-
    /// registry runs produce bit-identical output before/after the swap.
    pub fn resolve_object_v2(
        &self,
        kind: crate::types::object::TilemapObjectKind,
        biome_obj_type: Option<crate::types::biome::BiomeObjectType>,
    ) -> crate::types::object::V2Defaults {
        let defaults = kind.v2_defaults(biome_obj_type);
        match self.get_object(&defaults.tag) {
            Some(def) => crate::types::object::V2Defaults {
                tag: defaults.tag,
                primitive: def.primitive,
                footprint: def.footprint,
            },
            None => defaults,
        }
    }
}

/// Embedded default registry — covers all current V1 kinds under
/// `lw:` namespace. Loaded by `load_default()`.
const DEFAULT_REGISTRY_TOML: &str = include_str!("../registry/default.toml");

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::primitive::TerrainPrimitive;
    use crate::types::tile::TerrainKind;

    // TMP-Q1 chunk B — decoration registry tests. Lock the four
    // load-bearing invariants per plan v2 §B test list.

    #[test]
    fn default_registry_has_decoration_coverage_for_all_terrain_kinds() {
        // AC-DECO-12 — every TerrainKind variant must have ≥2 decorations
        // registered. Chunk-C placer falls back gracefully on empty pools
        // (skips the zone) but the spec promises non-empty coverage for
        // visible density across all 10 biomes.
        let reg = Registry::load_default().unwrap();
        for tk in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let pool = reg.decorations_for_terrain(tk);
            assert!(
                pool.len() >= 2,
                "TerrainKind::{:?} (tag={:?}) must have >=2 decorations, got {}",
                tk,
                tk.tag(),
                pool.len()
            );
            // Each ref is well-formed: kind_id non-empty, weight finite & positive.
            for r in pool {
                assert!(!r.kind_id.is_empty(), "decoration kind_id must not be empty");
                assert!(r.density_weight.is_finite() && r.density_weight > 0.0,
                    "density_weight must be finite + positive, got {} on {}",
                    r.density_weight, r.kind_id);
            }
        }
    }

    #[test]
    fn every_decoration_biome_key_is_known_terrain_kind() {
        // Registry-load validation: a decoration that lists an unknown
        // biome key (e.g. "desert" — the TerrainKind variant is `Sand`,
        // not Desert) fails the load with a named error. This guards
        // against silent drift when adding per-book registries.
        let bad_toml = r#"
[registry]
id = "test"
version = "0.0.1"

[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"

[[object]]
id = "test:decoration.broken"
primitive = "decoration"
label = "Broken"
biomes = ["desert"]
"#;
        let err = Registry::from_toml_str(bad_toml).unwrap_err();
        match err {
            RegistryError::Validation(msg) => {
                assert!(msg.contains("unknown biome"),
                    "expected 'unknown biome' in error, got: {msg}");
                assert!(msg.contains("desert"),
                    "expected the offending biome key in error, got: {msg}");
            }
            other => panic!("expected RegistryError::Validation, got {other:?}"),
        }
    }

    #[test]
    fn decoration_by_biome_iteration_is_deterministic() {
        // BTreeMap discipline: two loads of the same TOML produce
        // identical biome-key iteration order AND identical
        // sorted-by-kind_id order within EVERY biome's slice. Chunk C's
        // determinism golden relies on this. LOW-3 from chunk-B
        // /review-impl: iterate ALL biomes (not a sample of 3) so a
        // future refactor that walks object_by_tag.values() unsorted
        // gets caught here.
        let reg1 = Registry::load_default().unwrap();
        let reg2 = Registry::load_default().unwrap();
        let keys1: Vec<&str> = reg1.decoration_biome_keys().collect();
        let keys2: Vec<&str> = reg2.decoration_biome_keys().collect();
        assert_eq!(keys1, keys2, "biome key iteration must be deterministic");
        // Within each biome, refs are sorted by kind_id. Iterate every biome.
        for tk in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let pool = reg1.decorations_for_terrain(tk);
            let ids: Vec<&str> = pool.iter().map(|r| r.kind_id.as_str()).collect();
            let mut sorted = ids.clone();
            sorted.sort_unstable();
            assert_eq!(ids, sorted,
                "decoration_by_biome[{:?}] refs must be sorted by kind_id", tk);
        }
    }

    #[test]
    fn default_registry_has_at_least_28_decoration_tags_total() {
        // LOW-1 from chunk-B /review-impl. AC-DECO-12 clause 1 (≥28
        // total unique decoration tags). PO chose Q2(b) over Q2(a) for
        // higher variety; this test locks the lower bound so a future
        // contributor reducing variety silently fails.
        let reg = Registry::load_default().unwrap();
        let count = reg.object_tags()
            .filter(|tag| {
                reg.get_object(tag)
                    .map(|def| def.primitive == ObjectPrimitive::Decoration)
                    .unwrap_or(false)
            })
            .count();
        assert!(
            count >= 28,
            "AC-DECO-12 clause 1: expected ≥28 unique decoration tags, got {count}"
        );
    }

    #[test]
    fn registry_rejects_non_decoration_with_unknown_biome() {
        // MED-1 from chunk-B /review-impl. A blocker (or any non-decoration)
        // with biomes = ["dessert"] (typo for "sand") must fail at load
        // time. Previously the index step skipped non-decorations
        // without validating their biomes — author errors hidden.
        let bad = r#"
[registry]
id = "test"
version = "0.0.1"
[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"
[[object]]
id = "test:obstacle.peak"
primitive = "blocker"
label = "Peak"
biomes = ["dessert"]
"#;
        let err = Registry::from_toml_str(bad).unwrap_err();
        match err {
            RegistryError::Validation(msg) => {
                assert!(msg.contains("unknown biome"), "got: {msg}");
                assert!(msg.contains("dessert"), "got: {msg}");
            }
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[test]
    fn registry_rejects_non_finite_or_non_positive_density_weight() {
        // MED-2 from chunk-B /review-impl. NaN, Inf, negative, and zero
        // density_weight values fail at load time.
        for (label, weight) in [
            ("nan", "nan"),
            ("inf", "inf"),
            ("negative", "-0.5"),
            ("zero", "0.0"),
        ] {
            let toml = format!(r#"
[registry]
id = "test"
version = "0.0.1"
[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"
[[object]]
id = "test:decoration.bad"
primitive = "decoration"
label = "Bad"
biomes = ["grass"]
density_weight = {weight}
"#);
            let err = Registry::from_toml_str(&toml).expect_err(
                &format!("expected {label} density_weight to fail load"));
            match err {
                RegistryError::Validation(msg) => {
                    assert!(msg.contains("density_weight"),
                        "[{label}] msg missing 'density_weight': {msg}");
                }
                other => panic!("[{label}] expected Validation, got {other:?}"),
            }
        }
    }

    #[test]
    fn registry_rejects_duplicate_biomes_in_one_kind() {
        // MED-3 from chunk-B /review-impl. A decoration listing the same
        // biome twice would double-list in the index and over-weight in
        // chunk-C's weighted sample. Caught at load.
        let bad = r#"
[registry]
id = "test"
version = "0.0.1"
[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"
[[object]]
id = "test:decoration.dup"
primitive = "decoration"
label = "Dup"
biomes = ["grass", "grass"]
"#;
        let err = Registry::from_toml_str(bad).unwrap_err();
        match err {
            RegistryError::Validation(msg) => {
                assert!(msg.contains("duplicate"), "got: {msg}");
                assert!(msg.contains("grass"), "got: {msg}");
            }
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[test]
    fn empty_biomes_field_serializes_omitted() {
        // MED-4 from chunk-B /review-impl. ObjectKindDef.biomes default
        // is empty Vec; serde discipline matches world_zone — empty list
        // is skipped from JSON / TOML output so V2 entries that don't
        // declare the field stay byte-identical on round-trip.
        let def = crate::types::registry::ObjectKindDef {
            id: "lw:obstacle.peak".to_string(),
            primitive: ObjectPrimitive::Blocker,
            label: "Peak".to_string(),
            footprint: crate::types::registry::FootprintSize::unit(),
            walkability_pattern: None,
            min_spacing: 0,
            biomes: vec![],
            density_weight: 1.0,
            properties: serde_json::Value::Object(serde_json::Map::new()),
        };
        let json = serde_json::to_string(&def).unwrap();
        assert!(!json.contains("biomes"),
            "empty biomes must NOT appear in JSON (skip_serializing_if discipline): {json}");
        assert!(!json.contains("density_weight"),
            "default density_weight=1.0 must NOT appear in JSON: {json}");
    }

    #[test]
    fn xianxia_decoration_parallel_loads_clean() {
        // AC-DECO-3 — xianxia_sample.toml mirrors default coverage with
        // xianxia:decoration.* namespace. Same coverage invariants hold:
        // every TerrainKind variant has >=2 decorations, all ids start
        // with the xianxia namespace.
        // LOW-2 from chunk-B /review-impl: embed at compile-time via
        // include_str! to match the default registry's discipline —
        // working-directory-independent.
        let toml_text = include_str!("../registry/xianxia_sample.toml");
        let reg = Registry::from_toml_str(toml_text)
            .expect("xianxia sample must load clean");
        for tk in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let pool = reg.decorations_for_terrain(tk);
            assert!(
                pool.len() >= 2,
                "xianxia TerrainKind::{:?} must have >=2 decorations, got {}",
                tk, pool.len()
            );
            for r in pool {
                assert!(r.kind_id.starts_with("xianxia:decoration."),
                    "xianxia decoration id must use the xianxia namespace, got {}",
                    r.kind_id);
            }
        }
    }

    // ── TMP-Q2 chunk A biome-theme registry tests ──────────────────────
    //
    // LOW-2/LOW-3/LOW-4 from chunk-A /review-impl. Mirror the chunk-B
    // decoration-validation discipline above for the new biome-theme
    // surface: empty section path, id format reject, duplicate id reject.

    #[test]
    fn registry_loads_clean_without_biome_section() {
        // LOW-2 fix — pre-Q2 per-book registries that don't ship a
        // [[biome]] section must continue to load with biome_count() == 0.
        // The #[serde(default)] on RegistryFile.biome is what makes this
        // safe; locking it with a test prevents future refactors from
        // silently making it required.
        let toml = r#"
[registry]
id = "test"
version = "0.0.1"

[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"

[[object]]
id = "test:treasure"
primitive = "pickup"
label = "Treasure"
"#;
        let reg = Registry::from_toml_str(toml).expect("must load without [[biome]]");
        assert_eq!(reg.biome_count(), 0,
            "registry without [[biome]] section must report biome_count == 0");
        assert!(reg.get_biome("anything").is_none(),
            "get_biome must return None when no themes registered");
        let ids: Vec<&str> = reg.biome_ids().collect();
        assert!(ids.is_empty(),
            "biome_ids() iterator must be empty for biome-less registry");
    }

    #[test]
    fn registry_rejects_invalid_biome_id_format() {
        // LOW-3 fix — invalid biome ids (uppercase, empty, leading digit)
        // must fail registry-load with a clear error. Same is_valid_id
        // rule that gates terrain + object ids applies here.
        for (label, bad_id) in [
            ("uppercase", "INVALID"),
            ("empty", ""),
            ("leading-digit", "1lw:biome.bad"),
        ] {
            let toml = format!(r#"
[registry]
id = "test"
version = "0.0.1"

[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"

[[object]]
id = "test:treasure"
primitive = "pickup"
label = "Treasure"

[[biome]]
id = "{bad_id}"
label = "Bad"
mix = [{{ terrain = "grass", weight = 1.0 }}]
"#);
            let err = Registry::from_toml_str(&toml).expect_err(
                &format!("expected {label} biome id ({bad_id:?}) to fail registry load"));
            match err {
                RegistryError::Validation(msg) => {
                    assert!(msg.contains("invalid biome id"),
                        "[{label}] msg missing 'invalid biome id': {msg}");
                }
                other => panic!("[{label}] expected Validation, got {other:?}"),
            }
        }
    }

    #[test]
    fn registry_rejects_duplicate_biome_id() {
        // LOW-4 fix — two [[biome]] entries sharing an id must fail
        // registry-load. Without this guard a duplicate would either
        // second-wins (BTreeMap.insert) or silently merge — both wrong
        // for the per-zone Some(id) → Registry lookup contract.
        let bad = r#"
[registry]
id = "test"
version = "0.0.1"

[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"

[[object]]
id = "test:treasure"
primitive = "pickup"
label = "Treasure"

[[biome]]
id = "test:biome.forest"
label = "Forest A"
mix = [{ terrain = "forest", weight = 1.0 }]

[[biome]]
id = "test:biome.forest"
label = "Forest B (duplicate id)"
mix = [{ terrain = "grass", weight = 1.0 }]
"#;
        let err = Registry::from_toml_str(bad).expect_err(
            "duplicate biome id must fail registry load");
        match err {
            RegistryError::Validation(msg) => {
                assert!(msg.contains("duplicate biome id"),
                    "msg missing 'duplicate biome id': {msg}");
                assert!(msg.contains("test:biome.forest"),
                    "msg must name the duplicated id: {msg}");
            }
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[test]
    fn registry_rejects_biome_with_malformed_mix() {
        // LOW-3 companion — make sure the biome-load path actually
        // invokes `BiomeThemeDef::validate()` (not just id checks). A
        // theme with an unknown terrain tag must fail registry-load,
        // wrapping the BiomeThemeError into RegistryError::Validation.
        let bad = r#"
[registry]
id = "test"
version = "0.0.1"

[[terrain]]
id = "test:grass"
primitive = "land"
label = "Grass"

[[object]]
id = "test:treasure"
primitive = "pickup"
label = "Treasure"

[[biome]]
id = "test:biome.bad"
label = "Bad"
mix = [{ terrain = "atmosphere", weight = 1.0 }]
"#;
        let err = Registry::from_toml_str(bad).expect_err(
            "biome with unknown terrain tag must fail registry load");
        match err {
            RegistryError::Validation(msg) => {
                assert!(msg.contains("test:biome.bad"),
                    "msg must name the offending biome id: {msg}");
                assert!(msg.contains("atmosphere"),
                    "msg must name the offending terrain tag: {msg}");
            }
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[test]
    fn load_default_registry_succeeds() {
        let reg = Registry::load_default().expect("default registry must load");
        assert_eq!(reg.reference().id, "lw");
        assert!(!reg.reference().version.is_empty());
        // Sanity bounds — exact count asserted below.
        assert!(reg.terrain_count() >= 6, "expected at least 6 terrain kinds");
        assert!(reg.object_count() >= 9, "expected at least 9 object kinds");
    }

    #[test]
    fn default_registry_covers_all_v1_terrain_kinds() {
        // The 10 V1 TerrainKind variants — every one must resolve to a tag
        // under the `lw:` namespace, all mapped to a sensible primitive.
        let reg = Registry::load_default().unwrap();
        for tag in [
            "lw:grass",
            "lw:forest",
            "lw:mountain",
            "lw:water",
            "lw:sand",
            "lw:snow",
            "lw:swamp",
            "lw:road",
            "lw:rough",
            "lw:subterranean",
        ] {
            assert!(reg.get_terrain(tag).is_some(), "missing terrain tag {tag}");
        }
    }

    #[test]
    fn default_registry_covers_all_v1_object_kinds() {
        let reg = Registry::load_default().unwrap();
        // 9 V1 TilemapObjectKind + 9 BiomeObjectType subtypes
        for tag in [
            "lw:treasure",
            "lw:monster_lair",
            "lw:town",
            "lw:mine",
            "lw:landmark",
            "lw:monolith",
            "lw:decoration",
            "lw:ferry",
            "lw:obstacle.mountain",
            "lw:obstacle.tree",
            "lw:obstacle.lake",
            "lw:obstacle.crater",
            "lw:obstacle.rock",
            "lw:obstacle.plant",
            "lw:obstacle.structure",
            "lw:obstacle.animal",
            "lw:obstacle.other",
        ] {
            assert!(reg.get_object(tag).is_some(), "missing object tag {tag}");
        }
    }

    #[test]
    fn terrain_primitives_match_v1_semantics() {
        let reg = Registry::load_default().unwrap();
        // Walkable land variants
        for tag in ["lw:grass", "lw:forest", "lw:sand", "lw:snow", "lw:swamp", "lw:rough", "lw:subterranean"] {
            assert_eq!(reg.get_terrain(tag).unwrap().primitive, TerrainPrimitive::Land, "{tag} should be Land");
        }
        // Road is Path (carries road semantics; rendered as polyline overlay)
        assert_eq!(reg.get_terrain("lw:road").unwrap().primitive, TerrainPrimitive::Path);
        // Water is Water (bridge/ford crossings)
        assert_eq!(reg.get_terrain("lw:water").unwrap().primitive, TerrainPrimitive::Water);
        // Mountain TERRAIN is Land (walkable region with movement penalty).
        // Mountain OBJECT (`lw:obstacle.mountain`) is Blocker.
        assert_eq!(reg.get_terrain("lw:mountain").unwrap().primitive, TerrainPrimitive::Land);
    }

    #[test]
    fn object_primitives_match_v1_semantics() {
        let reg = Registry::load_default().unwrap();
        assert_eq!(reg.get_object("lw:treasure").unwrap().primitive, ObjectPrimitive::Pickup);
        assert_eq!(reg.get_object("lw:monster_lair").unwrap().primitive, ObjectPrimitive::Spawner);
        assert_eq!(reg.get_object("lw:town").unwrap().primitive, ObjectPrimitive::Habitable);
        assert_eq!(reg.get_object("lw:mine").unwrap().primitive, ObjectPrimitive::Habitable);
        assert_eq!(reg.get_object("lw:landmark").unwrap().primitive, ObjectPrimitive::Decoration);
        assert_eq!(reg.get_object("lw:monolith").unwrap().primitive, ObjectPrimitive::Trigger);
        assert_eq!(reg.get_object("lw:decoration").unwrap().primitive, ObjectPrimitive::Decoration);
        assert_eq!(reg.get_object("lw:ferry").unwrap().primitive, ObjectPrimitive::Vehicle);
        // Obstacle subtypes
        for tag in [
            "lw:obstacle.mountain",
            "lw:obstacle.tree",
            "lw:obstacle.lake",
            "lw:obstacle.crater",
            "lw:obstacle.rock",
            "lw:obstacle.plant",
            "lw:obstacle.structure",
            "lw:obstacle.animal",
            "lw:obstacle.other",
        ] {
            assert_eq!(
                reg.get_object(tag).unwrap().primitive,
                ObjectPrimitive::Blocker,
                "{tag} should be Blocker"
            );
        }
    }

    #[test]
    fn from_toml_str_round_trip_minimal() {
        let toml_text = r#"
[registry]
id = "test"
version = "0.1.0"

[[terrain]]
id = "test:land"
primitive = "land"
label = "Land"

[[object]]
id = "test:tree"
primitive = "blocker"
label = "Tree"
"#;
        let reg = Registry::from_toml_str(toml_text).unwrap();
        assert_eq!(reg.reference().id, "test");
        assert_eq!(reg.terrain_count(), 1);
        assert_eq!(reg.object_count(), 1);
    }

    #[test]
    fn empty_terrain_rejected() {
        let toml_text = r#"
[registry]
id = "bad"
version = "0.1.0"

[[object]]
id = "bad:tree"
primitive = "blocker"
label = "Tree"
"#;
        match Registry::from_toml_str(toml_text) {
            Err(RegistryError::Validation(msg)) => {
                assert!(msg.contains("terrain"), "msg = {msg}");
            }
            other => panic!("expected Validation error, got {other:?}"),
        }
    }

    #[test]
    fn duplicate_terrain_id_rejected() {
        let toml_text = r#"
[registry]
id = "dup"
version = "0.1.0"

[[terrain]]
id = "dup:x"
primitive = "land"
label = "X"

[[terrain]]
id = "dup:x"
primitive = "water"
label = "X again"

[[object]]
id = "dup:tree"
primitive = "blocker"
label = "Tree"
"#;
        match Registry::from_toml_str(toml_text) {
            Err(RegistryError::Validation(msg)) => {
                assert!(msg.contains("duplicate"), "msg = {msg}");
                assert!(msg.contains("dup:x"), "msg should name the dup id; got {msg}");
            }
            other => panic!("expected Validation error, got {other:?}"),
        }
    }

    #[test]
    fn unknown_tag_returns_none() {
        let reg = Registry::load_default().unwrap();
        assert!(reg.get_terrain("xianxia:qi-meadow").is_none());
        assert!(reg.get_object("xianxia:dao-pillar").is_none());
    }

    #[test]
    fn duplicate_object_id_rejected() {
        // /review-impl MED-4: parallel coverage with duplicate_terrain_id_rejected.
        // Same code path shape; a future copy-paste regression that broke only
        // the object branch wouldn't otherwise be caught.
        let toml_text = r#"
[registry]
id = "dup"
version = "0.1.0"

[[terrain]]
id = "dup:x"
primitive = "land"
label = "X"

[[object]]
id = "dup:tree"
primitive = "blocker"
label = "Tree"

[[object]]
id = "dup:tree"
primitive = "decoration"
label = "Tree again"
"#;
        match Registry::from_toml_str(toml_text) {
            Err(RegistryError::Validation(msg)) => {
                assert!(msg.contains("duplicate"), "msg = {msg}");
                assert!(msg.contains("dup:tree"), "msg should name the dup id; got {msg}");
            }
            other => panic!("expected Validation error, got {other:?}"),
        }
    }

    #[test]
    fn garbage_toml_returns_parse_error() {
        // /review-impl LOW-1: exercise the Parse error path.
        let garbage = "this is not valid toml { definitely ]] }}";
        match Registry::from_toml_str(garbage) {
            Err(RegistryError::Parse(_)) => {}
            other => panic!("expected Parse error, got {other:?}"),
        }
    }

    #[test]
    fn missing_file_returns_io_error() {
        // /review-impl LOW-2: exercise the Io error path.
        let nonexistent = std::path::Path::new("/this/path/does/not/exist/registry.toml");
        match Registry::load_from_path(nonexistent) {
            Err(RegistryError::Io(_)) => {}
            other => panic!("expected Io error, got {other:?}"),
        }
    }

    #[test]
    fn invalid_id_format_rejected() {
        // /review-impl MED-2: id must match ^[a-z][a-z0-9_:.-]*$
        for (bad_id, why) in [
            ("", "empty"),
            (" ", "single space"),
            ("Grass", "uppercase first"),
            ("1grass", "digit first"),
            ("lw:Grass", "uppercase later"),
            ("lw grass", "internal space"),
            ("lw/grass", "slash not allowed"),
            ("@lw:grass", "non-alpha first"),
        ] {
            let toml_text = format!(
                r#"
[registry]
id = "bad"
version = "0.1.0"

[[terrain]]
id = "{bad_id}"
primitive = "land"
label = "Bad"

[[object]]
id = "bad:tree"
primitive = "blocker"
label = "Tree"
"#
            );
            match Registry::from_toml_str(&toml_text) {
                Err(RegistryError::Validation(msg)) => {
                    assert!(
                        msg.contains("invalid") && msg.contains("id"),
                        "msg should explain id format violation for {why:?} ({bad_id:?}); got: {msg}"
                    );
                }
                other => panic!("expected Validation for {why:?} ({bad_id:?}), got {other:?}"),
            }
        }
    }

    #[test]
    fn valid_id_formats_accepted() {
        // /review-impl MED-2 positive — the legitimate id shapes used in
        // default.toml must all pass.
        for good_id in [
            "lw:grass",
            "xianxia:qi-meadow",
            "lw:obstacle.mountain",
            "noir:wet-asphalt",
            "lw:resource_node_a",
            "lw:digit9after",
        ] {
            let toml_text = format!(
                r#"
[registry]
id = "tst"
version = "0.1.0"

[[terrain]]
id = "{good_id}"
primitive = "land"
label = "Good"

[[object]]
id = "tst:tree"
primitive = "blocker"
label = "Tree"
"#
            );
            Registry::from_toml_str(&toml_text)
                .unwrap_or_else(|e| panic!("legit id {good_id:?} rejected: {e}"));
        }
    }

    #[test]
    fn zero_footprint_rejected() {
        // /review-impl MED-3: footprint area 0 is meaningless and would crash
        // placer geometry. Catch at registry-load time.
        for (w, h) in [(0, 0), (0, 4), (4, 0)] {
            let toml_text = format!(
                r#"
[registry]
id = "zero"
version = "0.1.0"

[[terrain]]
id = "zero:land"
primitive = "land"
label = "Land"

[[object]]
id = "zero:bad"
primitive = "decoration"
label = "Bad"
footprint = {{ width = {w}, height = {h} }}
"#
            );
            match Registry::from_toml_str(&toml_text) {
                Err(RegistryError::Validation(msg)) => {
                    assert!(
                        msg.contains("footprint") && msg.contains("> 0"),
                        "msg should mention footprint > 0 for {w}x{h}; got: {msg}"
                    );
                }
                other => panic!("expected Validation for {w}x{h}, got {other:?}"),
            }
        }
    }

    #[test]
    fn mask_length_mismatch_rejected() {
        // /review-impl MED-1: walkability_pattern mask length must equal
        // footprint area. Wrong length → silent per-tile mis-walkability if
        // not caught at load time.
        let toml_text = r#"
[registry]
id = "mask"
version = "0.1.0"

[[terrain]]
id = "mask:land"
primitive = "land"
label = "Land"

[[object]]
id = "mask:mine"
primitive = "habitable"
label = "Mine"
footprint = { width = 4, height = 4 }
walkability_pattern = { mask = [true, false, true, false] }
"#;
        match Registry::from_toml_str(toml_text) {
            Err(RegistryError::Validation(msg)) => {
                assert!(
                    msg.contains("mask length 4") && msg.contains("footprint area 16"),
                    "msg should name lengths; got: {msg}"
                );
            }
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[test]
    fn mask_length_matching_footprint_accepted() {
        // /review-impl MED-1 positive — 2×2 footprint + 4-bool mask passes.
        let toml_text = r#"
[registry]
id = "mask"
version = "0.1.0"

[[terrain]]
id = "mask:land"
primitive = "land"
label = "Land"

[[object]]
id = "mask:mine"
primitive = "habitable"
label = "Mine"
footprint = { width = 2, height = 2 }
walkability_pattern = { mask = [true, false, false, false] }
"#;
        Registry::from_toml_str(toml_text).expect("2x2 mask should be accepted");
    }

    #[test]
    fn io_error_via_from_impl() {
        // /review-impl COSMETIC-1 — `?` works via From<std::io::Error>.
        // Implicit conversion in load_from_path's body confirms compile-time
        // correctness; this test just exercises the wire-up at runtime.
        let err: RegistryError = std::io::Error::new(std::io::ErrorKind::NotFound, "x").into();
        assert!(matches!(err, RegistryError::Io(_)));
    }

    #[test]
    fn parse_error_via_from_impl() {
        // /review-impl COSMETIC-1 — `?` works via From<toml::de::Error>.
        let toml_err: toml::de::Error = toml::from_str::<RegistryFile>("not = }").unwrap_err();
        let err: RegistryError = toml_err.into();
        assert!(matches!(err, RegistryError::Parse(_)));
    }

    #[test]
    fn build_default_terrain_vocabulary_matches_static_helper() {
        // Drift-prevention: `Registry::build_default_terrain_vocabulary()`
        // on the default registry produces the same `Vec<TerrainCell>` as
        // `default_terrain_vocabulary()`. Engine swapped from helper to
        // registry-built in Batch 3.1c; this test guards the swap.
        let reg = Registry::load_default().unwrap();
        let from_registry = reg.build_default_terrain_vocabulary();
        let from_helper = crate::types::tile::default_terrain_vocabulary();
        assert_eq!(
            from_registry, from_helper,
            "registry-built vocab must equal static helper for default registry"
        );
        assert_eq!(from_registry.len(), 11, "11 entries: void + 10 V1 kinds");
    }

    #[test]
    fn terrain_v2_cells_match_default_registry() {
        // Drift-prevention: `TerrainKind::v2_cell()` + the
        // `default_terrain_vocabulary` must align with `default.toml`.
        // If they ever drift, terrain_vocabulary will report a
        // different primitive/tag from what the registry says — exactly
        // the silent corruption Batch 3.1 needs to avoid.
        use crate::types::tile::{default_terrain_vocabulary, TerrainKind};

        let reg = Registry::load_default().unwrap();

        // Every V1 TerrainKind variant resolves to a default.toml entry.
        for kind in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let cell = kind.v2_cell();
            let def = reg.get_terrain(&cell.tag).unwrap_or_else(|| {
                panic!("default registry missing terrain tag {:?} (kind {kind:?})", cell.tag)
            });
            assert_eq!(def.primitive, cell.primitive, "primitive drift for {kind:?}");
        }

        // Default vocabulary's V1 indexes must agree with the registry.
        let vocab = default_terrain_vocabulary();
        for kind in [
            TerrainKind::Grass,
            TerrainKind::Water,
            TerrainKind::Road,
            TerrainKind::Subterranean,
        ] {
            let cell = &vocab[kind as usize];
            let def = reg.get_terrain(&cell.tag).expect("vocab cell must be in registry");
            assert_eq!(def.primitive, cell.primitive);
        }
    }

    #[test]
    fn v2_defaults_match_default_registry() {
        // Drift-prevention: `TilemapObjectKind::v2_defaults` (used during
        // V1→V2 migration at placement-construction sites) must produce
        // the same tag + primitive + footprint as the corresponding
        // `registry/default.toml` entry. If the two ever drift, the
        // wire-shape's V2 fields would silently report something
        // different from what the registry says — perfect setup for a
        // mismatch in Batch 3.1 when placers switch to registry lookup.
        use crate::types::biome::BiomeObjectType;
        use crate::types::object::TilemapObjectKind;

        let reg = Registry::load_default().unwrap();

        // Non-obstacle kinds (no biome_object_type subtype).
        for kind in [
            TilemapObjectKind::Treasure,
            TilemapObjectKind::MonsterLair,
            TilemapObjectKind::Town,
            TilemapObjectKind::Mine,
            TilemapObjectKind::Landmark,
            TilemapObjectKind::Monolith,
            TilemapObjectKind::Decoration,
            TilemapObjectKind::Ferry,
        ] {
            let v2 = kind.v2_defaults(None);
            let def = reg.get_object(&v2.tag).unwrap_or_else(|| {
                panic!("default registry missing entry for v2 tag {:?} (kind {kind:?})", v2.tag)
            });
            assert_eq!(def.primitive, v2.primitive, "primitive drift for {kind:?}");
            assert_eq!(def.footprint, v2.footprint, "footprint drift for {kind:?}");
        }

        // Obstacle subtypes (every BiomeObjectType variant).
        for sub in [
            BiomeObjectType::Mountain,
            BiomeObjectType::Tree,
            BiomeObjectType::Lake,
            BiomeObjectType::Crater,
            BiomeObjectType::Rock,
            BiomeObjectType::Plant,
            BiomeObjectType::Structure,
            BiomeObjectType::Animal,
            BiomeObjectType::Other,
        ] {
            let v2 = TilemapObjectKind::Obstacle.v2_defaults(Some(sub));
            let def = reg.get_object(&v2.tag).unwrap_or_else(|| {
                panic!("default registry missing entry for v2 tag {:?} (subtype {sub:?})", v2.tag)
            });
            assert_eq!(def.primitive, v2.primitive, "primitive drift for obstacle.{sub:?}");
            assert_eq!(def.footprint, v2.footprint, "footprint drift for obstacle.{sub:?}");
        }
    }

    #[test]
    fn xianxia_sample_registry_loads_and_overrides_lw_tags() {
        // Batch 3.3 — proof-of-concept that a per-book registry loads from
        // disk and overrides the canonical `lw:*` tags. The xianxia sample
        // re-skins every V1 kind with thematic labels + properties while
        // keeping primitives compatible with the engine's V1 placement
        // algorithm (so e.g. `lw:water` stays `water` primitive and
        // RiverPlacer continues to work).
        let path = std::path::Path::new("registry/xianxia_sample.toml");
        let reg = Registry::load_from_path(path)
            .expect("xianxia_sample.toml must load successfully");

        assert_eq!(reg.reference().id, "xianxia");
        assert!(!reg.reference().version.is_empty());

        // Override evidence — `lw:treasure` is re-labelled "Spirit Stone Cache".
        let treasure = reg.get_object("lw:treasure").expect("lw:treasure present");
        assert_eq!(treasure.label, "Spirit Stone Cache");

        // Override evidence — `lw:grass` carries xianxia properties.
        let grass = reg.get_terrain("lw:grass").expect("lw:grass present");
        assert_eq!(grass.label, "Qi Meadow");
        let qi_density = grass.properties.get("qi_density").and_then(|v| v.as_str());
        assert_eq!(qi_density, Some("low"));

        // Primitives compatible with the engine algorithm — confirms the
        // re-skin does not break placement (water stays water, mountain
        // obstacle stays blocker = river source resolver).
        assert_eq!(
            reg.get_terrain("lw:water").unwrap().primitive,
            crate::types::primitive::TerrainPrimitive::Water
        );
        assert_eq!(
            reg.get_object("lw:obstacle.mountain").unwrap().primitive,
            crate::types::primitive::ObjectPrimitive::Blocker
        );

        // New xianxia-namespace tags exist (V3 placement engine fodder).
        for new_tag in ["xianxia:dao-stone", "xianxia:qi-spring", "xianxia:formation-array"] {
            assert!(
                reg.get_object(new_tag).is_some(),
                "xianxia sample must define {new_tag}"
            );
        }
    }

    #[test]
    fn place_tilemap_with_xianxia_registry_uses_xianxia_registry_ref() {
        // Batch 3.3 — `place_tilemap_with_registry` correctly propagates the
        // caller's registry into the resulting `TilemapView`. View shape is
        // still byte-compatible (V1 wire shape + V2 additive fields); the
        // override surface is `registry_ref` + `terrain_vocabulary` (rebuilt
        // from the per-book registry) + per-placement V2 fields (now
        // resolved against the per-book registry's overrides via
        // `resolve_object_v2`).
        use crate::engine::place_tilemap_with_registry;
        use crate::seed::TilemapSeed;
        use crate::types::channel::{ChannelId, ChannelTier};
        use crate::types::template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
        use crate::types::tilemap::GridSize;
        use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

        let xianxia = Registry::load_from_path(std::path::Path::new(
            "registry/xianxia_sample.toml",
        ))
        .expect("xianxia sample must load");

        let template = TilemapTemplate {
            template_id: TilemapTemplateId("xianxia_smoke".to_string()),
            zones: vec![
                ZoneSpec {
                    zone_id: ZoneId("z0".to_string()),
                    zone_role: ZoneRole::Wilderness,
                    size: 100,
                    terrain_types: vec![],
                    monster_strength: None,
                    connections: vec![TemplateConnection::new(
                        ZoneId("z1".to_string()),
                        PassageKind::Open,
                    )],
                    treasure_tiers: vec![],
                    biome_selection_rules: None,
                    inherit_treasure_from: None,
                    biome_theme: None,
                },
                ZoneSpec {
                    zone_id: ZoneId("z1".to_string()),
                    zone_role: ZoneRole::Hub,
                    size: 100,
                    terrain_types: vec![],
                    monster_strength: None,
                    connections: vec![],
                    treasure_tiers: vec![],
                    biome_selection_rules: None,
                    inherit_treasure_from: None,
                    biome_theme: None,
                },
            ],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
        };

        let view = place_tilemap_with_registry(
            &template,
            ChannelId("ch_xianxia".to_string()),
            ChannelTier::Town,
            GridSize { width: 32, height: 32 },
            TilemapSeed(0xCAFE_F00D),
            &xianxia,
        )
        .expect("place_tilemap_with_registry must succeed");

        // The view's `registry_ref` must match the xianxia registry's reference.
        let registry_ref = view.registry_ref.as_ref().expect("registry_ref must be present");
        assert_eq!(registry_ref.id, "xianxia");
        assert_eq!(registry_ref.version, "0.1.0");

        // The terrain vocabulary must have 11 entries (void + 10 V1 kinds),
        // each carrying the canonical `lw:*` tag (since the algorithm still
        // emits V1 u8 indexes). Per-book overrides change primitives /
        // properties but tags stay `lw:*`.
        let vocab = &view.terrain_vocabulary;
        assert_eq!(vocab.len(), 11, "vocab must be 11 entries: void + 10 V1 kinds");
        assert_eq!(vocab[1].tag, "lw:grass");
        assert_eq!(vocab[4].tag, "lw:water");
        assert_eq!(
            vocab[4].primitive,
            crate::types::primitive::TerrainPrimitive::Water,
            "xianxia water must still report Water primitive (engine compat)",
        );

        // At least one placement (the Hub zone always gets a monolith pair
        // via ConnectionsPlacer fallback or its `Open` passage; either way
        // the Wilderness + Hub generally yields some objects).
        assert!(
            !view.object_placements.is_empty(),
            "smoke template should place at least one object"
        );

        // For every placement, the V2 `tag` field must resolve to the
        // xianxia registry — confirming `resolve_object_v2` consulted the
        // per-book registry, not the default one. Spot-check that the
        // first placement's tag is a key into the xianxia registry.
        let placement = &view.object_placements[0];
        let tag = placement
            .tag
            .as_ref()
            .expect("placement.tag must be populated (V2 wire shape)");
        let def = xianxia
            .get_object(tag)
            .unwrap_or_else(|| panic!("placement tag {tag:?} must be in xianxia registry"));
        // Footprint matches the registry (xianxia overrides). For most
        // objects we kept the same 1×1 footprint, but the test asserts the
        // shape comes from the registry — not the static helper.
        assert_eq!(
            placement.footprint.as_ref().expect("footprint populated"),
            &def.footprint,
            "placement footprint must match xianxia registry entry"
        );
    }

    #[test]
    fn registry_loads_with_zone_role_colors_section() {
        // TMP-Q5 AC-ZRV-2 — a per-book registry that declares a full
        // `[registry.zone_role_colors]` block loads + flows through to
        // RegistryRef.
        let toml = r#"
[registry]
id = "xianxia"
version = "1.0.0"

[registry.zone_role_colors]
wilderness = 0xfacc15
hub = 0x818cf8
forbidden = 0xf87171
sea = 0x60a5fa

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#;
        let reg = Registry::from_toml_str(toml).expect("must load");
        let colors = reg
            .reference()
            .zone_role_colors
            .as_ref()
            .expect("zone_role_colors must be Some after declaration");
        assert_eq!(colors.wilderness, Some(0xfacc15));
        assert_eq!(colors.hub, Some(0x818cf8));
        assert_eq!(colors.forbidden, Some(0xf87171));
        assert_eq!(colors.sea, Some(0x60a5fa));
    }

    #[test]
    fn registry_loads_with_sparse_zone_role_colors() {
        // TMP-Q5 AC-ZRV-2 — partial overrides: only wilderness declared;
        // hub/forbidden/sea stay None so the frontend can fall back
        // to ZONE_ROLE_DEFAULTS per-field.
        let toml = r#"
[registry]
id = "xianxia"
version = "1.0.0"

[registry.zone_role_colors]
wilderness = 16769093

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#;
        let reg = Registry::from_toml_str(toml).expect("must load");
        let colors = reg.reference().zone_role_colors.as_ref().expect("Some");
        assert_eq!(colors.wilderness, Some(16769093));
        assert_eq!(colors.hub, None);
        assert_eq!(colors.forbidden, None);
        assert_eq!(colors.sea, None);
    }

    #[test]
    fn xianxia_sample_carries_zone_role_colors_override() {
        // TMP-Q5 chunk C — per-book demo verification: loading the
        // xianxia_sample.toml file (which declares a
        // `[registry.zone_role_colors]` block) carries all 4 fields
        // through to RegistryRef on the wire. Pins the chunk-A wire
        // shape end-to-end against the real per-book registry that
        // the FE viewer + chunk-B `zoneRoleColor` helper consume.
        let path = std::path::Path::new("registry/xianxia_sample.toml");
        let xianxia = Registry::load_from_path(path)
            .expect("xianxia_sample.toml must load successfully");
        let colors = xianxia
            .reference()
            .zone_role_colors
            .as_ref()
            .expect("xianxia_sample must declare zone_role_colors");
        assert_eq!(colors.wilderness, Some(0xfacc15), "amber-400 Spirit Wilds");
        assert_eq!(colors.hub, Some(0x4ade80), "emerald-400 Jade Court");
        assert_eq!(colors.forbidden, Some(0x9333ea), "purple-600 sealed realm");
        assert_eq!(colors.sea, Some(0x06b6d4), "cyan-500 celestial waters");
    }

    #[test]
    fn registry_loads_without_zone_role_colors_section() {
        // TMP-Q5 backward compat: a pre-Q5 TOML without the
        // `[registry.zone_role_colors]` block loads with
        // RegistryRef.zone_role_colors = None (the V2 byte-identical
        // wire path).
        let toml = r#"
[registry]
id = "test"
version = "0.0.1"

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#;
        let reg = Registry::from_toml_str(toml).expect("must load");
        assert_eq!(reg.reference().zone_role_colors, None);
    }

    #[test]
    fn registry_loads_with_inline_table_zone_role_colors() {
        // TMP-Q5 LOW-5 from chunk-A /review-impl — defensive coverage
        // of TOML inline-table syntax: a per-book author who writes
        // `registry = { ..., zone_role_colors = { wilderness = 0x... } }`
        // gets the same struct as the block form. Pins toml-rs +
        // serde's inline-table-of-table support so a future library
        // bump that breaks it fails loudly here.
        let toml = r#"
registry = { id = "inline", version = "1.0.0", zone_role_colors = { wilderness = 16769093 } }

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#;
        let reg = Registry::from_toml_str(toml).expect("inline-table TOML must load");
        let colors = reg.reference().zone_role_colors.as_ref().expect("Some");
        assert_eq!(colors.wilderness, Some(16769093));
        assert_eq!(colors.hub, None);
    }

    #[test]
    fn registry_rejects_negative_zone_role_color() {
        // TMP-Q5 MED-2 from chunk-A /review-impl — pin toml-rs behavior
        // on negative integers. Without this test pinning the reject,
        // a future toml-rs version bump that started silently
        // saturating or overflow-wrapping negatives could let garbage
        // values through the wire-shape contract.
        let toml = r#"
[registry]
id = "neg"
version = "1.0.0"

[registry.zone_role_colors]
wilderness = -1

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#;
        let result = Registry::from_toml_str(toml);
        assert!(
            result.is_err(),
            "MED-2: a negative wilderness color must be rejected at TOML \
             parse time (got Ok = silent acceptance of garbage values)",
        );
    }

    #[test]
    fn registry_rejects_overflow_zone_role_color() {
        // TMP-Q5 MED-2 from chunk-A /review-impl — pin toml-rs behavior
        // on values above u32::MAX. Same reasoning as negative: a
        // silent saturation / wrap would be a HIGH bug.
        // 5_000_000_000 > u32::MAX (4_294_967_295).
        let toml = r#"
[registry]
id = "over"
version = "1.0.0"

[registry.zone_role_colors]
wilderness = 5000000000

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#;
        let result = Registry::from_toml_str(toml);
        assert!(
            result.is_err(),
            "MED-2: an over-u32::MAX wilderness color must be rejected \
             at TOML parse time",
        );
    }

    #[test]
    fn registry_accepts_zone_role_color_at_u32_max() {
        // TMP-Q5 MED-2 — boundary test on the OK side: u32::MAX is a
        // valid 32-bit value (24-bit RGB packed with alpha bits set;
        // alpha bits are ignored at render). This pins inclusive
        // upper bound.
        let toml = format!(r#"
[registry]
id = "max"
version = "1.0.0"

[registry.zone_role_colors]
wilderness = {}

[[terrain]]
id = "test:t"
primitive = "land"
label = "T"

[[object]]
id = "test:obj"
primitive = "pickup"
label = "Obj"
"#, u32::MAX);
        let reg = Registry::from_toml_str(&toml).expect("u32::MAX must load");
        assert_eq!(
            reg.reference().zone_role_colors.as_ref().unwrap().wilderness,
            Some(u32::MAX),
        );
    }
}
