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
//! `sqlx::`/`redis::` appear in **47 files** outside the four pure crates
//! (`world-service` 15, `roleplay-service` 7, `commit-service` 6, `dp-kernel` 4,
//! `service-http` 3, `meta-rs` 2, `world-gen` 1). A lint that is green the day
//! it lands is a lint whose subject has not been found yet; this session
//! removed four mechanisms with that shape. The red is the evidence the rule
//! bites, and migrating those files is the work it drives.
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
//! The marker is re-added in the SAME change as this lint, deliberately:
//! `V1-F12` removed it because *"a declared input with no consumer is the
//! orphan shape `orphan-model-gate` refuses"*, and said it *"arrives in the
//! same commit as the lint that reads it"*.

#![feature(rustc_private)]
#![warn(unused_extern_crates)]

extern crate rustc_hir;
extern crate rustc_span;

use rustc_hir as hir;
use rustc_lint::{LateContext, LateLintPass, LintContext};
use rustc_span::Symbol;

dylint_linting::declare_late_lint! {
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
    /// That is for crates that ARE the data plane (`dp`, `dp-kernel`), not for
    /// crates that find the lint inconvenient.
    ///
    /// ### Example
    /// ```rust,ignore
    /// use sqlx::PgPool;             // error: a feature crate must go through `dp`
    /// ```
    pub FORBID_RAW_KERNEL_CLIENT,
    Deny,
    "a non-SDK crate must not import a raw kernel storage client (DP-R3)"
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

/// Crate names that ARE the data plane, and so may hold raw clients.
///
/// This is the compiled-in fallback for the `dp-crate = true` marker: a lint
/// runs inside rustc and cannot read the crate's `Cargo.toml`, so the marker is
/// checked by the wired gate that accompanies this lint
/// (`scripts/dp-crate-marker-gate.py`), and the lint itself keys on the crate
/// name it is compiling. The two must agree — the gate asserts they do, which
/// is what stops this list becoming a private exemption channel.
const DP_CRATES: &[&str] = &["dp", "dp_clippy", "dp_kernel", "dp_kernel_macros"];

impl<'tcx> LateLintPass<'tcx> for ForbidRawKernelClient {
    fn check_item(&mut self, cx: &LateContext<'tcx>, item: &'tcx hir::Item<'tcx>) {
        let hir::ItemKind::Use(path, _) = item.kind else {
            return;
        };

        // The crate being compiled. `dp-kernel` normalises to `dp_kernel`.
        let this_crate = cx.tcx.crate_name(hir::def_id::LOCAL_CRATE);
        if DP_CRATES.contains(&this_crate.as_str()) {
            return;
        }

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
