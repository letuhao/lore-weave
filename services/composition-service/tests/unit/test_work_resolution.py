"""Unit tests for §6.2 Work resolution (mock repo + mock knowledge client)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.db.models import CompositionWork
from app.work_resolution import resolve_work

USER = uuid.uuid4()
BOOK = uuid.uuid4()


def _work(project_id: uuid.UUID | None = None) -> CompositionWork:
    return CompositionWork(
        project_id=project_id or uuid.uuid4(),
        created_by=USER,
        book_id=BOOK,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _WorksRepoStub:
    def __init__(self, marked: list[CompositionWork]) -> None:
        self._marked = marked
        self.calls: list = []

    async def resolve_by_book(self, book_id):
        # 25 PM-9: BOOK-driven, caller-independent — no user id.
        self.calls.append(book_id)
        return self._marked


class _KnowledgeStub:
    def __init__(self, projects):
        self._projects = projects
        self.calls: list[tuple] = []

    async def list_projects_for_book(self, book_id, bearer):
        self.calls.append((book_id, bearer))
        return self._projects


def _project(project_id, *, ptype="book", book_id=BOOK, archived=False):
    return {
        "project_id": str(project_id), "project_type": ptype,
        "book_id": str(book_id), "is_archived": archived,
    }


async def _resolve(marked, projects):
    works = _WorksRepoStub(marked)
    kn = _KnowledgeStub(projects)
    res = await resolve_work(
        BOOK, bearer="jwt", works_repo=works, knowledge_client=kn,
    )
    return res, works, kn


async def test_found_single_marked_skips_knowledge():
    w = _work()
    res, works, kn = await _resolve([w], None)
    assert res.status == "found"
    assert res.work is w
    assert kn.calls == []  # short-circuit: never asks knowledge


async def test_candidates_multiple_marked():
    ws = [_work(), _work()]
    res, _, kn = await _resolve(ws, None)
    assert res.status == "candidates"
    assert res.works == ws
    assert kn.calls == []


async def test_unmarked_single_book_project():
    pid = uuid.uuid4()
    res, _, kn = await _resolve([], [_project(pid)])
    assert res.status == "unmarked_single"
    assert res.book_project_id == pid
    assert kn.calls and kn.calls[0][1] == "jwt"  # forwarded the bearer


async def test_unmarked_candidates_multiple_book_projects():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    res, _, _ = await _resolve([], [_project(p1), _project(p2)])
    assert res.status == "unmarked_candidates"
    assert set(res.book_project_ids) == {p1, p2}


async def test_none_when_no_book_project():
    res, _, _ = await _resolve([], [])
    assert res.status == "none"


async def test_none_filters_archived_and_mismatched_book():
    # An archived project and a project for a DIFFERENT book are filtered out.
    other_book = uuid.uuid4()
    projects = [
        _project(uuid.uuid4(), archived=True),
        _project(uuid.uuid4(), book_id=other_book),
    ]
    res, _, _ = await _resolve([], projects)
    assert res.status == "none"


async def test_resolves_book_linked_project_regardless_of_type():
    # FINDING-1 fix: a book's real grounding project is often type 'general'/
    # 'translation' (bound by book_id only). It MUST resolve, not be missed —
    # else POST /work would create a duplicate empty 'book' project.
    pid = uuid.uuid4()
    res, _, _ = await _resolve([], [_project(pid, ptype="general")])
    assert res.status == "unmarked_single" and res.book_project_id == pid


async def test_unavailable_when_knowledge_returns_none():
    res, _, _ = await _resolve([], None)
    assert res.status == "unavailable"
    assert res.book_project_id is None
