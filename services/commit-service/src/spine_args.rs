//! `spine`'s command line, lifted out of the binary.
//!
//! # Why the lib and not the bin
//!
//! `file-ceiling-gate` refused `spine.rs` at 435 lines against a cap of 425 —
//! and that cap's own reason says why raising it was not an option: *"a cap left
//! at its old value after a split is a silent licence to regrow into it."* The
//! precedent it cites is the one followed here: when `Q1 B2b` gave the binary a
//! new startup responsibility, the responsibility MOVED to `src/ruleset_boot.rs`
//! and the cap came down. `3E` gave it another (verifying the reality), so this
//! moves.
//!
//! Argument parsing was also the largest block in that file with no tests at
//! all, because nothing in a `bin` is reachable from an integration test. Here
//! it is testable, and the tests below are the first coverage it has had.

use uuid::Uuid;

#[derive(Debug)]
pub struct Args {
    pub redis_url: String,
    pub pg_url: String,
    pub reality: Uuid,
    pub channel: i64,
    pub drain_once: bool,
    /// F2 — the reality layer's TOML. Absent = the engine default, which is
    /// the bootstrap floor, NOT a silent fallback: the digest still describes
    /// exactly the rules in force, and the startup line says which.
    pub ruleset: Option<String>,
    /// Root for the ruleset state: `<root>/content` (immutable, content-
    /// addressed) and `<root>/bindings` (mutable `reality -> digest`). The two
    /// are separate directories on purpose — a binding MOVES on an epoch switch,
    /// and mutable state inside a content-addressed store is a category error.
    pub ruleset_state: Option<String>,
    /// The META DB. Present ⇒ the reality's ruleset binding lives in
    /// `reality_ruleset_binding` (Q1 B2, append-only, one row per epoch) instead
    /// of a TOML file. Absent ⇒ files, which is what every offline tool and the
    /// existing smokes want and is why this is an OPTION rather than a
    /// replacement: a node with no meta DB reachable should fail loudly at
    /// startup, not fall back to a private file and run different rules from its
    /// neighbours.
    pub meta_url: Option<String>,
    /// The polyglot allowlist SoT that MetaWrite validates against.
    pub meta_allowlist: String,
    /// Resolve the layer stack, store it, and bind this reality to it — ONCE.
    /// Without this flag the binary only LOADS, which is what a running node
    /// does.
    pub create_reality: bool,
}

impl Args {
    /// Parse from an explicit argv, so this is testable.
    ///
    /// `parse_args` below reads the real process arguments and delegates here.
    /// Splitting the two is the whole reason this module has tests: a parser
    /// that can only read `std::env::args()` can only be exercised by running
    /// the binary.
    pub fn from_argv(argv: Vec<String>) -> anyhow::Result<Args> {
        let mut redis_url = "redis://127.0.0.1:6399/0".to_string();
        let mut pg_url = None;
        let mut reality = None;
        let mut channel = 1i64;
        let mut drain_once = false;
        let mut ruleset = None;
        let mut ruleset_state = None;
        let mut create_reality = false;
        let mut meta_url = None;
        let mut meta_allowlist = "contracts/meta/events_allowlist.yaml".to_string();
        let mut i = 0;
        while i < argv.len() {
            match argv[i].as_str() {
                "--redis-url" => { redis_url = argv[i + 1].clone(); i += 2; }
                "--pg-url" => { pg_url = Some(argv[i + 1].clone()); i += 2; }
                "--reality" => { reality = Some(argv[i + 1].parse()?); i += 2; }
                "--channel" => { channel = argv[i + 1].parse()?; i += 2; }
                "--drain-once" => { drain_once = true; i += 1; }
                "--ruleset" => { ruleset = Some(argv[i + 1].clone()); i += 2; }
                "--ruleset-state" => { ruleset_state = Some(argv[i + 1].clone()); i += 2; }
                "--create-reality" => { create_reality = true; i += 1; }
                "--meta-url" => { meta_url = Some(argv[i + 1].clone()); i += 2; }
                "--meta-allowlist" => { meta_allowlist = argv[i + 1].clone(); i += 2; }
                other => anyhow::bail!("unknown arg {other}"),
            }
        }
        Ok(Args {
            redis_url,
            pg_url: pg_url.ok_or_else(|| anyhow::anyhow!("--pg-url required"))?,
            reality: reality.ok_or_else(|| anyhow::anyhow!("--reality <uuid> required"))?,
            channel,
            ruleset,
            ruleset_state,
            create_reality,
            meta_url,
            meta_allowlist,
            drain_once,
        })
    }


}

/// Read the real process arguments.
pub fn parse_args() -> anyhow::Result<Args> {
    Args::from_argv(std::env::args().skip(1).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The first tests this parser has ever had — it was unreachable in a `bin`.
    #[test]
    fn a_missing_required_argument_is_named_rather_than_defaulted() {
        // Both are required and neither has a sensible default: a spine pointed
        // at the wrong database or the wrong reality is worse than one that
        // refuses to start.
        let e = Args::from_argv(vec!["--reality".into(), uuid::Uuid::nil().to_string()])
            .expect_err("no --pg-url");
        assert!(e.to_string().contains("--pg-url"), "{e}");

        let e = Args::from_argv(vec!["--pg-url".into(), "postgres://x".into()])
            .expect_err("no --reality");
        assert!(e.to_string().contains("--reality"), "{e}");
    }

    #[test]
    fn an_unknown_argument_is_refused_rather_than_ignored() {
        // A silently ignored flag is how a smoke runs with settings nobody
        // applied and reports a pass.
        let e = Args::from_argv(vec!["--not-a-flag".into()]).expect_err("unknown");
        assert!(e.to_string().contains("--not-a-flag"), "{e}");
    }

    #[test]
    fn the_defaults_are_the_documented_ones() {
        let a = Args::from_argv(vec![
            "--pg-url".into(), "postgres://x".into(),
            "--reality".into(), uuid::Uuid::nil().to_string(),
        ])
        .expect("valid");
        assert_eq!(a.channel, 1);
        assert!(!a.drain_once);
        assert!(!a.create_reality);
        assert_eq!(a.meta_allowlist, "contracts/meta/events_allowlist.yaml");
        assert!(a.meta_url.is_none(), "meta_url has no default — 3E requires it explicitly");
    }
}
