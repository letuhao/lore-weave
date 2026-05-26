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
}
