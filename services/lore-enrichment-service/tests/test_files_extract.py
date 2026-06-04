"""Mode-F text extraction (app/files/extract.py) — unit tests.

Covers the pure dispatch + the formats that fixture cleanly in-process (txt/md/docx
+ a blank PDF exercising the OCR-fallback graceful-degradation path). PDF-with-text
and epub + real OCR are covered by the live smoke (need binaries/large fixtures).
"""

from __future__ import annotations

import io

import pytest

from app.files.extract import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFileError,
    extract_text,
    file_extension,
    tesseract_lang_for,
)


def test_file_extension_lowercases():
    assert file_extension("A.PDF") == ".pdf"
    assert file_extension("notes.MD") == ".md"
    assert file_extension("noext") == ""


@pytest.mark.parametrize("name", ["a.txt", "a.md"])
def test_txt_md_decode(name):
    r = extract_text(name, "蓬萊乃東海仙山。\n仙人所居。".encode("utf-8"))
    assert "蓬萊" in r.text and "仙人所居" in r.text
    assert r.pages == 1 and r.ocr_used is False


def test_txt_strips_and_handles_bad_bytes():
    r = extract_text("a.txt", b"  hi \xff\xfe ")  # invalid utf-8 → replaced, trimmed
    assert r.text.startswith("hi")


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedFileError):
        extract_text("malware.exe", b"MZ...")
    assert ".exe" not in SUPPORTED_EXTENSIONS


def test_docx_roundtrip():
    docx = pytest.importorskip("docx")  # python-docx
    document = docx.Document()
    document.add_paragraph("第一段：蓬萊。")
    document.add_paragraph("第二段：仙人。")
    buf = io.BytesIO()
    document.save(buf)
    r = extract_text("ref.docx", buf.getvalue())
    assert "蓬萊" in r.text and "仙人" in r.text
    assert r.ocr_used is False


def test_blank_pdf_no_text_ocr_degrades_gracefully():
    # A blank (no text-layer) PDF routes to OCR; without the Tesseract binary the
    # OCR path degrades to {} → ocr_used False + empty text, NEVER a crash.
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    r = extract_text("scan.pdf", buf.getvalue())
    assert r.pages == 1
    assert r.text == ""        # no text layer, OCR unavailable → empty (not a crash)
    assert r.ocr_used is False


def test_pdf_ocr_used_flag_when_ocr_returns_text(monkeypatch):
    # When OCR IS available, a no-text page picks up the OCR'd text + flags ocr_used.
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    import app.files.extract as ex
    monkeypatch.setattr(ex, "_ocr_pdf_pages", lambda data, indices, *, max_pages, lang=None: {0: "OCR文字"})
    r = extract_text("scan.pdf", buf.getvalue())
    assert r.ocr_used is True
    assert "OCR文字" in r.text


def test_pdf_ocr_lang_threaded_from_caller(monkeypatch):
    # extract_text(lang=...) reaches _ocr_pdf_pages so a book-aware lang is honored.
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    import app.files.extract as ex
    seen: dict[str, str | None] = {}

    def _spy(data, indices, *, max_pages, lang=None):
        seen["lang"] = lang
        return {0: "x"}

    monkeypatch.setattr(ex, "_ocr_pdf_pages", _spy)
    extract_text("scan.pdf", buf.getvalue(), lang="eng")
    assert seen["lang"] == "eng"


# ── tesseract_lang_for (D-COMPOSE-S3-OCR-LANG) — book-aware OCR language ──────
def test_tesseract_lang_for_chinese_variants():
    assert tesseract_lang_for("zh") == "chi_sim+chi_tra+eng"
    assert tesseract_lang_for("zh-TW") == "chi_tra+eng"   # Traditional → traditional pack
    assert tesseract_lang_for("zh-Hans") == "chi_sim+eng"


def test_tesseract_lang_for_installed_non_cjk():
    assert tesseract_lang_for("en") == "eng"
    assert tesseract_lang_for("ja") == "jpn+eng"
    assert tesseract_lang_for("vi") == "vie+eng"
    assert tesseract_lang_for("Japanese") == "jpn+eng"  # full name + base fallback


def test_tesseract_lang_for_auto_and_unknown_default():
    default = "chi_sim+chi_tra+eng"
    assert tesseract_lang_for("auto") == default
    assert tesseract_lang_for("") == default
    assert tesseract_lang_for(None) == default
    # A real language whose pack is NOT installed (e.g. Korean) → safe superset,
    # never a request for a missing 'kor' pack (which would fail OCR entirely).
    assert tesseract_lang_for("ko") == default
    assert tesseract_lang_for("xx-unknown") == default
