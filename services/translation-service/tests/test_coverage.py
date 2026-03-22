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
):
    return FakeRecord({
        "chapter_id": UUID(chapter_id),
        "target_language": lang,
        "version_count": version_count,
        "latest_status": latest_status,
        "latest_version_num": latest_version_num,
        "active_ct_id": active_ct_id,
        "active_version_num": active_version_num,
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
