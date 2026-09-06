#!/usr/bin/env python3
"""The refusal census — every `raise` in the membrane, neutered one at a time.

🔴 **WHY THIS EXISTS, AND WHY IT IS NOT ANOTHER COVERAGE NUMBER.**

Twelve rounds of independent V-CODE verification on CP-1 produced no convergence: findings introduced
per round read `2,1,2,1,3,2,4,3,2,2,2,5`, with the maximum on the *smallest* delta of the run. The
decisive evidence was not numeric. A verifier stopped reporting a defect and instead **wrote the
patch**, measured it at baseline and named the line; the builder applied it verbatim — the shortest
path a fix can take — and it still shipped a behavioural regression, an inert production wiring and a
false claim in three places. **When the pre-written fix still fails, the loop is not limited by the
quality of its findings.**

The mechanism behind that was named by the verifier who caught it: the patch had been certified
against **nine hand-picked orderings**. Enumerated exhaustively, it regressed 584 of 30,948 sequences.
*"Execution over a hand-picked sample is argument wearing a lab coat."*

Meanwhile exactly one measurement in the whole run **converged**: an AST enumeration of the package's
`raise` sites. Three verifiers derived it independently — 68 sites across 8 modules — and agreed
member for member on which are unguarded. Two of them added a hand-picked structural addendum on top
(87 and 92 sites); **no two cut the addendum the same way, and every unit of divergence lived there.**
So this mechanises the reproducible half and drops the addendum, on their advice.

**What it makes true.** "A finding is closed" stops meaning "the builder wrote a test" and starts
meaning **"this named site moved SILENT → RED"**. That structurally forbids this run's most-repeated
failure — a fix landing on the sibling of the site a verifier named, seven times — because the
sibling has its own id and its own row.

**What it does NOT do.** It does not measure whether a guard is *right*, only whether the suite
notices the check is gone. A site that reds for the wrong reason still reads RED here. That is the
job of the verdicts, and this does not replace them.

🔴 It reads and writes BYTES. The first version used `read_text`/`write_text`, which on
Windows silently rewrites LF as CRLF - so every "restore" reproduced the file's MEANING and not its
BYTES, and left the tree dirty in two files. A verifier recorded that exact defect one round earlier,
in its own harness, and I reproduced it in mine. **A restore that changes the artifact is not a
restore**, so each one now asserts the bytes back.

Usage:
    python scripts/agentruntime-census.py            # compare against the allowlist, exit 1 on drift
    python scripts/agentruntime-census.py --write    # regenerate the allowlist (review the diff!)
    python scripts/agentruntime-census.py --selftest # prove the harness can fire before trusting it
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_PKG_REL = pathlib.Path("services") / "chat-service" / "app" / "agentruntime"
_CS_REL = pathlib.Path("services") / "chat-service"

# The mirror's file set, and the verdict cache keyed on it, live in one module: both
# gates need the identical answer to "what can this measurement see", and two copies of
# that list would drift the first time one was widened.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from agentruntime_gatecache import MIRROR_PREFIXES  # noqa: E402
import agentruntime_gatecache as _gatecache  # noqa: E402

VERDICT = ROOT / "contracts" / "agentruntime-census-verdict.json"
PKG = ROOT / _PKG_REL
CS = ROOT / _CS_REL


def _mirror() -> pathlib.Path:
    """A throwaway copy of the tracked tree. **The census never writes into the live one.**

    🔴 **TWO FINDINGS DIED HERE, AND NEITHER WAS FIXABLE WHERE IT STOOD.**

    *The kills.* Neutering happened in the real `app/agentruntime/`, restored in a `finally` plus
    `atexit` plus signal handlers. On Linux that got 3 of 5 kill mechanisms; **on Windows a verifier
    measured 6 external kill mechanisms and 0 reaching the handler**, because `os.kill(pid, SIGTERM)`
    there *is* `TerminateProcess`. SIGKILL never runs `atexit` on any platform. **19% of the sites are
    SILENT, so roughly one kill in five left INVISIBLE damage in a tracked production module** — and
    a suite that then reds blaming a test.

    *The interference.* 16 of 20 concurrent suite runs went red during a census; it destroyed seven
    of a verifier's first eight baselines. A measuring instrument that corrupts what it measures.

    Both are the same defect — *the instrument writes into its subject* — and no amount of handler
    was going to fix a `SIGKILL`. So it stops writing there. Twenty-four lines of signal handling are
    gone, and the two findings with them.

    Tracked files only, copied from the WORKING tree rather than from `HEAD`: this runs as a
    pre-commit gate, and the thing that must be measured is what is about to be committed, not what
    was committed last.
    """
    import shutil
    import tempfile

    out = pathlib.Path(tempfile.mkdtemp(prefix="lw-census-"))
    prefixes = tuple(str(pref).replace("\\", "/") for pref in MIRROR_PREFIXES)
    # 🔴 **THE ALLOCATOR LEAKED, AND FIXING BOTH WRITERS DID NOT COVER IT — the twelfth pair in this
    # run repaired at one end.** `census()` and `_selftest()` each free their mirror in a `finally`
    # now; neither `try` has been ENTERED when this function raises, and `census()`'s `atexit` is not
    # registered yet either. A verifier executed both paths: `git ls-files` failing leaves one empty
    # directory, and an `OSError` mid-copy leaves one holding a **partial copy of the repository** —
    # 239 MB of a tree that is not the tree, which is worse debris than none. Both are ordinary here:
    # `git` absent, a permission error, or a Windows path-length limit on a deep tracked path under
    # the long temp prefix this verification workflow checks out into.
    #
    # A function that allocates before it can fail owns what it allocated until it returns.
    try:
        listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        for rel in listing.split(b"\0"):
            if not rel:
                continue
            name = rel.decode("utf-8")
            if not name.startswith(prefixes):       # not reachable from the suite - see above
                continue
            src = ROOT / name
            if not src.is_file():                   # a submodule or a deleted-but-tracked path
                continue
            dst = out / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    except BaseException:
        # `BaseException`, not `Exception`: a `KeyboardInterrupt` between `mkdtemp` and the return
        # is the same leak, and it is the one a person actually causes.
        _discard(out)
        raise
    return out


def _own_mirror(mirror: pathlib.Path) -> bool:
    """Did `_mirror()` create this directory? **A cleanup must only remove what it created.**

    🔴 The check exists because the version without it **deleted the system temp directory**: a
    guard monkeypatched `_mirror` to return `fixture.parent`, and `mkdtemp` returns a directory
    INSIDE temp, so its parent is `%TEMP%` itself. It destroyed this census's own mirror mid-run and
    is the most likely cause of six "another process deleted my output file" failures that were
    blamed on the environment for an evening.
    """
    import tempfile

    return (mirror.name.startswith("lw-census-")
            and mirror.parent == pathlib.Path(tempfile.gettempdir()))


def _discard(mirror: pathlib.Path) -> None:
    """Remove a mirror **this module made**, and say so when it declines.

    🔴 **BOTH WRITERS LEAKED, AND ONE OF THEM LEAKED EVERYTHING.** `census()` registered an
    `atexit` and therefore held a full 239 MB copy for the whole run; `_selftest()` called
    `_mirror()` and had **no cleanup at all**, so every invocation leaked one. Measured on this
    machine: **12 mirrors and 455 fixture directories, 2.4 GB** — and it was found by listing the
    temp directory, not by any gate, which is the part worth recording. A previous round had
    already measured 6.71 GB of the same thing and the fix landed on `census()` alone: **the tenth
    pair in this run repaired at one end.**

    A `finally` frees it deterministically; the `atexit` registration stays as the kill-path
    backstop, and `ignore_errors` makes the double-remove a no-op.
    """
    import shutil

    if _own_mirror(mirror):
        shutil.rmtree(mirror, ignore_errors=True)
    else:
        print(f"census: not removing {mirror} - this module did not create it")


def _suites(cwd) -> list[str]:
    """Every suite that IMPORTS the package - derived, never typed out.

    🔴 **THIS WAS A SINGLE HARD-CODED `tests/test_cp1_membrane.py`, AND CP-2 IS WHAT MADE THAT A
    DEFECT RATHER THAN A SIMPLIFICATION.** `assembly.py` arrived with two refusals guarded entirely
    by `tests/test_cp2_assembly.py`. Neutering either left the CP-1 suite green, so the census
    **reported both SILENT** - measured, not predicted, in the run that produced this fix. A file
    whose whole value is that its rows are true had two rows naming guarded refusals as unguarded.

    The failure direction is the safe one (a false SILENT is a finding, never a false green), and it
    is still a false finding, which is the defect one level up: an instrument that manufactures work.

    **The predicate is `imports app.agentruntime`, not a name glob**, and the difference is not
    cosmetic. A glob over `test_cp*.py` also takes `test_cp0_instrument.py` - which names the
    package in prose and in path strings but never imports it, spawns subprocesses, and measures
    **63 s**, on a run that executes the suite once per site - and `test_cp0_merge_db.py`, which is
    DB-gated and contributes skips. Neither can red on a membrane refusal, so both would be pure
    cost. What makes a suite relevant here is exactly that it can observe this package, so that is
    what is asked, and the answer today is two suites.

    Derived rather than listed for the reason five published denominators in this run have already
    demonstrated: a hand-maintained list is one someone must remember to grow, and every one of them
    turned out to be a lower bound.

    `cwd` is the mirror's `services/chat-service`. Reading the live tree instead would be the same
    category of error the `cwd=CS` default already produced here - the instrument answering a
    question about a tree other than the one under measurement.
    """
    out = []
    for p in sorted((pathlib.Path(cwd) / "tests").glob("test_*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            mods = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                    else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            if any(m == "app.agentruntime" or m.startswith("app.agentruntime.") for m in mods):
                out.append(f"tests/{p.name}")
                break
    return out


ALLOWLIST = ROOT / "contracts" / "agentruntime-census-silent.txt"


def _with_condition(node: ast.Raise, cond=None):
    """The refusal **and the test that reaches it**, as one expression.

    🔴 The condition used to be looked up in a module-level dict keyed by `id(node)`.
    **CPython reuses `id()` for freed objects**, so across parses — and across modules within one
    run — a raise could pick up a condition belonging to a node that no longer existed. The digest
    was therefore **non-deterministic**, and the gate caught it exactly as designed: the same site
    reported two different digests between a `--write` and the check run that followed it, one
    `NEWLY SILENT` and one `NOW GUARDED` for one refusal. An identity is not a key.
    """
    if cond is None:
        return node
    return ast.Expr(value=ast.Tuple(elts=[ast.parse(ast.unparse(cond)).body[0].value,
                                          ast.parse(ast.unparse(node)).body[0].exc
                                          or ast.Constant(value=None)], ctx=ast.Load()))


def _shape_digest(node: ast.Raise, cond=None) -> str:
    """A digest of the refusal's SHAPE, stable across interpreters and blind to its prose.

    🔴 **THE FIRST VERSION USED `ast.dump`, AND THAT BROKE CI IN A WAY THAT LOOKED LIKE A
    RESULT.** `ast.dump` is not version-stable — 3.13 omits `keywords=[]` where 3.12 emits it — so a
    verifier measured **0 of 68 ids matching across 3.12 and 3.13, and 0 of the 13 allowlist rows
    existing** under the pinned interpreter. The gate then printed thirteen `NEWLY SILENT` and
    thirteen `NOW GUARDED` lines and instructed the maintainer, thirteen times, to delete the
    allowlist. **That is worse than the failure it replaced**, because the previous one was obviously
    broken and this one is plausible.

    🔴 **AND IT WAS TOO SENSITIVE IN THE OTHER DIRECTION.** Enumerated over all 68 sites × four
    edit classes: reordering two raises **should** move a row and does (98/98 pairs, 0 collisions —
    the one thing the ordinal could not do); reindenting should not and does not; but **renaming the
    enclosing function moved 68/68**, and **rewording a message moved 68/68**, relocating all
    thirteen allowlist rows and emitting two false sentences each time.

    So the digest is taken over `ast.unparse` — stable source text rather than a dump format — with
    every string literal replaced by a placeholder. A reworded message keeps its row; a moved,
    retyped or restructured refusal does not. The function name is already the id's prefix, so a
    rename is visible there and does not need to churn the digest as well.
    """
    # \U0001F534 **THE ID COVERED THE `raise` AND NOT THE CONDITION THAT REACHES IT.** A verifier
    # replaced each guard's test with `False` — making the refusal unreachable — and the id set was
    # **unchanged for 59 of 59** guarded sites, including **10 of the 13 allowlisted rows**. So a
    # change that silently disables a refusal moves nothing in the allowlist. Widening the digest to
    # the enclosing branch test also takes the collision groups from 4 to **0** while a full reword
    # sweep still moves **0 of 68** rows — which refutes the framing I had accepted, that a stable id
    # and a prose-blind id were incompatible and one had to be chosen. The trade was never that.
    shape = ast.parse(ast.unparse(_with_condition(node, cond))).body[0]
    shape = _BlankProse().visit(shape)
    ast.fix_missing_locations(shape)
    return hashlib.sha256(ast.unparse(shape).encode("utf-8")).hexdigest()[:8]


class _BlankProse(ast.NodeTransformer):
    """Erase every spelling of a MESSAGE, so a reworded refusal keeps its row.

    \U0001F534 **AN f-STRING WAS NOT PROSE-BLIND, AND IT SILENTLY RELOCATED A ROW.** Blanking
    `ast.Constant` strings covers a plain message and misses a `JoinedStr`, whose `FormattedValue`
    carries a bare `ast.Name`. A verifier caught it: putting `{ID_MAX_LEN}` into one refusal's
    message moved `check_contract::ContractViolation::7` from `6899e25d` to `179f246e`, and the
    census then printed `NOW GUARDED - drop it from the allowlist` for a row whose id had simply
    ceased to exist.

    **The drift check cannot see this by itself**, and that is the part worth recording. The old id
    leaves the allowlist and reads as a closed finding; the new id, being RED, never appears as
    `NEWLY SILENT`. So *"zero NEWLY SILENT, therefore the digest did not churn"* is an inference
    whose control and seed agree by construction - and it was published as evidence. The outcome was
    right because the row is genuinely red; the evidence was not.

    An f-string **is** a message, and is replaced wholesale exactly as a plain one is. That also
    means two refusals differing only in what they interpolate now collide, which is precisely what
    `_selftest`'s ordinal-free injectivity check exists to refuse.
    """

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            return ast.Constant(value="\u0000")
        return node

    def visit_JoinedStr(self, node):
        return ast.Constant(value="\u0000")


def _sites(tree: ast.AST, mod: str) -> list[tuple[str, ast.Raise]]:
    """Every `raise`, keyed so the id survives an edit that moves it.

    `module::qualname::ExcClass::ordinal` — NOT the line number, which changes whenever anything
    above it changes, and an allowlist keyed on line numbers is an allowlist that goes stale
    silently. The ordinal disambiguates several raises of one class in one function.
    """
    out: list[tuple[str, ast.Raise]] = []
    seen: dict[str, int] = {}

    def walk(node, qual: str, cond=None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, f"{qual}.{child.name}" if qual else child.name)
                continue
            if isinstance(child, ast.Raise):
                exc = child.exc
                name = "reraise"
                if isinstance(exc, ast.Call):
                    name = getattr(exc.func, "id", getattr(exc.func, "attr", "?"))
                elif isinstance(exc, ast.Name):
                    name = exc.id
                # 🔴 **THE ORDINAL ALONE WAS SILENTLY STALE.** Reordering two same-class
                # raises that are BOTH silent produced `rc=0` and an allowlist pointing at the wrong
                # sites — the exact failure the ordinal was chosen to prevent, measured by a
                # verifier. A short hash of the statement's own source pins the row to the refusal
                # rather than to its position, so a reorder shows up as one row leaving and one
                # arriving instead of as nothing at all.
                key = f"{mod}::{qual or '<module>'}::{name}"
                seen[key] = seen.get(key, 0) + 1
                digest = _shape_digest(child, cond)
                out.append((f"{key}::{seen[key]}::{digest}", child))
            walk(child, qual, child.test if isinstance(child, (ast.If, ast.While)) else cond)

    walk(tree, "")
    return out


def _neutered(src: str, node: ast.Raise) -> str:
    """Replace one `raise` statement with `pass`, keeping every other byte and every line number."""
    lines = src.splitlines(keepends=True)
    start, end = node.lineno - 1, (node.end_lineno or node.lineno) - 1
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = list(lines)
    out[start] = " " * indent + "pass\n"
    for i in range(start + 1, end + 1):
        out[i] = "\n"                       # blank, so line numbers below are unchanged
    return "".join(out)


def _suite_is_green(cwd, explain: bool = False) -> bool:
    """Green / not-green — and **a crash is neither.**

    🔴 This returned `r.returncode == 0`, so **any** non-zero exit read as "the suite noticed",
    including a collection error, a missing dependency, or an interpreter that never got as far as a
    test. A verifier measured the consequence end to end: the census reported **68 sites, 0 silent,
    68 red** and printed thirteen `NOW GUARDED … good news: drop it from the allowlist` lines —
    which is verbatim the failure this file's own docstring calls *worse than the one it replaced*,
    because it looks like a result. `pytest` reserves exit 1 for test failures; 2–5 mean it did not
    get to run them, and that is a broken harness, not a guarded refusal.
    """
    # 🔴 `-p no:randomly` was passed UNCONDITIONALLY, and in an environment where that plugin
    # is absent pytest treats it as a usage error: **rc=4, "no tests ran"**. Measured here while the
    # same suite ran 2271 green on its own. A determinism flag that can turn "the suite is fine" into
    # "the suite noticed" is worse than non-determinism, so it is passed only when the plugin is
    # actually installed.
    # 🔴 `-x` — STOP AT THE FIRST FAILURE, and it is a cost fix that must not become an answer fix.
    #
    # This function asks one BOOLEAN question: did the suite notice? For a RED site the answer is
    # settled by the first failing test, and running the remaining ~290 is pure cost — which the
    # census pays **once per site**. At 88 sites × ~47 s the gate had grown to ~69 minutes, and
    # both numbers rise with every row added, so the instrument was on its way to consuming the run
    # it exists to verify.
    #
    # **It cannot change the verdict**, and that is why it is safe: `rc == 0` still means every test
    # ran and passed (a SILENT site still pays the full suite, and 9 of 88 do), while any non-zero
    # still means the suite noticed. `-x` changes only how much is executed AFTER the answer is
    # already known. The guard on this is a whole-census comparison, not an argument: the same
    # RED/SILENT partition with and without it, or the flag comes out.
    args = [sys.executable, "-m", "pytest", *_suites(cwd), "-q", "--no-header", "-x"]
    try:
        import importlib.util as _ilu
        if _ilu.find_spec("pytest_randomly") is not None:
            args += ["-p", "no:randomly"]
    except Exception:                                    # noqa: BLE001 - probing must never decide
        pass
    # 🔴 `cwd` HAD A DEFAULT OF `CS` — THE LIVE TREE — AND `_selftest`'s BASELINE CALL USED IT.
    # So one code path in this module started a subprocess whose working directory was the real
    # `services/chat-service`, which is `subprocess` as a write API: the fourteenth of the nineteen
    # a verifier enumerated, arriving through a keyword default rather than through a call. My own
    # path-taint gate reported it on its first run, which is the gate working before anyone
    # independent had to.
    #
    # The baseline belongs in the mirror anyway: what the census is about to measure IS the mirror,
    # so measuring "green before any injection" anywhere else answers a slightly different question.
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode not in (0, 1):
        raise SystemExit(
            "pytest exited " + str(r.returncode) + " in " + str(cwd) + " - it did "
            "not run the suite, so no site can be classified. Reporting these as RED would "
            "print a plausible lie." + chr(10) + r.stdout[-2000:] + chr(10) + r.stderr[-2000:])
    # 🔴 **THIS LINE WAS DELETED BY THE REPAIR THAT WAS FIXING THE LINES AROUND IT.** A line-based
    # script cleaning up a broken f-string above took the `return` with it, so this function fell
    # off the end and returned `None` — falsy — and every run reported "the suite is not green
    # before any injection" while the suite ran 137 green from the same directory, measured. The
    # census could not have classified a single site, and its failure message pointed at the suite.
    #
    # 🔴 `explain` — SAY WHICH TEST, on the ONE call where the answer is a verdict about the tree
    # rather than about a site. rc==1 is a real test failure and this function threw the output
    # away, so the only thing the caller could print was "the suite is not green before any
    # injection". That is true and unactionable: it names 18 suites and no test, and the reader
    # cannot tell a broken guard from a broken environment. CI printed exactly that line for a
    # whole cycle. Deliberately OFF for the per-site calls, where a red suite is the expected
    # answer and 88 pytest tails would bury the census's own output.
    if explain and r.returncode == 1:
        tail = [ln for ln in (r.stdout or "").splitlines()
                if ln.startswith("FAILED") or ln.startswith("ERROR")]
        for ln in tail[:10]:
            print("    " + ln[:200])
        if not tail:
            print("    " + (r.stdout or "")[-1200:])
    return r.returncode == 0


def default_jobs() -> int:
    """How many workers, derived from the machine rather than typed."""
    return max(1, min(12, (os.cpu_count() or 2) - 2))


def census_parallel(jobs: int, verbose: bool = False) -> dict[str, bool]:
    """The same census, N workers, **one mirror each** — and the mirror is the whole safety story.

    🔴 **WHY THIS IS SAFE TO PARALLELISE AT ALL, said as a property and not as a hope.** A site's
    measurement is *neuter one refusal, run the suite, restore it*. Sites never interact: each
    worker writes only inside its own `mkdtemp` copy, so two workers cannot see each other's
    neutered file, and the live tree is not written by any of them. The measurement is therefore
    identical to the sequential one **by construction**, not by observation — and it is checked
    against observation anyway, because that is the rule this instrument exists to enforce.

    🔴 **CONCURRENT CENSUS RUNS ONCE DELETED EACH OTHER'S MIRRORS**, reproduced earlier in this run.
    The repair is already in the tree and is what makes this change small: `_own_mirror()` gates the
    cleanup, so a worker removes only the directory it created. Without that guard this function
    would be a reliable way to make the instrument report a site RED because another worker pulled
    its files out from under it — a wrong answer that looks like a finding.

    Threads, not processes: every worker spends ~all of its wall-clock inside `subprocess.run`
    waiting on pytest, which holds no GIL. `results` is written under a lock; the site ids are
    disjoint across shards, so the lock is a formality rather than a correctness argument.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    results: dict[str, bool] = {}
    lock = threading.Lock()

    def worker(shard: int) -> None:
        mirror = _mirror()
        pkg, cs = mirror / _PKG_REL, mirror / _CS_REL
        local: dict[str, bool] = {}
        try:
            _walk_sites(pkg, cs, local, verbose, shard=shard, nshards=jobs)
        finally:
            _discard(mirror)
        with lock:
            results.update(local)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for fut in [pool.submit(worker, i) for i in range(jobs)]:
            fut.result()   # re-raise, rather than losing a shard to a swallowed exception
    return results


