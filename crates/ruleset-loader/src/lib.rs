//! `ruleset-loader` — F2: rules become CONTENT.
//!
//! F1 made the digest real and the `B` slice put it in the event log. But every
//! reality still ran the SAME rules, because `Ruleset::engine_default()` is a
//! `const fn` compiled into the binary. Two consequences, both live:
//!
//! * there was no way to author a reality with different rules — the platform's
//!   entire premise;
//! * **the digest was a function of the BUILD.** A deploy changing one constant
//!   silently changed the rules of every running reality, and the old ruleset
//!   existed nowhere to recover to.
//!
//! This crate is the I/O half `ruleset-core` deliberately has none of: the
//! RLS-A3 layer stack, TOML artifacts, load-time validation (RLS-A10), and the
//! content-addressed immutable store (RLS-D6/D18).
//!
//! **IMP-D2 — the laws must not depend on this crate.** They take a resolved
//! `&Rules` by reference and know nothing about where it came from. A law that
//! can read a file is a law that can be slow, fallible and untestable.
//!
//! ## What F2 deliberately does not build yet
//!
//! Tombstones (RLS-A5) and `UnionById*` (RLS-A4) operate on COLLECTIONS, and
//! `Ruleset` has none — F1 shipped only the two groups the laws actually read.
//! Building them now would be a mechanism with no consumer, which is the same
//! mistake as adding a `Manifest` with no resolver. They land with the first
//! collection field. Likewise the `(RealityId, Epoch)` registry (RLS-A11, needs
//! multi-reality hosting), presets as a scoped DB resource (RLS-D19), and
//! `forge_override` as an ordered event (§9, needs epoch-switch-as-ingress).

mod binding;
mod epoch;
mod layer;
mod patch;
mod labels;
mod patch_progression;
mod resolve_pin;
mod patch_resource;
mod progression_store;
mod store;
mod validate;

pub use binding::{binding_store, BindingError, BindingStore, FileBindingStore, RealityBinding};
pub use epoch::{activate_reality_epoch, prior_quantity_tables, EpochSwitchError};
pub use layer::Layer;
pub use patch::{CombatPatch, PatchError, RulesetPatch, StatPatch};
pub use labels::{Label, LabelError, LabelStore, ProgressionLabels};
pub use patch_progression::{ProgressionKindPatch, ProgressionPatchError, TierPatch};
pub use resolve_pin::resolve_and_pin;
pub use patch_resource::ResourcePatch;
pub use progression_store::{
    resolve_progression, ProgressionStore, ProgressionStoreError,
};
pub use store::{RulesetStore, StoreError};
pub use validate::{ValidationError, validate};

use std::path::Path;

use ruleset_core::{Floor, Ruleset};

/// The shipped `engine_default` artifact (RLS-D2 — *"an artifact, not prose"*).
///
/// Embedded at COMPILE time so a node with no filesystem still boots, and so
/// the file cannot drift from the binary that ships it. `engine_default_matches_the_code`
/// asserts it resolves to exactly `Ruleset::engine_default()`, which is what
/// turns every *"the engine default is X"* claim in the feature docs into an
/// assertion instead of prose.
pub const ENGINE_DEFAULT_TOML: &str = include_str!("../artifacts/engine_default.toml");

mod preset;
pub use preset::{proving_ground, PROVING_GROUND_TOML};

mod error;
pub use error::LoadError;

/// One layer of the stack, as gathered for resolution.
#[derive(Debug, Clone)]
pub struct LayerSource {
    pub layer: Layer,
    pub patch: RulesetPatch,
}

