//! Fail-closed environment config (CLAUDE.md "no hardcoded secrets" — services
//! refuse to start when a required secret is missing).

use anyhow::{Context, bail};

/// Read a required env var; trims whitespace (heredoc / shell-quoting hygiene);
/// errors if missing or empty-after-trim.
pub fn require_env(key: &str) -> anyhow::Result<String> {
    let raw = std::env::var(key).with_context(|| format!("required env var {key} is not set"))?;
    let trimmed = raw.trim().to_string();
    if trimmed.is_empty() {
        bail!("env var {key} is set but empty (or whitespace-only)");
    }
    Ok(trimmed)
}

/// Read an optional env var, falling back to `default`. Empty-after-trim is
/// treated as unset.
pub fn optional_env(key: &str, default: &str) -> String {
    std::env::var(key)
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| default.to_string())
}
