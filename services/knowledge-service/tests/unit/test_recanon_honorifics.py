"""D-ML-A5-RECANON-BACKFILL — unit tests for the pure re-canon planner.

`plan_recanon` decides how pre-A5 entities (whose stored canonical kept a native
honorific) reconcile to their post-A5 canonical id. These pin the reconciliation
logic; the apply path (real Neo4j) is operator-run and not unit-tested (mirrors
the C17 backfill split).
"""

from __future__ import annotations

from app.db.migrations.recanon_honorifics import (
    EntityRow,
    plan_recanon,
    run_recanon_backfill,
)
from loreweave_extraction.canonical import entity_canonical_id

_U = "user-1"
_P = "proj-1"
_K = "character"


def _new_id(name: str) -> str:
    return entity_canonical_id(_U, _P, name, _K)


def _row(id_: str, name: str, canonical_name: str) -> EntityRow:
    return EntityRow(id=id_, user_id=_U, project_id=_P, kind=_K, name=name, canonical_name=canonical_name)


def test_clean_entity_untouched():
    # canonical_name already equals the A5 re-canon → no drift, no action.
    rows = [_row(_new_id("田中"), "田中", "田中")]
    plan = plan_recanon(rows)
    assert plan.actions == []
    assert plan.clean == 1 and plan.rekeyed == 0 and plan.merged == 0


def test_stranded_no_sibling_rekeys_to_new_id():
    # A pre-A5 "田中様" node (stored canonical kept the honorific) with no clean
    # sibling → re-key it to the canonical id of "田中".
    rows = [_row("OLD_tanaka_sama", "田中様", "田中様")]
    plan = plan_recanon(rows)
    assert plan.rekeyed == 1 and plan.merged == 0
    (action,) = plan.actions
    assert action.op == "rekey"
    assert action.from_id == "OLD_tanaka_sama"
    assert action.into_id == _new_id("田中")


def test_stranded_merges_into_existing_clean_sibling():
    # A clean post-A5 "田中" node already exists at the new id → the stranded
    # "田中様" node MERGEs into it; the sibling survives (no rekey).
    sibling_id = _new_id("田中")
    rows = [
        _row(sibling_id, "田中", "田中"),
        _row("OLD_tanaka_sama", "田中様", "田中様"),
    ]
    plan = plan_recanon(rows)
    assert plan.merged == 1 and plan.rekeyed == 0
    (action,) = plan.actions
    assert action.op == "merge"
    assert action.from_id == "OLD_tanaka_sama"
    assert action.into_id == sibling_id


def test_multiple_stranded_variants_one_survivor():
    # "田中様" and "田中さん" both re-canon to "田中"; no clean sibling → one is
    # re-keyed as survivor, the other merges into it. Deterministic survivor
    # (lowest stored id).
    rows = [
        _row("id_b_sama", "田中様", "田中様"),
        _row("id_a_san", "田中さん", "田中さん"),
    ]
    plan = plan_recanon(rows)
    assert plan.rekeyed == 1 and plan.merged == 1
    rekey = next(a for a in plan.actions if a.op == "rekey")
    merge = next(a for a in plan.actions if a.op == "merge")
    assert rekey.from_id == "id_a_san"      # lowest id wins survivor
    assert rekey.into_id == _new_id("田中")
    assert merge.from_id == "id_b_sama"
    assert merge.into_id == _new_id("田中")


def test_vietnamese_and_korean_stranded():
    rows = [
        _row("OLD_ong_nam", "ông Nam", "ông nam"),
        _row("OLD_kim_nim", "김선생님", "김선생님"),
    ]
    plan = plan_recanon(rows)
    assert plan.rekeyed == 2 and plan.merged == 0
    into = {a.into_id for a in plan.actions}
    assert _new_id("Nam") in into and _new_id("김") in into


def test_empty_canonical_skipped():
    # A degenerate entity whose name is ONLY a honorific canonicalizes to "" →
    # left untouched (can't derive an id), counted as skipped_empty.
    rows = [_row("OLD_bare", "様", "様")]
    plan = plan_recanon(rows)
    assert plan.skipped_empty == 1 and plan.actions == []


