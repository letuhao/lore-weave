#!/usr/bin/env python3
"""Mutate each guard of `admin reality provision` and require its test to go RED.

WHY THIS EXISTS
---------------
`reality provision` is the command that CREATES a database. Its Go layer is
almost entirely guards — refuse a blank db_name, refuse a mismatched
reality_id, refuse an inherited environment, refuse a dry run that found no
capacity — and a guard whose test cannot fail is worse than no guard, because
it reports coverage (`docs/standards/non-vacuity.md`, NV-1).

Twenty tests passing proves nothing on its own. This proves each one is load
bearing: break the guard, watch the named test go red, put it back.

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

    python scripts/provision-command-bite-harness.py
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

# (label, file, anchor, mutation, test regex)
BITES: list[tuple[str, Path, str, str, str]] = [
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
        "if !out.WouldProvision {",
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
]

TARGETS = sorted({str(p.relative_to(REPO)).replace("\\", "/") for _, p, _, _, _ in BITES})


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def dirty() -> list[str]:
    out = git("status", "--porcelain", "--", *TARGETS).stdout.strip()
    return [ln for ln in out.splitlines() if ln.strip()]


def restore() -> None:
    git("checkout", "--", *TARGETS)


def run_test(regex: str) -> tuple[int, str]:
    p = subprocess.run(
        ["go", "test", "./internal/commands/", "-run", regex, "-count=1"],
        cwd=GOMOD,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout + p.stderr


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

    rc, out = run_test("Provision")
    if rc != 0:
        print("BASELINE NOT GREEN — fix before biting:\n" + out[-2500:])
        return 1
    print("baseline: GREEN\n")

    failures: list[tuple[str, str]] = []
    try:
        for label, path, anchor, mutation, regex in BITES:
            src = path.read_text(encoding="utf-8")
            n = src.count(anchor)
            if n != 1:
                print(f"[ANCHOR]  {label}: anchor found {n}x (need exactly 1) — bite skipped")
                failures.append((label, f"anchor found {n}x"))
                continue
            path.write_text(src.replace(anchor, mutation), encoding="utf-8")
            rc, out = run_test(regex)
            restore()
            if rc == 0:
                print(f"[VACUOUS] {label}\n           -> {regex} stayed GREEN with the guard broken")
                failures.append((label, "test stayed green"))
            elif "build failed" in out or "] undefined" in out:
                print(f"[WEAK]    {label}\n           -> went red via BUILD FAILURE, not the assertion")
                failures.append((label, "build failure, not an assertion"))
            else:
                line = next((l for l in out.splitlines() if "--- FAIL" in l), "(red)")
                print(f"[RED]     {label}\n           -> {line.strip()[:100]}")
    finally:
        restore()

    rc, _ = run_test("Provision")
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
    print(f"\nall {len(BITES)} guards proved load-bearing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
