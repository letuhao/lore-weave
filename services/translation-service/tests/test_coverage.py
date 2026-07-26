"""Unit tests for GET /v1/translation/books/{book_id}/coverage endpoint (LW-72)."""
import datetime
from uuid import UUID, uuid4

from tests.conftest import FakeRecord

BOOK_ID = str(uuid4())
CHAPTER_ID_1 = str(uuid4())
CHAPTER_ID_2 = str(uuid4())
_NOW = datetime.datetime.utcnow()
_ACTIVE_CT_ID = uuid4()


def _coverage_row(
    chapter_id: str,
    lang: str,
    version_count: int = 1,
    latest_status: str = "completed",
    latest_version_num: int | None = 1,
    active_ct_id=None,
    active_version_num: int | None = None,
    is_glossary_stale: bool = False,
):
    return FakeRecord({
        "chapter_id": UUID(chapter_id),
        "target_language": lang,
        "version_count": version_count,
        "latest_status": latest_status,
        "latest_version_num": latest_version_num,
        "active_ct_id": active_ct_id,
        "active_version_num": active_version_num,
        "is_glossary_stale": is_glossary_stale,
    })


# ── Basic structure ──────────────────────────────────────────────────────────

def test_coverage_returns_empty_when_no_translations(client, fake_pool):
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["book_id"] == BOOK_ID
    assert data["coverage"] == []
    assert data["known_languages"] == []


def test_coverage_returns_correct_book_id(client, fake_pool):
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.json()["book_id"] == BOOK_ID


# ── CoverageCell fields ───────────────────────────────────────────────────────

