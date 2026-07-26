"""KG adopt auto-seeds the glossary node-kinds a schema requires.

The M1 adopt-gate used to 422 KG_ADOPT_NEEDS_GLOSSARY and silently do nothing.
`adopt_with_autocreate_glossary` (shared by the human route + the agent confirm
effect) now copies the missing kinds down from System into the book tier and
retries once. These pin: direct success (no seed), seed+retry success, book-less
re-raise, and residual re-raise when the seed can't satisfy the gate.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.clients.glossary_ontology_client import FakeGlossaryOntologyClient
from app.db.repositories.ontology_mutations import NeedsGlossaryError
from app.ontology.glossary_gate import adopt_with_autocreate_glossary

OWNER = uuid4()
PROJECT = uuid4()
BOOK = uuid4()
SOURCE = uuid4()


class _Projects:
    def __init__(self, book: UUID | None = BOOK) -> None:
        self._book = book

    async def project_meta(self, pid: UUID):
        return (OWNER, self._book)


class _Mutations:
    """Models the gate: adopt raises NeedsGlossaryError when the required kinds
    aren't all present in glossary_kinds, else succeeds."""

    def __init__(self, required: set[str]) -> None:
        self._required = set(required)
        self.adopt_calls = 0

    async def required_node_kinds(self, source_id: UUID) -> set[str]:
        return set(self._required)

    async def adopt(self, *, owner_user_id, project_id, source_schema_id, glossary_kinds, book_id):
        self.adopt_calls += 1
        missing = sorted(self._required - set(glossary_kinds))
        if missing:
            raise NeedsGlossaryError(missing, str(book_id) if book_id else None)
        return SimpleNamespace(schema=SimpleNamespace(schema_id=uuid4()), missing_optional=[])


async def _run(projects, glossary, mutations):
    return await adopt_with_autocreate_glossary(
        projects, glossary, mutations,
        owner=OWNER, project_id=str(PROJECT), source_schema_id=SOURCE,
    )


@pytest.mark.asyncio
async def test_direct_success_when_glossary_has_kinds_no_seed():
    glossary = FakeGlossaryOntologyClient(book_kinds={str(BOOK): ["concept", "technique"]})
    mutations = _Mutations({"concept", "technique"})
    result = await _run(_Projects(), glossary, mutations)
    assert result.schema.schema_id is not None
    assert mutations.adopt_calls == 1  # no retry
    assert glossary.adopt_calls == []  # no seed needed


@pytest.mark.asyncio
async def test_seeds_missing_kinds_then_retries_and_succeeds():
    # Glossary empty → the seed CREATES the required kinds (System copy-down for
    # catalogue codes + a direct book-tier create for non-catalogue ones) + retry.
    glossary = FakeGlossaryOntologyClient(book_kinds={})
    mutations = _Mutations({"concept", "technique"})
    result = await _run(_Projects(), glossary, mutations)
    assert result.schema.schema_id is not None
    assert mutations.adopt_calls == 2  # first raised, retry succeeded
    assert glossary.adopt_calls == [(str(BOOK), str(OWNER), ["concept", "technique"])]
    # the seed landed on the book's kind set (realistic re-resolve)
    assert set(glossary._book_kinds[str(BOOK)]) >= {"concept", "technique"}


@pytest.mark.asyncio
async def test_non_catalogue_kinds_are_created_directly():
    # A template needing kinds that aren't System/User kinds still succeeds — the
    # endpoint creates them as book-tier kinds (the schema is authoritative).
    glossary = FakeGlossaryOntologyClient(book_kinds={})
    mutations = _Mutations({"technique"})  # not a catalogue kind
    result = await _run(_Projects(), glossary, mutations)
    assert result.schema.schema_id is not None
    assert "technique" in glossary._book_kinds[str(BOOK)]


@pytest.mark.asyncio
async def test_bookless_project_reraises_no_seed():
    # A book-less standards project has no book tier to seed into → re-raise.
    glossary = FakeGlossaryOntologyClient(user_kinds={str(OWNER): []})
    mutations = _Mutations({"concept"})
    with pytest.raises(NeedsGlossaryError):
        await _run(_Projects(book=None), glossary, mutations)
    assert glossary.adopt_calls == []  # never attempted a seed


@pytest.mark.asyncio
async def test_seed_failure_reraises():
    # The glossary reads fine (gate fires on the empty book) but the seed WRITE
    # fails (transport/outage on adopt-kinds) → re-raise (honest 422, no loop).
    glossary = FakeGlossaryOntologyClient(book_kinds={})

    async def _seed_fails(*_a, **_k):
        return False

    glossary.adopt_book_kinds = _seed_fails  # type: ignore[assignment]
    mutations = _Mutations({"concept", "technique"})
    with pytest.raises(NeedsGlossaryError):
        await _run(_Projects(), glossary, mutations)
    assert mutations.adopt_calls == 1  # tried once, seed failed, no retry
