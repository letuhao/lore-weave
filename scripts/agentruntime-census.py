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
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_PKG_REL = pathlib.Path("services") / "chat-service" / "app" / "agentruntime"
_CS_REL = pathlib.Path("services") / "chat-service"
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
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    for rel in listing.split(b"\0"):
        if not rel:
            continue
        src = ROOT / rel.decode("utf-8")
        if not src.is_file():                       # a submodule or a deleted-but-tracked path
            continue
        dst = out / rel.decode("utf-8")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return out
SUITE = "tests/test_cp1_membrane.py"
ALLOWLIST = ROOT / "contracts" / "agentruntime-census-silent.txt"


def _with_condition(node: ast.Raise):
    """The refusal **and the test that reaches it**, as one expression."""
    cond = getattr(_with_condition, "_ctx", {}).get(id(node))
    if cond is None:
        return node
    return ast.Expr(value=ast.Tuple(elts=[ast.parse(ast.unparse(cond)).body[0].value,
                                          ast.parse(ast.unparse(node)).body[0].exc
                                          or ast.Constant(value=None)], ctx=ast.Load()))


def _shape_digest(node: ast.Raise) -> str:
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
    shape = ast.parse(ast.unparse(_with_condition(node))).body[0]
    for n in ast.walk(shape):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            n.value = "\u0000"
    return hashlib.sha256(ast.unparse(shape).encode("utf-8")).hexdigest()[:8]


def _sites(tree: ast.AST, mod: str) -> list[tuple[str, ast.Raise]]:
    """Every `raise`, keyed so the id survives an edit that moves it.

    `module::qualname::ExcClass::ordinal` — NOT the line number, which changes whenever anything
    above it changes, and an allowlist keyed on line numbers is an allowlist that goes stale
    silently. The ordinal disambiguates several raises of one class in one function.
    """
    out: list[tuple[str, ast.Raise]] = []
    seen: dict[str, int] = {}

    def walk(node, qual: str):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, f"{qual}.{child.name}" if qual else child.name)
                continue
            if isinstance(child, (ast.If, ast.While)):
                for inner in ast.walk(child):
                    if isinstance(inner, ast.Raise):
                        _with_condition._ctx = getattr(_with_condition, "_ctx", {})
                        _with_condition._ctx.setdefault(id(inner), child.test)
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
                digest = _shape_digest(child)
                out.append((f"{key}::{seen[key]}::{digest}", child))
            walk(child, qual)

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


def _suite_is_green(cwd=None) -> bool:
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
    args = [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header"]
    try:
        import importlib.util as _ilu
        if _ilu.find_spec("pytest_randomly") is not None:
            args += ["-p", "no:randomly"]
    except Exception:                                    # noqa: BLE001 - probing must never decide
        pass
    r = subprocess.run(args, cwd=cwd or CS, capture_output=True, text=True)
    if r.returncode not in (0, 1):
        raise SystemExit(
            "pytest exited " + str(r.returncode) + " in " + str(cwd or CS) + " - it did "
            "not run the suite, so no site can be classified. Reporting these as RED would "
            "print a plausible lie." + chr(10) + r.stdout[-2000:] + chr(10) + r.stderr[-2000:])
    # 🔴 **THIS LINE WAS DELETED BY THE REPAIR THAT WAS FIXING THE LINES AROUND IT.** A line-based
    # script cleaning up a broken f-string above took the `return` with it, so this function fell
    # off the end and returned `None` — falsy — and every run reported "the suite is not green
    # before any injection" while the suite ran 137 green from the same directory, measured. The
    # census could not have classified a single site, and its failure message pointed at the suite.
    return r.returncode == 0


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
    _atexit.register(lambda: _shutil.rmtree(mirror, ignore_errors=True))
    for path in sorted(pkg.glob("*.py")):
        if path.name == "__init__.py":
            continue
        raw = path.read_bytes()
        src = raw.decode("utf-8")
        mod = path.name
        for site_id, node in _sites(ast.parse(src), mod):
            path.write_bytes(_neutered(src, node).encode("utf-8"))
            try:
                red = not _suite_is_green(cs)
            finally:
                path.write_bytes(raw)     # inside the mirror; the live tree is never touched
            results[site_id] = red
            if verbose:
                print(f"  {'RED   ' if red else 'SILENT'} {site_id}", flush=True)
    return results


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
    if not _suite_is_green():
        print("SELFTEST FAIL: the suite is not green before any injection")
        return 1
    # ...and it must go red when a known-guarded site is neutered.
    mirror = _mirror()
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
    print(f"agentruntime-census selftest OK - {len(sites)} raise sites, fires on a guarded one")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="regenerate the allowlist")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    rc = _selftest()
    if rc:
        return rc

    results = census(verbose=args.verbose)
    silent = sorted(k for k, red in results.items() if not red)

    if args.write:
        ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
        ALLOWLIST.write_text(
            "# Refusal sites the suite does not notice being removed ON THEIR OWN.\n"
            "#\n"
            "# \U0001F534 The header used to say 'a refusal nothing checks', and two verifiers measured\n"
            "# that false for 2 of these 13 rows: a site can be SILENT because a SAME-CLASS SIBLING\n"
            "# reds first, or because it is UNREACHABLE. This gate neuters one site at a time, so\n"
            "# what it observes is exactly 'alone' \u2014 and claiming more than the experiment supports is\n"
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
