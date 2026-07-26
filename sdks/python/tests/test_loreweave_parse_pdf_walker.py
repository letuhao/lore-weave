"""pdf_walker tests — docs/specs/2026-07-06-pdf-book-import.md.

Fixtures are built programmatically via PyMuPDF (fitz) itself so the
suite has no binary test-asset files to maintain.
"""

from __future__ import annotations

import io

import fitz
import pytest
from PIL import Image

from loreweave_parse.pdf_walker import (
    DEFAULT_VISION_MAX_DIMENSION_PX,
    MIN_IMAGE_DIMENSION_PX,
    PdfOpenError,
    downscale_for_vision,
    get_page_count,
    tesseract_lang_for,
    walk_pdf_pages,
)


def _make_pdf(page_texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf_with_images(pages_images: list[list[bytes]]) -> bytes:
    """pages_images[i] is a list of PNG bytes to insert on page i."""
    doc = fitz.open()
    for images in pages_images:
        page = doc.new_page()
        page.insert_text((72, 72), "page text")
        y = 100
        for img_bytes in images:
            rect = fitz.Rect(72, y, 172, y + 100)
            page.insert_image(rect, stream=img_bytes)
            y += 110
    data = doc.tobytes()
    doc.close()
    return data


# ─── get_page_count ────────────────────────────────────────────────────


def test_get_page_count_returns_correct_count():
    data = _make_pdf(["one", "two", "three"])
    assert get_page_count(data) == 3


def test_get_page_count_corrupted_raises():
    with pytest.raises(PdfOpenError):
        get_page_count(b"not a pdf at all")


def test_get_page_count_encrypted_raises():
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    with pytest.raises(PdfOpenError):
        get_page_count(data)


# ─── walk_pdf_pages — text ─────────────────────────────────────────────


def test_walk_pdf_pages_extracts_text_per_page():
    data = _make_pdf(["Hello page one", "Hello page two", "Hello page three"])
    result = walk_pdf_pages(data, page_start=1, page_end=2)
    assert [p.page_number for p in result.pages] == [1, 2]
    assert "Hello page one" in result.pages[0].text
    assert "Hello page two" in result.pages[1].text
    assert all(not p.ocr_used for p in result.pages)


def test_walk_pdf_pages_clamps_page_end_to_page_count():
    data = _make_pdf(["one", "two"])
    result = walk_pdf_pages(data, page_start=1, page_end=999)
    assert [p.page_number for p in result.pages] == [1, 2]


def test_walk_pdf_pages_clamps_page_start_minimum():
    data = _make_pdf(["one", "two"])
    result = walk_pdf_pages(data, page_start=0, page_end=1)
    assert [p.page_number for p in result.pages] == [1]


def test_walk_pdf_pages_corrupted_raises():
    with pytest.raises(PdfOpenError):
        walk_pdf_pages(b"garbage", page_start=1, page_end=1)


# ─── walk_pdf_pages — images ────────────────────────────────────────────


def test_walk_pdf_pages_extracts_images():
    chart = _make_png(200, 200, (0, 0, 255))
    data = _make_pdf_with_images([[chart]])
    result = walk_pdf_pages(data, page_start=1, page_end=1)
    assert len(result.images) == 1
    assert result.images[0].page_number == 1
    assert result.images[0].data


def test_walk_pdf_pages_dedups_repeated_image_across_pages():
    logo = _make_png(200, 200, (255, 0, 0))
    chart = _make_png(200, 200, (0, 255, 0))
    data = _make_pdf_with_images([[logo], [logo], [chart]])
    result = walk_pdf_pages(data, page_start=1, page_end=3)
    # The repeated logo should only be captured once (first occurrence,
    # page 1), plus the distinct chart on page 3 — 2 total, not 3.
    assert len(result.images) == 2
    hashes = {img.content_hash for img in result.images}
    assert len(hashes) == 2
    logo_entry = next(img for img in result.images if img.page_number == 1)
    assert logo_entry is not None


def test_walk_pdf_pages_skips_tiny_decorative_images():
    tiny = _make_png(MIN_IMAGE_DIMENSION_PX - 1, MIN_IMAGE_DIMENSION_PX - 1, (10, 10, 10))
    data = _make_pdf_with_images([[tiny]])
    result = walk_pdf_pages(data, page_start=1, page_end=1)
    assert result.images == []


def test_walk_pdf_pages_keeps_images_at_min_dimension():
    ok = _make_png(MIN_IMAGE_DIMENSION_PX, MIN_IMAGE_DIMENSION_PX, (10, 10, 10))
    data = _make_pdf_with_images([[ok]])
    result = walk_pdf_pages(data, page_start=1, page_end=1)
    assert len(result.images) == 1


# ─── tesseract_lang_for ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (None, "chi_sim+chi_tra+eng"),
        ("auto", "chi_sim+chi_tra+eng"),
        ("en", "eng"),
        ("vi", "vie+eng"),
        ("ja", "jpn+eng"),
        ("zh-tw", "chi_tra+eng"),
        ("totally-unknown-lang", "chi_sim+chi_tra+eng"),
    ],
)
def test_tesseract_lang_for(language, expected):
    assert tesseract_lang_for(language) == expected


# ─── downscale_for_vision ───────────────────────────────────────────────


def test_downscale_for_vision_noop_when_already_small():
    small = _make_png(100, 100, (1, 2, 3))
    assert downscale_for_vision(small) == small


def test_downscale_for_vision_resizes_oversized_image():
    big = _make_png(3000, 1000, (1, 2, 3))
    out = downscale_for_vision(big, max_dimension=DEFAULT_VISION_MAX_DIMENSION_PX)
    resized = Image.open(io.BytesIO(out))
    assert max(resized.size) <= DEFAULT_VISION_MAX_DIMENSION_PX
    assert out != big


def test_downscale_for_vision_never_raises_on_garbage():
    # Not a real image — must degrade to returning the input, not raise.
    garbage = b"not an image"
    assert downscale_for_vision(garbage) == garbage
