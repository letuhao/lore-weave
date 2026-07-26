"""24 H1.3 — the plan-overlay aggregate (read surface #3).

Two layers, no DB:
  • ``_build_overlay`` PURE-function tests — response shape, arc-subtree count
    rollup, the ~50-ref TOTAL cap + ``refs_capped``, empty-book → all-empty.
  • Route tests over a bare app that includes ONLY this slice's router (main.py
    registration is the orchestrator's integrate step) with a fake repo + a
    stub grant → prove the VIEW gate (404/403) and JSON wiring.

The live SQL (boundary anchor / scene-avg tension / lockfile join) is exercised by
the orchestrator's combined DB suite, not here (shared-dev-DB rule).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.plan_overlay import (
    _REFS_CAP,
    _build_overlay,
    get_plan_overlay_repo,
    router,
)
from app.services.coverage import Coverage

USER = UUID("00000000-0000-0000-0000-0000000000aa")
BOOK = UUID("00000000-0000-0000-0000-0000000000cc")


def _cov(**kw) -> Coverage:
    """The default coverage for builder tests that aren't about the tray. NOTE the
    builder takes this REQUIRED (no default): a default would let a future caller
    silently ship an empty tray again — the exact bug A1 fixes."""
    return Coverage(**kw)


# ── pure builder: shape ───────────────────────────────────────────────────────


def test_empty_book_returns_all_empty_structure():
    out = _build_overlay([], [], [], [], [], _cov())
    assert out == {
        "problems": {"by_node": {}, "refs_capped": False},
        "tension_rollup": [],
        "motif_chips": [],
        "unplanned_chapters": [],
        "unplanned_count": 0,
        "unplanned_capped": False,
    }
    # a stable contract for the FE: on the happy path these keys always ship, and
    # `warnings` never does (its presence IS the degraded signal).
    assert "warnings" not in out


def test_canon_and_thread_counts_and_refs_on_the_leaf_node():
    chap = uuid4()
    rule = uuid4()
    thread = uuid4()
    canon = [{"rule_id": rule, "rule_text": "Ha cannot fly before ch 40",
              "node_id": chap, "arc_id": None}]
    threads = [{"thread_id": thread, "summary": "who poisoned the well?",
                "trigger": "", "thread_kind": "question", "node_id": chap,
                "node_kind": "chapter", "arc_id": None}]
    out = _build_overlay(canon, threads, [], [], [], _cov())
    entry = out["problems"]["by_node"][str(chap)]
    assert entry["canon"] == 1
    assert entry["threads_open"] == 1
    # both refs land on the leaf node, with a short human line + the right kind/id
    kinds = {r["kind"]: r for r in entry["refs"]}
    assert kinds["canon"]["id"] == str(rule)
    assert kinds["canon"]["line"] == "Ha cannot fly before ch 40"
    assert kinds["thread"]["id"] == str(thread)
    assert kinds["thread"]["line"] == "who poisoned the well?"
    assert out["problems"]["refs_capped"] is False


def test_thread_line_falls_back_trigger_then_kind():
    chap = uuid4()
    threads = [{"thread_id": uuid4(), "summary": "", "trigger": "the locked door",
                "thread_kind": "foreshadow", "node_id": chap, "arc_id": None}]
    out = _build_overlay([], threads, [], [], [], _cov())
    (ref,) = out["problems"]["by_node"][str(chap)]["refs"]
    assert ref["line"] == "the locked door"  # summary empty → trigger


def test_unanchored_thread_is_skipped():
    # opened_at_node was SET NULL (node deleted) → no by_node attribution.
    threads = [{"thread_id": uuid4(), "summary": "orphan", "trigger": "",
                "thread_kind": "promise", "node_id": None, "arc_id": None}]
    out = _build_overlay([], threads, [], [], [], _cov())
    assert out["problems"]["by_node"] == {}


def test_line_is_single_line_and_truncated():
    chap = uuid4()
    long = "A" * 400 + "\n\t  tail"
    out = _build_overlay(
        [{"rule_id": uuid4(), "rule_text": long, "node_id": chap, "arc_id": None}],
        [], [], [], [], _cov(),
    )
    line = out["problems"]["by_node"][str(chap)]["refs"][0]["line"]
    assert "\n" not in line and "\t" not in line
    assert len(line) <= 160 and line.endswith("…")


# ── pure builder: arc-subtree rollup ──────────────────────────────────────────


def test_counts_roll_up_to_arc_and_saga_but_refs_stay_on_leaf():
    saga, arc, chap = uuid4(), uuid4(), uuid4()
    parents = [
        {"id": saga, "parent_id": None},
        {"id": arc, "parent_id": saga},
    ]
    canon = [{"rule_id": uuid4(), "rule_text": "x", "node_id": chap, "arc_id": arc}]
    out = _build_overlay(canon, [], parents, [], [], _cov())
    by = out["problems"]["by_node"]
    # leaf + arc + saga each count 1 (subtree rollup)
    assert by[str(chap)]["canon"] == 1
    assert by[str(arc)]["canon"] == 1
    assert by[str(saga)]["canon"] == 1
    # refs live only on the leaf; the arc/saga carry the count, not duplicated refs
    assert len(by[str(chap)]["refs"]) == 1
    assert by[str(arc)]["refs"] == []
    assert by[str(saga)]["refs"] == []


def test_two_rules_in_one_arc_sum_at_the_arc():
    arc, c1, c2 = uuid4(), uuid4(), uuid4()
    parents = [{"id": arc, "parent_id": None}]
    canon = [
        {"rule_id": uuid4(), "rule_text": "a", "node_id": c1, "arc_id": arc},
        {"rule_id": uuid4(), "rule_text": "b", "node_id": c2, "arc_id": arc},
    ]
    out = _build_overlay(canon, [], parents, [], [], _cov())
    by = out["problems"]["by_node"]
    assert by[str(arc)]["canon"] == 2  # rollup sums the subtree
    assert by[str(c1)]["canon"] == 1 and by[str(c2)]["canon"] == 1


def test_rollup_is_cycle_safe():
    # pathological self/mutual parent cycle must not hang or over-count.
    a, b, chap = uuid4(), uuid4(), uuid4()
    parents = [{"id": a, "parent_id": b}, {"id": b, "parent_id": a}]
    canon = [{"rule_id": uuid4(), "rule_text": "x", "node_id": chap, "arc_id": a}]
    out = _build_overlay(canon, [], parents, [], [], _cov())
    by = out["problems"]["by_node"]
    assert by[str(a)]["canon"] == 1 and by[str(b)]["canon"] == 1  # each once


# ── pure builder: the ~50-ref TOTAL cap ───────────────────────────────────────


def test_refs_capped_at_total_but_counts_stay_exact():
    # more canon anchors than the cap, spread across distinct nodes.
    n = _REFS_CAP + 25
    canon = [
        {"rule_id": uuid4(), "rule_text": f"rule {i}", "node_id": uuid4(), "arc_id": None}
        for i in range(n)
    ]
    out = _build_overlay(canon, [], [], [], [], _cov())
    total_refs = sum(len(v["refs"]) for v in out["problems"]["by_node"].values())
    total_canon = sum(v["canon"] for v in out["problems"]["by_node"].values())
    assert total_refs == _REFS_CAP          # refs truncated at the cap
    assert out["problems"]["refs_capped"] is True
    assert total_canon == n                 # counts stay EXACT (never truncated)


def test_exactly_at_cap_does_not_flag_capped():
    canon = [
        {"rule_id": uuid4(), "rule_text": "r", "node_id": uuid4(), "arc_id": None}
        for _ in range(_REFS_CAP)
    ]
    out = _build_overlay(canon, [], [], [], [], _cov())
    assert sum(len(v["refs"]) for v in out["problems"]["by_node"].values()) == _REFS_CAP
    assert out["problems"]["refs_capped"] is False  # filled exactly, not exceeded


# ── pure builder: tension rollup + motif chips ────────────────────────────────


def test_tension_rollup_passthrough_shape():
    c1, c2 = uuid4(), uuid4()
    rows = [
        {"chapter_node_id": c1, "story_order": 12, "tension": 65},
        {"chapter_node_id": c2, "story_order": None, "tension": 40},
    ]
    out = _build_overlay([], [], [], rows, [], _cov())
    assert out["tension_rollup"] == [
        {"chapter_node_id": str(c1), "story_order": 12, "tension": 65},
        {"chapter_node_id": str(c2), "story_order": None, "tension": 40},
    ]


def test_motif_chips_shape_pinned_vs_live():
    node, motif = uuid4(), uuid4()
    rows = [{"node_ref": node, "motif_id": motif, "pinned_version": 3,
             "title": "The red thread", "live_version": 4}]
    out = _build_overlay([], [], [], [], rows, _cov())
    assert out["motif_chips"] == [{
        "node_ref": str(node), "motif_id": str(motif),
        "title": "The red thread", "pinned_version": 3, "live_version": 4,
    }]


# ── pure builder: the PH21 tray (28 OQ-4's shared coverage diff) ──────────────


def test_unplanned_tray_carries_the_coverage_diff():
    ch = uuid4()
    cov = Coverage(
        unplanned=[{"chapter_id": str(ch), "title": "Chương 41", "sort_order": 41}],
        unplanned_count=1,
    )
    out = _build_overlay([], [], [], [], [], cov)
    assert out["unplanned_chapters"] == [
        {"chapter_id": str(ch), "title": "Chương 41", "sort_order": 41},
    ]
    assert out["unplanned_count"] == 1
    assert out["unplanned_capped"] is False


def test_degraded_coverage_OMITS_the_key_and_warns():
    """absent ≠ zero. If the manuscript spine can't be read we must NOT ship
    `unplanned_chapters: []` — that renders as 'nothing unplanned', a green-looking
    lie about an unknown (24 OQ-8's law, applied to the tray)."""
    cov = Coverage(degraded=True, warning="spine unreadable")
    out = _build_overlay([], [], [], [], [], cov)
    assert "unplanned_chapters" not in out
    assert "unplanned_count" not in out
    assert out["warnings"] == ["spine unreadable"]


# ── route: VIEW gate + wiring over a bare app (no main.py) ─────────────────────


class _FakeRepo:
    def __init__(self, canon=None, threads=None, parents=None, tension=None, motifs=None):
        self._canon = canon or []
        self._threads = threads or []
        self._parents = parents or []
        self._tension = tension or []
        self._motifs = motifs or []
        self.book_ids: list[UUID] = []

    async def fetch_canon_anchors(self, book_id):
        self.book_ids.append(book_id)
        return self._canon

    async def fetch_open_threads(self, book_id):
        return self._threads

    async def fetch_structure_parents(self, book_id):
        return self._parents

    async def fetch_tension_rollup(self, book_id):
        return self._tension

    async def fetch_motif_chips(self, book_id):
        return self._motifs


class _FakeOutline:
    """Only the coverage diff's half of OutlineRepo."""

    def __init__(self, planned: set[UUID] | None = None):
        self._planned = planned or set()

    async def planned_chapter_ids(self, book_id: UUID) -> set[UUID]:
        return self._planned


class _FakeBook:
    """book-service's chapter spine; `raises` simulates the service being down."""

    def __init__(self, chapters=None, raises: Exception | None = None):
        self._chapters = chapters or []
        self._raises = raises

    async def list_chapters(self, book_id, bearer, *, limit=2000, raise_on_404=False):
        if self._raises:
            raise self._raises
        return self._chapters


def _make_client(repo: _FakeRepo, level, *, outline=None, book=None):
    """Bare app with ONLY this slice's router (main.py wiring is the integrate
    step) + overridden gate/current-user/repo/coverage deps."""
    from app.deps import get_book_client_dep, get_grant_client_dep, get_outline_repo
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return level

        async def resolve_access(self, book_id, user_id):
            return level, "active"

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "test-bearer"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_plan_overlay_repo] = lambda: repo
    app.dependency_overrides[get_outline_repo] = lambda: outline or _FakeOutline()
    app.dependency_overrides[get_book_client_dep] = lambda: book or _FakeBook()
    return TestClient(app)


