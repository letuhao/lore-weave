//! The shipped content PRESET — the smallest reality that is actually runnable.
//!
//! Split out of `lib.rs` at `IMP-D3`'s 400-line ceiling. The seam is real and
//! not a line-count dodge: everything in `lib.rs` is MECHANISM (parse a layer,
//! fold a stack, validate the result); this file is CONTENT, and it is the only
//! file in the crate that is. They change for entirely different reasons — a new
//! quantity edits this file and nothing else.

use crate::{parse_layer, resolve, Layer, LoadError, ENGINE_DEFAULT_TOML};
use ruleset_core::Ruleset;

/// The `proving-ground` PRESET — the smallest reality that is actually runnable.
///
/// **`M1`.** `engine_default` declares no quantities and no pools, deliberately
/// (`QTY-A10(c)`: a pool in the engine default enters every reality forever and
/// can never be removed). So it cannot bind the three engine roles a law needs,
/// and a binary running on it has laws with no numbers. This preset is the
/// content that makes one runnable, and it is the reality the demo binaries and
/// the domain tests use.
///
/// Embedded for the same reason `ENGINE_DEFAULT_TOML` is: a node with no
/// filesystem still boots, and the file cannot drift from the binary.
///
/// **It is CONTENT, not engine configuration.** Everything it names —
/// `vitality`, `swiftness`, `breath` — is an author's vocabulary; the engine
/// only ever asks for a role. That distinction is what `M1` exists to establish,
/// and `scripts/engine-vocabulary-gate.py` is what enforces it.
pub const PROVING_GROUND_TOML: &str =
    include_str!("../artifacts/presets/proving-ground.toml");

/// Resolve the [`PROVING_GROUND_TOML`] preset over the engine default.
///
/// The whole layer stack, in the shape a real reality creation uses — so a
/// consumer of this cannot accidentally take a shortcut the production path
/// does not have.
pub fn proving_ground() -> Result<Ruleset, LoadError> {
    resolve(&[
        parse_layer(Layer::EngineDefault, ENGINE_DEFAULT_TOML)?,
        parse_layer(Layer::Preset, PROVING_GROUND_TOML)?,
    ])
}