/// Parse a TOML layer document.
///
/// **Two passes over one parse (S1a).** The document becomes a `toml::Value`
/// first so the `Forbidden` keys can be refused with a diagnostic that names
/// the field and the reason, *before* `deny_unknown_fields` gets to answer
/// "unknown field" — which is the wrong answer to a key that is very well
/// known and simply not the author's to set.
///
/// The rejected alternative was adding `schema_version`/`law_version` to
/// `RulesetPatch` so the validator could see them. That would make
/// `missing_fields`' totality check demand them in `engine_default.toml`:
/// **adding a field so it can be declared, in order to refuse declaring it.**
pub fn parse_layer(layer: Layer, toml_src: &str) -> Result<LayerSource, LoadError> {
    // Pass 1 — a permissive `Value`, ONLY to answer "does this document declare a
    // forbidden key?". Nothing is built from it.
    let doc: toml::Value =
        toml::from_str(toml_src).map_err(|source| LoadError::Parse { layer, source })?;
    // `as_table()` on a parsed TOML root cannot be `None` — the format has no
    // other root shape. Written as an explicit refusal rather than
    // `if let Some(t) = … {}` because that form makes the failure case **skip
    // the check silently**: if the assumption ever stopped holding, every
    // forbidden key would be quietly admitted and the gate would report nothing.
    // A guard whose else-branch is "do nothing" is not a guard.
    let table = doc.as_table().ok_or(LoadError::NotATable { layer })?;
    for (field, reason) in ruleset_core::FORBIDDEN_KEYS {
        if table.contains_key(*field) {
            return Err(LoadError::ForbiddenField { layer, field, reason });
        }
    }

    // Pass 2 — deserialize from the STRING, not from `doc`.
    //
    // **This costs a second parse and buys back the error spans.** Deserializing
    // the already-parsed `Value` looked free and silently destroyed every
    // diagnostic in this path: `toml`'s spans live on the source text, so
    // `Value -> T` reports
    //
    //     unknown field `max_hitt`, expected one of ... in `combat`
    //
    // where parsing the string reports
    //
    //     TOML parse error at line 4, column 1
    //       |
    //     4 | max_hitt = 9
    //       | ^^^^^^^^
    //
    // The module doc above justifies `deny_unknown_fields` by *"turning twenty
    // minutes of confusion into one line of diagnostic"* — so losing the line
    // number defeats the reason the refusal exists. Nothing caught it either:
    // `a_misspelled_key_is_refused_not_ignored` only asserts the key NAME is in
    // the message, which stayed true. `a_bad_key_is_reported_with_its_LINE` now
    // pins the span itself.
    //
    // The cost is one extra parse of a small file on the COLD path — layers are
    // resolved once at reality creation (RLS-A3 early binding), never in a step.
    let patch: RulesetPatch =
        toml::from_str(toml_src).map_err(|source| LoadError::Parse { layer, source })?;
    Ok(LayerSource { layer, patch })
}

/// Read a layer document from disk.
pub fn read_layer(layer: Layer, path: &Path) -> Result<LayerSource, LoadError> {
    let src = std::fs::read_to_string(path).map_err(|source| LoadError::Io { layer, source })?;
    parse_layer(layer, &src)
}

/// Fold the stack into one immutable resolved ruleset (RLS-A3 early binding).
///
/// Layers are applied in **ascending priority**, so a higher layer wins. The
/// caller's slice order is irrelevant — the sort is done here, because relying
/// on callers to pass layers in the right order is exactly the kind of
/// unenforced ordering contract that produces a bug nobody can see in a diff.
///
/// Validation runs on the RESOLVED ruleset, not per layer: a layer is a partial
/// override and may legitimately set `hit_floor_pm` above the *default*
/// ceiling while a lower-priority layer has already raised that ceiling. Only
/// the fold is a ruleset.
pub fn resolve(layers: &[LayerSource]) -> Result<Ruleset, LoadError> {
    let mut ordered: Vec<&LayerSource> = layers.iter().collect();
    ordered.sort_by_key(|l| l.layer.priority());

    let mut out = Ruleset::engine_default();
    for l in ordered {
        // S1b floor arm — checked BEFORE the merge, so the diagnostic names the
        // layer that overstepped rather than the resolved result, which by then
        // has lost track of who contributed what.
        if !l.patch.quantities.is_empty() && l.layer.priority() < Layer::Preset.priority() {
            return Err(LoadError::BelowFloor {
                layer: l.layer,
                field: "quantities",
                floor: Floor::Preset,
            });
        }
        // Q2 — the same floor, for the same reason. `resources` sits on the
        // preset floor because a pool is L2 CONTENT: the engine default must not
        // ship one, or every reality in existence would carry a pool it never
        // declared and could not remove (QTY-A10(c) forbids removal).
        if !l.patch.resources.is_empty() && l.layer.priority() < Layer::Preset.priority() {
            return Err(LoadError::BelowFloor {
                layer: l.layer,
                field: "resources",
                floor: Floor::Preset,
            });
        }
        // PGN-R2b — a progression kind folds into a TABLE, and this call has no
        // store to put one in. Refused rather than ignored: dropping the rows
        // would lose the author's entire ladder with the run staying green,
        // which is the QTY-Q5 class this whole tier exists to refuse.
        if !l.patch.progression_kinds.is_empty() {
            return Err(LoadError::ProgressionNeedsStore {
                layer: l.layer,
                kinds: l.patch.progression_kinds.len(),
            });
        }
        l.patch.apply(&mut out).map_err(|e| match e {
            patch::PatchError::Quantity(source) => LoadError::Quantity { layer: l.layer, source },
            patch::PatchError::Resource(source) => LoadError::Resource { layer: l.layer, source },
        })?;
    }

    validate(&out).map_err(LoadError::Invalid)?;
    Ok(out)
}

