"""D-AUTHOR-SEARCH-READS-ONLY-CANON — the author's own search was given the reader's answer.

`run_hybrid_search` defaults `surface="canon"` — PUBLISHED-revision text only. The two
AUTHOR-facing call sites, `_handle_memory_search` and `_handle_story_search`, never passed a
surface, so a chapter written and not yet published (editorial_status='draft',
published_revision_id=null) — the normal state of a manuscript in progress — was invisible to both.

MEASURED 2026-08-14, reproducible with NO model in the loop. A throwaway book with one seeded
chapter containing "The Obsidian Trench is only walkable during low tide", then memory_search for
each of 'Obsidian Trench', 'low tide', 'Obsidian', 'waterline', 'Aldric Vane':

    hits=0 total=0 degraded={'semantic': 'not_indexed'}  — every single query

while the tool's own description promises "lexical + semantic, so it finds an exact phrase even
with nothing indexed yet", and its docstring claims the merged legs mean it is "NEVER empty when
the raw chapter text matches". The lexical leg was working. It was searching canon, and canon was
empty.

WHAT THIS CORRECTS IN MY OWN EARLIER DIAGNOSIS: `story_search` is recorded BLOCKED in the
tool-deep-dive ledger on D-DEGRADED-READ-REPORTED-AS-ABSENCE, and I wrote the cause down as a
fixture gap — "story_search needs an INDEXED project, which a fresh book has not got". That was
wrong. The lexical leg needs no embeddings at all; the project being un-indexed was a red herring
that happened to co-occur.

🔴 THE BOUNDARY, which is why this is not "just pass all everywhere". Drafts are OWNER-ONLY —
raw_search.py states it and enforces it by downgrading a non-owner's surface=all to canon. The two
tools fixed here resolve `project` through the OWNER-KEYED `projects_repo.get(ctx.user_id, ...)`,
so the caller IS the owner by construction. The READER-facing sites (`reader_tools.py`,
`wiki/context.py`) keep the canon default deliberately: there the published surface is the right
answer, and flipping them would leak unpublished drafts to readers. The spoiler window
(`before_sort_order`) is a separate control and still applies on top.
"""
from __future__ import annotations

import pathlib
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tools import executor
from app.tools.definitions import MemorySearchArgs, StorySearchArgs

EXECUTOR_SRC = pathlib.Path(executor.__file__).read_text(encoding="utf-8")


class _Recorder:
    """Stands in for run_hybrid_search and records the surface it was handed."""

    def __init__(self) -> None:
        self.surface: object = "<never called>"
        self.calls = 0

    async def __call__(self, **kw):
        self.calls += 1
        self.surface = kw.get("surface", "<NOT PASSED — defaults to canon>")
        return SimpleNamespace(hits=[], degraded={})


def _ctx(project):
    class _Repo:
        async def get(self, _user_id, _project_id):
            return project

    return SimpleNamespace(
        user_id=uuid4(), project_id=uuid4(), projects_repo=_Repo(),
        book_client=object(), reranker_client=object(), embedding_client=object(),
    )


@pytest.fixture()
def recorder(monkeypatch):
    import app.search.retriever as retriever

    rec = _Recorder()
    monkeypatch.setattr(retriever, "run_hybrid_search", rec)
    return rec


def _project():
    # embedding_model None: the un-indexed project the live measurement used. The manuscript
    # leg must still run — that is the whole premise of the lexical arm.
    return SimpleNamespace(
        project_id=uuid4(), book_id=uuid4(), user_id=uuid4(),
        embedding_model=None, embedding_dimension=None,
    )


class TestTheAuthorFacingToolsAskForTheDraft:
    """THE FALSIFIER. Drop `surface="all"` from either call site and these go red — which is
    exactly the state the whole loop measured as 0 hits on 5 of 5 verbatim phrases."""

    async def test_memory_search_passes_surface_all(self, recorder):
        await executor._handle_memory_search(
            _ctx(_project()), MemorySearchArgs(query="Obsidian Trench"))
        assert recorder.calls == 1, "the manuscript leg did not run at all"
        assert recorder.surface == "all", (
            f"memory_search handed surface={recorder.surface!r} — an author searching their own "
            "unpublished manuscript gets the reader's canon-only answer")

    async def test_story_search_passes_surface_all(self, recorder):
        await executor._handle_story_search(
            _ctx(_project()), StorySearchArgs(query="Obsidian Trench"))
        assert recorder.calls == 1
        assert recorder.surface == "all", (
            f"story_search handed surface={recorder.surface!r} — this is the tool the ledger "
            "records BLOCKED on a false absence over a seeded chapter")

    async def test_the_leg_runs_even_with_no_embedding_model(self, recorder):
        """The lexical arm needs no embeddings; an un-indexed project must not skip it. My
        original root-cause note blamed exactly this and was wrong."""
        await executor._handle_memory_search(
            _ctx(_project()), MemorySearchArgs(query="low tide"))
        assert recorder.calls == 1


class TestTheReaderFacingSitesKeepCanon:
    """🔴 The boundary. If this ever goes red, unpublished drafts are reaching readers."""

    @pytest.mark.parametrize("module", ["tools/reader_tools.py", "wiki/context.py"])
    def test_no_surface_all_on_a_reader_path(self, module):
        src = (pathlib.Path(executor.__file__).parents[1] / module).read_text(encoding="utf-8")
        i = src.find("run_hybrid_search(")
        assert i != -1, f"{module} no longer calls run_hybrid_search — re-check the boundary"
        assert 'surface="all"' not in src[i:i + 900], (
            f"{module} is READER-facing and must keep the canon default; passing all here "
            "leaks unpublished drafts")


class TestTheEmptyNoteStopsAssertingAnIndexState:
    """The payload half of the same defect: an empty result was reported as 'this project has no
    indexed memory yet' for ANY reason, and the model relayed it to the author as 'it hasn't been
    established in the story yet' (measured live, rep3 of 5)."""

    async def test_it_no_longer_claims_nothing_is_indexed(self, recorder):
        out = await executor._handle_memory_search(
            _ctx(_project()), MemorySearchArgs(query="nothing matches this"))
        assert "no indexed memory yet" not in (out.get("note") or "")

    async def test_it_says_nothing_matched(self, recorder):
        out = await executor._handle_memory_search(
            _ctx(_project()), MemorySearchArgs(query="nothing matches this"))
        assert "matched" in (out.get("note") or "").lower()

    def test_the_index_caveat_is_conditional_not_unconditional(self):
        """It may still MENTION the index — but only when the semantic leg actually reported
        not_indexed, which is a fact it has, rather than a guess it does not."""
        i = EXECUTOR_SRC.index('no stored knowledge matched this query')
        window = EXECUTOR_SRC[i:i + 700]
        assert re.search(r'degraded\.get\("semantic"\)\s*==\s*"not_indexed"', window), (
            "the index caveat must be gated on the degraded marker, not stated unconditionally")
