//! LLM gateway client error variants.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum LlmError {
    #[error("gateway HTTP error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("gateway returned error event: {code}: {message}")]
    GatewayErrorEvent { code: String, message: String },

    #[error("stream parsing failed: {0}")]
    StreamParse(String),

    /// Per-call validation exhausted retries. Callers using TMP_008b §5
    /// per-object retry should fall back to TMP_008b §6 canonical-default
    /// for the remaining failing objects.
    #[error("validation rejected response after {attempts} attempt(s)")]
    ValidationExhausted { attempts: u32 },

    /// CLAUDE.md "no hardcoded secrets" — the internal token MUST be supplied
    /// via env var. Service fails to start if missing.
    #[error("LOREWEAVE_INTERNAL_TOKEN env var missing or empty")]
    MissingInternalToken,

    /// The token has characters that cannot be encoded into an HTTP header
    /// value (CR / LF / non-ASCII / etc.). Likely the env var is corrupted.
    #[error("LOREWEAVE_INTERNAL_TOKEN contains invalid header characters: {0}")]
    InvalidInternalToken(String),

    #[error("invalid gateway URL: {0}")]
    InvalidUrl(String),

    #[error("not implemented yet — Phase 0b: {0}")]
    NotImplementedPhase0a(&'static str),
}