def test_route_returns_overlay_for_a_viewer():
    from app.grant_client import GrantLevel

    chap = uuid4()
    repo = _FakeRepo(
        canon=[{"rule_id": uuid4(), "rule_text": "no flight before 40",
                "node_id": chap, "arc_id": None}],
        tension=[{"chapter_node_id": chap, "story_order": 1, "tension": 55}],
    )
    c = _make_client(repo, GrantLevel.VIEW)
    r = c.get(f"/v1/composition/books/{BOOK}/plan-overlay")
    assert r.status_code == 200
    body = r.json()
    assert body["problems"]["by_node"][str(chap)]["canon"] == 1
    assert body["tension_rollup"][0]["tension"] == 55
    assert body["unplanned_chapters"] == []  # no book chapters at all → nothing unplanned
    assert repo.book_ids == [BOOK]  # gate resolved → repo keyed on the path book


def test_route_serves_the_real_coverage_diff():
    """The whole point of A1: the tray is now COMPUTED, not hardcoded `[]`.
    Two book chapters, one of them planned ⇒ exactly one unplanned."""
    from app.grant_client import GrantLevel

    planned_ch, orphan_ch = uuid4(), uuid4()
    book = _FakeBook(chapters=[
        {"chapter_id": str(planned_ch), "title": "Ch 1", "sort_order": 1},
        {"chapter_id": str(orphan_ch), "title": "Chương 41", "sort_order": 41},
    ])
    c = _make_client(
        _FakeRepo(), GrantLevel.VIEW,
        outline=_FakeOutline(planned={planned_ch}), book=book,
    )
    body = c.get(f"/v1/composition/books/{BOOK}/plan-overlay").json()
    assert body["unplanned_chapters"] == [
        {"chapter_id": str(orphan_ch), "title": "Chương 41", "sort_order": 41},
    ]
    assert body["unplanned_count"] == 1


