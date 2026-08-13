#!/usr/bin/env python3
"""boundaries-lock-gate — enforce the `_boundaries/` single-writer mutex at commit time.

WHY THIS EXISTS
---------------
`_boundaries/_LOCK.md` declares a single-writer mutex over the boundary folder.
It is *advisory*: nothing enforced it, and on 2026-07-26 two independent failures
were found in one day —

  1. Three `_boundaries/` changelog entries asserted a `[boundaries-lock-claim+release]`
     cycle that **never happened** (`Owner:` was never set).
  2. A peer session wrote `99_changelog.md` while another session held the lock.

Both sessions saw git's "file changed on disk" warning repeatedly and continued.
The conclusion recorded in `_LOCK.md` was: *the hook is the fix, not more care.*

WHAT IT CHECKS
--------------
If a commit stages any `_boundaries/` file OTHER than `_LOCK.md`, then that same
folder's `_LOCK.md` MUST also be staged, and its staged diff MUST add a
`_Last released:_` line — i.e. the commit carries evidence of a completed
claim+release cycle.

Deliberately permitted:
  * staging `_LOCK.md` alone (a bare claim, before the work lands)
  * the repo's normal combined `[boundaries-lock-claim+release]` commit, which
    ends with `Owner: None` — so a naive "Owner must not be None" rule would have
    rejected every legitimate commit. Evidence-of-cycle is the correct check.

Also WARNS (never blocks) if the committed `_LOCK.md` still shows a non-None
`Owner:` — a lock left held is a bug too, but a different one, and blocking it
would break the legitimate bare-claim commit above.

GT8 · what this gate lacked
---------------------------
Its rules were welded to git: `main()` read the staged list and called `git show`
inline, so there was nothing a case could drive. `evaluate()` now takes the file
list plus two lookups, and only the lookups need git — the same split that let
`context-inspector-trace-gate` be proven without a stack.

Its structural limit, stated rather than left implicit: in a sweep nothing is
staged, so the live half has no subject and its green says only that the rules
are proven. The bare invocation now says so instead of printing a bare "nothing
to do".

USAGE
-----
    python scripts/boundaries-lock-gate.py --staged     # pre-commit
    python scripts/boundaries-lock-gate.py --staged --warn-only

Exit 0 = pass, 1 = violation. Bypass in a true emergency with `git commit --no-verify`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict

#: A child with no timeout hangs the pre-commit hook forever, with no
#: output and nothing to kill but the terminal. Surfaced by the bite
#: harness's unbounded-child survey when this gate joined its table.
GIT_TIMEOUT_S = 60

def _git_timed_out(args=()) -> None:
    """A git that never returns is CANNOT-RUN, not "no files changed".

    Returning an empty list here would make the gate scan nothing and print
    PASS, which is the exact shape this repo keeps finding. Exit 2 says so.
    """
    detail = " ".join(str(a) for a in args)
    print(f"CANNOT RUN — `git {detail}`".rstrip() +
          f" did not return within {GIT_TIMEOUT_S}s; refusing to report a verdict "
          f"on a file list that was never read.", file=sys.stderr)
    raise SystemExit(2)


LOCK_BASENAME = "_LOCK.md"
BOUNDARY_SEGMENT = "/_boundaries/"
RELEASE_MARKER = "_Last released:_"


def git(*args: str) -> str:
    """Run a git command and return stdout, tolerating undecodable bytes."""
    try:
        out = subprocess.run(
            ["git", *args],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        _git_timed_out(args)
    return out.stdout.decode("utf-8", errors="replace")


def staged_files() -> list[str]:
    return [p for p in git("diff", "--cached", "--name-only").splitlines() if p.strip()]


def added_lines(path: str) -> list[str]:
    """Lines ADDED to `path` in the staged diff (leading '+' stripped)."""
    diff = git("diff", "--cached", "--unified=0", "--", path)
    return [
        ln[1:]
        for ln in diff.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    ]


def lock_owner(path: str) -> str | None:
    """`Owner:` value from the STAGED content of a `_LOCK.md`, or None if unreadable."""
    blob = git("show", f":{path}")
    for line in blob.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **Owner:**"):
            return stripped.split("**Owner:**", 1)[1].strip()
    return None


def evaluate(files, added_lines_fn, owner_fn):
    """The ENTIRE rule set, as a pure function of the staged file list plus two
    lookups. Only the lookups need git; the rules do not — which is why
    `--self-test` can prove every one of them bites without staging anything.

    Returns (violations, warnings, n_folders).
    """
    edits: dict[str, list[str]] = defaultdict(list)
    locks: dict[str, str] = {}
    for path in files:
        if BOUNDARY_SEGMENT not in "/" + path:
            continue
        folder = path.rsplit("/", 1)[0]
        if path.rsplit("/", 1)[-1] == LOCK_BASENAME:
            locks[folder] = path
        else:
            edits[folder].append(path)

    violations: list[str] = []
    warnings: list[str] = []

    for folder, changed in sorted(edits.items()):
        lock_path = locks.get(folder)
        # Message refinement, not detection: with no staged lock there is no
        # release line either, so the next branch reds anyway. It stays because
        # "you did not stage the lock" and "the lock evidences no release" send a
        # committer to different actions. A bite arm on it came back green.
        if lock_path is None:
            violations.append(
                f"{folder}/: {len(changed)} file(s) staged but {LOCK_BASENAME} is NOT staged\n"
                f"    changed: {', '.join(sorted(changed))}\n"
                f"    → a _boundaries/ edit must carry a lock cycle. Claim the lock "
                f"(set Owner: BEFORE editing), do the work, then release it."
            )
            continue

        if not any(RELEASE_MARKER in ln for ln in added_lines_fn(lock_path)):
            violations.append(
                f"{folder}/: {LOCK_BASENAME} is staged but adds no '{RELEASE_MARKER}' line\n"
                f"    changed: {', '.join(sorted(changed))}\n"
                f"    → the commit does not evidence a completed claim+release cycle."
            )
            continue

        owner = owner_fn(lock_path)
        if owner is not None and owner.lower() not in ("none", "—", "-", ""):
            warnings.append(f"{folder}/: lock left HELD by {owner!r} after this commit")

    return violations, warnings, len(edits)


# ── SELF-TEST ────────────────────────────────────────────────────────────────
B = "docs/x/_boundaries"


def self_test() -> int:
    failures = 0

    def probe(name, want_v, want_w, files, added=None, owners=None):
        nonlocal failures
        added = added or {}
        owners = owners or {}
        try:
            v, w, _ = evaluate(files, lambda p: added.get(p, []), lambda p: owners.get(p))
        except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
            failures += 1
            print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
            return
        ok = (len(v) == want_v) and (len(w) == want_w)
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {len(v)} violation(s), {len(w)} warning(s) "
              f"(want {want_v}/{want_w})")

    RELEASED = [f"{RELEASE_MARKER} 2026-08-12"]
    print("boundaries-lock-gate --self-test")

    probe("nothing staged is clean", 0, 0, [])
    probe("a non-boundary file is not our business", 0, 0, ["services/a/main.go"])
    probe("the lock staged ALONE is a legitimate bare claim", 0, 0, [f"{B}/{LOCK_BASENAME}"])

    probe("boundary content WITHOUT the lock fails", 1, 0, [f"{B}/99_changelog.md"])
    probe("boundary content WITH a released lock passes", 0, 0,
          [f"{B}/99_changelog.md", f"{B}/{LOCK_BASENAME}"],
          added={f"{B}/{LOCK_BASENAME}": RELEASED})
    probe("...but a lock adding NO release line fails", 1, 0,
          [f"{B}/99_changelog.md", f"{B}/{LOCK_BASENAME}"],
          added={f"{B}/{LOCK_BASENAME}": ["- **Owner:** alice"]})

    # the warn leg — a lock left held is a different bug, and must NOT block
    probe("a lock left HELD warns but does not block", 0, 1,
          [f"{B}/99_changelog.md", f"{B}/{LOCK_BASENAME}"],
          added={f"{B}/{LOCK_BASENAME}": RELEASED},
          owners={f"{B}/{LOCK_BASENAME}": "alice"})
    for none_ish in ("None", "none", "—", "-", ""):
        probe(f"...and Owner={none_ish!r} is released, not held", 0, 0,
              [f"{B}/99_changelog.md", f"{B}/{LOCK_BASENAME}"],
              added={f"{B}/{LOCK_BASENAME}": RELEASED},
              owners={f"{B}/{LOCK_BASENAME}": none_ish})

    # per-folder, not one hardcoded path
    B2 = "docs/y/_boundaries"
    probe("TWO folders are judged independently", 1, 0,
          [f"{B}/99.md", f"{B}/{LOCK_BASENAME}", f"{B2}/99.md"],
          added={f"{B}/{LOCK_BASENAME}": RELEASED})
    probe("...and both released is clean", 0, 0,
          [f"{B}/99.md", f"{B}/{LOCK_BASENAME}", f"{B2}/99.md", f"{B2}/{LOCK_BASENAME}"],
          added={f"{B}/{LOCK_BASENAME}": RELEASED, f"{B2}/{LOCK_BASENAME}": RELEASED})

    if failures:
        print(f"boundaries-lock-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("boundaries-lock-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true", help="check staged files (pre-commit)")
    ap.add_argument("--warn-only", action="store_true", help="report but always exit 0")
    ap.add_argument("--self-test", "--selftest", dest="self_test", action="store_true",
                    help="prove every rule bites, over synthetic staged sets")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    rc = self_test()
    if rc:
        return rc

    if not args.staged:
        # Nothing is staged in a sweep, so the live half has no subject there.
        # Said out loud rather than reported as a pass with no qualifier: this
        # gate's green in `--run-all` means the RULES are proven (above), not
        # that any commit was inspected.
        print("[boundaries-lock] live half needs --staged; nothing inspected. "
              "The self-test above is what makes this gate's green mean something.")
        return 0

    files = staged_files()
    violations, warnings, n_folders = evaluate(files, added_lines, lock_owner)

    for w in warnings:
        print(f"[boundaries-lock] WARN — {w}")

    if not violations:
        if n_folders:
            print(f"[boundaries-lock] PASS — {n_folders} boundary folder(s), lock cycle evidenced")
        else:
            print("[boundaries-lock] PASS — no _boundaries/ content staged")
        return 0

    print("[boundaries-lock] FAIL — _boundaries/ edited without an evidenced lock cycle\n")
    for v in violations:
        print(f"  • {v}\n")
    print(
        "  Why this is enforced: on 2026-07-26 three changelog entries claimed lock\n"
        "  cycles that never happened, and a peer wrote 99_changelog.md while another\n"
        "  session held the lock. Discipline alone did not catch it.\n"
        "  Emergency bypass: git commit --no-verify"
    )
    return 0 if args.warn_only else 1


if __name__ == "__main__":
    sys.exit(main())
