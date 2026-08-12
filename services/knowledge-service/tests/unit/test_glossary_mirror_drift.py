"""The glossary→KG mirror detector (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).

Every test here exists because the corresponding mistake produces a number that LOOKS
like a measurement. A detector that miscounts does not crash — it reports a healthy
mirror, or an un-clearable alarm, and either way it is believed.
"""
from __future__ import annotations

import pytest

from app.mirror.glossary_mirror import detect_mirror_drift
from app.mirror.predicate import is_mirrorable


class _FakeGlossary:
    """Truth side. `rows` is exactly what the mirror-truth endpoint returns."""

    def __init__(self, rows, truncated: bool = False, unreachable: bool = False):
        self._rows = rows
        self._truncated = truncated
        self._unreachable = unreachable
        self.calls: list = []

    async def list_mirror_truth_ids(self, book_id, **kw):
        self.calls.append(book_id)
        if self._unreachable:
            return None
        return list(self._rows), self._truncated


class _FakeStore:
    """Graph side. Holds the glossary ids the KG actually has."""

    def __init__(self, present: set[str]):
        self._present = present
        self.asked: list[str] = []

    async def neighborhood(self, *, user_id, glossary_entity_id, project_id, rel_cap=50):
        self.asked.append(glossary_entity_id)
        return object() if glossary_entity_id in self._present else None


@pytest.fixture
def patch_store(monkeypatch):
    def _install(store):
        import app.adapters.graph_store_provider as provider
        monkeypatch.setattr(provider, "get_graph_store", lambda session: store)
    return _install


def _row(entity_id: str, *, has_name: bool = True, kind: str = "character") -> dict:
    return {"entity_id": entity_id, "kind_code": kind, "has_name": has_name}


IDS = {"p": "11111111-1111-1111-1111-111111111111",
       "b": "22222222-2222-2222-2222-222222222222",
       "u": "33333333-3333-3333-3333-333333333333"}


async def _detect(glossary, store, patch_store, **kw):
    patch_store(store)
    return await detect_mirror_drift(
        session=object(), glossary_client=glossary,
        project_id=IDS["p"], book_id=IDS["b"], user_id=IDS["u"], **kw,
    )


@pytest.mark.asyncio
async def test_missing_is_the_anti_join_not_a_count_difference(patch_store):
    """The store holds `ghost`, which the truth set does not. Comparing the two stores'
    COUNTS — the obvious implementation, and how the 48-vs-26 baseline was first taken —
    nets that extra against a real loss and reports 1. The per-id anti-join reports 2,
    because it asks about each truth id individually and a ghost cannot cancel one."""
    glossary = _FakeGlossary([_row("a"), _row("b"), _row("c")])
    store = _FakeStore({"a", "ghost"})

    drift = await _detect(glossary, store, patch_store)

    assert drift.missing == 2, drift.as_dict()
    assert sorted(drift.missing_ids) == ["b", "c"]
    assert drift.mirrored == 1


@pytest.mark.asyncio
async def test_nameless_rows_are_not_missing(patch_store):
    """The handler skips an event with no name BY DESIGN — a freshly-created draft emits
    before its name attribute is filled. Counting those as lost is an alarm that can
    never be cleared, on a metric whose whole contract is that it reaches zero."""
    glossary = _FakeGlossary([_row("a"), _row("nameless", has_name=False)])
    store = _FakeStore({"a"})

    drift = await _detect(glossary, store, patch_store)

    assert drift.missing == 0, drift.as_dict()
    assert drift.not_mirrorable == 1
    assert drift.truth_total == 2 and drift.mirrorable == 1
    assert "nameless" not in store.asked, "a row the handler declines was still probed"


