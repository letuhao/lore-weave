//! `dp-clippy` — the `DP-K11` lint crate. Slice 2 ships the first rule.
//!
//! # `dp::forbid_raw_kernel_client` (`DP-R3`)
//!
//! A crate that is not part of the data-plane SDK must not reach the kernel's
//! storage directly. It goes through `dp`, which is what makes tiering,
//! scoping, backpressure and instrumentation enforceable at all — a feature
//! crate holding a `PgPool` has stepped around every one of them.
//!
//! ## The subject is real, and that is why this ships RED
//!
//! Measured by the lint itself over the workspace: **9 findings across 4
//! crates** — `world-service` 5, `service-http` 2, `meta-rs` 1, `world-gen` 1 —
//! plus **2 crates it cannot reach yet** (`roleplay-service`,
//! `commit-service`, blocked behind `service-http`; see `2G`). A lint that is
//! green the day it lands is a lint whose subject has not been found yet; this
//! session removed four mechanisms with that shape. The red is the evidence the
//! rule bites, and migrating those crates is the work it drives.
//!
//! An earlier draft of this paragraph said *"47 files"*. That was a grep count
//! of files mentioning `sqlx::`/`redis::` anywhere — not a violation count, and
//! not something this lint had ever measured. The number that moves is the
//! ratchet in `contracts/dp/dp-clippy-baseline.json`.
//!
//! ## The exemption is a MARKER, not a name (`2F-2`)
//!
//! `11_access_pattern_rules.md:66` locks the rule as *"scans for forbidden
//! imports in any crate other than `dp` itself"*. Applied literally that fires
//! on **`crates/dp-kernel`** — which holds `event_store_pg.rs`, `outbox.rs` and
//! `load_aggregate.rs`, i.e. it is exactly where the database code is SUPPOSED
//! to live. A rule whose first true positive is the component it exists to
//! protect is a rule nobody will keep.
//!
//! So the exemption is `[package.metadata.dp] dp-crate = true` in the crate's
//! own `Cargo.toml`. `DP-R3` already specifies that marker; only its prose
//! exemption said "the crate named dp". The amendment is recorded in the
//! run-state as `2D`.
//!
//! `V1-F12` had removed the marker from `crates/dp/Cargo.toml` because *"a
//! declared input with no consumer is the orphan shape `orphan-model-gate`
//! refuses"*, and said it *"arrives in the same commit as the lint that reads
//! it"*. It arrived one commit later than that, in `2C`, because the lint
//! shipped first with a hardcoded name list standing in for the marker — see
//! the section below, which is the record of that stand-in being removed.
//!
//! ## The lint reads the MARKER, not a list of names (`2C`)
//!
//! The first draft of this file carried `const DP_CRATES: &[&str]` — a
//! hardcoded list of four crate names — and a comment claiming a companion
//! gate would keep that list in agreement with the manifests. Both halves were
//! wrong:
//!
//!   * The gate (`scripts/dp-crate-marker-gate.py`) **did not exist**. It was
//!     a citation of an apparatus that had never been written, which is the
//!     defect `V.1` round 1 caught as `M3` — a test named in evidence that was
//!     not there.
//!   * A name list is **default-uncovered** (`NV-3`) in the direction that
//!     matters least and over-covered in the direction that matters most: a
//!     data-plane crate created tomorrow is linted (merely annoying), while
//!     every name already on the list is exempt forever, whether or not its
//!     manifest says so. It is a private exemption channel that no reviewer
//!     of a `Cargo.toml` would ever see.
//!
//! A lint runs inside rustc and cannot ask cargo questions — but cargo puts
//! `CARGO_MANIFEST_DIR` in the environment of the rustc process it spawns
//! (which is exactly why `env!("CARGO_MANIFEST_DIR")` works in ordinary code).
//! Measured under `cargo dylint`: the variable is present and names the crate
//! being compiled. So the lint reads the crate's real manifest, and the marker
//! `DP-K11` specified is the mechanism rather than a description of one.
//!
//! Two consequences worth stating, because they are the reason this shape is
//! better rather than merely tidier:
//!
//!   * **The exemption is reviewable.** It lives in the exempted crate's own
//!     `Cargo.toml`, in the diff of whoever claims it, instead of in a lint
//!     crate outside the workspace that a feature author never opens.
//!   * **A new crate is covered by default.** No marker means not exempt, so
//!     the uncovered case fails safe. That is the `NV-3` direction.

