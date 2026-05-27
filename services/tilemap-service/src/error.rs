//! Top-level error type that forwards module-local errors via [`thiserror::Error`].
//!
//! Binary entry (`main.rs`) uses [`anyhow::Result`] for prototyping convenience;
//! library callers use this typed [`Error`] enum directly.

use loreweave_llm::LlmError;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("LLM gateway error: {0}")]
    Llm(#[from] LlmError),

    #[error("serde JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("config error: {0}")]
    Config(String),

    /// Zone-placement engine failure (TMP_002) — degenerate Penrose tiling or
    /// an unrecoverable state. Convergence hitting the iteration/wall-clock cap
    /// is NOT an error — it falls back to the grid-seed layout (TMP-PLACE-Q2).
    #[error("zone placement failed: {0}")]
    Placement(String),

    /// A zone received no tiles from Penrose assignment — almost always a
    /// template misconfiguration (zone too small for the grid resolution).
    #[error("zone '{0}' was assigned no tiles")]
    EmptyZone(String),

    /// The modificator dependency graph (TMP_003 §4.1) contains a cycle, so
    /// no topological order exists.
    #[error("modificator dependency cycle involving: {0}")]
    DependencyCycle(String),

    /// A modificator's `process()` step failed.
    #[error("modificator '{name}' failed: {reason}")]
    Modificator { name: String, reason: String },
}

pub type Result<T> = std::result::Result<T, Error>;