/// Resolve the engine default from its shipped artifact.
pub fn engine_default_from_artifact() -> Result<Ruleset, LoadError> {
    let base = parse_layer(Layer::EngineDefault, ENGINE_DEFAULT_TOML)?;
    resolve(&[base])
}


// ── the two paths doc 16 §12 draws as separate columns ──────────────────────

/// Why a reality could not be created or loaded.
#[derive(Debug)]
pub enum RealityError {
    Load(LoadError),
    Binding(BindingError),
    Store(StoreError),
    /// The reality is bound to a digest the content store does not have.
    ///
    /// RLS-D12 quarantine, and the honest diagnosis: the rules this reality was
    /// created with are GONE, so it cannot be resumed without reinterpreting it
    /// under different rules — which is the one thing the whole design forbids.
    /// (RLS-D6 is why: the store is append-only and never pruned *because* of
    /// this. A missing digest means someone pruned it or the store moved.)
    RulesetMissing { reality_id: String, digest: String },
    /// The ruleset resolves, and the progression table it PINS does not.
    ///
    /// A separate variant from `RulesetMissing` because the diagnosis differs:
    /// the rules are here and readable, and the ladders they name are gone. A
    /// reality in that state is unloadable in exactly the same way, and saying
    /// so is the whole point — the alternative is a world that boots with every
    /// progression system silently missing.
    Progression(ProgressionStoreError),
    /// The progression table resolves and its NAMES do not (`PGN-A18`).
    ///
    /// A separate variant because the diagnosis and the fix differ: the rules
    /// and the ladder are both intact, and the content that makes the ladder
    /// legible to a player is missing. Fixing it moves no digest.
    Labels(LabelError),
}

impl core::fmt::Display for RealityError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Load(e) => write!(f, "{e}"),
            Self::Binding(e) => write!(f, "{e}"),
            Self::Store(e) => write!(f, "{e}"),
            Self::Progression(e) => write!(f, "{e}"),
            Self::Labels(e) => write!(f, "{e}"),
            Self::RulesetMissing { reality_id, digest } => write!(
                f,
                "reality {reality_id} is UNLOADABLE: it is bound to ruleset {digest}, \
                 which the content store does not have. The rules it was created with \
                 are gone; resuming would mean running it under rules its log does not \
                 describe. The store is append-only and never pruned for exactly this \
                 reason (RLS-D6)"
            ),
        }
    }
}

impl From<LoadError> for RealityError {
    fn from(e: LoadError) -> Self {
        Self::Load(e)
    }
}
impl From<BindingError> for RealityError {
    fn from(e: BindingError) -> Self {
        Self::Binding(e)
    }
}
impl From<StoreError> for RealityError {
    fn from(e: StoreError) -> Self {
        Self::Store(e)
    }
}

/// **CREATE** — resolve the layer stack ONCE, validate it, store the bytes, and
/// bind the reality to their digest (doc 16 §12, left column).
///
/// This is the only path that reads layer files. Failure here is a **rejected
/// request** with an author sitting in front of it — the reality is never
/// created, as opposed to created-and-unloadable. Doc 16 calls that asymmetry
/// deliberate.
///
/// Refuses a second creation: RLS-A3 binds early and ONCE. Changing a live
/// reality's rules is an epoch switch, an ordered event (doc 16 §9), not a
/// re-create — and a silent re-resolve is precisely the bug this split closes.
pub fn create_reality(
    reality_id: &str,
    layers: &[LayerSource],
    store: &RulesetStore,
    bindings: &dyn BindingStore,
) -> Result<(Ruleset, RealityBinding), RealityError> {
    let resolved = resolve(layers)?;
    admit_progression(&resolved, store)?;
    let digest = store.put(&resolved)?;
    let binding = bindings.create(reality_id, &digest)?;
    Ok((resolved, binding))
}

