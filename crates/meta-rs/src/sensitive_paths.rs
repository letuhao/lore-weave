//! `sensitive_paths` — parse + query `meta-sensitive-read-paths.yml` so the
//! Rust kernel uses the SAME path-id namespace as the Go library (Q-L1B-2).

use serde::Deserialize;
use std::collections::HashMap;
use std::path::Path;

use crate::errors::MetaError;

/// One sensitive read path.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct SensitivePath {
    /// Stable kebab-case identifier (e.g., `audit_query`).
    pub id: String,
    /// Human-readable description.
    pub description: String,
    /// Meta tables this path reads.
    pub tables: Vec<String>,
    /// Why this path is sensitive (PII / bulk / cross-user / audit).
    pub rationale: String,
    /// Reviewer CODEOWNER aliases.
    pub reviewers: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SensitivePathsFile {
    version: u32,
    paths: Vec<SensitivePath>,
}

/// In-memory lookup over the parsed file.
#[derive(Debug, Clone)]
pub struct SensitivePaths {
    by_id: HashMap<String, SensitivePath>,
}

impl SensitivePaths {
    /// Load + validate the YAML file at `path`.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, MetaError> {
        let raw = std::fs::read(path.as_ref()).map_err(|e| {
            MetaError::ConfigInvalid(format!(
                "read sensitive paths {}: {e}",
                path.as_ref().display()
            ))
        })?;
        Self::parse(&raw)
    }

    /// Parse + validate an in-memory YAML payload.
    pub fn parse(raw: &[u8]) -> Result<Self, MetaError> {
        let f: SensitivePathsFile = serde_yaml::from_slice(raw)
            .map_err(|e| MetaError::ConfigInvalid(format!("unmarshal: {e}")))?;
        if f.version != 1 {
            return Err(MetaError::ConfigInvalid(format!(
                "sensitive paths version={} unsupported",
                f.version
            )));
        }
        if f.paths.is_empty() {
            return Err(MetaError::ConfigInvalid(
                "sensitive paths file is empty".into(),
            ));
        }
        let mut by_id = HashMap::with_capacity(f.paths.len());
        for p in f.paths {
            if p.id.trim().is_empty() {
                return Err(MetaError::ConfigInvalid("empty id".into()));
            }
            if p.tables.is_empty() {
                return Err(MetaError::ConfigInvalid(format!(
                    "path {} has no tables",
                    p.id
                )));
            }
            if p.reviewers.is_empty() {
                return Err(MetaError::ConfigInvalid(format!(
                    "path {} has no reviewers",
                    p.id
                )));
            }
            if by_id.contains_key(&p.id) {
                return Err(MetaError::ConfigInvalid(format!(
                    "duplicate sensitive path id {}",
                    p.id
                )));
            }
            by_id.insert(p.id.clone(), p);
        }
        Ok(Self { by_id })
    }

    /// Returns true when the id is registered.
    pub fn has(&self, id: &str) -> bool {
        self.by_id.contains_key(id)
    }

    /// Lookup a path by id.
    pub fn get(&self, id: &str) -> Option<&SensitivePath> {
        self.by_id.get(id)
    }

    /// List all registered ids — used by tests + lints to enumerate coverage.
    pub fn ids(&self) -> Vec<&str> {
        self.by_id.keys().map(String::as_str).collect()
    }

    /// Returns `Ok(())` if `id` is registered, else
    /// `Err(MetaError::SensitivePathNotRegistered)`.  Useful as a guard at
    /// the call site of any Rust read that targets a sensitive table.
    pub fn require(&self, id: &str) -> Result<(), MetaError> {
        if self.has(id) {
            Ok(())
        } else {
            Err(MetaError::SensitivePathNotRegistered(id.into()))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SHIPPED: &str = "../../contracts/meta/meta-sensitive-read-paths.yml";

    #[test]
    fn shipped_file_parses() {
        let sp = SensitivePaths::load(SHIPPED).expect("load shipped");
        for id in ["player_index_cross_user", "audit_query", "admin_bulk_export", "bulk_meta_query"] {
            assert!(sp.has(id), "id {id} missing");
            let p = sp.get(id).unwrap();
            assert!(!p.reviewers.is_empty(), "id {id} has no reviewers");
        }
        assert!(!sp.has("does-not-exist"));
    }

    #[test]
    fn require_returns_sentinel_error_when_unknown() {
        let sp = SensitivePaths::load(SHIPPED).expect("load shipped");
        let err = sp.require("zzz-unknown").unwrap_err();
        assert!(matches!(err, MetaError::SensitivePathNotRegistered(_)));
    }

    #[test]
    fn duplicate_id_rejected() {
        let doc = br#"
version: 1
paths:
  - id: x
    description: first
    tables: [a]
    rationale: r
    reviewers: [sec]
  - id: x
    description: second
    tables: [b]
    rationale: r
    reviewers: [sec]
"#;
        let err = SensitivePaths::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("duplicate")));
    }

    #[test]
    fn no_tables_rejected() {
        let doc = br#"
version: 1
paths:
  - id: x
    description: first
    tables: []
    rationale: r
    reviewers: [sec]
"#;
        let err = SensitivePaths::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("no tables")));
    }

    #[test]
    fn version_mismatch_rejected() {
        let doc = br#"
version: 2
paths:
  - id: x
    description: first
    tables: [a]
    rationale: r
    reviewers: [sec]
"#;
        let err = SensitivePaths::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("unsupported")));
    }
}
