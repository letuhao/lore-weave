//! The immutable, content-addressed ruleset store (RLS-D6 / RLS-D18).
//!
//! > *The envelope carries the digest, not the ruleset. Full-ruleset-in-event
//! > was considered: a self-contained log, no external store on the replay
//! > path. Rejected on re-emission — 200 realities sharing a preset would each
//! > write the same kilobytes, repeatedly, forever. Digest + immutable store
//! > keeps the log small and dedupes globally. **The dependency this creates
//! > (replay needs the ruleset store) is real and is the reason the store is
//! > append-only and never pruned.***
//!
//! Three consumers, all of which currently have no way to resolve historical
//! rules and are the reason this exists:
//!
//! * **F3** — replay must resolve the rules an event was pinned to, not the
//!   ones this binary happens to have compiled in;
//! * **`Island::restore`** — its refusal is only useful if the *correct* rules
//!   can then be fetched by the checkpoint's digest;
//! * **fork / rebind** — a reality created from another must resolve the exact
//!   bytes the original resolved to.
//!
//! ## What it stores
//!
//! The **canonical bytes**, not the TOML. RLS-D18 is explicit: *"the digest
//! addresses the stored bytes, not the upcast form."* The TOML is the authoring
//! input and may be reformatted, recommented or regenerated; the canonical
//! encoding is the identity. Storing the TOML would make a whitespace edit look
//! like a rules change.
//!
//! ## Why `get` re-digests
//!
//! A content-addressed store that trusts its own filenames is not
//! content-addressed — it is a directory with suggestive names. It would hand
//! back a corrupted, truncated or deliberately swapped ruleset under the right
//! digest, which is precisely the substitution the digest exists to detect. So
//! `get` hashes what it read and refuses a mismatch.

use std::fs;
use std::io;
use std::path::PathBuf;

use ruleset_core::{CanonError, Ruleset, RulesetDigest};

/// Why a store operation failed.
#[derive(Debug)]
pub enum StoreError {
    Io(io::Error),
    /// The bytes on disk do not hash to the digest they are filed under.
    ///
    /// Corruption, truncation, or substitution — the store does not guess
    /// which. It is the one error that must never be downgraded to a warning.
    DigestMismatch { requested: RulesetDigest, actual: RulesetDigest },
    /// The bytes are not a decodable ruleset at all.
    Malformed(CanonError),
    /// A digest string that is not 64 lowercase hex.
    BadDigestName(String),
}

impl core::fmt::Display for StoreError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "ruleset store I/O: {e}"),
            Self::DigestMismatch { requested, actual } => write!(
                f,
                "ruleset store CORRUPTION: {} contains bytes that hash to {} - refusing \
                 to serve a ruleset under a digest it does not match",
                requested.to_hex(),
                actual.to_hex()
            ),
            Self::Malformed(e) => write!(f, "stored ruleset is not decodable: {e}"),
            Self::BadDigestName(s) => write!(f, "not a ruleset digest: {s}"),
        }
    }
}

impl From<io::Error> for StoreError {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}

/// A filesystem ruleset store: `<root>/<digest>.canon`, append-only.
///
/// Filesystem rather than Postgres on purpose for F2: the store's contract is
/// *immutable bytes addressed by their own hash*, which a directory satisfies
/// exactly and a table only satisfies by convention. Moving it behind an object
/// store later changes this file and nothing else — `put`/`get` is the whole
/// surface.
#[derive(Debug, Clone)]
pub struct RulesetStore {
    root: PathBuf,
}

impl RulesetStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// Create the root if absent.
    pub fn ensure_root(&self) -> Result<(), StoreError> {
        fs::create_dir_all(&self.root)?;
        Ok(())
    }

    fn path_for(&self, digest: &RulesetDigest) -> PathBuf {
        self.root.join(format!("{}.canon", digest.to_hex()))
    }

    /// Store a ruleset, returning its digest.
    ///
    /// **Idempotent, and never overwrites.** Two puts of equal rules produce
    /// the same path and the same bytes, so re-storing is a no-op — that is
    /// what content addressing buys, and it is why 200 realities sharing a
    /// preset cost one file. A put whose path already exists is NOT rewritten:
    /// under content addressing an existing file either has identical bytes
    /// (nothing to do) or is corrupt (and rewriting would erase the evidence).
    pub fn put(&self, ruleset: &Ruleset) -> Result<RulesetDigest, StoreError> {
        self.ensure_root()?;
        let digest = ruleset.digest();
        let path = self.path_for(&digest);
        if path.exists() {
            return Ok(digest);
        }
        // Write to a temp name and rename: a reader must never observe a
        // half-written ruleset under a digest that promises the whole thing.
        let tmp = path.with_extension("canon.partial");
        fs::write(&tmp, ruleset.canon_bytes())?;
        fs::rename(&tmp, &path)?;
        Ok(digest)
    }

    /// Fetch by digest, verifying the content against the name.
    ///
    /// `Ok(None)` = not stored. An `Err` means the store has a file it cannot
    /// vouch for, which is a different and much louder situation.
    pub fn get(&self, digest: &RulesetDigest) -> Result<Option<Ruleset>, StoreError> {
        let path = self.path_for(digest);
        let bytes = match fs::read(&path) {
            Ok(b) => b,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e.into()),
        };
        let ruleset = Ruleset::from_canon_bytes(&bytes).map_err(StoreError::Malformed)?;
        // Re-digest the DECODED value rather than hashing the raw bytes: this
        // checks the decoder too. Bytes that hash correctly but decode into
        // something whose re-encoding differs would slip past a raw-bytes check
        // and are exactly the asymmetry the round-trip test hunts.
        let actual = ruleset.digest();
        if actual != *digest {
            return Err(StoreError::DigestMismatch { requested: *digest, actual });
        }
        Ok(Some(ruleset))
    }

    pub fn contains(&self, digest: &RulesetDigest) -> bool {
        self.path_for(digest).exists()
    }
}
