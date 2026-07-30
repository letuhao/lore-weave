//! How a node gets the rules it is going to run — `RLS-A3` at startup.
//!
//! Split out of `bin/spine.rs` in `Q1 B2b`, when `--meta-url` pushed that file
//! past its `IMP-D3` ceiling. The cap was **not** bumped: this is a separate
//! concern from the spine loop (bus → admission → island → commit) and reads
//! better named than inlined. It is also the only way to test the file-vs-meta
//! decision without starting a binary that wants Redis.
//!
//! ## The two columns of doc 16 §12, and why they must not be one function
//!
//! ```text
//! reality creation                     island Cold -> Hot
//! ────────────────                     ──────────────────
//!  gather layers 0..40                  read the reality's current binding
//!  merge, normalize, validate           fetch THOSE bytes by digest
//!  BLAKE3 over canonical encoding       construct the island with them
//!  store immutably; assign epoch 1
//! ```
//!
//! **Creation resolves. Load does not.** `F2.1` built the left column and used
//! it for both, so every start re-resolved the layer files and an edit to a TOML
//! silently changed a reality that was already running. The asymmetry below is
//! that bug's fix, and it is the reason `--create-reality` is a separate flag
//! rather than an "if absent, create" convenience.

use std::path::Path;

use ruleset_core::Ruleset;
use ruleset_loader::RealityBinding;
use ruleset_loader::{BindingStore, FileBindingStore, RulesetStore};
use sqlx::postgres::PgPoolOptions;

/// Where this node keeps rules, and where it keeps the pointer to them.
pub struct RulesetBoot {
    /// Immutable, content-addressed bytes (`RLS-D6`/`D18`). Always on disk: a
    /// filesystem holds "these bytes never change, and their name is their
    /// hash" perfectly well, and a database would add nothing.
    pub store: RulesetStore,
    /// The mutable `reality -> digest` pointer. This is the part that MOVES on
    /// an epoch switch, which is why it is the part that wants a database.
    pub bindings: Box<dyn BindingStore>,
    /// What to print so an operator can see which of the two is in use. "Which
    /// store am I reading?" is the first question a wrong-rules incident
    /// raises, and a silent default is how it gets answered wrong.
    pub provenance: String,
}

impl RulesetBoot {
    /// `meta_url` present ⇒ the binding lives in `reality_ruleset_binding`
    /// (append-only, one row per epoch). Absent ⇒ TOML files under
    /// `<state>/bindings`.
    ///
    /// **A meta URL that does not connect is a hard failure, deliberately.**
    /// There is no fall back to files: a node that quietly used a private file
    /// because the meta DB was unreachable would run different rules from its
    /// neighbours and be unable to say so.
    pub async fn open(
        state: &str,
        meta_url: Option<&str>,
        meta_allowlist: &str,
    ) -> anyhow::Result<Self> {
        let store = RulesetStore::new(Path::new(state).join("content"));
        let (bindings, provenance): (Box<dyn BindingStore>, String) = match meta_url {
            Some(url) => {
                let pool = PgPoolOptions::new().max_connections(2).connect(url).await?;
                (
                    Box::new(
                        crate::pg_binding::PgBindingStore::new(pool, meta_allowlist, "commit-service")
                            .map_err(|e| anyhow::anyhow!("{e}"))?,
                    ),
                    "meta DB (reality_ruleset_binding, append-only)".to_string(),
                )
            }
            None => (
                Box::new(FileBindingStore::new(Path::new(state).join("bindings"))),
                format!("{state}/bindings (files; pass --meta-url for the meta DB)"),
            ),
        };
        Ok(Self {
            store,
            bindings,
            provenance,
        })
    }