def census(verbose: bool = False) -> dict[str, bool]:
    """`{site_id: is_red}` — a site is RED when neutering it makes the suite fail."""
    results: dict[str, bool] = {}
    # 🔴 **SNAPSHOT EVERY FILE BEFORE THE FIRST WRITE, AND RESTORE ON ANY EXIT.** Two defects
    # in one line, both executed by verifiers:
    #
    #   * The read sat INSIDE the loop, so a re-run after a crash read the *neutered* file as its
    #     own original — and then reported `NOW GUARDED … good news` for a site nothing had guarded.
    #   * Killed at 12, 20, 30 and 45 seconds, **4 of 4 runs left a `raise → pass` in a tracked
    #     file**, and the suite then reddened blaming a test. That is the carried "probe modules in
    #     the live tree" finding, reproduced inside the instrument built to end this class of defect.
    #
    # A `finally` does not run when the process is killed, so the restore is also registered with
    # `atexit` and on SIGINT/SIGTERM.
    mirror = _mirror()
    pkg, cs = mirror / _PKG_REL, mirror / _CS_REL
    import atexit as _atexit
    import shutil as _shutil
    # \U0001F534 108 directories, 8.4 GB measured — one 237 MB copy per run, never removed, and one of
    # them landed inside the repo and reddened an unrelated test that a verifier nearly filed as a
    # finding. An instrument that leaves debris is an instrument that manufactures findings.
    #
    # The `atexit` is the KILL PATH only: a `finally` cannot run when the process is killed, and a
    # `SIGKILL` runs neither — but the ordinary exit must not hold 239 MB for the length of the run
    # either, so both are here and `_discard` makes the second call a no-op.
    if _own_mirror(mirror):
        _atexit.register(lambda: _shutil.rmtree(mirror, ignore_errors=True))
    else:
        print(f"census: not registering cleanup for {mirror} — this function did not create it")
    try:
        _walk_sites(pkg, cs, results, verbose, shard=0, nshards=1)
    finally:
        _discard(mirror)
    return results


