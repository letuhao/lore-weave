//! `LoadError` — every way a ruleset stack can refuse to become a reality.
//!
//! Split from `lib.rs` at `IMP-D3`'s 400-line ceiling. The seam is the one the
//! crate already implies: `lib.rs` is the LOADING PIPELINE (parse → fold →
//! validate → bind), and this is the vocabulary that pipeline refuses in. It
//! moved as one piece — the enum and its `Display` are a single artifact,
//! because a variant whose message lives in another file is a variant whose
//! message drifts.

use ruleset_core::{Floor, QuantityError, ResourceError};

use crate::validate::ValidationError;
use crate::Layer;

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
