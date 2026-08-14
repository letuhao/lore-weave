//! Fail-closed server config, read from the environment at boot.
//!
//! **The credential names are the `provision` worker's, deliberately.** An
//! operator who can run `provision` can run this server without learning a
//! second vocabulary for the same six secrets, and a deployment that sets one
//! set correctly cannot half-configure the other. Only the two genuinely new
//! things — the bind address and the internal token — get new names.
//!
//! Like the worker, this has **no default for any DSN or secret**: a default
//! silently targets the wrong stack instead of refusing.

use std::net::SocketAddr;

use crate::provision_flow::EffectsConfig;

/// Default bind. `7120` is the next free port after roleplay's `7110`.
pub const DEFAULT_BIND: &str = "0.0.0.0:7120";

/// Default location of the per-reality migration set.
pub const DEFAULT_SQL_DIR: &str = "contracts/migrations/per_reality";

/// The polyglot allowlist `MetaWrite`/`MetaControlPlane` validate against.
///
/// Optional-with-a-default, exactly like [`DEFAULT_SQL_DIR`]: it names a
/// file this repo ships, not a per-deployment choice, so it is not a
/// setting. Overridable for a relocated checkout and nothing else.
pub const DEFAULT_META_ALLOWLIST: &str = "contracts/meta/events_allowlist.yaml";

/// Every environment variable that must be present and non-empty.
///
/// `PROVISION_PG_PASSWORD` is **not** here: it may legitimately be empty under
/// peer/trust auth or a `.pgpass`. It is still read only from the environment,
/// never a literal.
pub const REQUIRED_ENV: [&str; 6] = [
    "LOREWEAVE_INTERNAL_TOKEN",
    "PROVISION_META_DSN",
    "PROVISION_SHARD_ADMIN_DSN",
    "PROVISION_BRIDGE_URL",
    "PROVISION_BRIDGE_TOKEN",
    "PROVISION_SHARD_HOSTPORT",
];

/// Resolved runtime configuration.
#[derive(Debug, Clone)]
pub struct Config {
    /// Address the HTTP server binds.
    pub bind: SocketAddr,
    /// Shared service-to-service token guarding every versioned route.
    pub internal_token: String,
    /// DSN of the meta database (`reality_registry`, `shard_utilization`).
    pub meta_dsn: String,
    /// DSN of the shard's maintenance database (runs `CREATE DATABASE`).
    pub shard_admin_dsn: String,
    /// Everything the provisioning effects need.
    pub effects: EffectsConfig,
}

impl Config {
    /// Read from the process environment.
    ///
    /// Reports **all** missing names at once — an operator fixing env one
    /// round-trip at a time is the failure mode this avoids.
    pub fn from_env() -> Result<Self, String> {
        Self::from_lookup(|k| std::env::var(k).ok())
    }

