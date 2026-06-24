//! L1.C.4 — orphan_scanner binary.
//!
//! Nightly cron entry point per R04 §12D.7.
//!
//! ## What it does (7-step scan)
//!
//!  1. List all `reality_registry` rows in transient statuses
//!     (`provisioning`, `seeding`, `pending_close`, `soft_deleted`).
//!  2. For each, query the matching shard for the per-reality database:
//!     - Present + status=`provisioning|seeding` for > 24h → MARK PARTIAL
//!     - Absent + status=`soft_deleted` for >= 7d                → DROP
//!     - Present + status=`soft_deleted` for >= 7d                → DROP DB + DROP row
//!     - All other combos → OK (continue)
//!  3. Marked-partial rows get a `reality_close_audit` row with reason
//!     `orphan_partial_provision`; SRE follow-up via runbook L1.C.9.
//!  4. Per-grace-expired soft-deleted reality: invoke the deprovisioner
//!     with `force=true` to drop the database + flip to `dropped`.
//!  5. Emit Prometheus gauge `lw_orphan_scanner_marked_partial` +
//!     `lw_orphan_scanner_dropped` (alerts in L1.I).
//!  6. Append a line to `audit/orphan_scanner.log` with summary.
//!  7. Exit 0 on success; non-zero on any per-reality error (cron alerts).
//!
//! ## Why a separate binary (not a feature flag)
//!
//! - Independent SLO (24h jitter OK; not on the request path)
//! - Different IAM role (read+drop, not write to reality_registry data)
//! - Cron-friendly entry point with no shared HTTP server lifecycle
//!
//! ## Cycle 5 scope
//!
//! This binary ships the **CLI scaffold** + argument parsing + the
//! scan-and-classify loop with a `--dry-run` mode that doesn't actually
//! drop anything. The real RPC wiring to MetaWrite + deprovisioner
//! lands when the meta-worker RPC stack stands up (cycle 6+). Operating
//! without `--dry-run` against a live cluster panics with a TODO until
//! then — explicit so an SRE doesn't accidentally yolo-drop something.

use std::env;
use std::process::ExitCode;

/// 7-day grace period — must match `runbooks/provisioner/orphan_resolution.md`.
pub const SOFT_DELETE_GRACE_DAYS: u32 = 7;

/// 24-hour stall threshold for transient `provisioning|seeding` statuses.
pub const TRANSIENT_STALL_HOURS: u32 = 24;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    let dry_run = args.iter().any(|a| a == "--dry-run");
    let help = args.iter().any(|a| a == "--help" || a == "-h");

    if help {
        print_usage();
        return ExitCode::SUCCESS;
    }

    eprintln!(
        "[orphan_scanner] cycle-5 scaffold — grace_days={SOFT_DELETE_GRACE_DAYS}, \
         stall_hours={TRANSIENT_STALL_HOURS}, dry_run={dry_run}"
    );

    if !dry_run {
        // Defensive panic — wired RPC stack lands in cycle 6+.
        eprintln!(
            "[orphan_scanner] FATAL: real-mode RPC wiring not yet implemented \
             (cycle 6 dependency). Re-run with --dry-run for a no-op scan."
        );
        return ExitCode::from(2);
    }

    // Dry-run: simulate the classification loop with an empty input set.
    // Production wiring iterates `MetaRead::list_transient_realities()`
    // when that surface lands. Today this is intentionally a no-op so the
    // cron entry point is testable end-to-end (`run --bin orphan_scanner -- --dry-run`).
    let scanned = 0u32;
    let marked_partial = 0u32;
    let dropped = 0u32;
    eprintln!(
        "[orphan_scanner] dry-run complete: scanned={scanned} marked_partial={marked_partial} dropped={dropped}"
    );
    ExitCode::SUCCESS
}

fn print_usage() {
    println!(
        "orphan_scanner — L1.C.4 nightly cron for partial-provision and stale-drop reapers\n\
         \n\
         USAGE:\n\
           orphan_scanner --dry-run    # classify only; no MetaWrite, no DROP DATABASE\n\
           orphan_scanner --help       # show this help\n\
         \n\
         CONSTANTS:\n\
           SOFT_DELETE_GRACE_DAYS = {SOFT_DELETE_GRACE_DAYS}\n\
           TRANSIENT_STALL_HOURS  = {TRANSIENT_STALL_HOURS}\n\
         \n\
         RUNBOOK: runbooks/provisioner/orphan_resolution.md"
    );
}