def _walk_sites(pkg, cs, results: dict, verbose: bool, *, shard: int, nshards: int) -> None:
    """One worker's pass: neuter each site IT owns, run the suite, restore.

    🔴 **THE SHARD IS AN INDEX FILTER OVER THE ONE ENUMERATION, NEVER A SECOND ENUMERATION.**
    Every worker walks `sorted(pkg.glob(...))` and `_sites(...)` in the identical order and keeps
    `i % nshards == shard`, so the union is exactly the sequential set and the shards are disjoint
    **by construction**. Splitting the site list some other way — by module, by count, by a
    partition computed once and handed out — would make "did every site get measured" a property
    somebody has to check, and this run has a standing finding about denominators nobody derives.
    """
    i = -1
    for path in sorted(pkg.glob("*.py")):
        if path.name == "__init__.py":
            continue
        raw = path.read_bytes()
        src = raw.decode("utf-8")
        mod = path.name
        for site_id, node in _sites(ast.parse(src), mod):
            i += 1
            if i % nshards != shard:
                continue
            path.write_bytes(_neutered(src, node).encode("utf-8"))
            try:
                red = not _suite_is_green(cs)
            finally:
                path.write_bytes(raw)   # inside this worker's mirror; the live tree is untouched
            results[site_id] = red
            if verbose:
                print(f"  {'RED   ' if red else 'SILENT'} {site_id}", flush=True)