def test_plan_is_deterministic():
    rows = [
        _row("id_b_sama", "田中様", "田中様"),
        _row("id_a_san", "田中さん", "田中さん"),
        _row(_new_id("李"), "李", "李"),
    ]
    p1 = plan_recanon(rows)
    p2 = plan_recanon(rows)
    assert [(a.op, a.from_id, a.into_id) for a in p1.actions] == \
           [(a.op, a.from_id, a.into_id) for a in p2.actions]


# ── T35e: the anchor collision guard ─────────────────────────────────────────

def _anchored(id_: str, name: str, canonical_name: str, anchor: str | None) -> EntityRow:
    return EntityRow(id=id_, user_id=_U, project_id=_P, kind=_K, name=name,
                     canonical_name=canonical_name, anchor=anchor)


def test_two_DISTINCT_glossary_entities_are_never_folded_together():
    """🔴 The destructive case, measured on the dev graph before it was guarded: of 1826
    planned actions, 7 were merges and SIX would have folded a node carrying one glossary
    anchor into a node carrying a different one — 卡維嘉小姐, 精靈小姐, 魔王殿, 魔王大人.

    Honorific stripping is precisely the operation that makes two different characters
    canonicalise together: 精靈小姐 ("Miss Elf") and 精靈 are one honorific apart, and the
    glossary knows they are two entities even when the canonicaliser cannot.

    `:Entity(user_id, project_id, glossary_entity_id)` is UNIQUE, so the fold either raises or
    silently unanchors one of them — and an unanchored glossary entity is invisible in the KG
    while looking perfectly healthy in the glossary. The group is REFUSED, not merged.
    """
    rows = [
        _anchored("id-a", "精靈小姐", "精靈小姐", anchor="glossary-A"),
        _anchored("id-b", "精靈大人", "精靈大人", anchor="glossary-B"),
    ]
    # Both strip to the same canonical, so they collide on one new id.
    plan = plan_recanon(rows)
    assert plan.conflicted == 2, plan
    assert plan.actions == [], "a distinct-anchor group must produce NO action"
    assert plan.conflicts == [("id-a", "id-b")], plan.conflicts


def test_the_SAME_anchor_still_merges_normally():
    """The guard must not refuse everything. Two stranded spellings of ONE glossary entity are
    the case this migration exists for, and they still fold — otherwise the guard would trade
    a destructive bug for a silently inert migration, which the plan would report as 'ran'."""
    rows = [
        _anchored("id-a", "田中様", "田中様", anchor="glossary-A"),
        _anchored("id-b", "田中大人", "田中大人", anchor="glossary-A"),
    ]
    plan = plan_recanon(rows)
    assert plan.conflicted == 0, plan
    assert plan.actions, "same-anchor drift must still reconcile"
    assert {a.op for a in plan.actions} <= {"rekey", "merge"}


def test_an_UNANCHORED_node_does_not_block_a_merge():
    """`None` is 'no claim', not 'a different claim'. A pre-anchor node folding into an
    anchored one loses nothing — and treating None as distinct would freeze the whole legacy
    population, which is most of what this backfill is for."""
    rows = [
        _anchored("id-a", "田中様", "田中様", anchor=None),
        _anchored("id-b", "田中大人", "田中大人", anchor="glossary-A"),
    ]
    plan = plan_recanon(rows)
    assert plan.conflicted == 0, plan
    assert plan.actions, "an unanchored node must not veto reconciliation"


def test_the_LOADER_actually_feeds_the_anchor_guard():
    """🔴 The wiring, not the rule. The guard above shipped correct and DEAD: the apply path's
    Cypher never selected `glossary_entity_id`, so every `EntityRow.anchor` defaulted to None,
    the distinct-anchor set never held two members, and the guard could not fire once against
    a real graph. Unit tests that build rows by hand cannot see that — they supply the field
    the loader forgot.

    So this drives `run_recanon_backfill` through a fake session and asserts the REFUSAL
    reaches the plan. It is the difference between "the guard is right" and "the guard runs".
    """
    import asyncio

    class _Result:
        def __init__(self, rows): self._rows = rows
        def __aiter__(self):
            async def gen():
                for r in self._rows:
                    yield r
            return gen()

    rows = [
        {"id": "id-a", "user_id": _U, "project_id": _P, "kind": _K,
         "name": "精靈小姐", "canonical_name": "精靈小姐", "anchor": "glossary-A"},
        {"id": "id-b", "user_id": _U, "project_id": _P, "kind": _K,
         "name": "精靈大人", "canonical_name": "精靈大人", "anchor": "glossary-B"},
    ]

    class _Session:
        async def run(self, cypher, **kw):
            assert "glossary_entity_id" in cypher, (
                "the loader stopped selecting the anchor — the guard is dead again")
            return _Result(rows)

    plan = asyncio.run(run_recanon_backfill(_Session(), apply=False))
    assert plan.conflicted == 2, plan
    assert plan.actions == [], "the loader fed the guard but the plan still acted"


