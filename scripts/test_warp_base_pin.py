#!/usr/bin/env python3
"""Real-git proof for warp/worktrees.py `pin-base` (D-WARP-WORKTREE-BASE-FLAKY).

Run: python -m pytest scripts/test_warp_base_pin.py

These are NOT mocked — they drive a throwaway git repo + a real linked worktree to
PROVE the self-heal: a slice worktree that starts on a STALE base (simulating the
flaky `Agent(isolation:worktree)` harness that handed out `main` instead of the
orchestrator's committed HEAD) is forced onto the exact committed base SHA, so it
builds against the right code. This is the mechanism the whole fix rests on, so it
is verified against git itself, not asserted in prose.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "warp", "worktrees.py")

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


def _git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
    return r.stdout.strip()


def _pin_base(cwd, branch, base):
    """Run the pin-base CLI exactly as a slice runner would, inside `cwd`."""
    return subprocess.run(
        [sys.executable, _SCRIPT, "pin-base", "--branch", branch, "--base", base],
        cwd=cwd, capture_output=True, text=True,
    )


@pytest.fixture()
def repo():
    """A repo with two commits on `main` (OLD then NEW) — NEW adds a file the slice
    depends on, mirroring the orchestrator's committed DESIGN HEAD."""
    root = tempfile.mkdtemp(prefix="warp-pin-")
    main = os.path.join(root, "origin")
    os.makedirs(main)
    _git(main, "init", "-q", "-b", "main")
    _git(main, "config", "user.email", "t@t.dev")
    _git(main, "config", "user.name", "t")
    with open(os.path.join(main, "base.txt"), "w") as f:
        f.write("v1\n")
    _git(main, "add", "base.txt")
    _git(main, "commit", "-q", "-m", "OLD: stale base")
    old_sha = _git(main, "rev-parse", "HEAD")
    # NEW commit = the work the slice MUST build against (missing on the stale base)
    with open(os.path.join(main, "phase3.txt"), "w") as f:
        f.write("M1-M5\n")
    _git(main, "add", "phase3.txt")
    _git(main, "commit", "-q", "-m", "NEW: committed DESIGN HEAD")
    new_sha = _git(main, "rev-parse", "HEAD")
    yield {"main": main, "old": old_sha, "new": new_sha, "root": root}
    shutil.rmtree(root, ignore_errors=True)


def _stale_worktree(repo):
    """A linked worktree checked out at the STALE OLD commit — what the flaky
    harness handed slices 1 & 5 in the real failure."""
    wt = os.path.join(repo["root"], "slice-wt")
    _git(repo["main"], "worktree", "add", "-q", "--detach", wt, repo["old"])
    assert _git(wt, "rev-parse", "HEAD") == repo["old"]
    assert not os.path.exists(os.path.join(wt, "phase3.txt"))  # stale: missing the dep
    return wt


def test_pin_base_heals_stale_worktree(repo):
    """The core proof: a worktree on the stale base is pinned to NEW, so the slice
    branch starts at the exact committed base and the dependency file appears."""
    wt = _stale_worktree(repo)
    r = _pin_base(wt, "warp/t/slice-1", repo["new"])
    assert r.returncode == 0, r.stderr
    assert _git(wt, "rev-parse", "HEAD") == repo["new"]
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "warp/t/slice-1"
    # the work the slice depends on is now present — it was missing on the stale base
    assert os.path.exists(os.path.join(wt, "phase3.txt"))


def test_pin_base_noop_when_already_correct(repo):
    """A worktree already on the right base pins cleanly (idempotent)."""
    wt = os.path.join(repo["root"], "good-wt")
    _git(repo["main"], "worktree", "add", "-q", "--detach", wt, repo["new"])
    r = _pin_base(wt, "warp/t/slice-2", repo["new"])
    assert r.returncode == 0, r.stderr
    assert _git(wt, "rev-parse", "HEAD") == repo["new"]


def test_pin_base_unreachable_sha_returns_blocked(repo):
    """An unreachable base SHA exits 3 (base_mismatch) so the slice returns BLOCKED
    instead of silently building on whatever base it landed on."""
    wt = _stale_worktree(repo)
    r = _pin_base(wt, "warp/t/slice-1", "0" * 40)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "base_mismatch" in (r.stdout + r.stderr)
    # the worktree was NOT moved off its (stale) base — no false pin
    assert _git(wt, "rev-parse", "HEAD") == repo["old"]


def test_pin_base_refuses_in_primary_worktree(repo):
    """The real-run hazard: running pin-base from the PRIMARY checkout (a slice whose
    isolation worktree was never created) must REFUSE — never yank the coordinator's
    main repo onto the slice branch. Exit 4 (wrong_worktree), main repo untouched."""
    main = repo["main"]
    before_head = _git(main, "rev-parse", "HEAD")
    before_branch = _git(main, "rev-parse", "--abbrev-ref", "HEAD")
    r = _pin_base(main, "warp/t/slice-1", repo["new"])
    assert r.returncode == 4, r.stdout + r.stderr
    assert "wrong_worktree" in (r.stdout + r.stderr)
    # the primary checkout did NOT move and was NOT switched to the slice branch
    assert _git(main, "rev-parse", "HEAD") == before_head
    assert _git(main, "rev-parse", "--abbrev-ref", "HEAD") == before_branch
    # and no slice branch was created in the primary repo
    rc = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/warp/t/slice-1"],
        cwd=main,
    ).returncode
    assert rc != 0


def test_pin_base_branch_tip_is_descendant_after_commit(repo):
    """After pin + a slice commit, the coordinator's post-return check
    (`merge-base --is-ancestor BASE branch`) holds — the belt to pin's suspenders."""
    wt = _stale_worktree(repo)
    assert _pin_base(wt, "warp/t/slice-1", repo["new"]).returncode == 0
    with open(os.path.join(wt, "slice_work.txt"), "w") as f:
        f.write("done\n")
    _git(wt, "add", "slice_work.txt")
    _git(wt, "commit", "-q", "-m", "warp(t): slice 1")
    rc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", repo["new"], "warp/t/slice-1"],
        cwd=wt,
    ).returncode
    assert rc == 0  # base is an ancestor of the slice tip → descended-from holds
