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


# ── trust ladder (D-TRANSL-M1D): verified_map vs correction_map ───────────────

class TestTrustLadder:
    """The V3 verifier hard-checks only *canon* translations. build_glossary_context
    splits the glossary into the full ``correction_map`` (V2 auto-correct + prompt,
    unchanged) and a ``verified_map`` subset the V3 verifier enforces."""

    def test_verified_map_keeps_only_verified_confidence(self):
        entries = [
            {"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character", "confidence": "verified"},
            {"zh": ["阿尔德里克"], "vi": ["Aldric"], "kind": "character", "confidence": "machine"},
            {"zh": ["伊斯坦莎"], "vi": ["Isutansha"], "kind": "character", "confidence": "draft"},
        ]
        text = "提拉米 阿尔德里克 伊斯坦莎"
        ctx = build_glossary_context(entries, text, "vi")
        # Full map carries every translated entry (V2 parity).
        assert ctx.correction_map == {
            "提拉米": "Tirami", "阿尔德里克": "Aldric", "伊斯坦莎": "Isutansha",
        }
        # Hard-check map carries ONLY the human-confirmed (verified) one.
        assert ctx.verified_map == {"提拉米": "Tirami"}

    def test_absent_confidence_key_is_legacy_trusted(self):
        """A glossary build that predates the confidence field (key absent) must
        behave exactly as before — every translation hard-checked. Guards the
        rolling-deploy window where translation-service reads confidence before
        glossary-service emits it."""
        entries = [
            {"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character"},
            {"zh": ["魔族"], "vi": ["Ma tộc"], "kind": "race"},
        ]
        text = "提拉米 魔族"
        ctx = build_glossary_context(entries, text, "vi")
        assert ctx.verified_map == ctx.correction_map
        assert ctx.verified_map == {"提拉米": "Tirami", "魔族": "Ma tộc"}

    def test_empty_confidence_string_is_demoted(self):
        """An explicit empty-string confidence (present but blank) is NOT verified —
        only a truly absent key is the legacy escape hatch."""
        entries = [{"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character", "confidence": ""}]
        ctx = build_glossary_context(entries, "提拉米", "vi")
        assert ctx.correction_map == {"提拉米": "Tirami"}
        assert ctx.verified_map == {}

    def test_verified_map_empty_when_no_entries(self):
        ctx = build_glossary_context([], CHAPTER_TEXT, "vi")
        assert ctx.verified_map == {}

    def test_machine_translation_does_not_hard_fail_verifier(self):
        """End-to-end at the unit level: a machine-confidence glossary term that the
        draft renders differently must NOT produce a HIGH wrong_name issue, because
        the verifier is fed verified_map (which excludes it)."""
        from app.workers.v3.verifier import verify_rules
        entries = [{"zh": ["提拉米"], "vi": ["Tirami"], "kind": "character", "confidence": "machine"}]
        ctx = build_glossary_context(entries, "提拉米", "vi")
        report = verify_rules({0: "提拉米 来了"}, {0: "Tilami came"}, ctx.verified_map, "vi")
        assert not any(i.type == "wrong_name" for i in report.issues)
        # And the full map still WOULD have flagged it (proves the demotion is the cause).
        report_full = verify_rules({0: "提拉米 来了"}, {0: "Tilami came"}, ctx.correction_map, "vi")
        assert any(i.type == "wrong_name" for i in report_full.issues)


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


# ── M4d-2b: writeback_name_pairs (target-translation seeding) ─────────────────

class _Pair:
    def __init__(self, source, target, kind="character"):
        self.source = source
        self.target = target
        self.kind = kind


class _WResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._p = payload

    def json(self):
        return self._p


class _WClient:
    last = {}

    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _WClient.last = {"url": url, "json": json, "headers": headers}
        if self._exc:
            raise self._exc
        return self._resp


def _patch_w(monkeypatch, *, url="http://gloss:8088", resp=None, exc=None):
    from app.workers import glossary_client as gc
    monkeypatch.setattr(gc.settings, "glossary_service_internal_url", url)
    monkeypatch.setattr(gc.settings, "internal_service_token", "tok")
    monkeypatch.setattr(gc.httpx, "AsyncClient", lambda *a, **k: _WClient(resp=resp, exc=exc))
    _WClient.last = {}


class TestSanitizeName:
    def test_strips_control_and_collapses(self):
        from app.workers.glossary_client import _sanitize_name
        assert _sanitize_name("提拉\t米  \n苏") == "提拉 米 苏"

    def test_caps_length(self):
        from app.workers.glossary_client import _sanitize_name
        assert len(_sanitize_name("x" * 500)) == 120

    def test_empty(self):
        from app.workers.glossary_client import _sanitize_name
        assert _sanitize_name("") == ""


@pytest.mark.asyncio
class TestWritebackNamePairs:
    async def test_body_shape_and_sanitize_and_skip_empty(self, monkeypatch):
        from app.workers.glossary_client import writeback_name_pairs
        _patch_w(monkeypatch, resp=_WResp(200, {"created": 2}))
        pairs = [_Pair("提拉米", "Tirami"), _Pair("  ", "x"),
                 _Pair("阿尔德里克", "Aldric", "location")]
        res = await writeback_name_pairs("b1", "zh", "vi", pairs)
        assert res == {"created": 2}
        body = _WClient.last["json"]
        assert body["default_tags"] == ["ai-suggested"]
        assert body["park_unknown_kinds"] is False
        assert body["source_language"] == "zh"
        assert len(body["entities"]) == 2  # blank-source pair skipped
        assert body["entities"][0] == {
            "kind_code": "character", "name": "提拉米", "attributes": {},
            "translation": {"language_code": "vi", "value": "Tirami"},
        }
        assert body["entities"][1]["kind_code"] == "location"
        assert _WClient.last["headers"]["X-Internal-Token"] == "tok"
        assert _WClient.last["url"].endswith("/internal/books/b1/extract-entities")

    async def test_null_gate_when_unconfigured(self, monkeypatch):
        from app.workers.glossary_client import writeback_name_pairs
        _patch_w(monkeypatch, url="", resp=_WResp(200, {}))
        assert await writeback_name_pairs("b1", "zh", "vi", [_Pair("a", "b")]) is None
        assert _WClient.last == {}  # no HTTP

    async def test_no_pairs_returns_none(self, monkeypatch):
        from app.workers.glossary_client import writeback_name_pairs
        _patch_w(monkeypatch, resp=_WResp(200, {}))
        assert await writeback_name_pairs("b1", "zh", "vi", []) is None

    async def test_non_200_degrades(self, monkeypatch):
        from app.workers.glossary_client import writeback_name_pairs
        _patch_w(monkeypatch, resp=_WResp(503, {}))
        assert await writeback_name_pairs("b1", "zh", "vi", [_Pair("a", "b")]) is None

    async def test_transport_error_degrades(self, monkeypatch):
        from app.workers.glossary_client import writeback_name_pairs
        _patch_w(monkeypatch, exc=RuntimeError("boom"))
        assert await writeback_name_pairs("b1", "zh", "vi", [_Pair("a", "b")]) is None