def test_the_cli_INITIALISES_the_driver_rather_than_merely_getting_it(monkeypatch):
    """The documented operator command (`python -m …recanon_honorifics`) called
    `get_neo4j_driver()` — a GETTER that raises unless the FastAPI lifespan hook
    already ran, which under `python -m` it never does. So the entry point in the
    module's own docstring could not run at all, on dry-run OR on `--apply`, and
    the figure T35 is gated on cannot have come from it.

    The apply path is `pragma: no cover (integration-only)`, which is exactly how
    this survived: nothing executed the four lines that choose the driver. This
    test drives `_cli_main` against fakes and asserts the ORDER — init before
    session, close after — so a future edit back to the getter goes red here
    instead of at 2 a.m. on an operator's terminal.
    """
    import asyncio

    from app.db.migrations import recanon_honorifics as mod

    calls: list[str] = []

    class _Session:
        async def __aenter__(self):
            calls.append("session")
            return self
        async def __aexit__(self, *a):
            return False

    async def _fake_init():
        calls.append("init")

    async def _fake_close():
        calls.append("close")

    async def _fake_run(session, *, apply):
        calls.append(f"run(apply={apply})")
        return mod.RecanonPlan()

    import app.db.neo4j as neo4j_mod
    monkeypatch.setattr(neo4j_mod, "init_neo4j_driver", _fake_init)
    monkeypatch.setattr(neo4j_mod, "close_neo4j_driver", _fake_close)
    monkeypatch.setattr(neo4j_mod, "neo4j_session", lambda **kw: _Session())
    monkeypatch.setattr(mod, "run_recanon_backfill", _fake_run)
    monkeypatch.setattr("sys.argv", ["recanon_honorifics"])

    asyncio.run(mod._cli_main())

    assert "init" in calls, (
        "the CLI never initialised the driver — it is back to calling the getter, "
        "and the operator command raises Neo4jNotConfiguredError before it reads a node"
    )
    assert calls.index("init") < calls.index("session"), (
        f"the driver must be initialised BEFORE a session is opened, got {calls}")
    assert calls[-1] == "close", (
        f"the CLI owns the driver's lifecycle and must close it, got {calls}")


def test_the_cli_closes_the_driver_even_when_the_backfill_RAISES(monkeypatch):
    """The `finally` is the point: a half-applied structural mutation is exactly
    when the driver must still be released, and a bare `await close()` after the
    `async with` would be skipped on the raise.
    """
    import asyncio

    from app.db.migrations import recanon_honorifics as mod

    calls: list[str] = []

    class _Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    async def _boom(session, *, apply):
        raise RuntimeError("merge exploded halfway")

    import app.db.neo4j as neo4j_mod
    monkeypatch.setattr(neo4j_mod, "init_neo4j_driver", lambda: _noop(calls, "init"))
    monkeypatch.setattr(neo4j_mod, "close_neo4j_driver", lambda: _noop(calls, "close"))
    monkeypatch.setattr(neo4j_mod, "neo4j_session", lambda **kw: _Session())
    monkeypatch.setattr(mod, "run_recanon_backfill", _boom)
    monkeypatch.setattr("sys.argv", ["recanon_honorifics"])

    try:
        asyncio.run(mod._cli_main())
    except RuntimeError:
        pass
    else:
        raise AssertionError("the CLI swallowed a failed backfill")

    assert "close" in calls, (
        "the driver leaked when the backfill raised — the `finally` is gone")


async def _noop(sink: list[str], tag: str) -> None:
    sink.append(tag)
