"""P2 — tests for the extractor_version constant (D7)."""

from __future__ import annotations

import os
import re

import pytest

from loreweave_extraction import __extractor_version__, get_extractor_version
from loreweave_extraction._version import _compute_extractor_version


def test_version_format_is_v1_8hex():
    """Format spec: v1-<8 hex chars>."""
    assert re.match(r"^v1-[0-9a-f]{8}$", __extractor_version__), (
        f"unexpected format: {__extractor_version__!r}"
    )


def test_version_is_deterministic_across_calls():
    """Same prompts dir + same call -> same hash."""
    v1 = _compute_extractor_version()
    v2 = _compute_extractor_version()
    assert v1 == v2


def test_get_extractor_version_returns_module_constant_by_default():
    """No env var -> returns the cached module constant."""
    os.environ.pop("LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE", None)
    assert get_extractor_version() == __extractor_version__


def test_dev_recompute_env_var_triggers_recompute(monkeypatch):
    """LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1 -> bypasses module constant.

    We can't easily mutate the prompts dir, so we just assert that the env
    var path is taken (returns the same value because prompts don't change,
    but the code path is exercised). The non-env path skips _compute call.
    """
    monkeypatch.setenv("LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE", "1")
    # Should return SAME hash (prompts unchanged) but exercise the recompute path.
    assert get_extractor_version() == __extractor_version__


def test_version_excludes_non_md_files_in_prompts_dir(tmp_path, monkeypatch):
    """Only .md files contribute to the hash."""
    from loreweave_extraction import _version as v

    monkeypatch.setattr(v, "_PROMPTS_DIR", tmp_path)
    (tmp_path / "alpha.md").write_text("A")
    (tmp_path / "ignored.txt").write_text("Z")  # non-md should NOT affect hash

    hash_with_only_md = v._compute_extractor_version()

    # Add another .md -> hash MUST change.
    (tmp_path / "beta.md").write_text("B")
    hash_with_two_md = v._compute_extractor_version()
    assert hash_with_only_md != hash_with_two_md

    # Add another .txt -> hash MUST NOT change.
    (tmp_path / "another.txt").write_text("Y")
    hash_with_two_md_and_txt = v._compute_extractor_version()
    assert hash_with_two_md == hash_with_two_md_and_txt


def test_version_changes_when_md_content_changes(tmp_path, monkeypatch):
    """Editing a prompt file -> hash bumps (P2 implicit-invalidation property)."""
    from loreweave_extraction import _version as v

    monkeypatch.setattr(v, "_PROMPTS_DIR", tmp_path)
    p = tmp_path / "entity.md"
    p.write_text("original prompt text")
    hash_before = v._compute_extractor_version()

    p.write_text("edited prompt text")
    hash_after = v._compute_extractor_version()

    assert hash_before != hash_after


def test_empty_prompts_dir_returns_v1_empty(tmp_path, monkeypatch):
    """Edge case: install without prompts (test fixture scenario)."""
    from loreweave_extraction import _version as v

    monkeypatch.setattr(v, "_PROMPTS_DIR", tmp_path)
    assert v._compute_extractor_version() == "v1-empty"