def test_coverage_has_active_true_when_active_ct_set(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", active_ct_id=_ACTIVE_CT_ID, active_version_num=1),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["has_active"] is True
    assert cell["active_version_num"] == 1


def test_coverage_has_active_false_when_no_active_ct(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", active_ct_id=None, active_version_num=None),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["has_active"] is False
    assert cell["active_version_num"] is None


def test_coverage_latest_version_num_populated(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", version_count=3, latest_version_num=3),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["latest_version_num"] == 3


def test_coverage_latest_version_num_null_when_no_versions(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", latest_version_num=None),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["latest_version_num"] is None


def test_coverage_version_count_correct(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", version_count=5),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["version_count"] == 5


def test_coverage_latest_status_running(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", latest_status="running"),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["latest_status"] == "running"


# ── M6b-2: is_glossary_stale on the cell ──────────────────────────────────────

def test_coverage_cell_glossary_stale_surfaced(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", active_ct_id=_ACTIVE_CT_ID,
                      active_version_num=1, is_glossary_stale=True),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    cell = resp.json()["coverage"][0]["languages"]["vi"]
    assert cell["is_glossary_stale"] is True


def test_coverage_cell_not_stale_by_default(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi"),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.json()["coverage"][0]["languages"]["vi"]["is_glossary_stale"] is False


# ── known_languages ───────────────────────────────────────────────────────────

def test_coverage_known_languages_sorted_alphabetically(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "zh"),
        _coverage_row(CHAPTER_ID_1, "vi"),
        _coverage_row(CHAPTER_ID_1, "en"),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.json()["known_languages"] == ["en", "vi", "zh"]


def test_coverage_known_languages_deduplicated(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi"),
        _coverage_row(CHAPTER_ID_2, "vi"),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.json()["known_languages"] == ["vi"]


# ── Multiple chapters ─────────────────────────────────────────────────────────

def test_coverage_multiple_chapters_returned(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi"),
        _coverage_row(CHAPTER_ID_2, "vi"),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert len(resp.json()["coverage"]) == 2


def test_coverage_multiple_languages_per_chapter(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi"),
        _coverage_row(CHAPTER_ID_1, "zh"),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    data = resp.json()
    # Both languages collapsed into one chapter entry
    assert len(data["coverage"]) == 1
    assert set(data["coverage"][0]["languages"].keys()) == {"vi", "zh"}


def test_coverage_active_and_non_active_in_same_chapter(client, fake_pool):
    fake_pool.fetch.return_value = [
        _coverage_row(CHAPTER_ID_1, "vi", active_ct_id=_ACTIVE_CT_ID, active_version_num=1),
        _coverage_row(CHAPTER_ID_1, "zh", active_ct_id=None, active_version_num=None),
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    langs = resp.json()["coverage"][0]["languages"]
    assert langs["vi"]["has_active"] is True
    assert langs["zh"]["has_active"] is False


# ── T2-M3 (A): per-segment coverage rollup ────────────────────────────────────

def _seg_cov_row(chapter_id, total, translated, dirty, stale=0, needs=None):
    return FakeRecord({"chapter_id": UUID(chapter_id), "segment_total": total,
                       "translated_count": translated, "dirty_count": dirty,
                       "stale_count": stale,
                       "needs_count": dirty if needs is None else needs})


def test_segment_coverage_counts(client, fake_pool):
    fake_pool.fetch.return_value = [
        # 8 segs, all translated, 3 source-changed + 2 glossary-stale → 5 need work
        _seg_cov_row(CHAPTER_ID_1, 8, 8, 3, stale=2, needs=5),
        _seg_cov_row(CHAPTER_ID_2, 5, 0, 5),   # untranslated → all dirty
    ]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/segment-coverage?target_language=vi")
    assert resp.status_code == 200
    d = resp.json()
    assert d["book_id"] == BOOK_ID and d["target_language"] == "vi"
    assert len(d["chapters"]) == 2
    c0 = d["chapters"][0]
    assert (c0["segment_total"], c0["translated_count"], c0["dirty_count"]) == (8, 8, 3)
    assert c0["stale_count"] == 2
    assert c0["needs_count"] == 5   # dirty ∪ stale
    assert d["chapters"][1]["needs_count"] == 5


def test_segment_coverage_requires_language(client, fake_pool):
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/segment-coverage")
    assert resp.status_code == 422  # target_language is required


def test_segment_coverage_empty(client, fake_pool):
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/segment-coverage?target_language=vi")
    assert resp.json()["chapters"] == []


# ── D-S05: untranslated chapters must be VISIBLE (not derived from translations only) ──

def test_coverage_surfaces_untranslated_book_chapters():
    """A chapter that exists in the BOOK but has no translation row was structurally invisible
    (the coverage SQL derives its chapter list from chapter_translations). Given the book's real
    chapter list, coverage must surface the untranslated one — the whole point of a
    'translate what's new' pass (D-S05-COVERAGE-MISMATCH)."""
    from app.mcp.server import _coverage_payload
    rows = [_coverage_row(CHAPTER_ID_1, "en", active_ct_id=_ACTIVE_CT_ID, active_version_num=1)]
    payload = _coverage_payload(rows, UUID(BOOK_ID), all_chapter_ids=[CHAPTER_ID_1, CHAPTER_ID_2])
    # the never-translated ch2 is flagged...
    assert CHAPTER_ID_2 in payload["untranslated_chapter_ids"]
    assert CHAPTER_ID_1 not in payload["untranslated_chapter_ids"]
    # ...and it APPEARS in coverage (with no language coverage), not omitted
    ids = [c["chapter_id"] for c in payload["coverage"]]
    assert CHAPTER_ID_1 in ids and CHAPTER_ID_2 in ids


def test_coverage_degrades_to_translated_only_without_book_list():
    """No book chapter list (book-service unreachable) → behave EXACTLY as before: translated-only,
    empty untranslated list. A read must never break the turn."""
    from app.mcp.server import _coverage_payload
    rows = [_coverage_row(CHAPTER_ID_1, "en", active_ct_id=_ACTIVE_CT_ID, active_version_num=1)]
    payload = _coverage_payload(rows, UUID(BOOK_ID), all_chapter_ids=None)
    assert payload["untranslated_chapter_ids"] == []
    assert [c["chapter_id"] for c in payload["coverage"]] == [CHAPTER_ID_1]
