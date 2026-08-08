#!/usr/bin/env python3
"""Mutate each guard of the reality layer and require its test to go RED.

Covers two suites, in two languages:

  * `admin reality provision` (Go)     — W3, the command that CREATES a database
  * `orphan_scan::classify`  (Rust)    — W5, what a half-finished provision leaves

WHY THIS EXISTS
---------------
Both subjects are almost entirely guards — refuse a blank db_name, refuse a
mismatched reality_id, refuse an inherited environment, refuse a dry run that
found no capacity; flag a stalled provision, flag a database no registry row
claims — and a guard whose test cannot fail is worse than no guard, because it
reports coverage (`docs/standards/non-vacuity.md`, NV-1).

Tests passing proves nothing on its own. This proves each one is load bearing:
break the guard, watch the named test go red, put it back.

WHY IT RESTORES WITH GIT
------------------------
`scripts/gate-bite-harness.py` records a hand-run of this same idea that was
killed mid-run and left two `if False:` mutations in the working tree. It
solved that by mutating a COPY — which Go cannot do, since a second file in the
package redeclares every symbol. So this mutates in place and treats **git as
the restore authority**: it refuses to start if the targets are already dirty,
and restores with `git checkout --` rather than from memory. A kill mid-run
therefore leaves dirt that the NEXT run refuses to paper over.

A mutation must stay COMPILABLE. A build failure proves the compiler works, not
that the test observes the defect — the harness treats a build failure as a
weak red and says so.

    python scripts/reality-layer-bite-harness.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CMDS = REPO / "services" / "admin-cli" / "internal" / "commands"
PROV = CMDS / "provision_reality.go"
PROVPG = CMDS / "provision_reality_pg.go"
GOMOD = REPO / "services" / "admin-cli"
ORPHAN = REPO / "services" / "world-service" / "src" / "orphan_scan.rs"
WORKER = REPO / "services" / "world-service" / "src" / "bin" / "provision.rs"

GO, RUST = "go", "rust"

# (label, file, anchor, mutation, test regex) — the Go suite
GO_BITES: list[tuple[str, Path, str, str, str]] = [
    (
        "blank db_name accepted (a success we cannot point at)",
        PROV,
        'if strings.TrimSpace(out.DBName) == "" {',
        "if false {",
        "TestRunProvision_BlankDBNameIsError",
    ),
    (
        "dry run reports success when no shard has capacity",
        PROV,
        "if req.DryRun && !out.WouldProvision {",
        "if false {",
        "TestRunProvision_DryRunNoCapacityIsError",
    ),
    (
        "nil invoker not refused",
        PROV,
        "if deps.Invoker == nil {",
        "if false && deps.Invoker == nil {",
        "TestRunProvision_NilInvokerRefuses",
    ),
    (
        "worker output for a DIFFERENT reality accepted as ours",
        PROVPG,
        'if got := strings.TrimSpace(out.RealityID); got != "" && got != req.RealityID.String() {',
        "if got := strings.TrimSpace(out.RealityID); false && got != req.RealityID.String() {",
        "TestProvisionInvoker_RealityIDMismatchRefused",
    ),
    (
        "exit 2 (nothing attempted) indistinguishable from a real failure",
        PROVPG,
        "case 2:",
        "case 222:",
        "TestProvisionInvoker_Exit2IsSetupFailure",
    ),
    (
        "child environment inherited from the host (the wrong-Postgres bug)",
        PROVPG,
        "\treturn env\n}",
        "\treturn append(os.Environ(), env...)\n}",
        "TestProvisionInvoker_ChildEnvIsNotInherited",
    ),
    (
        "--dry-run not forwarded: a 'preview' that provisions",
        PROVPG,
        'args = append(args, "--dry-run")',
        "_ = req.DryRun",
        "TestProvisionInvoker_DryRunFlagReachesWorker",
    ),
    (
        "env validated only after exec",
        PROVPG,
        "if err := i.env.Validate(); err != nil {",
        "if err := error(nil); err != nil {",
        "TestProvisionInvoker_IncompleteEnvRefusedBeforeExec",
    ),
    (
        "deploy_cohort range unchecked",
        PROV,
        "if r.DeployCohort < 0 || r.DeployCohort > 99 {",
        "if false {",
        "TestProvisionRequest_RejectsCohortOutOfRange",
    ),
    (
        "nil UUID accepted as a reality id",
        PROV,
        "if r.RealityID == uuid.Nil {",
        "if false {",
        "TestProvisionRequest_RejectsNilUUID",
    ),
    (
        "a placement naming NO shard is reported as success",
        PROV,
        'if strings.TrimSpace(out.Shard) == "" {',
        "if false {",
        "TestRunProvision_BlankShardIsError",
    ),
    (
        "no-capacity is diagnosed as a blank shard instead of as capacity",
        PROV,
        "if req.DryRun && !out.WouldProvision {",
        "if false {",
        "TestRunProvision_NoCapacityDiagnosedBeforeBlankShard",
    ),
    (
        "the owner never reaches the worker (reality silently becomes platform-owned)",
        PROVPG,
        'args = append(args, "--owner-user-id", req.OwnerUserID.String())',
        "_ = req.OwnerUserID",
        "TestProvisionInvoker_OwnerReachesWorker",
    ),
    (
        "an absent owner still sends the flag (an empty owner reaches the server)",
        PROVPG,
        # INVERT rather than `if true`: the latter orphans the uuid import and
        # the bite goes red on the build instead of the assertion.
        "if req.OwnerUserID != uuid.Nil {",
        "if req.OwnerUserID == uuid.Nil {",
        "TestProvisionInvoker_NoOwnerSendsNoFlag",
    ),
    (
        "locale is unvalidated (the old len>35 check)",
        PROV,
        "if l := strings.TrimSpace(r.Locale); l != \"\" && !looksLikeBCP47(l) {",
        "if l := strings.TrimSpace(r.Locale); l != \"\" && len(l) > 35 {",
        "TestProvisionRequest_LocaleIsValidated",
    ),
]

# The Rust suite — orphan_scan::classify (W5).
RUST_BITES: list[tuple[str, Path, str, str, str]] = [
    (
        "a stalled provision is never flagged",
        ORPHAN,
        "if in_flight && row.age_hours >= thresholds.stall_hours {",
        "if false {",
        "orphan_scan::tests::stalled_provision_is_flagged_past_the_window",
    ),
    (
        "the stall threshold is ignored (every in-flight row is an orphan)",
        ORPHAN,
        "if in_flight && row.age_hours >= thresholds.stall_hours {",
        "if in_flight {",
        "orphan_scan::tests::a_provision_inside_the_window_is_not_an_orphan",
    ),
    (
        "the threshold is hardcoded instead of taken from config",
        ORPHAN,
        "if in_flight && row.age_hours >= thresholds.stall_hours {",
        "if in_flight && row.age_hours >= 24 {",
        "orphan_scan::tests::thresholds_are_honoured_not_hardcoded",
    ),
    (
        "one broken provision reports twice (stalled AND missing-database)",
        ORPHAN,
        "            // A stalled row is already reported; do not also report its absent\n"
        "            // database as a separate finding — one broken provision is one\n"
        "            // problem, and duplicate findings inflate the alert.\n"
        "            continue;",
        "            // bite: dedup removed",
        "orphan_scan::tests::one_broken_provision_produces_one_finding",
    ),
    (
        "a registry row whose database vanished is not flagged",
        ORPHAN,
        "if !db_present && DB_EXPECTED_STATUSES.contains(&row.status.as_str()) {",
        "if false {",
        "orphan_scan::tests::active_row_without_a_database_is_missing_not_stalled",
    ),
    (
        "an untracked database (invisible to capacity) is not flagged",
        ORPHAN,
        "if !rows.iter().any(|r| &r.db_name == db) {",
        "if false {",
        "orphan_scan::tests::untracked_database_is_flagged",
    ),
    (
        "healthy active databases are reported as untracked (the filter inversion)",
        ORPHAN,
        "if !rows.iter().any(|r| &r.db_name == db) {",
        "if !rows.iter().any(|r| &r.db_name == db && IN_FLIGHT_STATUSES.contains(&r.status.as_str())) {",
        "orphan_scan::tests::active_databases_are_not_reported_as_untracked",
    ),
    (
        "the grace period is ignored — soft-deleted reclaimed immediately",
        ORPHAN,
        "if row.status == SOFT_DELETED_STATUS && row.age_hours >= thresholds.grace_days * 24 {",
        "if row.status == SOFT_DELETED_STATUS {",
        "orphan_scan::tests::soft_deleted_inside_grace_is_left_alone",
    ),
    (
        "soft-deleted past grace is never reclaimed",
        ORPHAN,
        "if row.status == SOFT_DELETED_STATUS && row.age_hours >= thresholds.grace_days * 24 {",
        "if false {",
        "orphan_scan::tests::soft_deleted_past_grace_is_drop_eligible",
    ),
    (
        "a stalled finding does not record whether the database exists",
        ORPHAN,
        "database_present: db_present,",
        "database_present: true,",
        "orphan_scan::tests::stalled_finding_records_whether_the_database_exists",
    ),
    (
        "an in-flight status is treated as settled (a retry would re-provision over it)",
        WORKER,
        # SWAP, not insert: SETTLED_STATUSES is `[&str; 6]`, so adding a seventh
        # element is a type error — the mutation would prove the compiler works
        # rather than that the test observes the defect.
        '    "migrating",',
        '    "provisioning",',
        "tests::settled_statuses_cover_every_state_past_provisioning",
    ),
    (
        "a malformed owner is silently ignored instead of refused",
        WORKER,
        'Uuid::parse_str(val).map_err(|e| format!("--owner-user-id: {e}"))?,',
        "Uuid::parse_str(val).unwrap_or(Uuid::nil()),",
        "tests::a_malformed_owner_is_refused_not_ignored",
    ),
    (
        "an absent owner is coerced to a default instead of staying None",
        WORKER,
        "let mut owner_user_id: Option<Uuid> = None;",
        "let mut owner_user_id: Option<Uuid> = Some(Uuid::nil());",
        "tests::owner_is_optional_and_absent_means_platform_owned",
    ),
    (
        "the dry-run preview re-implements the db name instead of calling it",
        WORKER,
        "world_service::provisioner::db_name_for(reality_id)",
        'format!("lw_reality_{}", &reality_id.simple().to_string()[..11])',
        "tests::preview_names_what_the_provisioner_will_create",
    ),
]

SUITES = [(GO, GO_BITES), (RUST, RUST_BITES)]
ALL_BITES = GO_BITES + RUST_BITES

TARGETS = sorted({str(p.relative_to(REPO)).replace("\\", "/") for _, p, _, _, _ in ALL_BITES})


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def dirty() -> list[str]:
    out = git("status", "--porcelain", "--", *TARGETS).stdout.strip()
    return [ln for ln in out.splitlines() if ln.strip()]


def restore() -> None:
    git("checkout", "--", *TARGETS)


def run_test(suite: str, regex: str) -> tuple[int, str]:
    if suite == GO:
        p = subprocess.run(
            ["go", "test", "./internal/commands/", "-run", regex, "-count=1"],
            cwd=GOMOD,
            capture_output=True,
            text=True,
        )
    else:
        # Tests inside `src/bin/provision.rs` belong to the BIN target, not the
        # lib; `--lib` would silently match nothing there.
        target = ["--bin", "provision"] if regex.startswith("tests::") else ["--lib"]
        p = subprocess.run(
            ["cargo", "test", "-p", "world-service", *target, regex, "--", "--exact"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        # cargo exits 0 when a filter matches NOTHING, which would read as a
        # passing bite. Demand that the named test actually ran.
        if p.returncode == 0 and "1 passed" not in (p.stdout + p.stderr):
            return 1, p.stdout + p.stderr + "\n[harness] filter matched no test — treated as red"
    return p.returncode, p.stdout + p.stderr


def red_names_the_test(out: str, regex: str) -> bool:
    """Did the NAMED test fail, or did something else break?

    A bite is only evidence if the test that names the property is the thing
    that went red. `BDR-50`: a cold-start review found a bite passing through a
    truncated assertion window — red, but for a reason unrelated to the guard.
    Build failures were already caught; this catches the subtler case where an
    unrelated test in the same package fails instead.
    """
    leaf = regex.rsplit("::", 1)[-1]
    for line in out.splitlines():
        if ("--- FAIL" in line or "FAILED" in line) and leaf in line:
            return True
    # Rust prints a `failures:` block listing the failing test paths.
    return any(leaf in l and l.strip().startswith(("test ", leaf)) and "FAILED" in l
               for l in out.splitlines())


def main() -> int:
    if d := dirty():
        print("REFUSING TO RUN — the bite targets have uncommitted changes:")
        for ln in d:
            print("   " + ln)
        print(
            "\nThis harness restores with `git checkout --`, which would DISCARD them.\n"
            "Commit or stash first. (If a previous run was killed mid-bite, the dirt\n"
            "above IS the leftover mutation — inspect it, then `git checkout --` it.)"
        )
        return 2

    for suite, name in ((GO, "Provision"), (RUST, "orphan_scan::tests::healthy_shard_yields_nothing")):
        rc, out = run_test(suite, name)
        if rc != 0:
            print(f"BASELINE NOT GREEN ({suite}) — fix before biting:\n" + out[-2500:])
            return 1
    print("baseline: GREEN (go + rust)\n")

    failures: list[tuple[str, str]] = []
    try:
        for suite, bites in SUITES:
            print(f"── {suite} ──")
            for label, path, anchor, mutation, regex in bites:
                src = path.read_text(encoding="utf-8")
                n = src.count(anchor)
                if n != 1:
                    print(f"[ANCHOR]  {label}: anchor found {n}x (need exactly 1) — bite skipped")
                    failures.append((label, f"anchor found {n}x"))
                    continue
                path.write_text(src.replace(anchor, mutation), encoding="utf-8")
                rc, out = run_test(suite, regex)
                restore()
                if rc == 0:
                    print(f"[VACUOUS] {label}\n           -> {regex} stayed GREEN with the guard broken")
                    failures.append((label, "test stayed green"))
                elif "build failed" in out or "] undefined" in out or "error[E" in out:
                    print(f"[WEAK]    {label}\n           -> went red via BUILD FAILURE, not the assertion")
                    failures.append((label, "build failure, not an assertion"))
                elif not red_names_the_test(out, regex):
                    print(
                        f"[WEAK]    {label}\n           -> red, but {regex} is not named in the "
                        f"failure — something ELSE broke"
                    )
                    failures.append((label, "red for an unrelated reason"))
                else:
                    line = next(
                        (l for l in out.splitlines() if "--- FAIL" in l or "FAILED" in l or "panicked at" in l),
                        "(red)",
                    )
                    print(f"[RED]     {label}\n           -> {line.strip()[:100]}")
            print()
    finally:
        restore()

    rc, _ = run_test(GO, "Provision")
    print()
    if rc != 0:
        print("RESTORE FAILED — tests are not green after restore. Inspect `git status`.")
        return 1
    if d := dirty():
        print("RESTORE INCOMPLETE — targets still dirty:\n  " + "\n  ".join(d))
        return 1
    print("restored: GREEN, working tree clean")

    if failures:
        print(f"\n{len(failures)} bite(s) did not prove their guard:")
        for label, why in failures:
            print(f"  - {label}: {why}")
        return 1
    print(
        f"\nall {len(ALL_BITES)} guards proved load-bearing "
        f"({len(GO_BITES)} go + {len(RUST_BITES)} rust)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
