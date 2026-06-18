#!/usr/bin/env python3
"""Unit tests for slice-manifest-validate.py — the /warp independence guarantee.

Run: python -m pytest scripts/test_slice_manifest_validate.py

The validator is the safety backbone of /warp parallel mode: it must BLOCK any
manifest whose slices could collide in parallel worktrees, while not over-
blocking legitimate disjoint decompositions. These tests pin both directions so
a future tweak can't silently weaken the disjointness guarantee.
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "warp", "slice-manifest-validate.py")
_SPEC = importlib.util.spec_from_file_location("slice_manifest_validate", _SCRIPT)
v = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v)


def _blocks(findings):
    return [f for f in findings if f.severity == "BLOCK"]


def _rules(findings, severity=None):
    return {f.rule for f in findings if severity is None or f.severity == severity}


def _valid_manifest():
    """A minimal, fully-valid two-slice manifest."""
    return {
        "task": "factory-budget-and-i18n",
        "frozen_interface": [
            {"path": "contracts/api/campaign.yaml", "sha": "abc123"},
        ],
        "slices": [
            {
                "id": 1,
                "label": "budget-backend",
                "writes": ["services/campaign-service/internal/budget/**"],
                "reads": ["contracts/api/campaign.yaml"],
                "acceptance": ["go test ./internal/budget/..."],
            },
            {
                "id": 2,
                "label": "picker-frontend",
                "writes": ["frontend/src/features/campaigns/**"],
                "reads": ["contracts/api/campaign.yaml"],
                "acceptance": ["pnpm -C frontend vitest run campaigns"],
            },
        ],
        "merge_plan": {
            "integrate_order": [1, 2],
            "reconcile_evidence": "live smoke: create campaign -> budget rejects over-cap",
            "on_contract_violation": "HALT_REDESIGN",
        },
    }


# ── component normalization + overlap (the heart) ─────────────────────


@pytest.mark.parametrize("glob,expected", [
    ("services/x/**", ("services", "x")),
    ("services/x/*", ("services", "x")),
    ("services/x/types.go", ("services", "x", "types.go")),
    ("services\\x\\budget\\**", ("services", "x", "budget")),  # windows seps
    ("./frontend/src/**", ("frontend", "src")),
    ("**", ()),
    ("", ()),
])
def test_components_normalization(glob, expected):
    assert v.components(glob) == expected


@pytest.mark.parametrize("a,b,expect", [
    # equal / nested -> overlap
    (("services", "x"), ("services", "x"), True),
    (("services", "x"), ("services", "x", "internal"), True),
    (("services", "x", "internal"), ("services", "x"), True),
    # siblings -> no overlap
    (("services", "x"), ("services", "y"), False),
    (("services", "book-service"), ("frontend", "src"), False),
    # whole-repo overlaps everything
    ((), ("services", "x"), True),
])
def test_overlap_logic(a, b, expect):
    assert v.overlaps(a, b) is expect


def test_component_prefix_not_string_prefix():
    """`services/book` must NOT overlap `services/book-service` — they are
    distinct path components, even though one is a string prefix of the other."""
    assert v.overlaps(v.components("services/book"),
                      v.components("services/book-service")) is False


# ── /review-impl HIGH-1: interior/partial-segment globs fail CLOSED ────


@pytest.mark.parametrize("glob", [
    "services/*/budget/**",   # interior wildcard
    "services/**/types.go",   # interior **
    "services/x*",            # partial-segment trailing
    "services/x?/**",         # char wildcard
    "services/{a,b}/**",      # brace expansion
    "**",                     # whole repo
    "*",
])
def test_unsupported_glob_flagged(glob):
    assert v.unsupported_glob(glob) is not None


@pytest.mark.parametrize("glob", [
    "services/x/budget/**",
    "services/x/**",
    "services/x/*",
    "services/x/types.go",
    "frontend/src/features/campaigns/**",
])
def test_supported_glob_ok(glob):
    assert v.unsupported_glob(glob) is None


def test_midpath_glob_in_manifest_blocks():
    m = _valid_manifest()
    m["slices"][0]["writes"] = ["services/*/budget/**"]
    findings = v.validate_manifest(m)
    assert v.has_block(findings)
    assert any("wildcard" in f.message for f in _blocks(findings))


def test_demonstrated_false_disjoint_now_blocks():
    """The exact /review-impl HIGH-1 repro: two slices that overlap
    (`services/*/budget/**` matches `services/campaign/budget/**`) but read as
    component-disjoint. Must BLOCK now (fail-closed on the interior glob)."""
    m = _valid_manifest()
    m["slices"][0]["writes"] = ["services/*/budget/**"]
    m["slices"][1]["writes"] = ["services/campaign/budget/**"]
    assert v.has_block(v.validate_manifest(m))


# ── /review-impl MED-3: case-insensitive overlap (Windows/macOS FS) ────


def test_overlaps_is_case_insensitive():
    assert v.overlaps(v.components("services/Book"),
                      v.components("services/book")) is True


def test_case_only_writes_collide_blocks():
    m = _valid_manifest()
    m["slices"][0]["writes"] = ["services/Book/**"]
    m["slices"][1]["writes"] = ["services/book/**"]
    assert "R2" in _rules(v.validate_manifest(m), "BLOCK")


# ── /review-impl MED-4: --verify-frozen drift check (injected hasher) ──


def _frozen(sha):
    m = _valid_manifest()
    m["frozen_interface"] = [{"path": "contracts/api/campaign.yaml", "sha": sha}]
    return m


def _ok(sha):
    return lambda p: ("ok", sha)


def test_verify_frozen_match_ok():
    f = v.verify_frozen_shas(_frozen("a" * 40), blob_getter=_ok("a" * 40))
    assert not v.has_block(f)


def test_verify_frozen_drift_blocks():
    f = v.verify_frozen_shas(_frozen("a" * 40), blob_getter=_ok("b" * 40))
    assert "R1c" in {x.rule for x in f if x.severity == "BLOCK"}


def test_verify_frozen_abbrev_prefix_ok():
    # a 7-char declared sha matches as a prefix of the full blob sha
    f = v.verify_frozen_shas(_frozen("abc1234"), blob_getter=_ok("abc1234" + "f" * 33))
    assert not v.has_block(f)


def test_verify_frozen_abbrev_mismatch_blocks():
    f = v.verify_frozen_shas(_frozen("abc1234"), blob_getter=_ok("abc9999" + "f" * 33))
    assert "R1c" in {x.rule for x in f if x.severity == "BLOCK"}


def test_verify_frozen_not_committed_blocks():
    # dry-run D1: a frozen file absent from HEAD is the catastrophic case —
    # slices fan out from a committed base and won't see it.
    f = v.verify_frozen_shas(_frozen("a" * 40), blob_getter=lambda p: ("absent", None))
    blocks = [x for x in f if x.severity == "BLOCK"]
    assert blocks and "not committed" in blocks[0].message


def test_verify_frozen_git_unavailable_warns_not_blocks():
    f = v.verify_frozen_shas(_frozen("a" * 40), blob_getter=lambda p: ("unavailable", None))
    assert not v.has_block(f)
    assert any(x.severity == "WARN" and x.rule == "R1c" for x in f)


def test_verify_frozen_case_insensitive():
    f = v.verify_frozen_shas(_frozen("ABCDEF1234"), blob_getter=_ok("abcdef1234" + "0" * 30))
    assert not v.has_block(f)


def test_cli_verify_frozen_real_git_match(tmp_path):
    """End-to-end against real git: a manifest whose frozen sha matches the
    file's COMMITTED (HEAD) blob sha clears --verify-frozen; a wrong sha BLOCKs."""
    import subprocess as sp
    target = "CLAUDE.md"  # a real, committed file
    repo_root = os.path.dirname(_HERE)
    try:
        sha = sp.run(["git", "rev-parse", f"HEAD:{target}"], cwd=repo_root,
                     capture_output=True, text=True, timeout=10)
    except (OSError, sp.SubprocessError):
        pytest.skip("git unavailable")
    if sha.returncode != 0:
        pytest.skip(f"{target} not committed in HEAD")
    real = sha.stdout.strip()
    m = _valid_manifest()
    m["frozen_interface"] = [{"path": target, "sha": real}]
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    r = sp.run([sys.executable, _SCRIPT, str(p), "--verify-frozen", "--json"],
               cwd=repo_root, capture_output=True, text=True)
    payload = json.loads(r.stdout)
    assert not any(b["rule"] == "R1c" for b in payload["blocks"]), payload
    assert r.returncode == 0, r.stdout

    # a deliberately wrong sha must BLOCK with R1c (drift)
    m["frozen_interface"] = [{"path": target, "sha": "0" * 40}]
    p.write_text(json.dumps(m), encoding="utf-8")
    r2 = sp.run([sys.executable, _SCRIPT, str(p), "--verify-frozen", "--json"],
                cwd=repo_root, capture_output=True, text=True)
    payload2 = json.loads(r2.stdout)
    assert any(b["rule"] == "R1c" for b in payload2["blocks"])
    assert r2.returncode == 1


