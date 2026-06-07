"""B3 prose_doc tests — text→Tiptap doc must mirror book-service tiptap.go."""

from __future__ import annotations

from app.engine.prose_doc import text_to_tiptap_doc


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
