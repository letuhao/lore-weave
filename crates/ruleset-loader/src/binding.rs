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
//! ## Where it lives — and the guess this paragraph used to make was wrong
//!
//! This said *"`reality_registry` in the meta DB, beside the lifecycle `status`
//! … it is a file here because `commit-service`'s spine has no meta pool."* The
//! second half was true and `Q1 B2b` fixed it ([`BindingStore`] is now a trait;
//! `commit-service::pg_binding` is the Postgres implementation, selected by
//! `--meta-url`). **The first half was wrong in a load-bearing way.**
//!
//! `reality_registry` is one row per reality, so putting the binding there means
//! one MUTABLE `ruleset_digest` column — and an epoch switch would overwrite the
//! previous epoch's digest. That history is exactly what `QTY-A5`'s *"an ordinal
//! is never reused on removal"* is computed over: the high-water ordinal is
//! `max(n)` across the rulesets of **every** prior epoch, and each is reachable
//! only through the digest that addressed it. Overwriting the column loses the
//! only pointer to a ruleset whose ordinals are still referenced by committed
//! events.
//!
//! So the table is `reality_ruleset_binding` (`migrations/meta/033`): one row
//! per epoch, append-only, enforced by an `ENABLE ALWAYS` trigger. That is the
//! answer `QTY-Q6` closed with — a *different* answer from the one doc 35 §4.6
//! proposed, and the reason the difference matters is written above.
//!
//! The FILE implementation stays. It is what every test here, and every offline
//! tool, wants: no container, no pool, no fixture.

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


/// Where a reality's binding lives — **the seam this module was written to
/// have**, and the file impl is now one implementation of it rather than the
/// only shape.
///
/// The doc comment above used to end *"it is a file here because
/// `commit-service`'s spine has no meta pool … the surface is `create`/`load`,
/// and moving it behind a table touches this file."* This is that move. The
/// file impl stays because it is what every loader test and every offline tool
/// wants: no Postgres, no container, no fixture.
///
/// **Deliberately synchronous.** The Postgres implementation lives in
/// `commit-service` — the crate that already owns sqlx and tokio — so this
/// crate keeps its three dependencies and a law still cannot reach a socket
/// through it (`IMP-D2`, `crate-purity-gate`).
pub trait BindingStore {
    /// Bind a reality to a resolved ruleset. **Refuses if already bound**
    /// (`RLS-A3` binds early and once).
    fn create(
        &self,
        reality_id: &str,
        digest: &RulesetDigest,
    ) -> Result<RealityBinding, BindingError>;

    /// Read a reality's CURRENT binding — the newest epoch. `Ok(None)` = never
    /// created.
    fn load(&self, reality_id: &str) -> Result<Option<RealityBinding>, BindingError>;

    /// **Every** epoch this reality has ever been bound to, ASCENDING.
    ///
    /// Not a convenience. `QTY-A5`'s never-reuse arm is computed over the union
    /// of *every* prior epoch, not the previous one — an ordinal freed at epoch
    /// 2 is still not available at epoch 3, because epoch 1's committed events
    /// still mean the old quantity by that number. Checking only against the
    /// current binding finds the ordinal free and hands it out, which is the
    /// trap `an_ordinal_freed_two_epochs_ago_is_still_not_available` exists to
    /// name. **This method is why the binding is one row per epoch instead of
    /// one mutable column** (`QTY-Q6`).
    fn history(&self, reality_id: &str) -> Result<Vec<RealityBinding>, BindingError>;

    /// Append the next epoch, binding the reality to `digest`.
    ///
    /// **Durability only — this method enforces no law.** The never-reuse
    /// refusal lives one layer up in [`crate::activate_reality_epoch`], which
    /// can reach the content store to fetch the prior rulesets the check needs.
    /// A store that tried to enforce it would have to load rulesets, which is
    /// how a storage seam grows a dependency on everything.
    ///
    /// Refuses [`BindingError::NotBound`] for a reality that was never created:
    /// an epoch switch moves an existing binding, and creating one by switching
    /// would re-open the RLS-A3 hole from the other side.
    fn activate_epoch(
        &self,
        reality_id: &str,
        digest: &RulesetDigest,
        reason: &str,
    ) -> Result<RealityBinding, BindingError>;

    /// The digest a reality is bound to, or [`BindingError::NotBound`].
    ///
    /// Defaulted because every implementation would write the same three lines,
    /// and the one thing an implementation could get wrong here — returning
    /// `Ok` of a default digest for an unbound reality — would silently load
    /// the wrong rules.
    fn digest_for(&self, reality_id: &str) -> Result<RulesetDigest, BindingError> {
        match self.load(reality_id)? {
            Some(b) => RulesetDigest::from_hex(&b.digest)
                .ok_or_else(|| BindingError::BadDigest(b.digest.clone())),
            None => Err(BindingError::NotBound {
                reality_id: reality_id.to_string(),
            }),
        }
    }
}

