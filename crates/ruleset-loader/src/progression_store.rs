//! `PGN-R2a` — where the progression bytes live, and the **nested** verify that
//! `RulesetStore::get` does not do for you.
//!
//! ## A sibling, not a generalisation
//!
//! Doc 39 §8.3 offered both: *"`RulesetStore` is `Ruleset`-typed and needs
//! generalising or a sibling."* This is the sibling, and the reason is
//! [`RulesetStore::get`]'s own body: it re-digests **at the artifact's own
//! schema version** (`digest_at(src_version)`), because an older `Ruleset` is
//! upcast on decode and re-encoding it at the current layout would reject every
//! artifact written before the last schema bump. A `ProgressionTable` has one
//! version and no upcast, so a trait abstracting "content-addressed thing"
//! would have to carry version dispatch for the one implementor that needs it
//! and a degenerate answer for the one that does not. Two small stores are
//! honest; one clever store is a place for the version logic to drift.
//!
//! ## The hazard this module exists to close
//!
//! `RulesetStore::get` verifies the **outer** artifact only. A `Ruleset` whose
//! `progression` pin names bytes that are absent, corrupt, or substituted comes
//! back from that call **completely clean** — the ruleset's own digest checks
//! out, because the pin is 32 bytes *inside* those verified bytes and nothing
//! has looked at what it points to.
//!
//! So the nested resolve is a **separately written** check, which doc 39 §8.3
//! flagged as the genuinely new cost of this placement:
//!
//! > *"a tolerant nested decoder would re-create non-vacuity register row 7
//! > (`QTY-A11 ⊥ get` re-digest) one level down."*
//!
//! Register row 7 is the near-miss where a decoder tolerance silently defeated
//! the store check that depended on it. The same shape is available here and is
//! deliberately refused: [`resolve_progression`] treats a missing pin target as
//! an **error**, never as `None`. `None` means *this reality declares no
//! progression*; a dangling pin means *this reality declares progression and
//! the bytes are gone*, and collapsing the two would make an unloadable world
//! look like an empty one.

use std::fs;
use std::io;
use std::path::PathBuf;

use ruleset_core::{CanonError, ProgressionDigest, ProgressionTable, Ruleset};

/// Why a progression store operation failed.
#[derive(Debug)]
pub enum ProgressionStoreError {
    Io(io::Error),
    /// The bytes on disk do not hash to the digest they are filed under.
    /// Corruption, truncation, or substitution — the store does not guess.
    DigestMismatch { requested: ProgressionDigest, actual: ProgressionDigest },
    /// The bytes are not a decodable progression table at all.
    Malformed(CanonError),
    /// The `Ruleset` pins a progression table these bytes do not contain.
    ///
    /// **Not `None`.** A reality that declares progression and cannot resolve
    /// it is unloadable, and saying so is the whole point — the alternative is
    /// a world that boots with every ladder silently missing.
    Dangling { digest: ProgressionDigest },
    /// An attempt to pin an EMPTY table (`D-PROGRESSION-EMPTY-PIN`).
    ///
    /// `None` and `Some(digest_of_empty)` are the same behavioural state under
    /// two different pins — one set of rules with two digests, which `RLS-A13`
    /// forbids. `None` is the canonical spelling, so the other one is refused
    /// at the only place it can be minted.
    EmptyPin,
}

impl core::fmt::Display for ProgressionStoreError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "progression store I/O: {e}"),
            Self::DigestMismatch { requested, actual } => write!(
                f,
                "progression store CORRUPTION: {} contains bytes that hash to {} - refusing \
                 to serve a progression table under a digest it does not match",
                requested.to_hex(),
                actual.to_hex()
            ),
            Self::Malformed(e) => write!(f, "stored progression table is not decodable: {e}"),
            Self::Dangling { digest } => write!(
                f,
                "this ruleset pins progression {} and the store does not have it. The reality \
                 is UNLOADABLE - reporting that is the point, because the alternative is a \
                 world that boots with every ladder silently missing",
                digest.to_hex()
            ),
            Self::EmptyPin => write!(
                f,
                "refusing to pin an EMPTY progression table. `None` is the only spelling of \
                 'this reality declares no progression'; pinning the empty table's digest \
                 would give one set of rules two digests, which RLS-A13 forbids \
                 (D-PROGRESSION-EMPTY-PIN)"
            ),
        }
    }
}

impl std::error::Error for ProgressionStoreError {}

impl From<io::Error> for ProgressionStoreError {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}

