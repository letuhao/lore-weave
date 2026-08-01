//! `PGN-A18` — the names, which are deliberately NOT rules.
//!
//! ## Why this module is in the loader and not in `ruleset-core`
//!
//! `ruleset-core` is the rules. A tier's name is not a rule — it changes
//! nothing about what happens to an actor — so the crate that defines the
//! hashed bytes never sees one. That placement IS the axiom: if labels lived
//! next to `ProgressionKindDecl`, someone would eventually hash them, and then
//! **fixing a Vietnamese translation would move every affected reality's digest
//! and strand a running world.** `quantity.rs` already made this call for
//! declared quantities — *"the hashed name is a MACHINE key; its human-readable
//! label is localized content and lives elsewhere."* This is elsewhere.
//!
//! ## A SIDECAR, not a content-addressed artifact
//!
//! The progression table is content-addressed and immutable: its name is its
//! hash, `put` never overwrites, and that is what makes a digest a promise.
//!
//! Labels are the opposite on purpose. They are filed under **the digest of the
//! table they label** — `<root>/<progression_digest>.labels.toml` — and writing
//! them **overwrites**. A translation is corrected in place, the table's digest
//! does not move, and no reality is disturbed. Two realities sharing a preset
//! share one label file, which is correct: same ladder, same names.
//!
//! Recording that distinction here rather than leaving it to be inferred,
//! because a reader who assumes "store" means "content-addressed" would see
//! `put` overwriting and read it as a bug.
//!
//! ## Coverage is refused at LOAD, not warned about
//!
//! Doc 39's `T10` shipped as **NOT ENFORCED**: a reality could load with a
//! 24-tier ladder and no names at all, and display `tier_9` to a player. A
//! missing label is not a cosmetic gap — it is content the pipeline was supposed
//! to produce and did not, and the honest response is the same one a dangling
//! pin gets: refuse, and say which key is missing.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::PathBuf;

use ruleset_core::{ProgressionDigest, ProgressionTable};

/// One localized string. `default` is required and must be non-empty —
/// `PROG_001` §2 requires an English default, and a bundle whose only content
/// is a translation is a bundle that renders as nothing for everyone else.
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct Label {
    pub name: String,
    #[serde(default)]
    pub translations: BTreeMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default, serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct TierLabel {
    index: u8,
    name: String,
    #[serde(default)]
    translations: BTreeMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default, serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct KindLabel {
    ordinal: u16,
    name: String,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    translations: BTreeMap<String, String>,
    #[serde(default)]
    tier: Vec<TierLabel>,
}

/// The names for one progression table.
#[derive(Debug, Clone, PartialEq, Eq, Default, serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProgressionLabels {
    #[serde(default)]
    kind: Vec<KindLabel>,
}

/// Why labels could not be read, written, or accepted.
#[derive(Debug)]
pub enum LabelError {
    Io(io::Error),
    Malformed(String),
    /// No label file at all for a table that has kinds.
    Missing { digest: ProgressionDigest },
    /// A declared kind or tier has no name.
    ///
    /// Named precisely — `kind 2` / `kind 0 tier 7` — because a translator
    /// handed *"labels are incomplete"* has to diff two files to find out which.
    NotCovered { what: String },
    /// A name exists and is empty, which renders as nothing and is worse than
    /// a missing one because it looks covered.
    EmptyName { what: String },
}

impl core::fmt::Display for LabelError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "progression labels I/O: {e}"),
            Self::Malformed(e) => write!(f, "progression labels are not readable: {e}"),
            Self::Missing { digest } => write!(
                f,
                "progression table {} has NO label file. The reality would load with a \
                 ladder whose tiers are numbers - a player would see `tier_9`. Labels live \
                 beside the table as `<digest>.labels.toml` and are not hashed, so writing \
                 them moves no digest and disturbs no running world",
                digest.to_hex()
            ),
            Self::NotCovered { what } => write!(
                f,
                "progression labels do not cover {what}. Refused rather than defaulted: a \
                 generated name is a name nobody chose, and it would ship to players looking \
                 exactly like one somebody did"
            ),
            Self::EmptyName { what } => write!(
                f,
                "progression label for {what} is EMPTY. That renders as nothing and is worse \
                 than a missing one, because every coverage check reads it as present"
            ),
        }
    }
}

impl std::error::Error for LabelError {}

impl From<io::Error> for LabelError {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}

impl ProgressionLabels {
    pub fn is_empty(&self) -> bool {
        self.kind.is_empty()
    }

