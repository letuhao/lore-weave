"""B3 prose_doc tests — text→Tiptap doc must mirror book-service tiptap.go."""

from __future__ import annotations

from app.engine.prose_doc import text_to_tiptap_doc, tiptap_doc_to_text


# ── C27 — tiptap_doc_to_text (flywheel chapter-text extraction) ─────────


def test_tiptap_doc_to_text_round_trips_via_snapshot():
    doc = text_to_tiptap_doc("First para.\n\nSecond para.")
    assert tiptap_doc_to_text(doc) == "First para.\n\nSecond para."


def test_tiptap_doc_to_text_falls_back_to_inline_runs():
    # a block with no _text snapshot (e.g. imported) → concatenate content[].text.
    doc = {"type": "doc", "content": [
        {"type": "paragraph", "content": [
            {"type": "text", "text": "Hello "}, {"type": "text", "text": "world."},
        ]},
    ]}
    assert tiptap_doc_to_text(doc) == "Hello world."


def test_tiptap_doc_to_text_degrades_to_empty_on_garbage():
    assert tiptap_doc_to_text(None) == ""
    assert tiptap_doc_to_text({"type": "doc"}) == ""
    assert tiptap_doc_to_text({"type": "doc", "content": []}) == ""


def test_paragraphs_split_on_blank_line_with_text_snapshot():
    doc = text_to_tiptap_doc("Hello world.\n\nSecond para.")
    assert doc["type"] == "doc" and len(doc["content"]) == 2
    # exact shape book-service produces: top-level _text + a text content node
    assert doc["content"][0] == {
        "type": "paragraph", "_text": "Hello world.",
        "content": [{"type": "text", "text": "Hello world."}]}


def test_empty_paragraph_has_no_content_node():
    # "A\n\n\n\nB" → ["A", "", "B"]; the middle empty paragraph carries no content
    # (matches tiptap.go — the chapter_blocks trigger reads _text="").
    doc = text_to_tiptap_doc("A\n\n\n\nB")
    assert {"type": "paragraph", "_text": ""} in doc["content"]
    assert len(doc["content"]) == 3


def test_crlf_normalized_to_lf():
    doc = text_to_tiptap_doc("A\r\n\r\nB")
    assert len(doc["content"]) == 2 and doc["content"][1]["_text"] == "B"


def test_trailing_newlines_stripped_per_paragraph():
    doc = text_to_tiptap_doc("A\n")
    assert doc["content"][0]["_text"] == "A"