/// **LOAD** — fetch the exact bytes this reality was created with (doc 16 §12,
/// right column).
///
/// **It does not look at a layer file at all.** That is the entire point: an
/// edit to `reality.toml`, or a deploy that changes `engine_default`, must not
/// change a reality that already exists. Before this split, `spine` re-resolved
/// at every start and both of those silently did.
///
/// Failure here is an **operational state** with players sitting in front of
/// it: this reality is `Unloadable`, its neighbours on the same node are
/// unaffected (RLS-D12).
pub fn load_reality(
    reality_id: &str,
    store: &RulesetStore,
    bindings: &dyn BindingStore,
) -> Result<(Ruleset, RealityBinding), RealityError> {
    // THE WHOLE BINDING, not just its digest.
    //
    // This used to call `digest_for` and return `(Ruleset, RulesetDigest)`,
    // throwing the EPOCH away — and `Island::new` then hardcoded epoch 1. So a
    // reality bound at epoch 5 produced an island claiming epoch 1, and
    // `RLS-I1` monotonicity was computed against 1: a redelivered switch to
    // epoch 3 would be ACCEPTED, moving the island onto rules the reality had
    // already moved past. The guard that exists to stop exactly that was
    // defeated by the constructor.
    //
    // Two individually correct decisions - the binding carries the epoch, a
    // fresh island starts at 1 - which together defeat a check. That is the
    // NV-4 shape, and the reason the epoch now travels WITH the rules rather
    // than being defaulted at the far end.
    let binding = bindings
        .load(reality_id)?
        .ok_or_else(|| RealityError::Binding(BindingError::NotBound {
            reality_id: reality_id.to_string(),
        }))?;
    let digest = ruleset_core::RulesetDigest::from_hex(&binding.digest).ok_or_else(|| {
        RealityError::Binding(BindingError::BadDigest(binding.digest.clone()))
    })?;
    match store.get(&digest)? {
        Some(r) => {
            admit_progression(&r, store)?;
            Ok((r, binding))
        }
        None => Err(RealityError::RulesetMissing {
            reality_id: reality_id.to_string(),
            digest: digest.to_hex(),
        }),
    }
}

/// **Every admission point resolves every pin the ruleset carries.**
///
/// `RulesetStore::get` verifies the OUTER artifact only — a `Ruleset` whose
/// `progression` pin names absent or corrupt bytes comes back from it clean,
/// because the pin is 32 bytes *inside* the bytes that verified. So each of the
/// three entry points that admits a ruleset into a reality — `create_reality`,
/// `load_reality`, `activate_reality_epoch` — calls this.
///
/// **This function exists because the check it performs already existed and was
/// never called.** `resolve_progression` shipped with 12 tests, a module doc
/// arguing for it, and ZERO production callers; a probe showed
/// `activate_reality_epoch` moving a reality to epoch 2 onto a ruleset whose
/// ladder had been deleted, returning `Ok`. A mechanism nothing invokes is not a
/// mechanism — it is a claim with a test suite attached.
pub(crate) fn admit_progression(
    ruleset: &Ruleset,
    store: &RulesetStore,
) -> Result<(), RealityError> {
    let progression = ProgressionStore::beside(store);
    let Some(table) = resolve_progression(ruleset, &progression).map_err(RealityError::Progression)?
    else {
        return Ok(()); // declares no progression; there is nothing to name
    };
    // PGN-A18 / T10. Doc 39 shipped this as NOT ENFORCED and it stayed that way
    // through three slices: a reality could load a 24-tier ladder with no names
    // and show a player `tier_9`. Labels are NOT hashed, so this refusal costs
    // no digest and a fix disturbs no running world.
    LabelStore::beside(store)
        .admit(&ruleset.progression.expect("a resolved table implies a pin"), &table)
        .map(|_| ())
        .map_err(RealityError::Labels)
}