#![feature(rustc_private)]
#![warn(unused_extern_crates)]

extern crate rustc_hir;
extern crate rustc_span;

use rustc_hir as hir;
use rustc_lint::{LateContext, LateLintPass, LintContext};
use rustc_span::Symbol;

dylint_linting::impl_late_lint! {
    /// ### What it does
    /// Forbids a non-SDK crate from importing a raw kernel storage client.
    ///
    /// ### Why is this bad?
    /// The `dp` SDK is what makes tier, scope, backpressure and instrumentation
    /// enforceable. A crate holding its own `PgPool` has bypassed all four, and
    /// no amount of review catches it reliably — `sqlx::` reads as ordinary Rust.
    ///
    /// ### Exemption
    /// Add to the crate's `Cargo.toml`:
    /// ```toml
    /// [package.metadata.dp]
    /// dp-crate = true
    /// ```
    /// That is for crates that ARE the data plane, not for crates that find the
    /// lint inconvenient. Today exactly one carries it: `dp-kernel`. `crates/dp`
    /// deliberately does NOT — its `[dependencies]` is empty and `S2.3`'s
    /// "declares no I/O" rests on that, so a raw client there is a defect and
    /// the lint firing on it is the point.
    ///
    /// ### Example
    /// ```rust,ignore
    /// use sqlx::PgPool;             // error: a feature crate must go through `dp`
    /// ```
    pub FORBID_RAW_KERNEL_CLIENT,
    Deny,
    "a non-SDK crate must not import a raw kernel storage client (DP-R3)",
    ForbidRawKernelClient::default()
}

/// Lint state: the exemption verdict for the crate under compilation.
///
/// `None` until the first `use` item is seen, then the parsed answer. Cached
/// because `check_item` runs per item and the manifest cannot change during a
/// single rustc invocation — but cached *in the pass*, not in a `static`, so
/// the correctness of this lint never depends on the assumption that one
/// process compiles exactly one crate.
#[derive(Default)]
struct ForbidRawKernelClient {
    is_dp_crate: Option<bool>,
}

/// The forbidden paths, verbatim from `DP-K11`'s skeleton.
///
/// Matched on the FIRST TWO segments (`sqlx::PgPool` → `["sqlx", "PgPool"]`)
/// rather than the full path string, because `use sqlx::pool::PgPool` and
/// `use sqlx::PgPool as P` are the same violation wearing different text. The
/// skeleton's list is a set of type paths; this is that set, resolved.
const FORBIDDEN: &[(&str, &str)] = &[
    ("sqlx", "PgPool"),
    ("sqlx", "Pool"),
    ("tokio_postgres", "Client"),
    ("redis", "Client"),
    ("redis", "Connection"),
    ("deadpool_postgres", "Pool"),
    ("deadpool_redis", "Pool"),
];

/// The one plane value that exempts a crate. Closed set of one, on purpose:
/// anything else — including `plane = "game"` — does NOT exempt, so a typo or
/// an invented value fails toward being governed.
const EXEMPT_PLANE: &str = "platform";

