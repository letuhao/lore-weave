"""D-AN-OVERRIDE-ACCEPTS-A-TARGET-ENTITY-THAT-IS-NOT-THERE — the ABSENT and FOREIGN cases.

`composition_entity_override_edit op=add` created an override for a `target_entity_id` it never
checked. Measured 2026-08-23 by direct probe against a real derivative, three cases that should
refuse all succeeded: a fresh UUIDv4 with no such entity, another BOOK's entity, and an empty
field-set. The empty case was closed then; these two were deferred.

🔴 THE DEFERRAL'S PREMISE WAS FALSE, and checking it is what closed them. It said glossary's
client is "documented to return [] / None on any failure and never raise", so gating on it would
be a fail-open/fail-closed product decision. That docstring describes the DEGRADE-SAFE methods.
The same module already carries `GlossaryClientError` and `seed_entities_or_raise`, whose own
docstring states this exact principle for a gate "which must never record a mutation as applied
when it actually failed".

`entities_by_ids` is BOOK-SCOPED, so one call answers both cases: an entity that does not exist
and one belonging to another book are alike absent from this book's items. They therefore earn
the SAME refusal, which is also what H13 wants — telling them apart would be an existence oracle
for a book the caller may not own.

Verified live before any of this was written (throwaway book, real entity):

    entities_by_ids(book, [real_id])          -> [{"entity_id": "01a030ea-1e4a-…", …}]
    entities_by_ids(book, [uuid4()])          -> []
    entities_by_ids(book, [real, uuid4()])    -> 1 item

so the check cannot reject a valid override, which was the refutation criterion.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.test_mcp_server import _Ctx, _derivative, _patched  # noqa: F401


def _glossary(items=None, raises=None):
    """A stand-in for the glossary client whose ONLY job is `entities_by_ids_or_raise`."""
    c = NS()
    c.entities_by_ids_or_raise = (
        AsyncMock(side_effect=raises) if raises is not None
        else AsyncMock(return_value=list(items or []))
    )
    return c


async def _add(srv, deriv, target, *, gloss, fields=None):
    async def get_deriv(pid):
        return deriv

    ov = NS(id=uuid.uuid4(), target_entity_id=target,
            overridden_fields=fields or {"role": "hero"})
    async with _patched(works_get=get_deriv) as s:
        s.WorksRepo(None).get = AsyncMock(return_value=deriv)
        with patch.object(srv, "DerivativesRepo") as DR, \
                patch.object(srv, "get_glossary_client", return_value=gloss):
            DR.return_value.add_override = AsyncMock(return_value=ov)
            res = await srv.composition_entity_override_add(
                _Ctx(), srv._EntityOverrideAddArgs(
                    project_id=str(deriv.project_id), target_entity_id=str(target),
                    overridden_fields=fields or {"role": "hero"}),
            )
            return res, DR.return_value.add_override


class TestATargetThatIsNotInThisBook:
    async def test_an_entity_that_does_not_exist_is_refused(self):
        import app.mcp.server as srv

        deriv, target = _derivative(), uuid.uuid4()
        res, add = await _add(srv, deriv, target, gloss=_glossary(items=[]))
        assert res["success"] is False
        assert "TARGET_NOT_IN_THIS_BOOK" in res["error"], res
        add.assert_not_awaited(), "the row was written despite the refusal"

    async def test_another_books_entity_is_refused_the_same_way(self):
        """FOREIGN and ABSENT are indistinguishable BY DESIGN — the read is book-scoped, so a
        foreign id simply is not in this book's items. A refusal that told them apart would
        confirm the existence of an entity in a book the caller may not own."""
        import app.mcp.server as srv

        deriv, foreign = _derivative(), uuid.uuid4()
        # glossary answers for THIS book and does not know the foreign id
        res, add = await _add(srv, deriv, foreign, gloss=_glossary(items=[]))
        assert res["success"] is False
        assert "TARGET_NOT_IN_THIS_BOOK" in res["error"]
        add.assert_not_awaited()

    async def test_the_refusal_says_how_to_find_the_right_id(self):
        import app.mcp.server as srv

        deriv = _derivative()
        res, _ = await _add(srv, deriv, uuid.uuid4(), gloss=_glossary(items=[]))
        assert "glossary_search" in res["error"], (
            "a refusal that names no way forward costs the model another attempt"
        )

    async def test_a_target_that_DOES_exist_still_writes(self):
        """The control that keeps the rest from being a tool that refuses everything."""
        import app.mcp.server as srv

        deriv, target = _derivative(), uuid.uuid4()
        gloss = _glossary(items=[{"entity_id": str(target), "cached_name": "Aldric"}])
        res, add = await _add(srv, deriv, target, gloss=gloss)
        assert res["success"] is True, res
        add.assert_awaited()

    async def test_the_id_is_matched_not_merely_counted(self):
        """A non-empty answer is not the same as an answer ABOUT this id. If the check only
        asked "did glossary return anything", a book with any entity at all would pass."""
        import app.mcp.server as srv

        deriv, target = _derivative(), uuid.uuid4()
        gloss = _glossary(items=[{"entity_id": str(uuid.uuid4()), "cached_name": "Someone else"}])
        res, add = await _add(srv, deriv, target, gloss=gloss)
        assert res["success"] is False
        assert "TARGET_NOT_IN_THIS_BOOK" in res["error"]
        add.assert_not_awaited()


class TestAnOutageIsNotARejection:
    """The third branch, and the reason the RAISING variant is used. This loop's standing rule
    is that a guard which cannot distinguish 'invalid' from 'unverified' must say so rather than
    pick silently — the degrade-safe `[]` cannot, and would have reported a glossary outage as a
    bad argument."""

    async def test_a_glossary_failure_refuses_with_a_DISTINCT_code(self):
        import app.mcp.server as srv
        from app.clients.glossary_client import GlossaryClientError

        deriv = _derivative()
        gloss = _glossary(raises=GlossaryClientError(502, "GLOSSARY_SERVICE_UNAVAILABLE", "boom"))
        res, add = await _add(srv, deriv, uuid.uuid4(), gloss=gloss)
        assert res["success"] is False
        assert "TARGET_UNVERIFIED" in res["error"], res
        assert "TARGET_NOT_IN_THIS_BOOK" not in res["error"], (
            "an outage was reported as an invalid argument"
        )
        add.assert_not_awaited(), "fail-open — the bug this whole change exists to close"

    async def test_it_says_nothing_was_written_and_that_the_argument_may_be_fine(self):
        import app.mcp.server as srv
        from app.clients.glossary_client import GlossaryClientError

        deriv = _derivative()
        gloss = _glossary(raises=GlossaryClientError(503, None, None))
        res, _ = await _add(srv, deriv, uuid.uuid4(), gloss=gloss)
        low = res["error"].lower()
        assert "nothing was written" in low
        assert "retry" in low


class TestTheClientContract:
    """`entities_by_ids_or_raise` must differ from its degrade-safe twin in exactly one way."""

    async def test_it_raises_on_a_non_200(self):
        from app.clients.glossary_client import GlossaryClient, GlossaryClientError

        c = GlossaryClient("http://glossary", "tok")
        c._http = NS(post=AsyncMock(return_value=NS(
            status_code=500, json=lambda: {"error": "BOOM", "message": "nope"})))
        with pytest.raises(GlossaryClientError) as e:
            await c.entities_by_ids_or_raise(uuid.uuid4(), [str(uuid.uuid4())])
        assert e.value.status == 500

    async def test_it_raises_on_a_transport_failure(self):
        import httpx

        from app.clients.glossary_client import GlossaryClient, GlossaryClientError

        c = GlossaryClient("http://glossary", "tok")
        c._http = NS(post=AsyncMock(side_effect=httpx.ConnectError("down")))
        with pytest.raises(GlossaryClientError):
            await c.entities_by_ids_or_raise(uuid.uuid4(), [str(uuid.uuid4())])

    async def test_a_200_returns_its_items(self):
        from app.clients.glossary_client import GlossaryClient

        eid = str(uuid.uuid4())
        c = GlossaryClient("http://glossary", "tok")
        c._http = NS(post=AsyncMock(return_value=NS(
            status_code=200, json=lambda: {"items": [{"entity_id": eid}]})))
        got = await c.entities_by_ids_or_raise(uuid.uuid4(), [eid])
        assert got == [{"entity_id": eid}]

    async def test_an_empty_id_list_never_calls_the_wire(self):
        from app.clients.glossary_client import GlossaryClient

        c = GlossaryClient("http://glossary", "tok")
        c._http = NS(post=AsyncMock())
        assert await c.entities_by_ids_or_raise(uuid.uuid4(), []) == []
        c._http.post.assert_not_awaited()

    async def test_the_degrade_safe_twin_is_unchanged(self):
        """The bystander. Every advisory caller of `entities_by_ids` still wants [] on failure —
        a glossary outage must keep degrading the context pack rather than 500ing a generate."""
        import httpx

        from app.clients.glossary_client import GlossaryClient

        c = GlossaryClient("http://glossary", "tok")
        c._http = NS(post=AsyncMock(side_effect=httpx.ConnectError("down")))
        assert await c.entities_by_ids(uuid.uuid4(), [str(uuid.uuid4())]) == []


class TestTheCanonicalRefusalPointsAtTheLookup:
    """D-THE-AMBIENT-PROJECT-IS-THE-WRONG-WORK-AND-THE-RUNTIME-SUPPLIES-IT.

    The book's ambient project is its CANONICAL Work, and chat-service backfills it into any
    tool that declares `project_id`. An override exists only on a DERIVATIVE, so the id the
    model is handed is refused by definition — and the refusal used to say "create one with
    composition_create_derivative" on a book that, in this scenario, ALREADY HAS ONE (the seed
    creates it). Measured c-override8, K=5: the model was told to make a second derivative
    instead of finding the first.

    Naming `composition_list_derivatives` also ARMS it — chat-service's
    `_tools_named_in_refusal` runs on dispatch results — which a message naming only the create
    tool never did for the lookup.
    """

    async def test_it_names_the_lookup_before_the_create(self):
        import app.mcp.server as srv

        canonical = NS(id=uuid.uuid4(), project_id=uuid.uuid4(),
                       book_id=uuid.uuid4(), source_work_id=None)

        async def get_canonical(pid):
            return canonical

        async with _patched(works_get=get_canonical) as s:
            s.WorksRepo(None).get = AsyncMock(return_value=canonical)
            with patch.object(srv, "DerivativesRepo") as DR:
                DR.return_value.add_override = AsyncMock()
                res = await srv.composition_entity_override_add(
                    _Ctx(), srv._EntityOverrideAddArgs(
                        project_id=str(canonical.project_id),
                        target_entity_id=str(uuid.uuid4()),
                        overridden_fields={"occupation": "cartographer"}),
                )
        assert res["success"] is False
        err = res["error"]
        assert "NOT_A_DERIVATIVE" in err
        assert "composition_list_derivatives" in err, (
            "the refusal never names the tool that FINDS the derivative, so a book that already "
            "has one is told to make another"
        )
        assert err.index("composition_list_derivatives") < err.index("composition_create_derivative"), (
            "create is offered before list — the wrong order for a book that already has a "
            "derivative, which is the common case"
        )
        assert "is_canonical" in err, "it does not say which entry of the list to take"
