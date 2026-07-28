//! RLS-A3 **early binding** — which ruleset a reality is bound to, durably.
//!
//! ## The hole this closes
//!
//! F2.1 let a reality load rules from a file, and then **re-resolved that file
//! at every start**. So an edit to the TOML — or a deploy that changed
//! `engine_default` — silently changed the rules of a reality that was already
//! running. The store had the old bytes; nothing read them. That is the exact
//! configuration trap RLS-A13 exists to close, reintroduced one layer up by the
//! thing meant to close it.
//!
//! Doc 16 §12 draws the two columns as separate for precisely this reason:
//!
//! ```text
//! reality creation                     island Cold -> Hot
//! ────────────────                     ──────────────────
//!  gather layers 0..40                  read the reality's current
//!  merge, normalize, validate           (reality_id, epoch)
//!  BLAKE3 over canonical encoding       registry: Arc<RealityRuleset>
//!  store immutably; assign epoch 1      construct the island with it
//! ```
//!
//! **Creation resolves. Load does not.** A binding is the arrow between them.
//!
//! > **RLS-A3:** *at reality creation the stack is resolved top-to-bottom,
//! > validated, normalized, hashed, and stored as an immutable resolved
//! > ruleset. A later edit to the `wuxia` preset never touches a reality that
//! > already exists. Replay-safety is then STRUCTURAL rather than procedural:
//! > there is no path by which a reality's rules change without an event in its
//! > own log.*
//!
//! ## Why this is NOT in the content-addressed store
//!
//! A binding is **mutable state** — it moves when an epoch switch happens. The
//! store holds immutable bytes addressed by their own hash. Putting a mutable
//! pointer inside a content-addressed directory is a category error: the thing
//! whose whole guarantee is *"these bytes never change"* would contain
//! something that must.
//!
//! ## Where it will eventually live
//!
//! `reality_registry` in the meta DB, beside the lifecycle `status` the append
//! guard already reads — a reality's ruleset binding is reality-level state and
//! belongs with the rest of it. It is a file here because `commit-service`'s
//! spine has no meta pool (it takes only a per-reality `--pg-url`), and
//! inventing that wiring to store two fields would be the larger change. The
//! surface is `create` / `load`; moving it behind a table touches this file.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use ruleset_core::{RulesetDigest, RulesetEpoch};
use serde::{Deserialize, Serialize};

/// What a reality is bound to.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RealityBinding {
    pub reality_id: String,
    /// RLS-A13 — ordering, not identity. Monotonic per reality; the first
    /// binding is epoch 1, matching doc 16 §12's *"assign epoch 1"*.
    pub epoch: u32,
    /// The resolved ruleset's content digest, 64 lowercase hex. This is the
    /// ONLY thing the load path needs — everything else is fetched from the
    /// content store by it.
    pub digest: String,
}

#[derive(Debug)]
pub enum BindingError {
    Io(io::Error),
    /// A reality already has a binding. **Creation happens once** (RLS-A3 early
    /// binding); re-creating would silently re-resolve, which is the whole bug
    /// this module exists to prevent. Changing a live reality's rules is an
    /// epoch switch, which is an ordered EVENT (doc 16 §9), not a re-create.
    AlreadyBound { reality_id: String, existing: String },
    /// The reality has no binding — it was never created.
    NotBound { reality_id: String },
    /// The binding file is corrupt.
    Malformed { reality_id: String, detail: String },
    /// A digest string that is not 64 lowercase hex.
    BadDigest(String),
}

impl core::fmt::Display for BindingError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "reality binding I/O: {e}"),
            Self::AlreadyBound { reality_id, existing } => write!(
                f,
                "reality {reality_id} is already bound to {existing}: creation happens \
                 ONCE (RLS-A3). Changing a live reality's rules is an epoch switch, \
                 which is an ordered event - not a re-create"
            ),
            Self::NotBound { reality_id } => write!(
                f,
                "reality {reality_id} has no ruleset binding - it was never created. \
                 Create it first (which resolves, validates and stores its ruleset); \
                 loading must never re-resolve"
            ),
            Self::Malformed { reality_id, detail } => {
                write!(f, "reality {reality_id} binding is corrupt: {detail}")
            }
            Self::BadDigest(s) => write!(f, "not a ruleset digest: {s}"),
        }
    }
}

impl From<io::Error> for BindingError {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}

fn parse_digest(hex: &str) -> Result<RulesetDigest, BindingError> {
    if hex.len() != 64 || !hex.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)) {
        return Err(BindingError::BadDigest(hex.to_string()));
    }
    let mut out = [0u8; 32];
    for (i, b) in out.iter_mut().enumerate() {
        *b = u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16)
            .map_err(|_| BindingError::BadDigest(hex.to_string()))?;
    }
    Ok(RulesetDigest(out))
}

/// Durable `reality -> ruleset digest` bindings, one small TOML per reality.
#[derive(Debug, Clone)]
pub struct BindingStore {
    root: PathBuf,
}

impl BindingStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    fn path_for(&self, reality_id: &str) -> PathBuf {
        self.root.join(format!("{reality_id}.toml"))
    }

    /// Bind a reality to a resolved ruleset. **Refuses if already bound.**
    pub fn create(
        &self,
        reality_id: &str,
        digest: &RulesetDigest,
    ) -> Result<RealityBinding, BindingError> {
        fs::create_dir_all(&self.root)?;
        let path = self.path_for(reality_id);
        if path.exists() {
            let existing = self
                .load(reality_id)?
                .map(|b| b.digest)
                .unwrap_or_else(|| "<unreadable>".into());
            return Err(BindingError::AlreadyBound {
                reality_id: reality_id.to_string(),
                existing,
            });
        }
        let binding = RealityBinding {
            reality_id: reality_id.to_string(),
            epoch: RulesetEpoch(1).0,
            digest: digest.to_hex(),
        };
        let body = format!(
            "# RLS-A3 early binding: which ruleset THIS reality resolved to, once.\n\
             # The load path reads the digest and fetches those exact bytes from the\n\
             # content store. It does NOT re-resolve the layer files - editing them\n\
             # after creation must not change a reality that already exists.\n\
             {}",
            toml::to_string(&binding).map_err(|e| BindingError::Malformed {
                reality_id: reality_id.to_string(),
                detail: e.to_string(),
            })?
        );
        fs::write(&path, body)?;
        Ok(binding)
    }

    /// Read a reality's binding. `Ok(None)` = never created.
    pub fn load(&self, reality_id: &str) -> Result<Option<RealityBinding>, BindingError> {
        let path = self.path_for(reality_id);
        let src = match fs::read_to_string(&path) {
            Ok(s) => s,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e.into()),
        };
        let b: RealityBinding =
            toml::from_str(&src).map_err(|e| BindingError::Malformed {
                reality_id: reality_id.to_string(),
                detail: e.to_string(),
            })?;
        Ok(Some(b))
    }

    /// The digest a reality is bound to, or [`BindingError::NotBound`].
    pub fn digest_for(&self, reality_id: &str) -> Result<RulesetDigest, BindingError> {
        match self.load(reality_id)? {
            Some(b) => parse_digest(&b.digest),
            None => Err(BindingError::NotBound { reality_id: reality_id.to_string() }),
        }
    }
}

/// Convenience for callers that hold a `&Path` root.
pub fn binding_store(root: &Path) -> BindingStore {
    BindingStore::new(root)
}
