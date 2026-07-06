"""Unit tests for POST /internal/parse/pdf-chunk.

docs/specs/2026-07-06-pdf-book-import.md — the PDF-import vision op's
per-chunk parse endpoint. Uses TestClient (no lifespan — no real DB/Redis
needed, mirrors internal_parse.py's stateless design) + fitz-generated
PDF fixtures + a monkeypatched get_llm_client for the caption_images=True
path (never hits a real provider-registry).
"""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routers import internal_parse_pdf

_INTERNAL_TOKEN_HEADER = {"X-Internal-Token": "default_test_token"}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _make_pdf_b64(page_texts: list[str]) -> str:
    doc = fitz.open()
    for text in page_texts:
        doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return base64.b64encode(data).decode("ascii")


def _make_pdf_with_image_b64(text: str, image_png: bytes) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    page.insert_image(fitz.Rect(72, 150, 272, 350), stream=image_png)
    data = doc.tobytes()
    doc.close()
    return base64.b64encode(data).decode("ascii")


def _make_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _base_body(**overrides):
    body = {
        "book_id": "019eadbe-0000-7000-8000-000000000001",
        "pdf_bytes_b64": _make_pdf_b64(["Hello world page one."]),
        "page_start": 1,
        "page_end": 1,
        "chunk_index": 0,
        "caption_images": False,
    }
    body.update(overrides)
    return body


# ── Validation ──────────────────────────────────────────────────────────