# ── happy path ────────────────────────────────────────────────────────


def test_valid_manifest_has_no_findings():
    findings = v.validate_manifest(_valid_manifest())
    assert findings == [], f"expected clean, got {findings}"
    assert not v.has_block(findings)


# ── R2 disjoint writes (the core invariant) ───────────────────────────


def test_identical_writes_block():
    m = _valid_manifest()
    m["slices"][1]["writes"] = ["services/campaign-service/internal/budget/**"]
    findings = v.validate_manifest(m)
    assert "R2" in _rules(findings, "BLOCK")


def test_nested_write_overlap_blocks():
    m = _valid_manifest()
    # slice 2 writes a subtree of slice 1's write-set
    m["slices"][1]["writes"] = ["services/campaign-service/internal/budget/calc/**"]
    assert "R2" in _rules(v.validate_manifest(m), "BLOCK")


def test_sibling_writes_ok():
    m = _valid_manifest()
    m["slices"][0]["writes"] = ["services/campaign-service/internal/budget/**"]
    m["slices"][1]["writes"] = ["services/campaign-service/internal/picker/**"]
    assert "R2" not in _rules(v.validate_manifest(m), "BLOCK")


def test_three_slices_one_overlap_blocks():
    m = _valid_manifest()
    m["slices"].append({
        "id": 3, "label": "third",
        "writes": ["frontend/src/features/campaigns/widgets/**"],  # nested under slice 2
        "reads": [], "acceptance": ["x"],
    })
    assert "R2" in _rules(v.validate_manifest(m), "BLOCK")


