"""B3 (BA2 fail-loud) — `_assert_lift_applied` refuses to boot when the DB carries the
package re-key but not the arc lift, so post-lift-assuming code can never silently serve an
unlifted DB (arcs still in outline_node, the 4-kind CHECK still standing). Q2-sealed.
"""
from __future__ import annotations

import pytest

from app.db.migrate import _assert_lift_applied


class _FakeConn:
    def __init__(self, markers):
        self._markers = markers

    async def fetch(self, _query, _args):
        return [{"marker": m} for m in self._markers]


@pytest.mark.asyncio
async def test_rekeyed_but_unlifted_refuses_to_boot():
    with pytest.raises(RuntimeError, match="arc lift .*has NOT run"):
        await _assert_lift_applied(_FakeConn({"pkg_rekey_v1"}))


@pytest.mark.asyncio
async def test_both_markers_boots():
    await _assert_lift_applied(_FakeConn({"pkg_rekey_v1", "pkg_lift_v1"}))  # no raise


@pytest.mark.asyncio
async def test_neither_marker_boots():
    # A truly pre-rekey DB (should not happen — the assertion runs after run_package_rekey —
    # but the guard must not fire on "no package model at all").
    await _assert_lift_applied(_FakeConn(set()))  # no raise
