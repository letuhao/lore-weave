"""M4d-2a: V3 bilingual source→target name extractor — parse + best-effort fetch."""
import pytest

from app.workers.v3.bilingual_extractor import (
    NamePair, parse_name_pairs, extract_name_pairs, build_namepair_block, _MAX_PAIRS,
)
from tests.test_session_translator import FakeLLMClient

_MSG = {"user_id": "u1", "model_source": "openai", "model_ref": "gpt-x"}


# ── parse_name_pairs (pure, tolerant) ─────────────────────────────────────────

def test_parse_valid_array():
    text = '[{"source": "提拉米", "target": "Tirami", "kind": "character"}, ' \
           '{"source": "暗黑魔殿", "target": "Hắc Ám Ma Điện", "kind": "location"}]'
    assert parse_name_pairs(text) == [
        NamePair("提拉米", "Tirami", "character"),
        NamePair("暗黑魔殿", "Hắc Ám Ma Điện", "location"),
    ]


def test_parse_strips_code_fence():
    text = '```json\n[{"source": "提拉米", "target": "Tirami", "kind": "character"}]\n```'
    assert parse_name_pairs(text) == [NamePair("提拉米", "Tirami", "character")]


def test_parse_extracts_array_from_prose():
    text = 'Here are the names: [{"source":"王","target":"Vương","kind":"character"}] done.'
    assert parse_name_pairs(text) == [NamePair("王", "Vương", "character")]


def test_parse_unknown_kind_defaults_other():
    text = '[{"source": "X", "target": "Y", "kind": "spaceship"}]'
    assert parse_name_pairs(text) == [NamePair("X", "Y", "other")]


def test_parse_missing_kind_defaults_other():
    assert parse_name_pairs('[{"source": "X", "target": "Y"}]') == [NamePair("X", "Y", "other")]


def test_parse_skips_entries_missing_source_or_target():
    text = '[{"source": "A", "target": ""}, {"source": "", "target": "B"}, ' \
           '{"source": "C", "target": "D"}]'
    assert parse_name_pairs(text) == [NamePair("C", "D", "other")]


def test_parse_dedups_on_source():
    text = '[{"source": "A", "target": "X"}, {"source": "A", "target": "Y"}]'
    assert parse_name_pairs(text) == [NamePair("A", "X", "other")]  # first wins


def test_parse_caps_at_max():
    text = "[" + ",".join(
        f'{{"source": "s{i}", "target": "t{i}"}}' for i in range(_MAX_PAIRS + 10)
    ) + "]"
    assert len(parse_name_pairs(text)) == _MAX_PAIRS


def test_parse_malformed_json_returns_empty():
    assert parse_name_pairs('[{"source": "A", "target":}]') == []


def test_parse_non_list_returns_empty():
    assert parse_name_pairs('{"source": "A", "target": "B"}') == []


def test_parse_empty_and_blank():
    assert parse_name_pairs("") == []
    assert parse_name_pairs("   ") == []
    assert parse_name_pairs("no json here") == []


def test_parse_ignores_non_dict_entries():
    assert parse_name_pairs('["bad", 3, null, {"source":"A","target":"B"}]') == [NamePair("A", "B")]


# ── extract_name_pairs (best-effort LLM) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_happy_path():
    fake = FakeLLMClient()
    fake.queue_translation(content='[{"source":"提拉米","target":"Tirami","kind":"character"}]')
    pairs = await extract_name_pairs(
        "提拉米来了。提拉米走了。", "Tirami came. Tirami left.",
        "zh", "vi", llm_client=fake, msg=_MSG,
    )
    assert pairs == [NamePair("提拉米", "Tirami", "character")]
    assert len(fake.calls) == 1  # one LLM pass


@pytest.mark.asyncio
async def test_extract_empty_inputs_skip_llm():
    fake = FakeLLMClient()
    assert await extract_name_pairs("", "x", "zh", "vi", llm_client=fake, msg=_MSG) == []
    assert await extract_name_pairs("x", "", "zh", "vi", llm_client=fake, msg=_MSG) == []
    assert fake.calls == []  # no request when either side is empty


@pytest.mark.asyncio
async def test_extract_non_completed_job_degrades():
    fake = FakeLLMClient()
    fake.queue_translation(content="", status="failed")
    assert await extract_name_pairs("s", "t", "zh", "vi", llm_client=fake, msg=_MSG) == []


@pytest.mark.asyncio
async def test_extract_transport_error_degrades():
    class _BoomClient:
        calls: list = []
        async def submit_and_wait(self, **k):
            raise RuntimeError("gateway down")
    assert await extract_name_pairs("s", "t", "zh", "vi", llm_client=_BoomClient(), msg=_MSG) == []


@pytest.mark.asyncio
async def test_extract_uses_model_override():
    fake = FakeLLMClient()
    fake.queue_translation(content="[]")
    await extract_name_pairs("s", "t", "zh", "vi", llm_client=fake, msg=_MSG,
                             model=("anthropic", "claude-x"))
    assert fake.calls[0]["model_source"] == "anthropic"
    assert fake.calls[0]["model_ref"] == "claude-x"


# ── M4d-2c: build_namepair_block (pass-2 name-consistency block) ──────────────

def test_build_namepair_block_renders_pairs():
    block = build_namepair_block([
        NamePair("提拉米", "Tirami", "character"),
        NamePair("", "skipped"),          # blank source dropped
        NamePair("阿尔德里克", "Aldric"),
    ])
    assert block.startswith("NAME CONSISTENCY")
    assert "提拉米 → Tirami" in block
    assert "阿尔德里克 → Aldric" in block
    assert "skipped" not in block


def test_build_namepair_block_empty():
    assert build_namepair_block([]) == ""
    assert build_namepair_block([NamePair("", "")]) == ""


def test_build_namepair_block_sanitizes_block_marker():
    block = build_namepair_block([NamePair("[BLOCK 0]x", "Tirami")])
    assert "[BLOCK" not in block
