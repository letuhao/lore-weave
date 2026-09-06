#!/usr/bin/env python3
"""test-dsn-coverage-gate.py — a gated test that no workflow arms has never run.

## Why this exists

Twice in one day, a sweep found DB-gated tests that had never executed anywhere:

  · **ROT-0** — `JOBS_TEST_PG_DSN` and `PIIKMS_TEST_PG_URL` were set by no workflow. 41
    test functions: PgKEKManager, PII erasure, admin-cli erasure/archive/drift,
    meta-worker's erased-writer, breach-notifier, the meta-outbox relay. They COMPILED —
    foundation-ci's module loop builds them — and compiling does not check SQL.

  · **ROT-1** — because ROT-0 swept only the two variables it happened to be holding and
    reported "41" as the answer. Sweeping every `*_TEST_*` variable afterwards found
    **eight more** and **159 further test functions**: provider-registry 54,
    usage-billing 37, auth 36, and five more services.

Both were invisible for the same reason: a skip is indistinguishable from a pass in the
summary line, and nothing ever compared the set of gating variables against the set of
variables CI arms. **200 never-run tests; 41 was reported.** This gate is the comparison,
so there is no ROT-2.

Its first run also proved the ROT-1 triage was worth doing rather than assuming: all three
failures were STALE TESTS, not product bugs — a hand-listed migration set missing the very
migration written for it; a test that predated a lease guard and so never claimed its row;
and a free-tier assertion colliding with an unrelated daily cap.

## The rule

Every `*_TEST_*`-shaped environment variable read by a test file must be set by some
workflow, **or** be declared here with the reason it cannot be. Declaring is honest;
silence is how 200 tests stopped running.

Usage:  python scripts/test-dsn-coverage-gate.py
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = os.path.join(REPO_ROOT, ".github", "workflows")
SEARCH_DIRS = ("services", "sdks", "tests")

#: Env-var reads in a test file, across the languages that have gated suites here.
#:
#: ⚠ The subscript form is a SEPARATE alternative, and it did not used to be.
#: `os\.environ\[` sat in the list of function NAMES, which was then followed by
#: `\s*[(\[]` — so the pattern demanded `os.environ[[` and `os.environ["X"]` was
#: never matched, in every run since this gate was written. A suite gated by a
#: subscript read was invisible to the gate whose whole purpose is making gated
#: suites visible. Found by the `--self-test` added 2026-08-11, on its first run:
#: the case was written because the docstring CLAIMS the form is covered.
READ = re.compile(
    r"""(?:(?:os\.Getenv|os\.getenv|os\.environ\.get|getenv|std::env::var)\s*\("""
    r"""|os\.environ\s*\[)"""
    r"""\s*['"]([A-Z][A-Z0-9_]*)['"]"""
)
#: The shape of a gating variable: it names a TEST resource.
GATING = re.compile(r"(^|_)TEST(_|$)")

#: Variables that MATCH the shape above but do not gate anything — a name containing `TEST`
#: is a heuristic, and this is where the heuristic is corrected, with the reading that
#: corrected it. Distinct from DECLARED_UNARMED on purpose: that list means "the tests really
#: do not run and we are saying so", which would be a FALSE statement about these. Merging the
#: two would make the gate's most valuable output — the list of suites CI is not running —
#: quietly untrue, which is the failure this gate exists to prevent, one level up.
NOT_GATING: dict[str, str] = {
    "LOREWEAVE_TEST_MIGRATION_MEMO": (
        "not a gate — a PERFORMANCE opt-out. `composition-service/tests/conftest.py` "
        "memoises `run_migrations` per schema-fingerprint; setting this to '0' takes the "
        "un-memoised branch. BOTH branches run the migrations and BOTH run every test, so "
        "nothing is skipped whether or not a workflow sets it. Arming it in CI would only "
        "make the suite slower."
    ),
}

#: Variables that genuinely cannot be armed in CI, with the reason. An entry here is a
#: DECLARATION, not an exemption — the tests still do not run, and saying so keeps that
#: fact visible instead of letting a skip read as a pass.
DECLARED_UNARMED: dict[str, str] = {
    "PIIKMS_TEST_KMS_ENDPOINT": (
        "needs a LocalStack-KMS container. The test it gates "
        "(`TestLive_ErasePII_WritesRealAuditRow`) proves that ErasePII's meta_read_audit "
        "row satisfies the migration-014/029 CHECK constraints — and its own docstring "
        "notes a CHECK violation would otherwise surface only AFTER the KEK is "
        "irreversibly shredded. Wiring LocalStack is worth doing; it is declared rather "
        "than silently missing so it stays on the board."
    ),
}


#: Reach floors. Measured 2026-08-11: 1838 test files walked, 13 workflow files.
#: Both floors sit WELL BELOW the measurement and well above zero on purpose — a
#: floor set AT the measured value turns every arm above it into a floor test
#: (`BDR-82`), and a floor of zero is not a floor.
MIN_TEST_FILES = 500
MIN_WORKFLOWS = 3


def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel or "/test/" in rel
        or base.startswith("test_")
        or base.endswith(("_test.go", "_test.rs", "_test.py"))
    )


def collect_gating(root: str) -> tuple[dict[str, set[str]], int]:
    """`({var: {test files reading it}}, test files walked)`.

    The count is returned because THIS gate's silent-nothing path runs through
    it: with no test files, `gating` is empty, `unarmed` is empty, and the gate
    prints *"OK — every gating variable is armed in CI"*. A walk that reaches
    nothing is byte-identical to a fully-armed tree.

    `root` is a parameter so the arms are provable on a synthetic tree rather
    than on whatever this repo happens to contain (`BDR-71`).
    """
    gating: dict[str, set[str]] = {}
    seen = 0
    for d in SEARCH_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames
                           if x not in {"node_modules", "__pycache__", "target", ".venv", "vendor"}]
            for fn in filenames:
                if not fn.endswith((".go", ".py", ".rs")):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if not is_test_file(rel):
                    continue
                seen += 1
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        body = fh.read()
                except OSError:
                    continue
                for name in READ.findall(body):
                    if GATING.search(name) and name not in NOT_GATING:
                        gating.setdefault(name, set()).add(rel)
    return gating, seen