# ── R1 / R1b frozen interface ─────────────────────────────────────────


def test_missing_frozen_blocks():
    m = _valid_manifest()
    del m["frozen_interface"]
    assert "R1" in _rules(v.validate_manifest(m), "BLOCK")


def test_frozen_without_sha_blocks():
    m = _valid_manifest()
    m["frozen_interface"] = [{"path": "contracts/api/campaign.yaml"}]
    assert "R1" in _rules(v.validate_manifest(m), "BLOCK")


def test_empty_sha_blocks():
    m = _valid_manifest()
    m["frozen_interface"] = [{"path": "contracts/api/campaign.yaml", "sha": "  "}]
    assert "R1" in _rules(v.validate_manifest(m), "BLOCK")


def test_slice_writing_frozen_path_blocks():
    m = _valid_manifest()
    # slice 1 writes the frozen interface file -> R1b
    m["slices"][0]["writes"] = ["contracts/api/campaign.yaml"]
    # also re-point slice 2 so the only issue is R1b (avoid incidental overlap)
    findings = v.validate_manifest(m)
    assert "R1b" in _rules(findings, "BLOCK")


# ── R3 reads bounded ──────────────────────────────────────────────────


def test_read_of_other_slice_writes_blocks():
    m = _valid_manifest()
    # slice 2 reads slice 1's write-set -> runtime dependency
    m["slices"][1]["reads"] = ["services/campaign-service/internal/budget/types.go"]
    assert "R3" in _rules(v.validate_manifest(m), "BLOCK")


