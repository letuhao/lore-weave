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
    monkeypatch.setattr(ex, "_ocr_pdf_pages", lambda data, indices, *, max_pages: {0: "OCR文字"})
    r = extract_text("scan.pdf", buf.getvalue())
    assert r.ocr_used is True
    assert "OCR文字" in r.text