def collect_armed(workflows: str, names) -> tuple[set[str], int]:
    """`({vars a workflow sets}, workflow files read)`."""
    armed: set[str] = set()
    seen = 0
    if os.path.isdir(workflows):
        for fn in sorted(os.listdir(workflows)):
            if not fn.endswith((".yml", ".yaml")):
                continue
            seen += 1
            with open(os.path.join(workflows, fn), "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            for name in names:
                if name in text:
                    armed.add(name)
    return armed, seen


def check_reach(root: str, workflows: str, test_files: int, wf_files: int,
                gating: dict[str, set[str]]) -> list[str]:
    """The family that separates "nothing to report" from "nothing looked at"."""
    problems: list[str] = []

    for d in SEARCH_DIRS:
        if not os.path.isdir(os.path.join(root, d)):
            problems.append(
                f"PHANTOM SEARCH DIR: `{d}` is in SEARCH_DIRS and does not exist. The walk skips "
                f"a missing directory silently, so a rename retires this gate over that whole "
                f"tree while it goes on reporting OK.")

    if test_files < MIN_TEST_FILES:
        problems.append(
            f"REACH FLOOR: walked only {test_files} test file(s) (floor {MIN_TEST_FILES}, measured "
            f"1838). With no test files there are no gating variables, no unarmed variables, and "
            f"this gate prints \"every gating variable is armed\" — the exact false clean it was "
            f"written to prevent, one level up.")

    if not os.path.isdir(workflows):
        problems.append(
            f"NO WORKFLOW DIRECTORY at `{workflows}`. Nothing would be found armed.")
    elif wf_files < MIN_WORKFLOWS:
        problems.append(
            f"REACH FLOOR: read only {wf_files} workflow file(s) (floor {MIN_WORKFLOWS}, measured "
            f"13). Too few to have found the arming, so every variable would read as unarmed.")

    # Phantom register rows. Both tables are claims ABOUT variables some test
    # reads; a row naming a variable nothing reads any more is a claim about
    # code that is not there — and it silently pre-excuses the name if it ever
    # comes back for a different reason.
    read_names = set(gating) | {n for n in NOT_GATING} | {n for n in DECLARED_UNARMED}
    all_read: set[str] = set()
    for d in SEARCH_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames
                           if x not in {"node_modules", "__pycache__", "target", ".venv", "vendor"}]
            for fn in filenames:
                if not fn.endswith((".go", ".py", ".rs")):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                if not is_test_file(rel):
                    continue
                try:
                    with open(os.path.join(dirpath, fn), "r", encoding="utf-8",
                              errors="ignore") as fh:
                        all_read.update(READ.findall(fh.read()))
                except OSError:
                    continue
    del read_names
    for table, label in ((NOT_GATING, "NOT_GATING"), (DECLARED_UNARMED, "DECLARED_UNARMED")):
        for name in sorted(table):
            if name not in all_read:
                problems.append(
                    f"PHANTOM {label} ROW: `{name}` is declared here and no test file reads it. "
                    f"The test was deleted or the variable renamed, and the row outlived it — "
                    f"delete the row, so this register keeps shrinking.")
    return problems


