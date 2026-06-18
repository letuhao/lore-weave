#!/usr/bin/env python3
"""Unit tests for warp/worktrees.py pure helpers.

Run: python -m pytest scripts/test_warp_worktrees.py

Covers the parsing/derivation logic (the part where RAID's bash worktree scripts
historically had bugs — ref-namespace collisions, porcelain parsing). The git
side-effecting commands are thin subprocess wrappers, exercised in the /warp
dry-run rather than mocked here.
"""
import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "warp", "worktrees.py")
_SPEC = importlib.util.spec_from_file_location("warp_worktrees", _SCRIPT)
wt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wt)


def test_slice_branch_is_flat_namespace():
    # never prefixed with a base branch -> cannot collide with an existing ref
    assert wt.slice_branch("factory-budget", 1) == "warp/factory-budget/slice-1"
    assert wt.slice_branch("factory-budget", "2a") == "warp/factory-budget/slice-2a"


@pytest.mark.parametrize("task,expected", [
    ("foo", "warp/foo/slice-*"),
    (None, "warp/*"),
])
def test_branch_glob(task, expected):
    assert wt.branch_glob(task) == expected


@pytest.mark.parametrize("branch,task,expect", [
    ("warp/foo/slice-1", "foo", True),
    ("warp/foo/slice-1", None, True),
    ("warp/bar/slice-1", "foo", False),
    ("main", "foo", False),
    ("main", None, False),
    (None, None, False),
])
def test_is_warp_branch(branch, task, expect):
    assert wt.is_warp_branch(branch, task) is expect


def test_parse_worktree_porcelain_basic():
    text = (
        "worktree /repo/main\n"
        "HEAD aaaa1111\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /tmp/warp-foo-slice-1\n"
        "HEAD bbbb2222\n"
        "branch refs/heads/warp/foo/slice-1\n"
    )
    recs = wt.parse_worktree_porcelain(text)
    assert len(recs) == 2
    assert recs[0] == {"path": "/repo/main", "head": "aaaa1111", "branch": "main"}
    assert recs[1]["branch"] == "warp/foo/slice-1"
    assert recs[1]["path"] == "/tmp/warp-foo-slice-1"


def test_parse_worktree_porcelain_detached():
    text = (
        "worktree /repo/main\n"
        "HEAD cccc3333\n"
        "detached\n"
    )
    recs = wt.parse_worktree_porcelain(text)
    assert len(recs) == 1
    assert recs[0]["branch"] is None
    assert recs[0]["head"] == "cccc3333"


def test_parse_worktree_porcelain_empty():
    assert wt.parse_worktree_porcelain("") == []
    assert wt.parse_worktree_porcelain("\n\n") == []


def test_parse_filters_blocks_without_path():
    # a stray block lacking a `worktree` line is dropped
    text = "HEAD deadbeef\nbranch refs/heads/orphan\n"
    assert wt.parse_worktree_porcelain(text) == []


def test_parse_worktree_porcelain_crlf():
    # /review-impl LOW-5: CRLF porcelain must still split into N records, not
    # collapse to one (last-wins) — "\n\n" is not a substring of "\r\n\r\n".
    text = (
        "worktree /repo/main\r\nHEAD aaaa\r\nbranch refs/heads/main\r\n"
        "\r\n"
        "worktree /tmp/wt\r\nHEAD bbbb\r\nbranch refs/heads/warp/foo/slice-1\r\n"
    )
    recs = wt.parse_worktree_porcelain(text)
    assert len(recs) == 2
    assert recs[1]["branch"] == "warp/foo/slice-1"
    assert recs[1]["path"] == "/tmp/wt"


# ── /review-impl MED-2: cleanup must never force-remove on an unknown state ──


def test_is_dirty_git_error_treated_dirty(monkeypatch):
    monkeypatch.setattr(wt, "_git", lambda *a: (1, "", "fatal: not a git repo"))
    assert wt._is_dirty("/whatever") is True


def test_is_dirty_clean(monkeypatch):
    monkeypatch.setattr(wt, "_git", lambda *a: (0, "", ""))
    assert wt._is_dirty("/whatever") is False


def test_is_dirty_modified(monkeypatch):
    monkeypatch.setattr(wt, "_git", lambda *a: (0, " M file.go\n", ""))
    assert wt._is_dirty("/whatever") is True