    /// Build from `(ordinal, name, description, tier names)` tuples.
    pub fn from_rows(
        rows: Vec<(u16, String, Option<String>, Vec<(u8, String)>)>,
    ) -> Self {
        Self {
            kind: rows
                .into_iter()
                .map(|(ordinal, name, description, tiers)| KindLabel {
                    ordinal,
                    name,
                    description,
                    translations: BTreeMap::new(),
                    tier: tiers
                        .into_iter()
                        .map(|(index, name)| TierLabel {
                            index,
                            name,
                            translations: BTreeMap::new(),
                        })
                        .collect(),
                })
                .collect(),
        }
    }

    pub fn name_of(&self, ordinal: u16) -> Option<&str> {
        self.kind.iter().find(|k| k.ordinal == ordinal).map(|k| k.name.as_str())
    }

    pub fn tier_name(&self, ordinal: u16, index: u8) -> Option<&str> {
        self.kind
            .iter()
            .find(|k| k.ordinal == ordinal)?
            .tier
            .iter()
            .find(|t| t.index == index)
            .map(|t| t.name.as_str())
    }

    /// **Every declared kind and every declared tier has a non-empty name.**
    ///
    /// Reports the FIRST gap by name rather than a count, because the fix is
    /// per-key and a count sends a translator diffing two files.
    pub fn covers(&self, table: &ProgressionTable) -> Result<(), LabelError> {
        for row in table.rows() {
            let what = format!("kind at ordinal {}", row.quantity);
            match self.name_of(row.quantity) {
                None => return Err(LabelError::NotCovered { what }),
                Some(n) if n.trim().is_empty() => return Err(LabelError::EmptyName { what }),
                Some(_) => {}
            }
            for tier in &row.tiers {
                let what = format!("kind {} tier {}", row.quantity, tier.tier_index);
                match self.tier_name(row.quantity, tier.tier_index) {
                    None => return Err(LabelError::NotCovered { what }),
                    Some(n) if n.trim().is_empty() => {
                        return Err(LabelError::EmptyName { what })
                    }
                    Some(_) => {}
                }
            }
        }
        Ok(())
    }
}

/// The label sidecar, filed beside the tables it names.
#[derive(Debug, Clone)]
pub struct LabelStore {
    root: PathBuf,
}

impl LabelStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn beside(rules: &crate::RulesetStore) -> Self {
        Self { root: rules.root().to_path_buf() }
    }

    pub fn path_for(&self, digest: &ProgressionDigest) -> PathBuf {
        self.root.join(format!("{}.labels.toml", digest.to_hex()))
    }

    /// Write the labels for a table. **Overwrites, deliberately.**
    ///
    /// This is the one write in this crate that replaces an existing file, and
    /// the asymmetry with `ProgressionStore::put` is the design: the table is
    /// immutable because its digest is a promise about behaviour; the names are
    /// mutable because correcting a translation must NOT be a rules change.
    pub fn put(
        &self,
        digest: &ProgressionDigest,
        labels: &ProgressionLabels,
    ) -> Result<(), LabelError> {
        fs::create_dir_all(&self.root)?;
        let body = toml::to_string_pretty(labels)
            .map_err(|e| LabelError::Malformed(e.to_string()))?;
        let path = self.path_for(digest);
        // Temp + rename, the same reason `RulesetStore::put` does it: a reader
        // must never observe a half-written file. Here it matters more, because
        // this path OVERWRITES - a failed write must leave the old names intact
        // rather than a truncated file. (Learned the hard way on a doc the same
        // day: `open(w)` truncates before the write can fail.)
        let tmp = path.with_extension("toml.partial");
        fs::write(&tmp, body)?;
        fs::rename(&tmp, &path)?;
        Ok(())
    }

    pub fn get(&self, digest: &ProgressionDigest) -> Result<Option<ProgressionLabels>, LabelError> {
        let body = match fs::read_to_string(self.path_for(digest)) {
            Ok(b) => b,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e.into()),
        };
        toml::from_str(&body).map_err(|e| LabelError::Malformed(e.to_string()))
    }

    /// Fetch and check coverage in one call — the shape every admission point
    /// wants, so none of them can do half of it.
    pub fn admit(
        &self,
        digest: &ProgressionDigest,
        table: &ProgressionTable,
    ) -> Result<ProgressionLabels, LabelError> {
        let labels = self.get(digest)?.ok_or(LabelError::Missing { digest: *digest })?;
        labels.covers(table)?;
        Ok(labels)
    }
}