def main() -> int:
    if "--self-test" in sys.argv[1:] or "--selftest" in sys.argv[1:]:
        return self_test()

    gating, test_files = collect_gating(REPO_ROOT)
    armed, wf_files = collect_armed(WORKFLOWS, gating)

    reach = check_reach(REPO_ROOT, WORKFLOWS, test_files, wf_files, gating)
    if reach:
        print("test-dsn-coverage-gate: FAIL — the gate cannot see its corpus\n")
        for p in reach:
            print(f"  - {p}")
        return 1

    unarmed = {n: fs for n, fs in gating.items() if n not in armed and n not in DECLARED_UNARMED}
    declared = [n for n in gating if n in DECLARED_UNARMED]

    print(f"test-dsn-coverage-gate: {len(gating)} gating variable(s) "
          f"across {test_files} test file(s) and {wf_files} workflow(s)")
    print(f"  {len(armed)} armed by a workflow")
    for n in sorted(NOT_GATING):
        print(f"  NOT A GATE — {n}")
        print(f"      {NOT_GATING[n].splitlines()[0]}")
    for n in sorted(declared):
        print(f"  DECLARED UNARMED — {n}")
        print(f"      {DECLARED_UNARMED[n].splitlines()[0]}")

    if not unarmed:
        print(f"OK — every gating variable is armed in CI or declared with its reason "
              f"(reach floors: >= {MIN_TEST_FILES} test file(s), >= {MIN_WORKFLOWS} workflow(s))")
        return 0

    print("\n[gated tests that NO workflow arms]")
    print("  → a skip is indistinguishable from a pass in the summary line. Arm it in a")
    print("    workflow, or add it to DECLARED_UNARMED with the reason it cannot be.\n")
    for n, files in sorted(unarmed.items()):
        print(f"  {n}  ({len(files)} test file(s))")
        for f in sorted(files)[:4]:
            print(f"      {f}")
    return 1


