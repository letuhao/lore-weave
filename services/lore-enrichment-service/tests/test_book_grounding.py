"""Unit tests for the book-chapter grounding seam (LE-PROD slice C).

No DB / no network: the BookClient, KnowledgeClient and SourceCorpusStore are
faked. Pins the two behaviours the seed depends on — (1) ``chapter_ids=None``
lists EVERY chapter then ingests their concatenated text into the
``book-chapters:{book_id}`` corpus, (2) all-blank chapters raise
``NoChapterTextError`` (the caller maps it to a 400 / a clear seed message)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

import app.services.book_grounding as bg
from app.clients.book import ChapterMeta
from app.services.book_grounding import (
    NoChapterTextError,
    book_corpus_name,
    ingest_book_chapters,
)


class _FakeBook:
    def __init__(self, *, chapters: list[ChapterMeta], texts: dict) -> None:
        self._chapters = chapters
        self._texts = texts
        self.listed = False

    async def list_chapters(self, *, book_id, limit=200, offset=0):
        self.listed = True
        return self._chapters, len(self._chapters)

    async def get_chapter_text(self, *, book_id, chapter_id):
        return self._texts.get(chapter_id, "")

    async def aclose(self):
        pass


class _FakeKC:
    async def aclose(self):
        pass


class _Ingest:
    def __init__(self):
        self.calls = []

    async def ingest_corpus(self, **kw):
        self.calls.append(kw)
        class _R:
            chunks_total = 3
            chunks_inserted = 3
            chunks_embedded = 3
        return _R()


class _FakeStore:
    def __init__(self, pool):
        self._ing = pool  # the test injects the _Ingest as the "pool"

    async def ingest_corpus(self, **kw):
        return await self._ing.ingest_corpus(**kw)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(bg, "KnowledgeClient", lambda **kw: _FakeKC())
    monkeypatch.setattr(bg, "SourceCorpusStore", _FakeStore)


@pytest.mark.asyncio
async def test_chapter_ids_none_lists_all_then_ingests_concatenated(monkeypatch):
    book_id, user_id, embed = uuid4(), uuid4(), uuid4()
    c1, c2, c3 = uuid4(), uuid4(), uuid4()
    chapters = [ChapterMeta(chapter_id=c) for c in (c1, c2, c3)]
    texts = {c1: "第一回 …", c2: "  ", c3: "第三回 …"}  # c2 blank → skipped
    fake_book = _FakeBook(chapters=chapters, texts=texts)
    monkeypatch.setattr(bg, "BookClient", lambda **kw: fake_book)
    ing = _Ingest()

    res = await ingest_book_chapters(
        ing, user_id=user_id, project_id=book_id, book_id=book_id,
        embedding_model_ref=embed, chapter_ids=None,
    )

    assert fake_book.listed is True  # None → listed ALL chapters
    assert res.chapters_ingested == 2  # the blank chapter was skipped
    assert len(ing.calls) == 1
    call = ing.calls[0]
    assert call["name"] == book_corpus_name(book_id)
    assert call["license"] == "licensed" and call["kind"] == "other"
    assert "第一回" in call["text"] and "第三回" in call["text"]


@pytest.mark.asyncio
async def test_explicit_selection_does_not_list_all(monkeypatch):
    book_id, user_id, embed = uuid4(), uuid4(), uuid4()
    c1 = uuid4()
    fake_book = _FakeBook(chapters=[], texts={c1: "選定章節"})
    monkeypatch.setattr(bg, "BookClient", lambda **kw: fake_book)
    ing = _Ingest()

    res = await ingest_book_chapters(
        ing, user_id=user_id, project_id=book_id, book_id=book_id,
        embedding_model_ref=embed, chapter_ids=[c1],
    )

    assert fake_book.listed is False  # an explicit selection never lists all
    assert res.chapters_ingested == 1


def _load_seed_pd():
    """Load the seed_pd_corpus script (not a package) to test its pure helper."""
    path = Path(__file__).parents[1] / "scripts" / "seed_pd_corpus.py"
    spec = importlib.util.spec_from_file_location("seed_pd_corpus", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_read_corpus_text_sorts_concats_and_skips_empties(tmp_path):
    seed = _load_seed_pd()
    (tmp_path / "卷012.txt").write_text("乙太乙真人", encoding="utf-8")
    (tmp_path / "卷001.txt").write_text("甲女媧宮", encoding="utf-8")
    (tmp_path / "blank.txt").write_text("   \n  ", encoding="utf-8")  # skipped
    (tmp_path / "notes.md").write_text("not a txt", encoding="utf-8")  # ignored
    text, n = seed._read_corpus_text(tmp_path)
    assert n == 2  # the blank .txt is skipped; the .md is ignored
    # sorted by filename → 卷001 before 卷012
    assert text == "甲女媧宮\n\n乙太乙真人"


def test_read_corpus_text_empty_dir(tmp_path):
    seed = _load_seed_pd()
    text, n = seed._read_corpus_text(tmp_path)
    assert text == "" and n == 0


@pytest.mark.asyncio
async def test_all_blank_chapters_raises_no_chapter_text(monkeypatch):
    book_id, user_id, embed = uuid4(), uuid4(), uuid4()
    c1 = uuid4()
    fake_book = _FakeBook(chapters=[ChapterMeta(chapter_id=c1)], texts={c1: "   "})
    monkeypatch.setattr(bg, "BookClient", lambda **kw: fake_book)

    with pytest.raises(NoChapterTextError):
        await ingest_book_chapters(
            _Ingest(), user_id=user_id, project_id=book_id, book_id=book_id,
            embedding_model_ref=embed, chapter_ids=None,
        )