def _selftest() -> int:
    """🔴 A census that cannot fire is a green light with no subject. Prove both directions first.

    The membrane gate next door runs its own selftest before every real run for exactly this reason,
    and this run has paid three times for a check that was green over nothing.
    """
    sites = []
    for path in sorted(PKG.glob("*.py")):
        if path.name != "__init__.py":
            sites += _sites(ast.parse(path.read_bytes().decode("utf-8")), path.name)
    _ids = [sid for sid, _ in sites]
    _ordinal_free = {sid.rsplit("::", 2)[0] + "::" + sid.rsplit("::", 1)[1] for sid in _ids}
    if len(_ordinal_free) != len(_ids):
        print(f"SELFTEST FAIL: {len(_ids)} sites share {len(_ordinal_free)} ordinal-free ids. "
              f"Two refusals with one id means an allowlist row does not name a site.")
        return 1
    if len(sites) < 50:
        print(f"SELFTEST FAIL: found only {len(sites)} raise sites; the enumeration broke")
        return 1
    # 🔴 **THE SHARDS MUST PARTITION THE SITE SET EXACTLY** — every site measured once, none
    # twice, at every worker count. A parallel census whose shards overlap reports a site twice and
    # whichever worker finishes last wins; one whose shards gap reports a SILENT site as absent, and
    # the allowlist then loses a row nobody decided to remove. Both are wrong answers that look like
    # results, which is the failure class this whole instrument exists to end.
    #
    # `jobs > len(sites)` is in the list deliberately: the empty shards it produces are the shape a
    # partition written as "chunk of size n//k" gets wrong.
    for _n in (1, 2, 3, 7, 8, 12, len(sites), len(sites) + 1):
        _union = [sid for _sh in range(_n)
                  for i, (sid, _) in enumerate(sites) if i % _n == _sh]
        if sorted(_union) != sorted(sid for sid, _ in sites) or len(set(_union)) != len(_union):
            print(f"SELFTEST FAIL: --jobs {_n} does not partition {len(sites)} sites exactly "
                  f"({len(_union)} measured, {len(set(_union))} distinct)")
            return 1
    # 🔴 The baseline used to run in the LIVE tree, through `_suite_is_green`'s `cwd or CS` default.
    # It runs in the mirror now — which is both safer (no subprocess is ever started in the real
    # `services/chat-service`) and more correct, since the mirror is what every other measurement in
    # this run is taken against.
    mirror = _mirror()
    try:
        return _selftest_in(mirror, len(sites))
    finally:
        # 🔴 **THIS FUNCTION LEAKED ITS MIRROR ENTIRELY** — `census()` at least registered an
        # `atexit`, and this one had nothing, so every invocation left a 239 MB copy behind. The
        # previous round's fix for "mirrors never removed" landed on `census()` alone: a pair
        # repaired at one end, twenty lines apart, for the second time in this same file.
        _discard(mirror)


