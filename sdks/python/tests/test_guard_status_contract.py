"""The check-status vocabulary is a POLYGLOT contract, and Python is its SSOT.

`CheckStatus` existed only in Python, so the rule it carries — *a guard that could not run must
not be shaped like one that ran and found nothing* — stopped at the language boundary. The two
worst false-greens this project's red team found were both on the other side of it: a Go sweep
whose failed chunk takes the same branch as "no drift", and a Rust narration whose fallback
count nothing obliges a consumer to read.

Publishing the vocabulary is what lets a Go or Rust mirror be CHECKED rather than copied. This
test is the Python half of that lock: the committed contract must equal the enum, so a member
added or renamed here reds until the contract is regenerated, and the other languages' drift
tests then red against the new contract.

Regenerate: `WRITE_GUARD_STATUS_CONTRACT=1 python -m pytest sdks/python/tests/test_guard_status_contract.py`
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from loreweave_guard import CheckStatus, _RANK, worst

_CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "guard-status.contract.json"


def _built() -> dict:
    return {
        "statuses": [s.value for s in CheckStatus],
        "rank_worst_first": [s.value for s in _RANK],
        "filtered_before_ranking": ["not_applicable"],
    }


def test_the_committed_contract_matches_the_enum():
    built = _built()
    if os.environ.get("WRITE_GUARD_STATUS_CONTRACT") == "1":
        doc = json.loads(_CONTRACT.read_text(encoding="utf-8"))
        doc.update(built)
        _CONTRACT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        pytest.skip("regenerated contracts/guard-status.contract.json")

    on_disk = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    for key, want in built.items():
        assert on_disk[key] == want, (
            f"{key} drifted from loreweave_guard. Regenerate with "
            f"WRITE_GUARD_STATUS_CONTRACT=1, then update every language that mirrors it."
        )


def test_the_rank_covers_every_status_that_can_be_ranked():
    """`worst()` falls through to CHECKED when nothing in `_RANK` matches — so a member added
    to the enum and forgotten in `_RANK` would silently report as the BEST outcome. That is the
    direction that hides a failure, which is why it is pinned rather than left to the fallback.
    """
    rankable = set(CheckStatus) - {CheckStatus.NOT_APPLICABLE}
    assert set(_RANK) == rankable, f"unranked: {sorted(s.value for s in rankable - set(_RANK))}"


def test_worst_actually_prefers_the_worse_of_two():
    """A control for the ordering the contract publishes. Without it, a `_RANK` reversed by a
    bad edit would still satisfy the coverage assertion above."""
    assert worst(["checked", "degraded"]) is CheckStatus.DEGRADED
    assert worst(["degraded", "failed"]) is CheckStatus.FAILED
    assert worst(["checked", "checked"]) is CheckStatus.CHECKED
    # …and the filter: out-of-scope must not drag the headline, nor invent one.
    assert worst(["not_applicable", "checked"]) is CheckStatus.CHECKED
    assert worst(["not_applicable"]) is CheckStatus.NOT_APPLICABLE


def test_no_language_may_invent_a_member_the_contract_does_not_carry():
    """States the direction a mirror test in another language must assert: its constants are a
    SUBSET of `statuses`. A Go file inventing `"partial"` would render as a status nobody can
    interpret, which is the closed-set defect the Frontend-Tool Contract exists to prevent."""
    on_disk = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    assert set(on_disk["statuses"]) == {s.value for s in CheckStatus}
