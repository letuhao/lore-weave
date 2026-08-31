#!/usr/bin/env python3
"""`DFO-6` — keep `contracts/testing/live-suites.yaml` honest.

# The problem this gate has, stated before the rules

The registry is AUTHORED, because a live suite cannot be discovered from Rust
source: `epoch_activation_live` reads its DSNs through a helper, and
`spine_drain_once_live` reaches `env::var` with the name as a PARAMETER. A
discovery pass that misses a suite reports complete coverage of an incomplete
list, which is worse than no discovery at all.

So this gate's four original checks never grep Rust for env vars. They check the
registry against things that cannot lie about themselves:

  * **the coverage claim** — `foundation-ci.yml` must run
    `python scripts/live-suites.py` over the WHOLE registry. That single leg is
    what makes every row actually execute; a `--only` or `--filter` on it looks
    like coverage and is not, so it reds.
  * **`foundation-ci.yml`'s per-target legs**, which are structured YAML. Every
    `cargo test -p X --test Y` step must have a `dedicated_ci_leg: true` row
    naming the same databases, and every such row must have a step. Both
    directions, so neither a dropped leg nor an aspirational row survives.
  * **the filesystem**, for `tests/<target>.rs`. A row naming a target that
    does not exist is a phantom.
  * **each target's own source**, for a skip announcement. A live suite that
    skips SILENTLY is indistinguishable from one that ran — both exit 0 — so
    the runner could report a clean sweep of no-ops.

`C4` ADDED A FIFTH, AND THE PARAGRAPH ABOVE IS WHY IT IS BOUNDED
--------------------------------------------------------------
Nothing walked disk -> registry, so a suite nobody registered was invisible:
the gate reported *"23 live suite(s), ALL run"* and was telling the truth about
the 23 it could see. Four more sat on disk in no row at all, three of them
shipped by an earlier run, and registering them then surfaced a SECOND latent
defect -- none of the four announced its skip.

So there is now a disk -> registry walk, and the warning above applies to it in
full. **It can only ADD findings. It can never certify that everything is
registered.** Measured 2026-08-22: it sees **19 of the 27** registered suites.
The other 8 hide their DSN exactly as this docstring predicted -- through a
helper (`epoch_activation_live`) or with the name as a PARAMETER
(`spine_drain_once_live`) -- and a suite that both hides its DSN and is
unregistered is still invisible.

That is worth having anyway: all four suites it would have caught named the env
var literally. What it must never be read as is a completeness claim, which is
why the OK line still counts REGISTRY rows and not discovered files.

Exit 0 clean · 1 finding · 2 misuse (the gate could not do its job).
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "contracts" / "testing" / "live-suites.yaml"
WORKFLOW = REPO / ".github" / "workflows" / "foundation-ci.yml"

# THE COVERAGE CHECK, and it replaced a ratchet.
#
# For one commit this file carried `UNCOVERED_MAX = 15` — how many live suites
# had no CI leg — on the reasoning that a count which may only shrink stops a
# new suite being default-uncovered. Then CI gained a single registry-driven
# leg that runs EVERY row, and the ratchet was measuring a quantity that no
# longer meant coverage: 15 suites with no leg OF THEIR OWN, all of them run.
# A check whose subject has drifted out from under it is worse than none, so it
# is gone, and this is what took its place.
#
# The workflow must invoke the runner over the WHOLE registry. `--only` or
# `--filter` would silently narrow it back to a subset, which is the exact
# shape — a leg that looks like coverage and is not — this exists to refuse.
REGISTRY_LEG = re.compile(r"python\s+scripts/live-suites\.py(?P<args>[^\r\n]*)")
NARROWING = ("--only", "--filter")

# A dev database name must announce itself as disposable. Same list the
# fixtures' own `guarded()` uses; these fixtures seed and truncate.
THROWAWAY_MARKERS = ("test", "smoke", "scratch", "throwaway", "sandbox")

CI_LEG = re.compile(
    r"cargo test\s+-p\s+(?P<pkg>[a-z0-9_-]+)"
    r"(?:\s+--features\s+(?P<feat>[a-z0-9_,-]+))?"
    r"\s+--test\s+(?P<target>[a-z0-9_]+)"
)


def load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except ImportError:
        print("live-suite-registry-gate: MISUSE — pyyaml is not installed", file=sys.stderr)
        sys.exit(2)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def ci_legs(text: str) -> dict[tuple[str, str], set[str]]:
    """`(package, target) -> the set of database names its step's env names`.

    A leg's databases are read from the `LOREWEAVE_*_URL:` lines in the same
    step, which sit ABOVE the `run:` in the workflow — so the scan walks
    backwards from each match to the step boundary rather than forwards.
    """
    lines = text.splitlines()
    legs: dict[tuple[str, str], set[str]] = {}
    for i, line in enumerate(lines):
        m = CI_LEG.search(line)
        if not m:
            continue
        dbs: set[str] = set()
        for j in range(i, max(-1, i - 12), -1):
            if j != i and re.match(r"\s*- name:", lines[j]):
                break
            for dsn in re.findall(r"postgres://[^/\s]+/([A-Za-z0-9_]+)", lines[j]):
                dbs.add(dsn)
        legs[(m.group("pkg"), m.group("target"))] = dbs
    return legs


SKIP_ANNOUNCE = re.compile(r'(eprintln!|println!)\s*\(\s*"?\s*(SKIP|\[skip\])', re.IGNORECASE)


def announces_skip(target_file: Path) -> bool:
    """Does this suite SAY when it does nothing?

    Reads the target and its helper MODULES — `epoch_activation_live` skips
    through `epoch_live_common::dsns()`, so the announcement is not in the
    target's own bytes.

    Helper modules only: `tests/<dir>/**.rs`, never the sibling `tests/*.rs`.
    The first version globbed the whole `tests/` directory, so ONE suite's
    `[skip]` vouched for every other target in the same crate — the check
    passed for a file that says nothing. Its own self-test arm caught it, which
    is the argument for writing the arm.
    """
    text = target_file.read_text(encoding="utf-8", errors="replace")
    for helper_dir in (p for p in target_file.parent.iterdir() if p.is_dir()):
        for sib in helper_dir.rglob("*.rs"):
            text += sib.read_text(encoding="utf-8", errors="replace")
    return bool(SKIP_ANNOUNCE.search(text))


def package_dir(pkg: str) -> Path | None:
    for base in ("crates", "services"):
        p = REPO / base / pkg
        if (p / "Cargo.toml").is_file():
            return p
    return None


#: A test file that reads one of these is a LIVE suite whatever else it is.
#:
#: `C4`. This gate walked registry -> disk and nothing walked disk -> registry,
#: so a suite that was never registered was INVISIBLE to it. It reported
#: "23 live suite(s), ALL run by the registry leg" and was telling the truth
#: about the 23 it could see; four more sat on disk in no row at all, three of
#: them shipped by an earlier run. Registering them then surfaced a second
#: latent defect — none of the four announced its skip — so the missing
#: direction was hiding two classes of problem, not one.
LIVE_DSN_ENV = re.compile(
    r"LOREWEAVE_TEST_PG_ADMIN_URL|LOREWEAVE_TEST_PG_URL|LOREWEAVE_TEST_REDIS_URL"
)


def live_suite_files(root: Path) -> list[tuple[str, str, Path]]:
    """`(package, target, path)` for every `tests/*.rs` that reads a live DSN.

    The package is the DIRECTORY name. That is what every registry row uses, and
    a Cargo `name =` that disagrees with its directory would be caught by the
    existing `package that does not exist` arm rather than here.
    """
    found: list[tuple[str, str, Path]] = []
    for base in ("crates", "services"):
        for tdir in sorted((root / base).glob("*/tests")):
            if not tdir.is_dir():
                continue
            for f in sorted(tdir.glob("*.rs")):
                try:
                    if LIVE_DSN_ENV.search(f.read_text(encoding="utf-8", errors="replace")):
                        found.append((tdir.parent.name, f.stem, f))
                except OSError:
                    continue
    return found


def unregistered_suites(reg: dict, root: Path) -> list[str]:
    """Live suites on disk that NO registry row names. The missing direction."""
    registered = {(s.get("package"), s.get("target")) for s in (reg.get("suites") or [])}
    return [
        f"{pkg}/{target}"
        for pkg, target, _ in live_suite_files(root)
        if (pkg, target) not in registered
    ]


def check(reg: dict, workflow_text: str, root: Path = REPO) -> list[str]:
    findings: list[str] = []
    suites = reg.get("suites") or []
    if not suites:
        print("live-suite-registry-gate: MISUSE — the registry lists no suites", file=sys.stderr)
        sys.exit(2)

    legs = ci_legs(workflow_text)
    if not legs:
        print(
            "live-suite-registry-gate: MISUSE — no `cargo test -p X --test Y` leg found in the\n"
            "  workflow. Either it was restructured or the pattern stopped matching; either way a\n"
            "  clean result here would mean nothing.",
            file=sys.stderr,
        )
        sys.exit(2)

    # `C4` -- THE MISSING DIRECTION. Everything below walks registry -> disk;
    # this walks disk -> registry. Without it a suite nobody registered is
    # invisible, and the gate reports full coverage of the subset it can see.
    on_disk = live_suite_files(root)
    if not on_disk:
        print(
            "live-suite-registry-gate: MISUSE -- no test file anywhere reads a live DSN.\n"
            "  Either the env names changed or the walk is looking in the wrong place;\n"
            "  either way a clean disk -> registry result would mean nothing.",
            file=sys.stderr,
        )
        sys.exit(2)
    for missing in unregistered_suites(reg, root):
        findings.append(
            f"`{missing}` reads a live DSN and is in NO registry row. The registry is the "
            "only complete list of live suites, so an unregistered suite runs in no CI leg "
            "and this gate cannot see it -- it would report full coverage of the rest."
        )

    seen_ids: set[str] = set()
    uncovered = 0
    claimed: set[tuple[str, str]] = set()

    for s in suites:
        sid = s.get("id", "<no id>")
        if sid in seen_ids:
            findings.append(f"duplicate id `{sid}`")
        seen_ids.add(sid)

        pkg, target = s.get("package"), s.get("target")
        pdir = package_dir(pkg or "")
        if pdir is None:
            findings.append(f"`{sid}`: no crate or service named `{pkg}`")
        elif not (pdir / "tests" / f"{target}.rs").is_file():
            findings.append(
                f"`{sid}`: names target `{target}` but "
                f"{pdir.relative_to(REPO)}/tests/{target}.rs does not exist — a phantom row"
            )
        elif not announces_skip(pdir / "tests" / f"{target}.rs"):
            # A live suite that skips SILENTLY is indistinguishable from one
            # that ran: both exit 0 and print `test result: ok`. The runner
            # reports SKIPPED as not-a-pass, and it can only do that if the
            # suite says so. This is checking a KNOWN list, not discovering one
            # — the registry names the file, so no grep is deciding scope.
            findings.append(
                f"`{sid}`: {target}.rs never announces a skip. Print `SKIP …` (or `[skip] …`) "
                f"on the no-DSN path, or a run where it did nothing is reported as a pass."
            )

        needs = s.get("needs") or []
        if not needs:
            findings.append(f"`{sid}`: declares no backing store, so it is not a live suite")
        for n in needs:
            if n.get("kind") in ("postgres", "postgres-admin") and n.get("schema") is None:
                findings.append(f"`{sid}`: `{n.get('env')}` has no `schema`")

        if s.get("dedicated_ci_leg"):
            claimed.add((pkg, target))
            if (pkg, target) not in legs:
                findings.append(
                    f"`{sid}`: claims `dedicated_ci_leg: true` but foundation-ci.yml has no "
                    f"`cargo test -p {pkg} --test {target}` leg"
                )
            else:
                want = {n["ci_db"] for n in needs if "ci_db" in n}
                got = legs[(pkg, target)]
                if want != got:
                    findings.append(
                        f"`{sid}`: CI databases disagree — registry says {sorted(want) or '[]'}, "
                        f"the workflow step names {sorted(got) or '[]'}"
                    )
        else:
            uncovered += 1
            if not (s.get("no_leg_reason") or "").strip():
                findings.append(
                    f"`{sid}`: `dedicated_ci_leg: false` with no `no_leg_reason`. "
                    f'"nobody got to it" is an honest reason; blank is not.'
                )

    for pkg, target in sorted(legs):
        if (pkg, target) not in claimed:
            findings.append(
                f"foundation-ci.yml runs `-p {pkg} --test {target}` and the registry has no "
                f"`dedicated_ci_leg: true` row for it — CI drifted ahead of the registry"
            )

    # THE COVERAGE CHECK. Everything above is about the six legacy legs not
    # drifting; THIS is the line that makes every suite actually run.
    m = REGISTRY_LEG.search(workflow_text)
    if not m:
        findings.append(
            "foundation-ci.yml never runs `python scripts/live-suites.py`. Without it CI "
            "covers only the suites with a leg of their own, and the rest are green in "
            "`cargo test --workspace` because they SKIPPED — which is how "
            "`epoch_activation_live` stayed dead since `M1`."
        )
    elif any(n in m.group("args") for n in NARROWING):
        findings.append(
            f"the registry leg is NARROWED (`{m.group('args').strip()}`). A filtered run "
            f"looks like coverage and is not — the suites outside the filter report nothing "
            f"at all."
        )
    return findings


def selftest() -> int:
    """Each rule, bitten. A gate is not trusted about the tree until it is.

    No `import yaml` here. It had one — UNUSED, under a comment claiming it was
    *"already proven importable by load_yaml's caller path"*, which is backwards:
    `main` runs `selftest()` BEFORE it ever calls `load_yaml`. On a runner
    without PyYAML that import made this gate die as a bare `Traceback` where
    its siblings printed a reason, and the self-test cases below need no YAML at
    all — they pass dicts. Second unused import to break something in one
    session; the first failed the only CI job on the branch.
    """
    ok_wf = """
      - name: run it
        env:
          LOREWEAVE_TEST_PG_URL: postgres://u:p@localhost:5432/real_smoke
        run: cargo test -p dp-kernel --test integration_event_store
      - name: every live suite
        run: python scripts/live-suites.py
