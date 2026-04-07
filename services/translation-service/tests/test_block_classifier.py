"""Unit tests for block_classifier module (TF-13)."""
import pytest
from app.workers.block_classifier import (
    classify_block,
    extract_translatable_text,
    rebuild_block,
    _inline_to_text,
    _text_to_inline,
)


# ── classify_block ──────────────────────────────────────────────────────────

class TestClassifyBlock:
    @pytest.mark.parametrize("btype", ["paragraph", "heading", "blockquote", "callout", "bulletList", "orderedList"])
    def test_translate_types(self, btype):
        assert classify_block({"type": btype}) == "translate"

    @pytest.mark.parametrize("btype", ["horizontalRule", "codeBlock"])
    def test_passthrough_types(self, btype):
        assert classify_block({"type": btype}) == "passthrough"

    @pytest.mark.parametrize("btype", ["imageBlock", "videoBlock", "audioBlock"])
    def test_caption_only_types(self, btype):
        assert classify_block({"type": btype}) == "caption_only"

    def test_unknown_type_is_passthrough(self):
        assert classify_block({"type": "foobar"}) == "passthrough"

    def test_missing_type_is_passthrough(self):
        assert classify_block({}) == "passthrough"


# ── extract_translatable_text ────────────────────────────────────────────────

class TestExtractText:
    def test_paragraph_plain(self):
        block = {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}
        assert extract_translatable_text(block) == "Hello world"

    def test_paragraph_with_marks(self):
        block = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "bold", "marks": [{"type": "bold"}]},
                {"type": "text", "text": " world"},
            ],
        }
        assert extract_translatable_text(block) == "Hello **bold** world"

    def test_heading(self):
        block = {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Title"}]}
        assert extract_translatable_text(block) == "Title"

    def test_code_block_returns_empty(self):
        block = {"type": "codeBlock", "content": [{"type": "text", "text": "let x = 1;"}]}
        assert extract_translatable_text(block) == ""

    def test_image_block_returns_caption(self):
        block = {"type": "imageBlock", "attrs": {"src": "x.png", "caption": "A photo"}}
        assert extract_translatable_text(block) == "A photo"

    def test_image_block_no_caption(self):
        block = {"type": "imageBlock", "attrs": {"src": "x.png"}}
        assert extract_translatable_text(block) == ""

    def test_bullet_list(self):
        block = {
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "First"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Second"}]}]},
            ],
        }
        assert extract_translatable_text(block) == "First\nSecond"

    def test_link_mark(self):
        block = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Click "},
                {"type": "text", "text": "here", "marks": [{"type": "link", "attrs": {"href": "https://x.com"}}]},
            ],
        }
        assert extract_translatable_text(block) == "Click [here](https://x.com)"


# ── inline mark round-trip ──────────────────────────────────────────────────

class TestInlineRoundTrip:
    def test_bold(self):
        text = _inline_to_text([{"type": "text", "text": "bold", "marks": [{"type": "bold"}]}])
        assert text == "**bold**"
        nodes = _text_to_inline(text)
        assert nodes[0]["marks"][0]["type"] == "bold"
        assert nodes[0]["text"] == "bold"

    def test_italic(self):
        text = _inline_to_text([{"type": "text", "text": "em", "marks": [{"type": "italic"}]}])
        assert text == "*em*"

    def test_code(self):
        text = _inline_to_text([{"type": "text", "text": "x", "marks": [{"type": "code"}]}])
        assert text == "`x`"

    def test_link(self):
        nodes = _text_to_inline("[click](https://x.com)")
        assert nodes[0]["text"] == "click"
        assert nodes[0]["marks"][0]["attrs"]["href"] == "https://x.com"

    def test_plain_text(self):
        nodes = _text_to_inline("just plain text")
        assert nodes[0]["text"] == "just plain text"
        assert "marks" not in nodes[0]


# ── rebuild_block ────────────────────────────────────────────────────────────

class TestRebuildBlock:
    def test_paragraph(self):
        orig = {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}
        result = rebuild_block(orig, "Xin chào")
        assert result["content"][0]["text"] == "Xin chào"
        assert result["type"] == "paragraph"

    def test_passthrough(self):
        orig = {"type": "codeBlock", "content": [{"type": "text", "text": "let x = 1;"}]}
        result = rebuild_block(orig, "")
        assert result["content"][0]["text"] == "let x = 1;"

    def test_caption_only(self):
        orig = {"type": "imageBlock", "attrs": {"src": "x.png", "caption": "A photo"}}
        result = rebuild_block(orig, "Một bức ảnh")
        assert result["attrs"]["caption"] == "Một bức ảnh"
        assert result["attrs"]["src"] == "x.png"  # preserved

    def test_preserves_marks_in_rebuild(self):
        orig = {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}
        result = rebuild_block(orig, "Xin **chào** thế giới")
        texts = [n.get("text", "") for n in result["content"]]
        assert "chào" in texts
        bold_nodes = [n for n in result["content"] if n.get("marks")]
        assert bold_nodes[0]["marks"][0]["type"] == "bold"

    def test_does_not_mutate_original(self):
        orig = {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}
        rebuild_block(orig, "Xin chào")
        assert orig["content"][0]["text"] == "Hello"