def _selftest_in(mirror: pathlib.Path, n_sites: int) -> int:
    if not _suite_is_green(mirror / _CS_REL, explain=True):
        print("SELFTEST FAIL: the suite is not green before any injection")
        return 1
    # ...and it must go red when a known-guarded site is neutered.
    probe = mirror / _PKG_REL / "contract.py"
    raw = probe.read_bytes()
    src = raw.decode("utf-8")
    target = next((n for sid, n in _sites(ast.parse(src), "contract.py")
                   if "check_row_shape" in sid), None)
    if target is None:
        print("SELFTEST FAIL: no probe site in check_row_shape")
        return 1
    # \U0001F534 **THE NINTH BYPASS, AND IT IS THIS RUN'S SIGNATURE:** `_selftest` neuters and restores
    # **twenty lines below `census()`**, and the guard never calls it — so pointing its probe at the
    # live tree left the gate green. **The fix moved one writer into the mirror and left its sibling
    # behind**, the tenth pair in this run repaired at one end. Enumerated as {2 writers} × {4 write
    # APIs}: **1 of 8 caught.**
    _mutated = _neutered(src, target).encode("utf-8")
    if _mutated == raw:
        # \U0001F534 And the control was theatre: it printed `fires on a guarded one` when `_neutered`
        # returned its input unchanged, and again when this write was deleted outright. A positive
        # control that cannot tell "fired" from "never ran" certifies nothing.
        print("SELFTEST FAIL: neutering produced an identical file; the injection is a no-op")
        return 1
    probe.write_bytes(_mutated)
    try:
        fired = not _suite_is_green(mirror / _CS_REL)
    finally:
        probe.write_bytes(raw)
        assert probe.read_bytes() == raw, "restore changed the probe file"
    if not fired:
        print("SELFTEST FAIL: neutering a guarded refusal did not red the suite")
        return 1
    print(f"agentruntime-census selftest OK - {n_sites} raise sites, fires on a guarded one")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="regenerate the allowlist")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="is the recorded verdict about THIS tree? (exit 1 if stale or absent)")
    ap.add_argument("--force", action="store_true",
                    help="re-measure even when the recorded verdict is current (CI uses this)")
    ap.add_argument("-j", "--jobs", type=int, default=None,
                    help="workers, one mirror each (default: derived from cpu count; 1 = sequential)")
    args = ap.parse_args(argv)

    if args.check:
        return _gatecache.check(VERDICT, "agentruntime-census")

    if args.selftest:
        return _selftest()

    # 🔴 **THE CACHE IS AN ACCELERATOR, NEVER AN AUTHORITY.** CI runs this gate with `--force`, so a
    # recorded verdict cannot be the last word on a branch; what it removes is re-measuring a tree
    # that has not moved — two of five census runs in the session that motivated it. `--check` is
    # the other half, and the more important one: it refuses a verdict about a DIFFERENT tree, which
    # is what turns *"run the gates once per row, at the end"* from prose into a mechanism. That
    # sentence was already in that session's own instructions, and it was violated inside the hour.
    #
    # 🔴 **AND THE COMPARISON BELOW STAYED HERE** rather than moving into a helper shared with the
    # cached path. Splitting it out put `mkdir` and `write_text` on a live-tree path inside a new
    # function, and `test_NO_LIVE_TREE_PATH_REACHES_A_MUTATING_CALL` named all five calls. That
    # gate's `EXEMPT` set is two functions with two stated reasons; widening it to accommodate a
    # restructure nobody needed is how such a list stops meaning anything. The split had also left
    # the helper reading a `silent` that no longer existed in its scope.
    # Captured BEFORE the measurement: a run takes minutes, and a verdict must be stamped with
    # the tree it was taken on, never with whatever the tree became while it ran.
    started_on = _gatecache.tree_digest()
    results = None if args.force else _gatecache.load(VERDICT)
    if results is None:
        # 🔴 The selftest is INSIDE the miss branch, and that is not a shortcut. It proves
        # the instrument can fire — a census that cannot is a green light with no subject — and that
        # proof is a property of the same mirrored tree the verdict is keyed on. Running it on a
        # cache hit would re-prove, for 60 s, something about a tree that has not moved; skipping it
        # on a MISS would be the failure it exists to prevent. `selftest_ok` is recorded in the
        # payload so a verdict cannot claim a proof that never ran.
        rc = _selftest()
        if rc:
            return rc
    if results is not None:
        print(f"census: verdict is current for this tree ({results['tree_digest'][:12]}) — "
              f"reusing {len(results['sites'])} site(s); --force to re-measure")
        results = {k: bool(v) for k, v in results["sites"].items()}
    else:
        jobs = args.jobs if args.jobs is not None else default_jobs()
        if jobs < 1:
            print(f"census: --jobs must be >= 1, got {jobs}")
            return 1
        if jobs == 1:
            results = census(verbose=args.verbose)
        else:
            print(f"census: {jobs} workers, one mirror each", flush=True)
            results = census_parallel(jobs, verbose=args.verbose)
        _gatecache.store(VERDICT, {"sites": results, "selftest_ok": True},
                          digest=started_on)

    silent = sorted(k for k, red in results.items() if not red)

    if args.write:
        ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
        ALLOWLIST.write_text(
            "# Refusal sites the suite does not notice being removed ON THEIR OWN.\n"
            "#\n"
            "# \U0001F534 The header used to say 'a refusal nothing checks', and two verifiers measured\n"
            "# that false for 2 of these 13 rows: a site can be SILENT because a SAME-CLASS SIBLING\n"
            "# reds first, or because it is UNREACHABLE. This gate neuters one site at a time, so\n"
            "# what it observes is exactly 'alone' — and claiming more than the experiment supports is\n"
            "# the failure this whole effort exists to end. Deciding WHY a row is here still needs a\n"
            "# person and a verdict id.\n"
            "# Generated by scripts/agentruntime-census.py --write. Every line is a claim that\n"
            "# nothing checks; adding one is a decision, and removing one is a closed finding.\n"
            + "".join(f"{s}\n" for s in silent), "utf-8")
        print(f"wrote {len(silent)} silent site(s) to {ALLOWLIST.relative_to(ROOT)}")
        return 0

    if not ALLOWLIST.exists():
        print(f"MISSING {ALLOWLIST.relative_to(ROOT)} - run with --write and review the diff")
        return 1
    expected = sorted(l.strip() for l in ALLOWLIST.read_text("utf-8").splitlines()
                      if l.strip() and not l.startswith("#"))
    new_silent = [s for s in silent if s not in expected]
    now_red = [s for s in expected if s not in silent]

    for s in new_silent:
        print(f"NEWLY SILENT  {s}  <- a refusal nothing checks; guard it or record it deliberately")
    for s in now_red:
        print(f"NOW GUARDED   {s}  <- good news: drop it from the allowlist in the same change")
    print(f"agentruntime-census: {len(results)} sites, {len(silent)} silent, "
          f"{len(results) - len(silent)} red")
    return 1 if (new_silent or now_red) else 0


if __name__ == "__main__":
    raise SystemExit(main())