"""

    def reg(**over):
        base = {
            "version": 1,
            "suites": [
                {
                    "id": "covered",
                    "package": "dp-kernel",
                    "target": "integration_event_store",
                    "dedicated_ci_leg": True,
                    "needs": [{"env": "X", "kind": "postgres", "schema": "self",
                               "ci_db": "real_smoke"}],
                },
                {
                    "id": "uncovered",
                    "package": "dp-kernel",
                    "target": "integration_writer_lease",
                    "dedicated_ci_leg": False,
                    "no_leg_reason": "no leg",
                    "needs": [{"env": "Y", "kind": "postgres", "schema": "per_reality"}],
                },
            ],
        }
        base.update(over)
        return base

    cases: list[tuple[str, dict, str, int]] = []

    cases.append(("a matching registry passes", reg(), ok_wf, 0))

    r = reg()
    r["suites"][0]["needs"][0]["ci_db"] = "wrong_smoke"
    cases.append(("a CI database name that disagrees fails", r, ok_wf, 1))

    r = reg()
    r["suites"][0]["target"] = "no_such_target"
    cases.append(("a target with no file on disk fails", r, ok_wf, 1))

    r = reg()
    r["suites"][0]["package"] = "not-a-crate"
    cases.append(("a package that does not exist fails", r, ok_wf, 1))

    r = reg()
    r["suites"][1]["no_leg_reason"] = "   "
    cases.append(("`dedicated_ci_leg: false` with a blank reason fails", r, ok_wf, 1))

    r = reg()
    r["suites"][0]["dedicated_ci_leg"] = False
    r["suites"][0]["no_leg_reason"] = "pretend"
    cases.append(("a leg CI runs with no `dedicated_ci_leg: true` row fails", r, ok_wf, 1))

    # THE COVERAGE ARMS. Everything else here is about drift between two
    # existing things; these two are the only ones that ask whether the suites
    # RUN at all.
    no_leg_wf = "\n".join(
        ln for ln in ok_wf.splitlines() if "live-suites.py" not in ln and "every live suite" not in ln
    )
    cases.append(("no registry leg in CI fails — nothing would run the other 15",
                  reg(), no_leg_wf, 1))

    narrowed_wf = ok_wf.replace("run: python scripts/live-suites.py",
                                "run: python scripts/live-suites.py --filter dp-kernel")
    cases.append(("a NARROWED registry leg fails — it looks like coverage and is not",
                  reg(), narrowed_wf, 1))

    r = reg()
    r["suites"][1]["needs"] = []
    cases.append(("a row with no backing store fails", r, ok_wf, 1))

    # A REAL target that genuinely never prints a skip line. Not a fabricated
    # file: `bulkhead_shuttle` is an ordinary dp-kernel integration test with no
    # DSN gate, so it is exactly the shape this arm must catch if someone
    # registers a live suite that skips in silence.
    r = reg()
    r["suites"][1]["target"] = "bulkhead_shuttle"
    cases.append(("a target that never announces a skip fails", r, ok_wf, 1))

    r = reg()
    r["suites"].append(dict(r["suites"][1]))
    cases.append(("a duplicate id fails", r, ok_wf, 1))

    # `C4`. The fixture cases are judged against a FAKE root holding exactly the
    # two suites they name. Without it every one of them would also trip the new
    # disk -> registry arm against the real repo's 27 live suites, and the arms
    # above would be reporting something they were not written to judge.
    tmp = tempfile.TemporaryDirectory()
    fake = Path(tmp.name)
    td = fake / 'crates' / 'dp-kernel' / 'tests'
    td.mkdir(parents=True)
    (td / 'integration_event_store.rs').write_text(
        'std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL")', encoding='utf-8')
    (td / 'integration_writer_lease.rs').write_text(
        'std::env::var("LOREWEAVE_TEST_PG_URL")', encoding='utf-8')

    bad = 0
    for name, registry, wf, want in cases:
        got = len(check(registry, wf, fake))
        got = 1 if got else 0
        mark = "ok  " if got == want else "FAIL"
        if got != want:
            bad = 1
        print(f"  {mark} {name}: findings={got} (want {want})")

    # MISUSE, both shapes — a gate that cannot see its subject must say so.
    for name, registry, wf in (
        ("an empty registry is misuse, not a pass", {"suites": []}, ok_wf),
        ("a workflow with no cargo leg is misuse", reg(), "jobs:\n  build:\n    steps: []\n"),
    ):
        try:
            check(registry, wf, fake)
        except SystemExit as e:
            print(f"  {'ok  ' if e.code == 2 else 'FAIL'} {name}: rc={e.code} (want 2)")
            if e.code != 2:
                bad = 1
        else:
            print(f"  FAIL {name}: it returned instead of refusing")
            bad = 1

    # `C4` -- the DISK -> REGISTRY direction, both ways.
    #
    # Without these the new walk could return an empty list forever and every
    # arm above would still pass: the exact shape that let four real suites sit
    # unregistered while this gate reported full coverage.
    extra = fake / 'services' / 'world-service' / 'tests'
    extra.mkdir(parents=True)
    (extra / 'orphan_live.rs').write_text(
        'std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL")', encoding='utf-8')
    got = len(check(reg(), ok_wf, fake))
    ok = got == 1
    bad |= not ok
    print(f"  {'ok  ' if ok else 'FAIL'} a live suite in NO registry row fails: findings={got} (want 1)")
    (extra / 'orphan_live.rs').unlink()

    # ...and it does not cry wolf on a test that reads no DSN at all.
    (extra / 'plain_unit.rs').write_text('fn main() {}', encoding='utf-8')
    got = len(check(reg(), ok_wf, fake))
    ok = got == 0
    bad |= not ok
    print(f"  {'ok  ' if ok else 'FAIL'} a test that reads no DSN is not a live suite: findings={got} (want 0)")

    # A root with NO live suite anywhere is MISUSE, not a clean disk -> registry
    # result -- the subject floor.
    empty = Path(tempfile.mkdtemp())
    (empty / 'crates').mkdir()
    try:
        check(reg(), ok_wf, empty)
    except SystemExit as e:
        ok = e.code == 2
        bad |= not ok
        print(f"  {'ok  ' if ok else 'FAIL'} no live suite anywhere is misuse: rc={e.code} (want 2)")
    else:
        bad = 1
        print('  FAIL no live suite anywhere is misuse: it returned instead of refusing')

    if bad:
        print("live-suite-registry-gate --self-test: FAIL")
        return 2
    print("live-suite-registry-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if not REGISTRY.is_file():
        print(f"live-suite-registry-gate: MISUSE — no registry at {REGISTRY}", file=sys.stderr)
        return 2
    if not WORKFLOW.is_file():
        print(f"live-suite-registry-gate: MISUSE — no workflow at {WORKFLOW}", file=sys.stderr)
        return 2

    rc = selftest()
    if rc:
        return rc
    if "--self-test" in sys.argv:
        return 0

    reg = load_yaml(REGISTRY)
    findings = check(reg, WORKFLOW.read_text(encoding="utf-8"))

    # The throwaway-marker rule is about the RUNNER's derived names, so it is
    # checked here against the id rather than against a field nobody sets.
    for s in reg.get("suites") or []:
        dev_db = f"ls_{str(s.get('id', '')).replace('-', '_')}_smoke"
        if not any(m in dev_db for m in THROWAWAY_MARKERS):
            findings.append(f"`{s.get('id')}`: derived dev database `{dev_db}` carries no marker")

    if findings:
        print(f"live-suite-registry-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f"  {f}")
        print(
            "\nThe registry is the only complete list of live suites — a grep cannot build it.\n"
            "If it drifts from CI, the thing that says which suites actually run is wrong."
        )
        return 1

    total = len(reg["suites"])
    covered = sum(1 for s in reg["suites"] if s.get("dedicated_ci_leg"))
    print(
        f"live-suite-registry-gate: OK — {total} live suite(s), ALL run by the registry leg; "
        f"{covered} also have a per-target leg whose databases match, and the other "
        f"{total - covered} each say why they have none"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
