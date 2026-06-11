#!/usr/bin/env python3
"""worktrees.py — lifecycle for /warp slice worktrees (Python, cross-platform).

Slices fan out via Agent(isolation:"worktree"); each commits to a FLAT-namespace
branch `warp/<task>/slice-<id>`. This utility inspects + cleans those branches and
their worktrees at the reconcile/cleanup boundary, and guards against stale
worktrees from a prior run before a new fan-out begins.

Why a flat namespace: git refuses to create `refs/heads/<base>/...` when `<base>`
already exists as a branch (refs are filesystem-backed — a leaf ref cannot also
be a directory). RAID hit this (worktrees-create.sh cycle-4 fix). We never prefix
with the base-branch name, so `warp/<task>/slice-<id>` is always safe.

Why Python (not bash like RAID): bash wrappers fail on the project's Windows box
(see workflow-gate.sh → workflow-gate.py rationale). This is the cross-platform
equivalent of RAID's worktrees-*.sh.

Usage:
  worktrees.py check   [--task <slug>]              # exit 1 if stale warp worktrees/branches linger
  worktrees.py list    --task <slug> [--json]
  worktrees.py cleanup --task <slug> [--delete-branches]

Exit codes:
  0  success (check: nothing stale)
  1  check: stale warp worktrees/branches found (refuse to start a new fan-out)
  2  usage / git error
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


# ── pure helpers (testable without a repo) ───────────────────────────


def slice_branch(task: str, slice_id) -> str:
    """The flat-namespace branch for one slice. Never prefixed with the base
    branch, so it cannot collide with an existing ref."""
    return f"warp/{task}/slice-{slice_id}"


def branch_glob(task: str | None) -> str:
    """git ref glob for a task's slice branches (or all warp branches)."""
    return f"warp/{task}/slice-*" if task else "warp/*"


def parse_worktree_porcelain(text: str) -> list[dict]:
    """Parse `git worktree list --porcelain` into [{path, head, branch}].

    Blocks are separated by blank lines. A detached worktree has a `detached`
    line instead of `branch refs/heads/...`; we record branch=None for it.
    """
    # /review-impl LOW-5: normalize CRLF first — `"\n\n"` is NOT a substring of
    # `"\r\n\r\n"`, so an un-normalized CRLF porcelain (possible on Windows)
    # would collapse every worktree into one last-wins record.
    text = text.replace("\r\n", "\n")
    out: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        rec: dict = {"path": None, "head": None, "branch": None}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("worktree "):
                rec["path"] = line[len("worktree "):]
            elif line.startswith("HEAD "):
                rec["head"] = line[len("HEAD "):]
            elif line.startswith("branch "):
                ref = line[len("branch "):]
                rec["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        if rec["path"]:
            out.append(rec)
    return out


def is_warp_branch(branch: str | None, task: str | None) -> bool:
    if not branch:
        return False
    prefix = f"warp/{task}/" if task else "warp/"
    return branch.startswith(prefix)


# ── git plumbing ─────────────────────────────────────────────────────


def _git(*args: str) -> tuple[int, str, str]:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        return 127, "", str(e)


def warp_worktrees(task: str | None) -> list[dict]:
    rc, out, _ = _git("worktree", "list", "--porcelain")
    if rc != 0:
        return []
    return [w for w in parse_worktree_porcelain(out) if is_warp_branch(w["branch"], task)]


def warp_branches(task: str | None) -> list[str]:
    rc, out, _ = _git("branch", "--list", branch_glob(task), "--format=%(refname:short)")
    if rc != 0:
        return []
    return [b.strip() for b in out.splitlines() if b.strip()]


def _is_dirty(path: str) -> bool:
    # /review-impl MED-2: a non-zero `git status` (corrupt/locked worktree, bad
    # path) means we DON'T KNOW the state — treat as dirty so cleanup never
    # `worktree remove --force`s away a slice's uncommitted work on an error.
    rc, out, _ = _git("-C", path, "status", "--porcelain")
    if rc != 0:
        return True
    return bool(out.strip())


def _merged_branches() -> set[str]:
    rc, out, _ = _git("branch", "--merged", "--format=%(refname:short)")
    if rc != 0:
        return set()
    return {b.strip() for b in out.splitlines() if b.strip()}


# ── commands ─────────────────────────────────────────────────────────


def cmd_check(args) -> int:
    wts = warp_worktrees(args.task)
    brs = warp_branches(args.task)
    scope = f"task '{args.task}'" if args.task else "any warp task"
    if not wts and not brs:
        print(f"OK: no stale warp worktrees/branches for {scope}.")
        return 0
    print(f"STALE warp state for {scope} — refuse to start a new fan-out:", file=sys.stderr)
    for w in wts:
        print(f"  worktree {w['path']} ({w['branch']})", file=sys.stderr)
    for b in brs:
        print(f"  branch   {b}", file=sys.stderr)
    print("  → run: python scripts/warp/worktrees.py cleanup --task <slug> "
          "[--delete-branches]", file=sys.stderr)
    return 1


def cmd_list(args) -> int:
    wts = warp_worktrees(args.task)
    brs = warp_branches(args.task)
    if args.json:
        print(json.dumps({"worktrees": wts, "branches": brs}, indent=2))
    else:
        print(f"warp worktrees for task '{args.task}': {len(wts)}")
        for w in wts:
            print(f"  {w['branch']:40s} {w['path']}")
        orphan = [b for b in brs if b not in {w["branch"] for w in wts}]
        if orphan:
            print(f"branches without a worktree: {len(orphan)}")
            for b in orphan:
                print(f"  {b}")
    return 0


def cmd_cleanup(args) -> int:
    wts = warp_worktrees(args.task)
    merged = _merged_branches() if args.delete_branches else set()
    removed, kept_dirty, kept_unmerged = 0, 0, 0

    for w in wts:
        path, branch = w["path"], w["branch"]
        if _is_dirty(path):
            print(f"  {branch} — DIRTY, leaving worktree for forensic ({path})", file=sys.stderr)
            kept_dirty += 1
            continue
        rc, _, err = _git("worktree", "remove", "--force", path)
        if rc != 0:
            print(f"  {branch} — worktree remove failed: {err.strip()}", file=sys.stderr)
            continue
        print(f"  {branch} — worktree removed")
        removed += 1
        if args.delete_branches:
            if branch in merged:
                _git("branch", "-d", branch)
                print(f"  {branch} — branch deleted (merged)")
            else:
                print(f"  {branch} — branch KEPT (not merged into HEAD)", file=sys.stderr)
                kept_unmerged += 1

    print(f"\ncleanup: {removed} removed, {kept_dirty} dirty-kept, "
          f"{kept_unmerged} unmerged-kept")
    # dirty worktrees are a real signal (a slice left uncommitted work) — surface
    # via exit 1 so the orchestrator notices, but never on the happy path.
    return 1 if kept_dirty else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lifecycle for /warp slice worktrees.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="exit 1 if stale warp worktrees/branches linger")
    pc.add_argument("--task", default=None)
    pc.set_defaults(fn=cmd_check)

    pl = sub.add_parser("list", help="list warp worktrees + branches for a task")
    pl.add_argument("--task", required=True)
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(fn=cmd_list)

    pk = sub.add_parser("cleanup", help="remove clean warp worktrees for a task")
    pk.add_argument("--task", required=True)
    pk.add_argument("--delete-branches", action="store_true",
                    help="also delete branches already merged into HEAD")
    pk.set_defaults(fn=cmd_cleanup)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
