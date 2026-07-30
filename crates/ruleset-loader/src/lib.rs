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
mod patch_resource;
mod store;
mod validate;

pub use binding::{binding_store, BindingError, BindingStore, FileBindingStore, RealityBinding};
pub use epoch::{activate_reality_epoch, prior_quantity_tables, EpochSwitchError};
pub use layer::Layer;
pub use patch::{CombatPatch, PatchError, RulesetPatch, StatPatch};
pub use patch_resource::ResourcePatch;
pub use store::{RulesetStore, StoreError};
pub use validate::{ValidationError, validate};

use std::path::Path;

use ruleset_core::{Floor, QuantityError, ResourceError, Ruleset};

/// The shipped `engine_default` artifact (RLS-D2 — *"an artifact, not prose"*).
///
/// Embedded at COMPILE time so a node with no filesystem still boots, and so
/// the file cannot drift from the binary that ships it. `engine_default_matches_the_code`
/// asserts it resolves to exactly `Ruleset::engine_default()`, which is what
/// turns every *"the engine default is X"* claim in the feature docs into an
/// assertion instead of prose.
pub const ENGINE_DEFAULT_TOML: &str = include_str!("../artifacts/engine_default.toml");

/// Why a ruleset could not be loaded.
#[derive(Debug)]
pub enum LoadError {
    /// A layer file could not be read.
    Io { layer: Layer, source: std::io::Error },
    /// A layer file is not valid TOML, or declares a key the engine does not
    /// know. An unknown key is an ERROR, not a warning: the most likely
    /// authoring mistake is a misspelling, and ignoring it means the author's
    /// edit silently does nothing while they tune the number that had no effect.
    Parse { layer: Layer, source: toml::de::Error },
    /// S1a — the layer declares a key **no layer may declare** (RLS-A4
    /// `Strategy::Forbidden`, `ruleset_core::FORBIDDEN_KEYS`).
    ///
    /// Distinct from `Parse`'s unknown-key refusal on purpose. `deny_unknown_fields`
    /// already stops these keys today, but it answers *"unknown field"* — wrong
    /// twice: the field is not unknown, and the author is not told **why** they
    /// may never set it. That guarantee is also incidental, holding only while
    /// the field happens to be absent from `RulesetPatch`, which is `NV-4`
    /// waiting to happen. Named and tested instead.
    ForbiddenField { layer: Layer, field: &'static str, reason: &'static str },
    /// The document's root is not a table. TOML has no other root shape, so
    /// this is unreachable today — it exists so that the forbidden-key scan
    /// FAILS rather than silently skipping if that ever stops being true.
    NotATable { layer: Layer },
    /// Q1 — a declared quantity is malformed, repeated within one layer, or
    /// pushes the set past this engine's ordinal capacity (QTY-A5/A6).
    Quantity { layer: Layer, source: QuantityError },
    /// Q2 — a declared POOL is malformed: it names a quantity no layer
    /// declared, repeats one, or gives bounds no actor could satisfy (QTY-A4).
    Resource { layer: Layer, source: ResourceError },
    /// **S1b — the layer-floor arm (RLS-A16), and its FIRST real subject.**
    ///
    /// 16a gives every Ruleset field a *lowest permissible layer*. Until `Q1`
    /// every field's floor was `preset` — the lowest AUTHORABLE layer — so the
    /// check could refuse nothing and was deliberately not built (`NV-2`).
    /// `quantities` is the first field where the floor bites: `engine_default`
    /// ships the engine's own vocabulary and **must not invent world content**,
    /// or every reality on this binary would silently inherit a quantity nobody
    /// declared for it.
    BelowFloor { layer: Layer, field: &'static str, floor: Floor },
    /// The resolved ruleset is not loadable (RLS-A10). Carries EVERY reason,
    /// not the first — an author fixing one number per round trip is how a
    /// validator earns the reputation that gets it bypassed.
    Invalid(Vec<ValidationError>),
}

impl core::fmt::Display for LoadError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Io { layer, source } => {
                write!(f, "layer `{}`: {source}", layer.name())
            }
            Self::Parse { layer, source } => {
                write!(f, "layer `{}`: {source}", layer.name())
            }
            Self::ForbiddenField { layer, field, reason } => {
                write!(f, "layer `{}` declares `{field}`: {reason}", layer.name())
            }
            Self::Quantity { layer, source } => {
                write!(f, "layer `{}`: {source}", layer.name())
            }
            Self::Resource { layer, source } => {
                write!(f, "layer `{}`: {source}", layer.name())
            }
            Self::BelowFloor { layer, field, floor } => write!(
                f,
                "layer `{}` declares `{field}`, but its lowest permissible layer is `{:?}` \
                 (RLS-A16). The engine default ships engine vocabulary, not world content: a \
                 quantity declared there would be inherited by every reality on this binary \
                 without any of them asking for it",
                layer.name(),
                floor
            ),
            Self::NotATable { layer } => write!(
                f,
                "layer `{}`: the document root is not a table, so its keys could not be \
                 checked against the forbidden set",
                layer.name()
            ),
            Self::Invalid(errs) => {
                writeln!(f, "ruleset is unloadable ({} problem(s)):", errs.len())?;
                for e in errs {
                    writeln!(f, "  - {e}")?;
                }
                Ok(())
            }
        }
    }
}

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
}

impl core::fmt::Display for RealityError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Load(e) => write!(f, "{e}"),
            Self::Binding(e) => write!(f, "{e}"),
            Self::Store(e) => write!(f, "{e}"),
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
        Some(r) => Ok((r, binding)),
        None => Err(RealityError::RulesetMissing {
            reality_id: reality_id.to_string(),
            digest: digest.to_hex(),
        }),
    }
}