    /// The testable half: `lookup` stands in for the environment.
    ///
    /// Exists so the fail-closed behaviour can be asserted without mutating
    /// process-global state, which is unsound under a parallel test runner.
    pub fn from_lookup(lookup: impl Fn(&str) -> Option<String>) -> Result<Self, String> {
        let get = |k: &str| lookup(k).unwrap_or_default();

        let missing: Vec<&str> =
            REQUIRED_ENV.iter().copied().filter(|k| get(k).trim().is_empty()).collect();
        if !missing.is_empty() {
            return Err(format!(
                "missing required env: {} (this server has NO credential defaults — \
                 a default would silently target the wrong stack)",
                missing.join(", ")
            ));
        }

        let raw_bind = lookup("WORLD_HTTP_BIND").unwrap_or_else(|| DEFAULT_BIND.to_string());
        let bind = raw_bind
            .parse::<SocketAddr>()
            .map_err(|e| format!("WORLD_HTTP_BIND={raw_bind:?} is not a socket address: {e}"))?;

        Ok(Config {
            bind,
            internal_token: get("LOREWEAVE_INTERNAL_TOKEN"),
            meta_dsn: get("PROVISION_META_DSN"),
            shard_admin_dsn: get("PROVISION_SHARD_ADMIN_DSN"),
            effects: EffectsConfig {
                bridge_url: get("PROVISION_BRIDGE_URL"),
                bridge_token: get("PROVISION_BRIDGE_TOKEN"),
                shard_hostport: get("PROVISION_SHARD_HOSTPORT"),
                pg_user: get("PROVISION_PG_USER"),
                pg_pass: get("PROVISION_PG_PASSWORD"),
                sql_dir: lookup("PROVISION_SQL_DIR")
                    .filter(|s| !s.trim().is_empty())
                    .unwrap_or_else(|| DEFAULT_SQL_DIR.to_string()),
                meta_allowlist: lookup("PROVISION_META_ALLOWLIST")
                    .filter(|s| !s.trim().is_empty())
                    .unwrap_or_else(|| DEFAULT_META_ALLOWLIST.to_string()),
            },
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn full() -> HashMap<&'static str, &'static str> {
        HashMap::from([
            ("LOREWEAVE_INTERNAL_TOKEN", "tok"),
            ("PROVISION_META_DSN", "postgres://m"),
            ("PROVISION_SHARD_ADMIN_DSN", "postgres://s"),
            ("PROVISION_BRIDGE_URL", "http://bridge:8090"),
            ("PROVISION_BRIDGE_TOKEN", "btok"),
            ("PROVISION_SHARD_HOSTPORT", "pg:5432"),
            ("PROVISION_PG_USER", "loreweave_provisioner"),
        ])
    }

    fn load(m: &HashMap<&'static str, &'static str>) -> Result<Config, String> {
        Config::from_lookup(|k| m.get(k).map(|s| s.to_string()))
    }

    #[test]
    fn a_complete_environment_loads() {
        let cfg = load(&full()).expect("should load");
        assert_eq!(cfg.bind.port(), 7120);
        assert_eq!(cfg.effects.sql_dir, DEFAULT_SQL_DIR);
        // Absent password is empty, not a failure.
        assert_eq!(cfg.effects.pg_pass, "");
    }

    #[test]
    fn every_required_name_is_individually_load_bearing() {
        // Non-vacuity: assert each name matters ON ITS OWN. A single
        // "empty env fails" test would pass even if five of the six were
        // silently optional.
        for name in REQUIRED_ENV {
            let mut m = full();
            m.remove(name);
            let err = load(&m).expect_err(&format!("removing {name} should refuse"));
            assert!(err.contains(name), "error for missing {name} does not name it: {err}");
        }
    }

    #[test]
    fn all_missing_names_are_reported_together() {
        let m: HashMap<&'static str, &'static str> = HashMap::new();
        let err = load(&m).expect_err("empty env should refuse");
        for name in REQUIRED_ENV {
            assert!(err.contains(name), "{name} missing from the report: {err}");
        }
    }

    #[test]
    fn a_present_but_blank_value_is_treated_as_missing() {
        let mut m = full();
        m.insert("PROVISION_BRIDGE_TOKEN", "   ");
        let err = load(&m).expect_err("whitespace token should refuse");
        assert!(err.contains("PROVISION_BRIDGE_TOKEN"), "{err}");
    }

    #[test]
    fn a_malformed_bind_is_refused_rather_than_defaulted() {
        let mut m = full();
        m.insert("WORLD_HTTP_BIND", "not-an-address");
        let err = load(&m).expect_err("bad bind should refuse");
        assert!(err.contains("WORLD_HTTP_BIND"), "{err}");
    }

    #[test]
    fn the_password_is_never_required_but_is_carried_when_set() {
        let mut m = full();
        m.insert("PROVISION_PG_PASSWORD", "hunter2");
        assert_eq!(load(&m).expect("loads").effects.pg_pass, "hunter2");
    }
}
