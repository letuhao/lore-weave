"""Unit tests for block_batcher module — V2 with expansion ratio + block cap."""
import pytest
from app.workers.block_batcher import (
    build_batch_plan,
    parse_translated_blocks,
    compute_input_budget,
    get_expansion_ratio,
    MAX_BLOCKS_PER_BATCH,
    _lang_category,
)


# ── language helpers ─────────────────────────────────────────────────────────

class TestLangCategory:
    def test_chinese(self):
        assert _lang_category("zh") == "cjk"
        assert _lang_category("zh-hans") == "cjk"

    def test_japanese(self):
        assert _lang_category("ja") == "cjk"

    def test_korean(self):
        assert _lang_category("ko") == "cjk"

    def test_latin(self):
        assert _lang_category("en") == "latin"
        assert _lang_category("vi") == "latin"
        assert _lang_category("fr") == "latin"

    def test_empty(self):
        assert _lang_category("") == "latin"


class TestExpansionRatio:
    def test_cjk_to_latin(self):
        ratio = get_expansion_ratio("zh", "vi")
        assert ratio == 2.0

    def test_cjk_to_cjk(self):
        ratio = get_expansion_ratio("zh", "ja")
        assert ratio == 1.2

    def test_latin_to_latin(self):
        ratio = get_expansion_ratio("en", "fr")
        assert ratio == 1.3

    def test_unknown_pair_defaults_to_latin(self):
        # "ar" and "th" both classify as "latin" → latin→latin ratio
        ratio = get_expansion_ratio("ar", "th")
        assert ratio == 1.3


class TestComputeInputBudget:
    def test_basic_budget(self):
        # 32000 ctx, zh→vi (ratio 2.0)
        # overhead = 500 + 1500 + 300 = 2300
        # available = 29700
        # input = 29700 / (1 + 2.0) = 9900
        budget = compute_input_budget(32000, "zh", "vi")
        assert budget == 9900

    def test_small_context_window(self):
        budget = compute_input_budget(1000, "zh", "vi")
        assert budget >= 100  # floor

    def test_no_languages_uses_latin_default(self):
        budget = compute_input_budget(32000)
        # empty lang → "latin" → latin→latin ratio = 1.3
        # overhead = 500 + 1500 + 300 = 2300
        # available = 29700, input = 29700 / (1 + 1.3) = 12913
        assert budget == 12913


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
        assert plan.translatable_count == 3
        assert plan.passthrough_count == 2
        assert plan.caption_count == 1

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
        assert 2 not in batch_indices
        assert 5 not in batch_indices

    def test_caption_in_batches(self):
        plan = build_batch_plan(self._blocks())
        batch_indices = set()
        for b in plan.batches:
            batch_indices.update(b.block_indices)
        assert 4 in batch_indices

    def test_combined_text_has_markers(self):
        plan = build_batch_plan(self._blocks())
        text = plan.batches[0].combined_text()
        assert "[BLOCK 0]" in text
        assert "[BLOCK 1]" in text

    def test_language_aware_budget(self):
        """With source/target langs, uses expansion-ratio-aware budget."""
        long_blocks = [
            {"type": "paragraph", "content": [{"type": "text", "text": "A " * 200}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "B " * 200}]},
        ]
        plan = build_batch_plan(
            long_blocks, context_window_tokens=500,
            source_lang="zh", target_lang="vi",
        )
        assert len(plan.batches) >= 1

    def test_empty_blocks(self):
        plan = build_batch_plan([])
        assert len(plan.batches) == 0
        assert len(plan.all_entries) == 0

    def test_all_passthrough(self):
        blocks = [
            {"type": "codeBlock", "content": [{"type": "text", "text": "x"}]},
            {"type": "horizontalRule"},
        ]
        plan = build_batch_plan(blocks)
        assert len(plan.batches) == 0

    def test_block_count_cap(self):
        """No batch should exceed MAX_BLOCKS_PER_BATCH."""
        # Create 60 small blocks
        blocks = [
            {"type": "paragraph", "content": [{"type": "text", "text": f"Block {i}"}]}
            for i in range(60)
        ]
        plan = build_batch_plan(blocks, context_window_tokens=100000)
        for batch in plan.batches:
            assert len(batch.entries) <= MAX_BLOCKS_PER_BATCH

    def test_legacy_budget_ratio_fallback(self):
        """Without source/target langs, falls back to budget_ratio."""
        long_blocks = [
            {"type": "paragraph", "content": [{"type": "text", "text": "A " * 200}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "B " * 200}]},
        ]
        # budget_ratio=0.25 → 500*0.25 = 125 tokens
        plan = build_batch_plan(long_blocks, context_window_tokens=500)
        assert len(plan.batches) >= 2


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