def self_test() -> int:
    """Detectors on synthetic strings, reach on a synthetic tree.

    Every arm here is unreachable on the real repo: the tree has 1838 test files
    and 13 workflows, so nothing in it can distinguish a working reach family
    from a deleted one. That is precisely the condition under which a check
    quietly stops working.
    """
    import tempfile
    fails: list[str] = []

    # ── the READ detector, one case per language form it claims to cover ──────
    for src, want in [
        ('os.Getenv("JOBS_TEST_PG_DSN")', "JOBS_TEST_PG_DSN"),
        ('os.getenv("A_TEST_B")', "A_TEST_B"),
        ('os.environ.get("A_TEST_B")', "A_TEST_B"),
        ('os.environ["A_TEST_B"]', "A_TEST_B"),
        ('std::env::var("A_TEST_B")', "A_TEST_B"),
    ]:
        got = READ.findall(src)
        if got != [want]:
            fails.append(f"READ on {src!r} gave {got}, want [{want!r}]")
    if READ.findall("# TEST_PG_DSN in a comment, not a read"):
        fails.append("READ matched a bare mention with no getenv call")

    # ── the GATING shape, both directions ─────────────────────────────────────
    for name, want in [("JOBS_TEST_PG_DSN", True), ("TEST_DSN", True), ("PG_TEST", True),
                       ("LATEST_RUN", False), ("CONTEST_ID", False), ("PROTEST", False)]:
        if bool(GATING.search(name)) is not want:
            fails.append(f"GATING on {name!r} = {not want}, want {want}")

    # ── is_test_file, both directions ─────────────────────────────────────────
    for rel, want in [("services/a/tests/x.py", True), ("services/a/x_test.go", True),
                      ("services/a/test_x.py", True), ("services/a/x_test.rs", True),
                      ("services/a/main.go", False), ("services/a/latest.py", False)]:
        if is_test_file(rel) is not want:
            fails.append(f"is_test_file({rel!r}) = {not want}, want {want}")

    with tempfile.TemporaryDirectory() as td:
        svc = os.path.join(td, "services", "alpha")
        os.makedirs(svc)
        wf = os.path.join(td, ".github", "workflows")
        os.makedirs(wf)
        with open(os.path.join(svc, "a_test.go"), "w", encoding="utf-8") as fh:
            fh.write('func T(t *testing.T) { d := os.Getenv("ALPHA_TEST_DSN") }\n')

        # ARM — a gating variable in a test file is found; a non-test sibling is not.
        gating, seen = collect_gating(td)
        if set(gating) != {"ALPHA_TEST_DSN"} or seen != 1:
            fails.append(f"collect_gating found {sorted(gating)} across {seen} file(s), "
                         f"want ['ALPHA_TEST_DSN'] across 1")
        with open(os.path.join(svc, "main.go"), "w", encoding="utf-8") as fh:
            fh.write('d := os.Getenv("BETA_TEST_DSN")\n')
        gating, seen = collect_gating(td)
        if "BETA_TEST_DSN" in gating:
            fails.append("a gating variable read by a NON-test file was counted")

        # ARM — armed vs unarmed, both directions.
        armed, wfn = collect_armed(wf, gating)
        if armed:
            fails.append(f"nothing arms anything and collect_armed returned {armed}")
        with open(os.path.join(wf, "ci.yml"), "w", encoding="utf-8") as fh:
            fh.write("env:\n  ALPHA_TEST_DSN: postgres://x\n")
        armed, wfn = collect_armed(wf, gating)
        if armed != {"ALPHA_TEST_DSN"} or wfn != 1:
            fails.append(f"collect_armed gave {armed} over {wfn} file(s), want the one variable")

        # ── THE REACH FAMILY ──────────────────────────────────────────────────
        # An empty tree yields no gating variables, hence no unarmed ones. That
        # is the false clean; the floors are what separate it from a real one.
        empty = os.path.join(td, "empty")
        os.makedirs(os.path.join(empty, "services"))
        os.makedirs(os.path.join(empty, "sdks"))
        os.makedirs(os.path.join(empty, "tests"))
        g2, s2 = collect_gating(empty)
        if g2 or s2:
            fails.append(f"an empty tree yielded {g2} over {s2} file(s)")
        probs = check_reach(empty, wf, s2, 1, g2)
        if not any("REACH FLOOR" in p and "test file" in p for p in probs):
            fails.append("the test-file floor did NOT red on a tree with zero test files — this "
                         "is the arm that stops 'nothing scanned' reading as 'all armed'")

        # A missing SEARCH_DIR is skipped silently by the walk; the phantom arm
        # is the only thing that notices.
        import shutil
        shutil.rmtree(os.path.join(empty, "sdks"))
        if not any("PHANTOM SEARCH DIR" in p for p in check_reach(empty, wf, 999, 9, {})):
            fails.append("a missing SEARCH_DIRS entry did NOT red")

        # Too few workflows, and none at all.
        if not any("REACH FLOOR" in p and "workflow" in p
                   for p in check_reach(td, wf, 999, 1, {})):
            fails.append("the workflow floor did NOT red on 1 workflow file")
        if not any("NO WORKFLOW DIRECTORY" in p
                   for p in check_reach(td, os.path.join(td, "nope"), 999, 0, {})):
            fails.append("a missing workflow directory did NOT red")

        # A phantom register row — declared, but nothing reads it.
        if not any("PHANTOM NOT_GATING ROW" in p or "PHANTOM DECLARED_UNARMED ROW" in p
                   for p in check_reach(td, wf, 999, 9, {})):
            fails.append("a register row naming a variable no test reads did NOT red")

        # ...and the clean twin: with the declared names actually read, silence.
        with open(os.path.join(svc, "b_test.go"), "w", encoding="utf-8") as fh:
            for n in list(NOT_GATING) + list(DECLARED_UNARMED):
                fh.write(f'os.Getenv("{n}")\n')
        if any("PHANTOM" in p and "ROW" in p for p in check_reach(td, wf, 999, 9, {})):
            fails.append("a register row WAS flagged phantom while a test reads it")

    # The floors must be live and unsaturated against the real tree (`BDR-82`).
    _, real_files = collect_gating(REPO_ROOT)
    _, real_wf = collect_armed(WORKFLOWS, [])
    if not 0 < MIN_TEST_FILES < real_files:
        fails.append(f"MIN_TEST_FILES {MIN_TEST_FILES} is not between 0 and the real {real_files}")
    if not 0 < MIN_WORKFLOWS < real_wf:
        fails.append(f"MIN_WORKFLOWS {MIN_WORKFLOWS} is not between 0 and the real {real_wf}")

    for f in fails:
        print(f"FAIL: {f}")
    if fails:
        return 1
    print(f"test-dsn-coverage-gate: SELFTEST PASS — {17} detector case(s) plus a reach family "
          f"proven on synthetic trees: an empty corpus reds instead of reporting every variable "
          f"armed, a vanished SEARCH_DIR reds, too-few/no workflows red, a phantom register row "
          f"reds while a read one does not, and both floors are calibrated "
          f"live-but-unsaturated against {real_files} test file(s) / {real_wf} workflow(s)")
    return 0


if __name__ == "__main__":
    # 🔴 THIS CALLED `_selftest()`, WHICH HAS NEVER EXISTED -- the function is
    # `self_test()`. Any run with `--selftest` died on `NameError: name '_selftest' is not
    # defined`, so the self-test this gate is CERTIFIED on could not run through that door.
    # It was invisible because `main()` already handles BOTH spellings correctly two hundred
    # lines up and returns `self_test()`, so the branch was redundant as well as broken and
    # nothing reached it until `gate-teeth-gate --verify-proofs` started calling gates by
    # their advertised flag. Deleted rather than repaired: one entry point, not two.
    sys.exit(main())