/// The on-disk shape: an APPEND-ONLY list, mirroring `reality_ruleset_binding`.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct BindingHistory {
    #[serde(default)]
    binding: Vec<RealityBinding>,
}

/// Durable `reality -> ruleset digest` bindings, one small TOML per reality.
#[derive(Debug, Clone)]
pub struct FileBindingStore {
    root: PathBuf,
}

impl FileBindingStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    fn path_for(&self, reality_id: &str) -> PathBuf {
        self.root.join(format!("{reality_id}.toml"))
    }

    /// Read the whole file as a history, tolerating the ONE-BINDING shape this
    /// file used to write.
    ///
    /// A version-dispatched decoder rather than a migration, and the reason is
    /// `QTY-A11`'s lesson from three days ago: a decoder tolerance that changes
    /// what a re-encode produces breaks anything that re-digests the decoded
    /// value. Nothing re-digests a binding file, so tolerance is safe *here* —
    /// but it is written down because the same shape was NOT safe one crate
    /// over, and the difference is worth a sentence rather than a rediscovery.
    fn read_history(&self, reality_id: &str) -> Result<Vec<RealityBinding>, BindingError> {
        let src = match fs::read_to_string(self.path_for(reality_id)) {
            Ok(s) => s,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(e) => return Err(e.into()),
        };
        let malformed = |e: toml::de::Error| BindingError::Malformed {
            reality_id: reality_id.to_string(),
            detail: e.to_string(),
        };
        // New shape first. An empty `binding` array is indistinguishable from a
        // file that has neither key, so the fallback runs on empty too.
        if let Ok(h) = toml::from_str::<BindingHistory>(&src) {
            if !h.binding.is_empty() {
                return Ok(h.binding);
            }
        }
        Ok(vec![toml::from_str::<RealityBinding>(&src).map_err(malformed)?])
    }

    fn write_history(
        &self,
        reality_id: &str,
        history: &[RealityBinding],
    ) -> Result<(), BindingError> {
        let body = format!(
            "# RLS-A3 early binding: which ruleset THIS reality resolved to, once,\n\
             # plus every epoch it has been switched to since. The load path reads\n\
             # the NEWEST digest and fetches those exact bytes from the content\n\
             # store; it does NOT re-resolve the layer files.\n\
             #\n\
             # The older rows are not archaeology: QTY-A5's never-reuse rule is\n\
             # computed over ALL of them, because an ordinal freed two epochs ago\n\
             # is still meant by the committed events of the epoch that declared it.\n\
             {}",
            toml::to_string(&BindingHistory { binding: history.to_vec() }).map_err(|e| {
                BindingError::Malformed {
                    reality_id: reality_id.to_string(),
                    detail: e.to_string(),
                }
            })?
        );
        fs::create_dir_all(&self.root)?;
        fs::write(self.path_for(reality_id), body)?;
        Ok(())
    }
}

impl BindingStore for FileBindingStore {
    fn create(
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
        self.write_history(reality_id, std::slice::from_ref(&binding))?;
        Ok(binding)
    }

    fn load(&self, reality_id: &str) -> Result<Option<RealityBinding>, BindingError> {
        // The NEWEST epoch, not the first. `history` is ascending, so this is
        // its tail — the same `ORDER BY epoch DESC LIMIT 1` the Postgres store
        // does, expressed once rather than twice.
        Ok(self.history(reality_id)?.pop())
    }

    fn history(&self, reality_id: &str) -> Result<Vec<RealityBinding>, BindingError> {
        let mut h = self.read_history(reality_id)?;
        // Sorted rather than trusted. The file is append-only by convention
        // only — a human can edit it, and `history` is consumed by the
        // never-reuse check, where a mis-ordered prior is not a cosmetic bug:
        // it decides whether an epoch switch is refused.
        h.sort_by_key(|b| b.epoch);
        Ok(h)
    }

    fn activate_epoch(
        &self,
        reality_id: &str,
        digest: &RulesetDigest,
        _reason: &str,
    ) -> Result<RealityBinding, BindingError> {
        let mut history = self.history(reality_id)?;
        let Some(current) = history.last() else {
            return Err(BindingError::NotBound {
                reality_id: reality_id.to_string(),
            });
        };
        let next = RealityBinding {
            reality_id: reality_id.to_string(),
            epoch: current.epoch + 1,
            digest: digest.to_hex(),
        };
        history.push(next.clone());
        self.write_history(reality_id, &history)?;
        Ok(next)
    }
}

/// Convenience for callers that hold a `&Path` root.
pub fn binding_store(root: &Path) -> FileBindingStore {
    FileBindingStore::new(root)
}
