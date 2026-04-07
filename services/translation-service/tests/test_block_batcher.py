"""Unit tests for block_batcher module (TF-13)."""
import pytest
from app.workers.block_batcher import build_batch_plan, parse_translated_blocks


# ── build_batch_plan ─────────────────────────────────────────────────────────

class TestBuildBatchPlan:
    def _blocks(self):
        return [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Chapter One"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "First paragraph."}]},
            {"type": "codeBlock", "content": [{"type": "text", "text": "let x = 1;"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second paragraph."}]},
            {"type": "imageBlock", "attrs": {"src": "img.png", "caption": "A photo"}},
            {"type": "horizontalRule"},
        ]

    def test_counts(self):
        plan = build_batch_plan(self._blocks())
        assert plan.translatable_count == 3  # heading, 2 paragraphs
        assert plan.passthrough_count == 2   # codeBlock, horizontalRule
        assert plan.caption_count == 1       # imageBlock

    def test_batches_created(self):
        plan = build_batch_plan(self._blocks())
        assert len(plan.batches) >= 1

    def test_all_entries_tracked(self):
        plan = build_batch_plan(self._blocks())
        assert len(plan.all_entries) == 6

    def test_passthrough_not_in_batches(self):
        plan = build_batch_plan(self._blocks())
        batch_indices = set()
        for b in plan.batches:
            batch_indices.update(b.block_indices)
        assert 2 not in batch_indices  # codeBlock at index 2
        assert 5 not in batch_indices  # horizontalRule at index 5

    def test_caption_in_batches(self):
        plan = build_batch_plan(self._blocks())
        batch_indices = set()
        for b in plan.batches:
            batch_indices.update(b.block_indices)
        assert 4 in batch_indices  # imageBlock caption

    def test_combined_text_has_markers(self):
        plan = build_batch_plan(self._blocks())
        text = plan.batches[0].combined_text()
        assert "[BLOCK 0]" in text
        assert "[BLOCK 1]" in text

    def test_small_context_splits_batches(self):
        # Create blocks with enough text to exceed 100 tokens budget
        long_blocks = [
            {"type": "paragraph", "content": [{"type": "text", "text": "A " * 200}]},  # ~114 tokens
            {"type": "paragraph", "content": [{"type": "text", "text": "B " * 200}]},  # ~114 tokens
        ]
        plan = build_batch_plan(long_blocks, context_window_tokens=500)
        # Budget = 500 * 0.25 = 125 tokens, each block ~114, so should split
        assert len(plan.batches) >= 2

    def test_empty_blocks(self):
        plan = build_batch_plan([])
        assert len(plan.batches) == 0
        assert len(plan.all_entries) == 0

    def test_all_passthrough(self):
        blocks = [{"type": "codeBlock", "content": [{"type": "text", "text": "x"}]},
                  {"type": "horizontalRule"}]
        plan = build_batch_plan(blocks)
        assert len(plan.batches) == 0


# ── parse_translated_blocks ──────────────────────────────────────────────────

class TestParseTranslatedBlocks:
    def test_basic_parse(self):
        response = "[BLOCK 0]\nChương Một\n\n[BLOCK 1]\nĐoạn đầu tiên."
        result = parse_translated_blocks(response, [0, 1])
        assert result[0] == "Chương Một"
        assert result[1] == "Đoạn đầu tiên."

    def test_extra_block_ignored(self):
        response = "[BLOCK 0]\nHello\n\n[BLOCK 99]\nExtra"
        result = parse_translated_blocks(response, [0])
        assert 0 in result
        assert 99 not in result

    def test_missing_block(self):
        response = "[BLOCK 0]\nHello"
        result = parse_translated_blocks(response, [0, 1])
        assert 0 in result
        assert 1 not in result

    def test_empty_response(self):
        result = parse_translated_blocks("", [0, 1])
        assert len(result) == 0

    def test_multiline_block_text(self):
        response = "[BLOCK 0]\nLine one\nLine two\n\n[BLOCK 1]\nSingle line"
        result = parse_translated_blocks(response, [0, 1])
        assert "Line one\nLine two" == result[0]
