//! Top-level error type that forwards module-local errors via [`thiserror::Error`].
//!
//! Binary entry (`main.rs`) uses [`anyhow::Result`] for prototyping convenience;
//! library callers use this typed [`Error`] enum directly.

use thiserror::Error;

use crate::llm::LlmError;

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
}

pub type Result<T> = std::result::Result<T, Error>;