    /// **CREATE** — the only path that reads a layer file. Resolves once,
    /// validates, stores the bytes, binds the reality to their digest. Refuses
    /// a second creation.
    ///
    /// `ruleset` absent = the engine default, which is the bootstrap floor and
    /// **not** a silent fallback: the digest still describes exactly the rules
    /// in force, and the returned line says which.
    pub fn create(&self, reality_id: &str, ruleset: Option<&str>) -> anyhow::Result<String> {
        let mut layers = Vec::new();
        if let Some(path) = ruleset {
            layers.push(
                ruleset_loader::read_layer(ruleset_loader::Layer::Reality, Path::new(path))
                    .map_err(|e| anyhow::anyhow!("reality NOT created: {e}"))?,
            );
        }
        let (_, binding) =
            ruleset_loader::create_reality(reality_id, &layers, &self.store, self.bindings.as_ref())
                .map_err(|e| anyhow::anyhow!("reality NOT created: {e}"))?;
        Ok(format!(
            "CREATED reality {reality_id} epoch {} -> ruleset {} (from {})",
            binding.epoch,
            binding.digest,
            ruleset.unwrap_or("engine_default"),
        ))
    }

    /// **LOAD** — fetch the exact bytes this reality was created with. Does not
    /// look at a layer file at all.
    ///
    /// `RLS-D12`: a bad ruleset quarantines ONE reality, never the process. This
    /// binary hosts one channel, so "quarantine" is a clean refusal to start
    /// carrying the author's diagnostic; a node hosting forty realities marks
    /// this one `Unloadable` and carries on with the other thirty-nine.
    /// Returns the rules AND the binding — epoch included.
    ///
    /// It used to return `(Ruleset, RulesetDigest)`, and the caller then built
    /// an island that defaulted to epoch 1. A reality durably bound at epoch 5
    /// therefore ran on an island claiming epoch 1, and `RLS-I1` monotonicity
    /// was computed against the wrong number. The epoch travels with the rules
    /// now, so a caller cannot forget it.
    pub fn load(&self, reality_id: &str) -> anyhow::Result<(Ruleset, RealityBinding)> {
        ruleset_loader::load_reality(reality_id, &self.store, self.bindings.as_ref())
            .map_err(|e| anyhow::anyhow!("{e}"))
    }
}

/// Open the binding store, optionally create the reality, and load its rules
/// **with its epoch**.
///
/// Lifted out of `spine.rs` wholesale when the audit fix pushed that binary past
/// its ceiling. It is not a line-count dodge: the block was already the only
/// part of the spine that knows what a *binding* is, and the epoch it returns is
/// the value the whole `RLS-I1` chain hangs on — a caller that has to remember
/// to read `binding.epoch` is a caller that can forget, which is precisely the
/// bug this returns it to prevent.
/// Returns the [`RulesetBoot`] itself as well as the loaded rules, and that is
/// `Q0b B3b`'s doing. Boot used to drop it: the binding was read once, at
/// startup, and the handle that could read it *again* went out of scope with
/// the function. An epoch switch has to re-read the binding while the node is
/// running, so a node that had thrown the store away could only have obtained
/// the new rules by trusting a Redis payload — which is the design
/// `epoch_signal` exists to refuse.
pub async fn boot_reality(
    state_root: &str,
    meta_url: Option<&str>,
    allowlist: &str,
    reality_id: &str,
    create: bool,
    ruleset_path: Option<&str>,
) -> anyhow::Result<(RulesetBoot, std::sync::Arc<Ruleset>, sim_core::RulesetEpoch)> {
    let boot = RulesetBoot::open(state_root, meta_url, allowlist).await?;
    println!("BINDINGS <- {}", boot.provenance);
    if create {
        println!("{}", boot.create(reality_id, ruleset_path)?);
    }
    let (r, binding) = boot.load(reality_id)?;
    println!(
        "RULESET {} <- store (NOT re-resolved), reality epoch {}",
        binding.digest, binding.epoch
    );
    Ok((boot, std::sync::Arc::new(r), sim_core::RulesetEpoch(binding.epoch)))
}
