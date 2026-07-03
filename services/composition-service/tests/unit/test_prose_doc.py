"""B3 prose_doc tests — text→Tiptap doc must mirror book-service tiptap.go."""

from __future__ import annotations

from app.engine.prose_doc import normalize_title, text_to_tiptap_doc, tiptap_doc_to_text


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


# ── F4a (D-SCENEMARKER-EMIT) — ATX headings + sceneId attach ─────────────


def test_atx_heading_becomes_heading_node_tiptap_go_shape():
    doc = text_to_tiptap_doc("### Cuộc Truy Sát Trong Đêm\n\nProse here.")
    assert doc["content"][0] == {
        "type": "heading", "attrs": {"level": 3},
        "_text": "Cuộc Truy Sát Trong Đêm",
        "content": [{"type": "text", "text": "Cuộc Truy Sát Trong Đêm"}]}
    assert doc["content"][1]["type"] == "paragraph"


def test_heading_level_clamped_to_3():
    doc = text_to_tiptap_doc("##### Deep")
    assert doc["content"][0]["attrs"] == {"level": 3}
    # exactly-heading block → NO trailing empty paragraph
    assert len(doc["content"]) == 1


def test_heading_and_prose_in_one_block_split():
    # tiptap.go handles "### Title\nprose..." in ONE blank-line block.
    doc = text_to_tiptap_doc("## T\nline one\nline two")
    assert doc["content"][0]["type"] == "heading"
    # the remainder keeps intra-block newlines (plain-variant paragraph shape)
    assert doc["content"][1]["_text"] == "line one\nline two"


def test_non_heading_hash_line_stays_paragraph():
    # "#no space" and a mid-block heading line are NOT lifted (leading lines only).
    doc = text_to_tiptap_doc("#nospace\n\nprose\n### mid-block")
    assert all(n["type"] == "paragraph" for n in doc["content"])
    assert doc["content"][1]["_text"] == "prose\n### mid-block"


def test_scene_id_attached_on_unique_title_match():
    scenes = [{"id": "s-1", "title": "Cuộc Truy Sát Trong Đêm"},
              {"id": "s-2", "title": "Bên Bờ Suối"}]
    doc = text_to_tiptap_doc(
        "### CUỘC TRUY SÁT TRONG ĐÊM!\n\nProse.\n\n### Bên bờ suối\n\nMore.", scenes)
    heads = [n for n in doc["content"] if n["type"] == "heading"]
    # case + trailing punctuation folded; DIACRITICS significant
    assert heads[0]["attrs"] == {"level": 3, "sceneId": "s-1"}
    assert heads[1]["attrs"] == {"level": 3, "sceneId": "s-2"}


def test_ambiguous_duplicate_headings_left_unmarked():
    scenes = [{"id": "s-1", "title": "Đêm"}]
    doc = text_to_tiptap_doc("### Đêm\n\nProse.\n\n### Đêm\n\nMore.", scenes)
    heads = [n for n in doc["content"] if n["type"] == "heading"]
    assert all("sceneId" not in h["attrs"] for h in heads)


def test_unmatched_scene_and_diacritic_mismatch_no_marker():
    # "Sát" vs "Sat" must NOT match (VN tone marks are significant).
    doc = text_to_tiptap_doc("### Truy Sat\n\nProse.", [{"id": "s-1", "title": "Truy Sát"}])
    assert "sceneId" not in doc["content"][0]["attrs"]


def test_no_scenes_arg_keeps_prior_paragraph_behavior():
    # A heading-free text is byte-identical with and without the scenes arg.
    assert text_to_tiptap_doc("A\n\nB") == text_to_tiptap_doc("A\n\nB", [])


def test_normalize_title_port_matches_fe():
    assert normalize_title("  Cuộc   Truy Sát Trong Đêm…—  ") == "cuộc truy sát trong đêm"
    assert normalize_title("...") == ""