def test_route_omits_the_tray_when_book_service_is_down():
    """Degraded ⇒ the key is ABSENT + a warning — never `[]`. A zero here would
    render an empty tray over an UNKNOWN (absent ≠ zero)."""
    from app.clients.book_client import BookClientError
    from app.grant_client import GrantLevel

    c = _make_client(
        _FakeRepo(), GrantLevel.VIEW,
        book=_FakeBook(raises=BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")),
    )
    r = c.get(f"/v1/composition/books/{BOOK}/plan-overlay")
    assert r.status_code == 200  # the Hub still paints; only the tray is unknown
    body = r.json()
    assert "unplanned_chapters" not in body
    assert body["warnings"] and "not zero" in body["warnings"][0]


def test_route_404_when_no_grant():
    from app.grant_client import GrantLevel

    c = _make_client(_FakeRepo(), GrantLevel.NONE)
    r = c.get(f"/v1/composition/books/{BOOK}/plan-overlay")
    assert r.status_code == 404  # OwnershipError → uniform no-oracle 404


def test_route_403_when_grant_below_view():
    # A grant strictly below VIEW is InsufficientGrant → 403. Skips if the enum
    # has no sub-VIEW tier (VIEW is already the floor).
    from app.grant_client import GrantLevel

    below = [lvl for lvl in GrantLevel if not lvl.at_least(GrantLevel.VIEW)
             and lvl is not GrantLevel.NONE]
    if not below:
        pytest.skip("no grant tier below VIEW in this enum")
    c = _make_client(_FakeRepo(), below[0])
    r = c.get(f"/v1/composition/books/{BOOK}/plan-overlay")
    assert r.status_code == 403