/// Is the crate being compiled outside `DP-R3`'s reach?
///
/// TWO DIFFERENT TRUE THINGS, and conflating them is why this function is not
/// just a boolean read:
///
///   * `dp-crate = true` — the crate **IS** the data plane. Holding a raw
///     client is its job (`dp-kernel`: `event_store_pg.rs`, `outbox.rs`).
///   * `plane = "platform"` — the crate is **not governed by `DP-R3` at all**.
///     `01_scope_and_boundary.md` §4 is LOCKED and defines the scope by the
///     DATABASE, not by the language: *"if a service reads or writes any
///     aggregate in a per-reality database (`reality_<id>_db`), it is a
///     game-layer service and uses the DP SDK."* A crate whose Postgres is a
///     platform-plane per-service DB, the meta DB, or a cache is simply not
///     what the rule is about.
///
/// The second key exists because four crates were red for a reason that was
/// not debt. `crates/service-http`'s own module doc says its `db::init` is
/// *"the per-service-DB pattern … a normal platform-plane DB like
/// `loreweave_chat`, NOT the kernel services' per-reality sidecar model"* —
/// i.e. the crate documented itself as out of scope before the lint existed.
/// Marking those four `dp-crate = true` would have put a FALSE claim in four
/// manifests to silence a true positive of the wrong rule.
///
/// Every failure path returns `false` — no manifest, unreadable file, malformed
/// TOML, absent key, wrong type, unrecognised plane. A crate wins the exemption
/// only by successfully asserting it, so every failure mode produces a lint
/// error to investigate rather than silent permission.
///
/// The CLAIM is not checked here — a lint cannot know which database a crate
/// opens. `scripts/dp-clippy-gate.py` does that: it requires a written reason
/// and refuses a `platform` claim from any crate that consumes per-reality
/// ROUTING, which is how a game-layer crate finds a `reality_<id>` database in
/// the first place. Measured: exactly `world-service` consumes it, and
/// `world-service` is the one crate here whose findings are real debt.
fn is_exempt() -> bool {
    let Ok(dir) = std::env::var("CARGO_MANIFEST_DIR") else {
        return false;
    };
    let Ok(text) = std::fs::read_to_string(std::path::Path::new(&dir).join("Cargo.toml")) else {
        return false;
    };
    let Ok(manifest) = text.parse::<toml::Table>() else {
        return false;
    };
    let Some(dp) = manifest
        .get("package")
        .and_then(toml::Value::as_table)
        .and_then(|p| p.get("metadata"))
        .and_then(toml::Value::as_table)
        .and_then(|m| m.get("dp"))
        .and_then(toml::Value::as_table)
    else {
        return false;
    };

    if dp.get("dp-crate").and_then(toml::Value::as_bool) == Some(true) {
        return true;
    }
    dp.get("plane").and_then(toml::Value::as_str) == Some(EXEMPT_PLANE)
}

impl<'tcx> LateLintPass<'tcx> for ForbidRawKernelClient {
    fn check_item(&mut self, cx: &LateContext<'tcx>, item: &'tcx hir::Item<'tcx>) {
        let hir::ItemKind::Use(path, _) = item.kind else {
            return;
        };

        if *self.is_dp_crate.get_or_insert_with(is_exempt) {
            return;
        }

        // Only for the message. `dp-kernel` normalises to `dp_kernel`.
        let this_crate = cx.tcx.crate_name(hir::def_id::LOCAL_CRATE);

        let segments: Vec<Symbol> = path.segments.iter().map(|s| s.ident.name).collect();
        if segments.len() < 2 {
            return;
        }
        let (head, next) = (segments[0].as_str(), segments[1].as_str());

        for (krate, ty) in FORBIDDEN {
            // `use sqlx::PgPool` matches head+next; `use sqlx::pool::PgPool`
            // matches on the head plus the LAST segment.
            let last = segments.last().map(|s| s.as_str().to_string()).unwrap_or_default();
            if head == *krate && (next == *ty || last == *ty) {
                cx.span_lint(FORBID_RAW_KERNEL_CLIENT, item.span, |diag| {
                    diag.primary_message(format!(
                        "`{krate}::{ty}` in `{this_crate}`: a non-SDK crate must not hold a raw \
                         kernel client (DP-R3)"
                    ));
                    diag.help(
                        "go through the `dp` SDK. If this crate IS the data plane, declare it: \
                         [package.metadata.dp] dp-crate = true",
                    );
                });
                return;
            }
        }
    }
}