def test_pdf_peek_returns_page_count(client: TestClient):
    b64 = _make_pdf_b64(["one", "two", "three"])
    resp = client.post(
        "/internal/parse/pdf-peek", json={"pdf_bytes_b64": b64}, headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["page_count"] == 3


def test_pdf_peek_rejects_encrypted_pdf(client: TestClient):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    resp = client.post(
        "/internal/parse/pdf-peek",
        json={"pdf_bytes_b64": base64.b64encode(data).decode()},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 422
    assert "cannot open PDF" in resp.json()["detail"]


def test_pdf_peek_rejects_corrupted_pdf(client: TestClient):
    resp = client.post(
        "/internal/parse/pdf-peek",
        json={"pdf_bytes_b64": base64.b64encode(b"garbage").decode()},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 422


def test_rejects_invalid_base64(client: TestClient):
    resp = client.post(
        "/internal/parse/pdf-chunk",
        json=_base_body(pdf_bytes_b64="not-valid-base64!!!"),
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400
    assert "base64" in resp.json()["detail"]


def test_rejects_page_end_before_page_start(client: TestClient):
    resp = client.post(
        "/internal/parse/pdf-chunk",
        json=_base_body(page_start=3, page_end=1),
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400
    assert "page_end" in resp.json()["detail"]


def test_rejects_caption_images_without_model_ref(client: TestClient):
    resp = client.post(
        "/internal/parse/pdf-chunk",
        json=_base_body(caption_images=True),
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400
    assert "caption_images" in resp.json()["detail"]


def test_rejects_corrupted_pdf(client: TestClient):
    resp = client.post(
        "/internal/parse/pdf-chunk",
        json=_base_body(pdf_bytes_b64=base64.b64encode(b"not a pdf").decode()),
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 422
    assert "cannot open PDF" in resp.json()["detail"]


def test_rejects_missing_internal_token(client: TestClient):
    resp = client.post("/internal/parse/pdf-chunk", json=_base_body())
    assert resp.status_code in (401, 403)


# ── Happy path — no captioning ───────────────────────────────────────────


def test_happy_path_no_captioning_builds_one_chapter(client: TestClient):
    body = _base_body(
        pdf_bytes_b64=_make_pdf_b64(["First page text.", "Second page text."]),
        page_start=1,
        page_end=2,
    )
    resp = client.post("/internal/parse/pdf-chunk", json=body, headers=_INTERNAL_TOKEN_HEADER)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    chapter = data["chapter"]
    assert chapter["title"].startswith("Pages 1-2")
    assert len(chapter["scenes"]) == 1
    assert "First page text." in chapter["scenes"][0]["leaf_text"]
    assert "Second page text." in chapter["scenes"][0]["leaf_text"]
    assert data["images"] == []


def test_guess_heading_rejects_cjk_sentence_punctuation():
    # /review-impl 2026-07-06 — the terminal-punctuation check was
    # originally ASCII-only (".,;:"); a CJK sentence ending in "。" was
    # incorrectly treated as heading-like. Multilingual standard: no
    # ASCII-only punctuation checks.
    assert internal_parse_pdf._guess_heading("這是一個句子，不是標題。") is None


def test_guess_heading_accepts_a_plausible_heading_line():
    assert internal_parse_pdf._guess_heading("Section 1.2: Throughput Benchmarks") == (
        "Section 1.2: Throughput Benchmarks"
    )


def test_no_captioning_extracts_images_uncaptioned(client: TestClient):
    chart = _make_png(200, 200, (0, 0, 255))
    body = _base_body(pdf_bytes_b64=_make_pdf_with_image_b64("chart page", chart))
    resp = client.post("/internal/parse/pdf-chunk", json=body, headers=_INTERNAL_TOKEN_HEADER)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["images"]) == 1
    assert data["images"][0]["caption"] is None
    # No image markers should be inlined into the chapter text when
    # nothing was captioned.
    assert "[Image" not in data["chapter"]["scenes"][0]["leaf_text"]


# ── Happy path — with captioning (mocked LLM client) ─────────────────────


def test_captioning_inlines_caption_into_chapter_text(client: TestClient, monkeypatch):
    chart = _make_png(200, 200, (0, 255, 0))
    body = _base_body(
        pdf_bytes_b64=_make_pdf_with_image_b64("chart page", chart),
        caption_images=True,
        user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
        model_source="user_model",
        model_ref="019eadbe-8027-77f2-af80-35e71c71cba5",
    )

    fake_job = SimpleNamespace(status="completed", result={"caption": "A green square chart."})
    fake_llm = SimpleNamespace(submit_and_wait=AsyncMock(return_value=fake_job))
    monkeypatch.setattr(internal_parse_pdf, "get_llm_client", lambda: fake_llm)

    resp = client.post("/internal/parse/pdf-chunk", json=body, headers=_INTERNAL_TOKEN_HEADER)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["images"][0]["caption"] == "A green square chart."
    assert "[Image (page 1): A green square chart.]" in data["chapter"]["scenes"][0]["leaf_text"]
    fake_llm.submit_and_wait.assert_awaited_once()
    call_kwargs = fake_llm.submit_and_wait.call_args.kwargs
    assert call_kwargs["operation"] == "vision"
    assert call_kwargs["model_ref"] == "019eadbe-8027-77f2-af80-35e71c71cba5"


def test_captioning_degrades_gracefully_on_llm_failure(client: TestClient, monkeypatch):
    chart = _make_png(200, 200, (255, 255, 0))
    body = _base_body(
        pdf_bytes_b64=_make_pdf_with_image_b64("chart page", chart),
        caption_images=True,
        user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
        model_source="user_model",
        model_ref="019eadbe-8027-77f2-af80-35e71c71cba5",
    )

    fake_llm = SimpleNamespace(submit_and_wait=AsyncMock(side_effect=RuntimeError("upstream down")))
    monkeypatch.setattr(internal_parse_pdf, "get_llm_client", lambda: fake_llm)

    resp = client.post("/internal/parse/pdf-chunk", json=body, headers=_INTERNAL_TOKEN_HEADER)
    # The chunk must still succeed — a captioning failure is advisory,
    # never fatal (spec §6.4/§6.7).
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["images"][0]["caption"] is None
    assert "[Image" not in data["chapter"]["scenes"][0]["leaf_text"]


def test_captioning_dedups_repeated_image_within_chunk(client: TestClient, monkeypatch):
    logo = _make_png(200, 200, (10, 20, 30))
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), "page with logo")
        page.insert_image(fitz.Rect(72, 150, 272, 350), stream=logo)
    data_bytes = doc.tobytes()
    doc.close()

    body = _base_body(
        pdf_bytes_b64=base64.b64encode(data_bytes).decode(),
        page_start=1,
        page_end=2,
        caption_images=True,
        user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
        model_source="user_model",
        model_ref="019eadbe-8027-77f2-af80-35e71c71cba5",
    )

    fake_job = SimpleNamespace(status="completed", result={"caption": "A logo."})
    fake_llm = SimpleNamespace(submit_and_wait=AsyncMock(return_value=fake_job))
    monkeypatch.setattr(internal_parse_pdf, "get_llm_client", lambda: fake_llm)

    resp = client.post("/internal/parse/pdf-chunk", json=body, headers=_INTERNAL_TOKEN_HEADER)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # pdf_walker already dedupes identical images across pages within one
    # walk — only one ExtractedImage should come back, so only one vision
    # call should have been made.
    assert len(data["images"]) == 1
    fake_llm.submit_and_wait.assert_awaited_once()
