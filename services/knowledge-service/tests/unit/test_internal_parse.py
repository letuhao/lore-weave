"""P1 — unit tests for /internal/parse router."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

_INTERNAL_TOKEN_HEADER = {"X-Internal-Token": "default_test_token"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_HTML_BODY = """\
<html><head><title>Test</title></head>
<body>
  <h2>Chapter 1</h2>
  <p>Body of chapter 1.</p>
  <h2>Chapter 2</h2>
  <p>Body of chapter 2.</p>
</body></html>
"""


def test_parse_html_returns_tree(client: TestClient):
    """POST html -> 200 + StructuralTree shape (D6 success path)."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "html", "content": _HTML_BODY},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200, resp.text
    tree = resp.json()
    assert tree["source_format"] == "html"
    assert tree["walker_path"] == "headings"
    assert tree["book_title"] == "Test"
    assert len(tree["parts"]) == 1
    assert len(tree["parts"][0]["chapters"]) == 2


def test_parse_plain_returns_tree(client: TestClient):
    """POST plain -> 200 with detected_language populated for auto-detect."""
    resp = client.post(
        "/internal/parse",
        json={
            "source_format": "plain",
            "content": "Chapter 1\nBody 1.\n\nChapter 2\nBody 2.\n",
        },
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200, resp.text
    tree = resp.json()
    assert tree["source_format"] == "plain"
    assert tree["detected_language"] == "en"


_TIPTAP_BODY = json.dumps(
    {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2, "sceneId": "node-42"},
                "content": [{"type": "text", "text": "The Arrival"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "She stepped off the train."}],
            },
        ],
    }
)


def test_parse_tiptap_passthrough_carries_anchor(client: TestClient):
    """26 IX-6: source_format='tiptap' routes through the dispatcher and each
    scene carries anchor_scene_id from the heading's sceneId — the field
    book-service reads to back-link source_scene_id."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "tiptap", "content": _TIPTAP_BODY, "language": "en"},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200, resp.text
    tree = resp.json()
    assert tree["source_format"] == "tiptap"
    scene = tree["parts"][0]["chapters"][0]["scenes"][0]
    assert scene["anchor_scene_id"] == "node-42"
    assert scene["leaf_text"] == "She stepped off the train."


def test_parse_tiptap_malformed_json_returns_400(client: TestClient):
    """A tiptap body that is not a JSON object -> ValueError in the walker ->
    400 (dispatcher's caller-bug path; body-cap + 422 semantics unchanged)."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "tiptap", "content": "not-a-json-doc{"},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400


def test_parse_requires_internal_token(client: TestClient):
    """Missing X-Internal-Token -> 401 (middleware path)."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "html", "content": "<p>x</p>"},
    )
    assert resp.status_code == 401


def test_parse_empty_content_returns_422(client: TestClient):
    """L4 lock: content='' -> 422."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "html", "content": ""},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 422


def test_parse_whitespace_only_html_returns_422(client: TestClient):
    """L4 lock: whitespace-only HTML body -> 422 (no extractable structure)."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "html", "content": "   \n\n   "},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 422


def test_parse_malformed_request_returns_400(client: TestClient):
    """Missing source_format -> 400 (Pydantic validation)."""
    resp = client.post(
        "/internal/parse",
        json={"content": "<p>x</p>"},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400


def test_parse_unknown_source_format_returns_400(client: TestClient):
    """source_format not in literal set -> 400 at envelope validation."""
    resp = client.post(
        "/internal/parse",
        json={"source_format": "pdf", "content": "x"},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400


def test_parse_body_exceeds_limit_returns_413(client: TestClient, monkeypatch):
    """H3 lock: body > MAX_PARSE_BODY_BYTES -> 413.

    We monkey-patch the setting down to 100 bytes for the test so we
    don't have to send a real 200MiB payload.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "max_parse_body_bytes", 100)
    big = "<p>" + ("x" * 200) + "</p>"
    resp = client.post(
        "/internal/parse",
        content=big.encode("utf-8"),
        headers={**_INTERNAL_TOKEN_HEADER, "Content-Type": "application/json"},
    )
    assert resp.status_code == 413


def test_parse_language_auto_populates_detected(client: TestClient):
    """language=null -> response includes detected_language field."""
    resp = client.post(
        "/internal/parse",
        json={
            "source_format": "plain",
            "content": "Chương 1\nVăn bản chương một.\n\nChương 2\nVăn bản hai.\n",
            "language": None,
        },
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    assert resp.json()["detected_language"] == "vi"