@pytest.mark.asyncio
async def test_the_handler_actually_CALLS_the_shared_predicate(monkeypatch):
    """Not a style point. If the handler keeps its own copy of the skip rule, the day
    either changes the detector reports rows as lost that the handler is deliberately
    declining to mirror — an alarm nobody can clear.

    ⚠️ This asserts the predicate is CONSULTED, not merely imported. The first version of
    this test compared `handlers.is_mirrorable is is_mirrorable`, and reverting the call
    site to an inline `if not name or not kind` left it green: the import was still
    there. A spy that must be reached is the only version with teeth.
    """
    import app.events.handlers as handlers
    from app.events.dispatcher import EventData

    seen: list[tuple] = []

    def _spy(name, kind):
        seen.append((name, kind))
        return False          # force the skip, whatever the payload says

    monkeypatch.setattr(handlers, "is_mirrorable", _spy)

    class _Pool:
        def __init__(self):
            self.queried = False

        async def fetchrow(self, *a, **kw):
            self.queried = True
            return None

    pool = _Pool()
    await handlers.handle_glossary_entity_updated(
        EventData(
            stream="loreweave:events:glossary", message_id="m1",
            event_type="glossary.entity_updated", aggregate_id=IDS["b"],
            payload={"book_id": IDS["b"], "glossary_entity_id": IDS["b"],
                     # doc-language-gate: ok -- real book entity name (the live mirror is Vietnamese)
                     "name": "Lâm Diệp", "kind": "character"},
            source="test", raw={},
        ),
        pool=pool,
    )

    assert seen == [("Lâm Diệp", "character")], (  # doc-language-gate: ok -- as above
        "the handler did not consult is_mirrorable — it is deciding for itself"
    )
    assert not pool.queried, (
        "is_mirrorable said no and the handler carried on anyway"
    )


@pytest.mark.asyncio
async def test_unreachable_truth_reports_nothing_rather_than_everything(patch_store):
    """An empty truth list and an unreachable glossary are indistinguishable in a naive
    implementation, and they mean opposite things: one is a clean book, the other is an
    outage that would render as "every entity is missing"."""
    glossary = _FakeGlossary([], unreachable=True)
    store = _FakeStore(set())

    assert await _detect(glossary, store, patch_store) is None


@pytest.mark.asyncio
async def test_a_capped_walk_says_it_was_capped(patch_store):
    """A silent cap under-reports the divergence, and an under-reported divergence looks
    exactly like a healthy mirror."""
    glossary = _FakeGlossary([_row(str(i)) for i in range(10)])
    store = _FakeStore(set())

    drift = await _detect(glossary, store, patch_store, entity_cap=4)

    assert drift.truncated is True
    assert drift.mirrorable == 4 and drift.missing == 4
    assert len(store.asked) == 4, "the cap did not actually bound the graph reads"


@pytest.mark.asyncio
async def test_truncated_truth_pages_propagate(patch_store):
    """The cap can also bite on the truth side — max_pages in the client. Same rule."""
    glossary = _FakeGlossary([_row("a")], truncated=True)
    drift = await _detect(glossary, _FakeStore({"a"}), patch_store)
    assert drift.truncated is True and drift.missing == 0


@pytest.mark.asyncio
async def test_orphans_are_reported_as_unmeasured_not_as_zero(patch_store):
    """The other anti-join direction needs a bulk graph enumeration the port does not
    have. `orphans: 0` from a check that never ran is the accounting artefact this plan
    exists to prevent."""
    drift = await _detect(_FakeGlossary([_row("a")]), _FakeStore({"a"}), patch_store)
    assert drift.as_dict()["orphans"] != 0
    assert "not measured" in str(drift.as_dict()["orphans"])


@pytest.mark.parametrize(
    "name,kind,expected",
    [
        ("Lâm Diệp", "character", True),   # doc-language-gate: ok -- real book entity name
        ("", "character", False),
        (None, "character", False),
        ("   ", "character", False),   # whitespace is not a name
        ("Lâm Diệp", "", False),           # doc-language-gate: ok -- real book entity name
        ("Lâm Diệp", None, False),         # doc-language-gate: ok -- real book entity name
    ],
)
def test_is_mirrorable(name, kind, expected):
    assert is_mirrorable(name, kind) is expected
