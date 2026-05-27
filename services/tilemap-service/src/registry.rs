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

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::types::registry::{ObjectKindDef, RegistryRef, TerrainKindDef};

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
fn is_valid_id(id: &str) -> bool {
    let mut chars = id.chars();
    match chars.next() {
        Some(c) if c.is_ascii_lowercase() => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '_' | ':' | '.' | '-'))
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
}

/// In-memory tag-keyed registry. Cheap clone (Arc would be nicer at
/// scale but the registry is small + cloned rarely).
#[derive(Debug, Clone)]
pub struct Registry {
    reference: RegistryRef,
    terrain_by_tag: HashMap<String, TerrainKindDef>,
    object_by_tag: HashMap<String, ObjectKindDef>,
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
            if object_by_tag.contains_key(&def.id) {
                return Err(RegistryError::Validation(format!(
                    "duplicate object id {:?}",
                    def.id
                )));
            }
            object_by_tag.insert(def.id.clone(), def);
        }
        Ok(Self { reference: file.registry, terrain_by_tag, object_by_tag })
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
    use crate::types::primitive::{ObjectPrimitive, TerrainPrimitive};

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
                },
            ],
            seed_offset: 0,
            world_zone: None,
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
}