def test_read_of_own_writes_ok():
    m = _valid_manifest()
    m["slices"][0]["reads"] = ["services/campaign-service/internal/budget/helpers.go"]
    assert "R3" not in _rules(v.validate_manifest(m), "BLOCK")


def test_read_of_frozen_ok():
    m = _valid_manifest()
    # both already read the frozen contract; assert no R3
    assert "R3" not in _rules(v.validate_manifest(m), "BLOCK")


def test_read_of_unrelated_existing_code_ok():
    m = _valid_manifest()
    # reading some stable shared lib not owned by any slice is fine
    m["slices"][0]["reads"] = ["pkg/common/logging/**"]
    assert "R3" not in _rules(v.validate_manifest(m), "BLOCK")


# ── R0 structural ─────────────────────────────────────────────────────


def test_fewer_than_two_slices_blocks():
    m = _valid_manifest()
    m["slices"] = [m["slices"][0]]
    assert "R0" in _rules(v.validate_manifest(m), "BLOCK")


def test_duplicate_ids_block():
    m = _valid_manifest()
    m["slices"][1]["id"] = 1
    assert "R0" in _rules(v.validate_manifest(m), "BLOCK")


def test_missing_writes_blocks():
    m = _valid_manifest()
    m["slices"][0]["writes"] = []
    assert "R0" in _rules(v.validate_manifest(m), "BLOCK")


def test_missing_task_blocks():
    m = _valid_manifest()
    del m["task"]
    assert "R0" in _rules(v.validate_manifest(m), "BLOCK")


def test_missing_acceptance_warns_not_blocks():
    m = _valid_manifest()
    del m["slices"][0]["acceptance"]
    findings = v.validate_manifest(m)
    assert "R0" in _rules(findings, "WARN")
    assert not v.has_block(findings)


def test_non_mapping_manifest_blocks():
    assert v.has_block(v.validate_manifest(["not", "a", "dict"]))


# ── R4 merge plan (advisory — never blocks) ───────────────────────────


def test_missing_merge_plan_warns_not_blocks():
    m = _valid_manifest()
    del m["merge_plan"]
    findings = v.validate_manifest(m)
    assert "R4" in _rules(findings, "WARN")
    assert not v.has_block(findings)


def test_bad_integrate_order_warns():
    m = _valid_manifest()
    m["merge_plan"]["integrate_order"] = [1, 3]  # 3 is not a slice id
    findings = v.validate_manifest(m)
    assert "R4" in _rules(findings, "WARN")
    assert not v.has_block(findings)


def test_missing_halt_redesign_warns():
    m = _valid_manifest()
    m["merge_plan"]["on_contract_violation"] = "patch_it"
    assert "R4" in _rules(v.validate_manifest(m), "WARN")


# ── CLI / exit codes ──────────────────────────────────────────────────


def test_cli_valid_manifest_exit_0(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(_valid_manifest()), encoding="utf-8")
    r = subprocess.run([sys.executable, _SCRIPT, str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK: manifest valid" in r.stdout


def test_cli_overlap_manifest_exit_1(tmp_path):
    m = _valid_manifest()
    m["slices"][1]["writes"] = m["slices"][0]["writes"]
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    r = subprocess.run([sys.executable, _SCRIPT, str(p)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "R2" in r.stderr


def test_cli_json_output(tmp_path):
    m = _valid_manifest()
    m["slices"][1]["writes"] = m["slices"][0]["writes"]
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    r = subprocess.run([sys.executable, _SCRIPT, str(p), "--json"], capture_output=True, text=True)
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["ok"] is False
    assert any(b["rule"] == "R2" for b in payload["blocks"])


def test_cli_missing_file_exit_3(tmp_path):
    r = subprocess.run([sys.executable, _SCRIPT, str(tmp_path / "nope.yaml")],
                       capture_output=True, text=True)
    assert r.returncode == 3
