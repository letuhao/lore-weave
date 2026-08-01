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

LOCK_BASENAME = "_LOCK.md"
BOUNDARY_SEGMENT = "/_boundaries/"
RELEASE_MARKER = "_Last released:_"


def git(*args: str) -> str:
    """Run a git command and return stdout, tolerating undecodable bytes."""
    out = subprocess.run(
        ["git", *args],
        capture_output=True,
        check=False,
    )
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true", help="check staged files (pre-commit)")
    ap.add_argument("--warn-only", action="store_true", help="report but always exit 0")
    args = ap.parse_args()

    if not args.staged:
        print("[boundaries-lock] nothing to do (pass --staged)")
        return 0

    files = staged_files()

    # Group staged boundary files by their owning `_boundaries/` directory, so the
    # rule works for any number of boundary folders rather than one hardcoded path.
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

    if not edits:
        print("[boundaries-lock] PASS — no _boundaries/ content staged")
        return 0

    violations: list[str] = []
    warnings: list[str] = []

    for folder, changed in sorted(edits.items()):
        lock_path = locks.get(folder)
        if lock_path is None:
            violations.append(
                f"{folder}/: {len(changed)} file(s) staged but {LOCK_BASENAME} is NOT staged\n"
                f"    changed: {', '.join(sorted(changed))}\n"
                f"    → a _boundaries/ edit must carry a lock cycle. Claim the lock "
                f"(set Owner: BEFORE editing), do the work, then release it."
            )
            continue

        if not any(RELEASE_MARKER in ln for ln in added_lines(lock_path)):
            violations.append(
                f"{folder}/: {LOCK_BASENAME} is staged but adds no '{RELEASE_MARKER}' line\n"
                f"    changed: {', '.join(sorted(changed))}\n"
                f"    → the commit does not evidence a completed claim+release cycle."
            )
            continue

        owner = lock_owner(lock_path)
        if owner is not None and owner.lower() not in ("none", "—", "-", ""):
            warnings.append(f"{folder}/: lock left HELD by {owner!r} after this commit")

    for w in warnings:
        print(f"[boundaries-lock] WARN — {w}")

    if not violations:
        print(f"[boundaries-lock] PASS — {len(edits)} boundary folder(s), lock cycle evidenced")
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