/// A filesystem progression store: `<root>/<digest>.prog`.
///
/// A different extension from `RulesetStore`'s `.canon` so the two may share a
/// root without a digest collision across artifact KINDS ever being possible —
/// two different artifacts cannot hash the same, but two stores that agree on a
/// filename convention can be pointed at one directory by a future operator,
/// and the extension makes that safe by construction rather than by policy.
#[derive(Debug, Clone)]
pub struct ProgressionStore {
    root: PathBuf,
}

impl ProgressionStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn ensure_root(&self) -> Result<(), ProgressionStoreError> {
        fs::create_dir_all(&self.root)?;
        Ok(())
    }

    /// Where a digest is filed. Public for the same reason `RulesetStore`'s is:
    /// under content addressing the path IS derivable from the content, so
    /// there is nothing to encapsulate — and hiding it made tests hand-roll the
    /// layout, which then lived in two places.
    pub fn path_for(&self, digest: &ProgressionDigest) -> PathBuf {
        self.root.join(format!("{}.prog", digest.to_hex()))
    }

    /// Store a table, returning its digest.
    ///
    /// **This is the pin-writing path**, so it is where `D-PROGRESSION-EMPTY-PIN`
    /// is refused. Idempotent and never overwrites, for the same reasons
    /// `RulesetStore::put` gives: an existing file under a content address
    /// either has identical bytes or is corrupt, and rewriting would erase the
    /// evidence.
    pub fn put(&self, table: &ProgressionTable) -> Result<ProgressionDigest, ProgressionStoreError> {
        if table.is_empty() {
            return Err(ProgressionStoreError::EmptyPin);
        }
        self.ensure_root()?;
        let digest = table.digest();
        let path = self.path_for(&digest);
        if path.exists() {
            return Ok(digest);
        }
        let tmp = path.with_extension("prog.partial");
        fs::write(&tmp, table.canon_bytes())?;
        fs::rename(&tmp, &path)?;
        Ok(digest)
    }

    /// Fetch by digest, verifying the content against the name.
    ///
    /// Re-digests the **decoded** value, not the raw bytes — the same call
    /// `RulesetStore::get` makes and for the same reason: bytes that hash
    /// correctly but decode into something whose re-encoding differs would slip
    /// past a raw-bytes check, and that asymmetry is exactly what a
    /// content-addressed store must not tolerate. There is no version dispatch
    /// here because a progression table has one version; when it gains a
    /// second, this line must grow a `digest_at` the way `RulesetStore`'s did,
    /// and `a_table_re_encodes_to_exactly_its_stored_bytes` is what will say so.
    pub fn get(
        &self,
        digest: &ProgressionDigest,
    ) -> Result<Option<ProgressionTable>, ProgressionStoreError> {
        let path = self.path_for(digest);
        let bytes = match fs::read(&path) {
            Ok(b) => b,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e.into()),
        };
        let table = ProgressionTable::decode(&bytes).map_err(ProgressionStoreError::Malformed)?;
        let actual = table.digest();
        if actual != *digest {
            return Err(ProgressionStoreError::DigestMismatch { requested: *digest, actual });
        }
        Ok(Some(table))
    }

    pub fn contains(&self, digest: &ProgressionDigest) -> bool {
        self.path_for(digest).exists()
    }
}

/// Resolve a ruleset's progression pin — **the check `RulesetStore::get` does
/// not do.**
///
/// | pin | store | result |
/// |---|---|---|
/// | `None` | — | `Ok(None)` — this reality declares no progression |
/// | `Some(d)` | has `d` | `Ok(Some(table))`, digest-verified |
/// | `Some(d)` | missing | **`Err(Dangling)`** — never `Ok(None)` |
/// | `Some(d)` | corrupt | `Err(DigestMismatch)` |
/// | `Some(d)` | empty table | **`Err(EmptyPin)`** |
///
/// The third row is the one worth stating twice. Returning `Ok(None)` for a
/// dangling pin would make an unloadable reality indistinguishable from an
/// empty one, and every ladder would vanish with the run staying green — the
/// `QTY-Q5` silent-drop class, at load time, for a whole progression system.
///
/// The fifth row is defence in depth: [`ProgressionStore::put`] already refuses
/// to mint an empty pin, but bytes can arrive in a store by other routes (a
/// restored backup, an operator copy, a future writer), and a rule enforced at
/// exactly one end is a rule that holds until someone adds a second end.
pub fn resolve_progression(
    ruleset: &Ruleset,
    store: &ProgressionStore,
) -> Result<Option<ProgressionTable>, ProgressionStoreError> {
    let Some(digest) = ruleset.progression else {
        return Ok(None);
    };
    match store.get(&digest)? {
        None => Err(ProgressionStoreError::Dangling { digest }),
        Some(table) if table.is_empty() => Err(ProgressionStoreError::EmptyPin),
        Some(table) => Ok(Some(table)),
    }
}
