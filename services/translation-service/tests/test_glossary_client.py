"""
Unit tests for glossary_client module (V2 P4).

Covers:
- build_glossary_context: scoring, token budget, correction map
- auto_correct_glossary: source term replacement
"""
import pytest

from app.workers.glossary_client import (
    build_glossary_context,
    auto_correct_glossary,
    GlossaryContext,
    GlossaryEntry,
)


# ── Sample data ──────────────────────────────────────────────────────────────

SAMPLE_ENTRIES = [
    {"zh": ["伊斯坦莎"], "vi": ["Isutansha"], "kind": "character"},
    {"zh": ["提拉米", "提拉米·苏兰特"], "vi": ["Tirami", "Tirami Sulant"], "kind": "character"},
    {"zh": ["阿尔德里克"], "vi": ["Aldric"], "kind": "character"},
    {"zh": ["暗黑魔殿"], "vi": ["Hắc Ám Ma Điện"], "kind": "location"},
    {"zh": ["魔族"], "vi": ["Ma tộc"], "kind": "race"},
]

CHAPTER_TEXT = (
    "伊斯坦莎从沉睡中苏醒，黑色的长发散落在暗黑魔殿的王座之上。"
    "「陛下，勇者提拉米已经率领圣骑士团穿过了北方的冰原。」"
    "暗影侍卫长阿尔德里克单膝跪地。他是魔族中为数不多的混血种。"
    "「三日……」伊斯坦莎轻声呢喃。"
    "「阿尔德里克，传令下去。」"
    "伊斯坦莎独自站在空旷的王座大厅中。提拉米和他的军队带来的圣光力量扭曲了天象。"
    "「提拉米……你这个固执的家伙。」"
)


# ── build_glossary_context ───────────────────────────────────────────────

class TestBuildGlossaryContext:
    def test_basic_build(self):
        ctx = build_glossary_context(SAMPLE_ENTRIES, CHAPTER_TEXT, "vi")
        assert len(ctx.entries) > 0
        assert ctx.prompt_block != ""
        assert ctx.token_estimate > 0

    def test_entries_scored_by_occurrence(self):
        """Most-occurring entities should be first."""
        ctx = build_glossary_context(SAMPLE_ENTRIES, CHAPTER_TEXT, "vi")
        # 伊斯坦莎 appears 3x, 提拉米 appears 3x, 阿尔德里克 appears 2x
        names = [e.zh_names[0] for e in ctx.entries]
        # Top entries should be the most frequent
        assert "伊斯坦莎" in names[:3]
        assert "提拉米" in names[:3]

    def test_prompt_block_contains_glossary(self):
        ctx = build_glossary_context(SAMPLE_ENTRIES, CHAPTER_TEXT, "vi")
        assert "GLOSSARY" in ctx.prompt_block
        assert "Isutansha" in ctx.prompt_block
        assert "Tirami" in ctx.prompt_block
        assert "Aldric" in ctx.prompt_block

    def test_correction_map_built(self):
        ctx = build_glossary_context(SAMPLE_ENTRIES, CHAPTER_TEXT, "vi")
        assert ctx.correction_map["伊斯坦莎"] == "Isutansha"
        assert ctx.correction_map["提拉米"] == "Tirami"
        assert ctx.correction_map["阿尔德里克"] == "Aldric"

    def test_empty_entries(self):
        ctx = build_glossary_context([], CHAPTER_TEXT, "vi")
        assert ctx.entries == []
        assert ctx.prompt_block == ""
        assert ctx.correction_map == {}

    def test_empty_chapter_text(self):
        """Entities not in text get score 0 but are still included (pinned/Tier 0)."""
        ctx = build_glossary_context(SAMPLE_ENTRIES, "", "vi")
        # Score 0 entries still included — they serve as Tier 0 pinned glossary
        assert len(ctx.entries) == len(SAMPLE_ENTRIES)

    def test_token_budget_cap(self):
        """With a tiny token budget, not all entries should fit."""
        ctx = build_glossary_context(SAMPLE_ENTRIES, CHAPTER_TEXT, "vi", max_tokens=30)
        # Only 1-2 entries should fit in 30 tokens
        assert len(ctx.entries) < len(SAMPLE_ENTRIES)

    def test_entries_without_target_translation(self):
        """Entries with no target translation should still be included (ZH only)."""
        entries = [{"zh": ["新角色"], "kind": "character"}]
        text = "新角色出现了。"
        ctx = build_glossary_context(entries, text, "vi")
        assert len(ctx.entries) == 1
        assert ctx.entries[0].target_names == []
        assert "新角色" in ctx.prompt_block

    def test_jsonl_format(self):
        """Each entry should be valid JSON."""
        import json
        ctx = build_glossary_context(SAMPLE_ENTRIES, CHAPTER_TEXT, "vi")
        lines = ctx.prompt_block.split("\n")[1:]  # skip header
        for line in lines:
            if line.strip():
                parsed = json.loads(line)
                assert "zh" in parsed
                assert "kind" in parsed


# ── auto_correct_glossary ────────────────────────────────────────────────

class TestAutoCorrectGlossary:
    def test_replaces_source_terms(self):
        correction_map = {"伊斯坦莎": "Isutansha", "提拉米": "Tirami"}
        text = "Istansa tỉnh giấc. 伊斯坦莎 nói với 提拉米."
        corrected, count = auto_correct_glossary(text, correction_map)
        assert "Isutansha" in corrected
        assert "Tirami" in corrected
        assert "伊斯坦莎" not in corrected
        assert "提拉米" not in corrected
        assert count == 2

    def test_no_corrections_needed(self):
        correction_map = {"伊斯坦莎": "Isutansha"}
        text = "Isutansha tỉnh giấc từ giấc ngủ sâu."
        corrected, count = auto_correct_glossary(text, correction_map)
        assert corrected == text
        assert count == 0

    def test_empty_correction_map(self):
        text = "Some translated text with 伊斯坦莎."
        corrected, count = auto_correct_glossary(text, {})
        assert corrected == text
        assert count == 0

    def test_multiple_occurrences(self):
        correction_map = {"提拉米": "Tirami"}
        text = "提拉米 đã đến. 提拉米 rất mạnh."
        corrected, count = auto_correct_glossary(text, correction_map)
        assert corrected.count("Tirami") == 2
        assert count == 2

    def test_preserves_surrounding_text(self):
        correction_map = {"魔族": "Ma tộc"}
        text = "Anh ta là người 魔族 duy nhất."
        corrected, count = auto_correct_glossary(text, correction_map)
        assert corrected == "Anh ta là người Ma tộc duy nhất."
        assert count == 1
