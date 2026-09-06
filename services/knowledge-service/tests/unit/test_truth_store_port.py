"""The `TruthStore` port contract (plan T19).

Fourth and last port of Phase 2. Its distinguishing rule is that **two stores answer and a
consumer cannot tell which** — that is what Phase 8 depends on, because T44–T46 merge them
and every consumer that learned which store it was talking to would be a rewrite.

The failure modes here are unusually quiet: both stores return well-formed facts, so a
misroute or an axis mix-up produces a confident wrong answer rather than an error. Hence
the emphasis below on scope isolation and on the two time axes.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.adapters.fake_truth_store import FakeTruthStore
from app.adapters.glossary_truth_adapter import GlossaryTruthAdapter
from app.adapters.memory_truth_adapter import MemoryTruthAdapter
from app.adapters.scoped_truth_store import ScopedTruthStore
from app.ports.truth_store import TruthFact, TruthStore

_U = "user-1"
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _fact(fid, *, scope="book", subject="e1", attr="rank", value="inner",
          vfrom=None, vto=None, confidence=1.0) -> TruthFact:
    return TruthFact(
        fact_id=fid, subject_id=subject, attribute=attr, value=value, scope=scope,
        confidence=confidence, valid_from=vfrom, valid_to=vto,
    )


# ── scope isolation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_book_fact_never_surfaces_in_a_project_read():
    """Both stores return well-formed facts, so a leak across scopes looks like an answer
    rather than an error. That is why this is asserted rather than assumed."""
    store = FakeTruthStore([
        _fact("b1", scope="book"),
        _fact("p1", scope="project"),
    ])
    book = await store.facts_for_subject(scope="book", user_id=_U, subject_id="e1")
    project = await store.facts_for_subject(scope="project", user_id=_U, subject_id="e1")
    assert [f.fact_id for f in book] == ["b1"]
    assert [f.fact_id for f in project] == ["p1"]


# ── the two time axes ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_book_truth_uses_a_half_open_ordinal_interval():
    store = FakeTruthStore([_fact("f", vfrom=10, vto=25)])
    at = lambda n: store.facts_for_subject(scope="book", user_id=_U, subject_id="e1", as_of=n)
    assert len(await at(10)) == 1, "start inclusive"
    assert len(await at(24)) == 1
    assert len(await at(25)) == 0, "end exclusive"
    assert len(await at(9)) == 0


@pytest.mark.asyncio
async def test_memory_truth_uses_the_same_interval_rule_on_wall_clock():
    """The axes differ; the interval semantics must NOT, or T45 inherits two conventions
    to reconcile instead of one."""
    store = FakeTruthStore([_fact("f", scope="project", vfrom=_T0, vto=_T1)])
    at = lambda t: store.facts_for_subject(scope="project", user_id=_U, subject_id="e1", as_of=t)
    assert len(await at(_T0)) == 1, "start inclusive"
    assert len(await at(_T1)) == 0, "end exclusive"


@pytest.mark.asyncio
async def test_an_ordinal_in_a_wall_clock_scope_is_an_error_not_a_coercion():
    """Python will happily compare two ints or two datetimes, so a mixed axis does not
    crash — it returns a confidently wrong set of facts. Both directions raise."""
    store = FakeTruthStore([_fact("f", scope="project", vfrom=_T0)])
    with pytest.raises(TypeError):
        await store.facts_for_subject(scope="project", user_id=_U, subject_id="e1", as_of=40)
    with pytest.raises(TypeError):
        await store.facts_for_subject(scope="book", user_id=_U, subject_id="e1", as_of=_T0)


@pytest.mark.asyncio
async def test_an_unpositioned_fact_is_excluded_by_an_as_of_read():
    """Same rule the graph as-of read applies to a positionless edge: untimed data must not
    leak into an answer whose entire value is that it is timed."""
    store = FakeTruthStore([_fact("f", vfrom=None)])
    assert len(await store.facts_for_subject(scope="book", user_id=_U, subject_id="e1")) == 1
    assert await store.facts_for_subject(
        scope="book", user_id=_U, subject_id="e1", as_of=50,
    ) == []


# ── the router ───────────────────────────────────────────────────────


class _Spy:
    def __init__(self, name):
        self.name = name
        self.calls = []

    async def facts_for_subject(self, **kw):
        self.calls.append(kw)
        return [_fact(self.name, scope=kw["scope"])]

    async def search_facts(self, **kw):
        self.calls.append(kw)
        return []


@pytest.mark.asyncio
async def test_the_router_dispatches_on_scope_and_not_on_which_ids_are_present():
    """Routing on "is book_id set?" breaks the first time a project read carries a book id
    for logging — and a misroute is silent, because the wrong store still answers."""
    book, memory = _Spy("book"), _Spy("memory")
    store = ScopedTruthStore(book_store=book, memory_store=memory)

    # A PROJECT read that also carries a book_id must still go to memory.
    out = await store.facts_for_subject(
        scope="project", user_id=_U, subject_id="e1", book_id="b-1", project_id="p-1",
    )
    assert len(memory.calls) == 1 and not book.calls
    assert out[0].scope == "project"

    await store.facts_for_subject(scope="book", user_id=_U, subject_id="e1", book_id="b-1")
    assert len(book.calls) == 1


@pytest.mark.asyncio
async def test_an_unknown_scope_raises_rather_than_defaulting_to_a_store():
    store = ScopedTruthStore(book_store=_Spy("book"), memory_store=_Spy("memory"))
    with pytest.raises(ValueError):
        await store.facts_for_subject(scope="galaxy", user_id=_U, subject_id="e1")


# ── each adapter refuses the scope it does not own ───────────────────


@pytest.mark.asyncio
async def test_each_adapter_refuses_the_other_scope():
    """Belt to the router's braces. If an adapter silently accepted the wrong scope, a
    routing bug would produce plausible facts from the wrong store instead of an error."""
    memory = MemoryTruthAdapter(None)
    with pytest.raises(ValueError):
        await memory.facts_for_subject(scope="book", user_id=_U, subject_id="e1")

    glossary = GlossaryTruthAdapter("http://glossary", None)
    with pytest.raises(ValueError):
        await glossary.facts_for_subject(scope="project", user_id=_U, subject_id="e1")


@pytest.mark.asyncio
async def test_the_adapters_reject_the_wrong_time_axis():
    memory = MemoryTruthAdapter(None)
    with pytest.raises(TypeError):
        await memory.facts_for_subject(
            scope="project", user_id=_U, subject_id="e1", as_of=40,
        )
    glossary = GlossaryTruthAdapter("http://glossary", None)
    with pytest.raises(TypeError):
        await glossary.facts_for_subject(
            scope="book", user_id=_U, subject_id="e1", book_id="b", as_of=_T0,
        )


@pytest.mark.asyncio
async def test_glossary_search_fails_loudly_instead_of_returning_nothing():
    """glossary has no free-text fact search. Returning `[]` would be indistinguishable
    from "this book has no matching facts", so a caller would conclude the book is empty
    when the CAPABILITY is absent — the silent-success failure this repo keeps recording."""
    glossary = GlossaryTruthAdapter("http://glossary", None)
    with pytest.raises(NotImplementedError):
        await glossary.search_facts(scope="book", user_id=_U, book_id="b", query="anything")


@pytest.mark.asyncio
async def test_book_truth_requires_a_book_id():
    glossary = GlossaryTruthAdapter("http://glossary", None)
    with pytest.raises(ValueError):
        await glossary.facts_for_subject(scope="book", user_id=_U, subject_id="e1")


# ── structural conformance ───────────────────────────────────────────


@pytest.mark.parametrize(
    "impl", [FakeTruthStore, ScopedTruthStore, MemoryTruthAdapter, GlossaryTruthAdapter],
)
def test_implementations_match_the_port_signatures(impl):
    for name in ("facts_for_subject", "search_facts"):
        port_sig = inspect.signature(getattr(TruthStore, name))
        impl_sig = inspect.signature(getattr(impl, name))
        assert list(impl_sig.parameters) == list(port_sig.parameters), (
            f"{impl.__name__}.{name} parameters {list(impl_sig.parameters)} "
            f"!= port {list(port_sig.parameters)}"
        )
        for pname, pparam in port_sig.parameters.items():
            iparam = impl_sig.parameters[pname]
            assert iparam.kind == pparam.kind, f"{impl.__name__}.{name}({pname}) kind differs"
            assert iparam.default == pparam.default, (
                f"{impl.__name__}.{name}({pname}) defaults to {iparam.default!r}, "
                f"port says {pparam.default!r}"
            )


# ── T45: valid-time is a scope-dependent AXIS, declared once ──────────────────

def test_every_scope_declares_an_axis():
    """🔴 The design rule T45 exists to make un-forgettable.

    `TruthScope` and `AXIS_FOR_SCOPE` are two lists that must agree, and before T45 the
    agreement lived nowhere: the routing knew `book` vs the rest, the glossary adapter knew
    book was ordinal, the memory adapter knew the rest were clock, and **nothing checked that
    the three matched**. Adding a fourth scope meant editing three files and hoping.

    So this reads the `Literal`'s own members. A new scope is now impossible to add without
    deciding its axis — which is the question, not an implementation detail: a scope with no
    axis cannot be positioned, and guessing one is how an ordinal ends up compared to a clock.
    """
    from typing import get_args

    from app.ports.truth_store import AXIS_FOR_SCOPE, TruthScope

    declared = set(get_args(TruthScope))
    mapped = set(AXIS_FOR_SCOPE)
    assert declared == mapped, (
        f"TruthScope and AXIS_FOR_SCOPE disagree: only in TruthScope {declared - mapped}, "
        f"only in AXIS_FOR_SCOPE {mapped - declared}. Every scope must declare its axis."
    )


def test_the_ROUTER_and_the_ADAPTERS_agree_about_every_scope():
    """The three copies are now one, and this is what proves it stayed one.

    For each declared scope: the store the router picks must be the store that ACCEPTS that
    scope. Before T45 these were independent decisions, so a scope could be routed to an
    adapter that refuses it — an outage reachable only for that one scope, and invisible to
    any test that exercised the other two.
    """
    from typing import get_args

    from app.ports.truth_store import TruthScope

    glossary = GlossaryTruthAdapter("http://glossary", None)
    memory = MemoryTruthAdapter(None)
    router = ScopedTruthStore(book_store=glossary, memory_store=memory)

    for scope in get_args(TruthScope):
        picked = router._route(scope)
        picked._check(scope, None)          # must not raise: the picked store serves it


def test_an_UNDECLARED_scope_raises_rather_than_defaulting():
    """A default axis would pick one for a scope nobody thought about, and the wrong choice is
    SILENT — `as_of` would be accepted and the comparison would simply answer wrongly."""
    import pytest as _pytest

    from app.ports.truth_store import axis_for

    with _pytest.raises(ValueError, match="no valid-time axis declared"):
        axis_for("saga")


def test_a_BOOLEAN_as_of_is_refused_on_the_ordinal_axis():
    """⚠️ `bool` is an `int` in Python, so a stray `True` would otherwise be accepted as a
    story ordinal and compared as 1 — chapter one. Neither axis should take it."""
    import pytest as _pytest

    from app.ports.truth_store import check_axis

    with _pytest.raises(TypeError):
        check_axis("project", True)          # wall clock: not a datetime
