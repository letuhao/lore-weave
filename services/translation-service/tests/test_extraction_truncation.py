"""Regression tests for the extraction truncation fix (D-EXTRACTION-TOKEN-TRUNCATION).

Root cause measured live: plan_kind_batches budgeted only the *input* schema, so a
book with many kinds packed 7+ kinds into one LLM call; the model's *output* then
either truncated mid-array at max_tokens (finish_reason=length → invalid JSON → 0
entities) or ran away to fill the ceiling. The fix caps kinds-per-batch so each call's
output stays bounded and terminates cleanly, and the JSON extractor now salvages a
truncated/fenced array instead of discarding every entity.
"""
from app.workers.extraction_prompt import (
    MAX_KINDS_PER_BATCH,
    build_extraction_prompt,
    build_user_prompt,
    plan_kind_batches,
    _extract_json_from_text,
    parse_and_validate,
    parse_and_validate_with_stats,
)


def _profile(n: int) -> dict[str, dict[str, str]]:
    # n kinds, each with a couple of attributes (cheap schema so the OLD
    # SCHEMA_TOKEN_BUDGET alone would NOT split them — isolates the kinds cap).
    return {f"kind{i}": {"a": "fill", "b": "fill"} for i in range(n)}


def _meta(n: int) -> list[dict]:
    return [{"code": f"kind{i}", "attributes": [{"code": "a"}, {"code": "b"}]} for i in range(n)]


def test_plan_kind_batches_caps_kinds_per_batch():
    # 9 cheap kinds would all fit one schema budget, but the output-side cap must
    # split them so no single call asks the model for too many kinds at once.
    batches = plan_kind_batches(_profile(9), _meta(9))
    assert batches, "expected at least one batch"
    assert all(len(b) <= MAX_KINDS_PER_BATCH for b in batches), batches
    # every kind is covered exactly once
    flat = [k for b in batches for k in b]
    assert sorted(flat) == sorted(_profile(9).keys())


def test_plan_kind_batches_small_book_single_call():
    # The common case (≤ cap kinds) still resolves to a single LLM call.
    batches = plan_kind_batches(_profile(MAX_KINDS_PER_BATCH), _meta(MAX_KINDS_PER_BATCH))
    assert len(batches) == 1


def test_extract_json_repairs_truncated_fenced_array():
    # The exact failure shape: a ```json fence the model never closed because it was
    # cut at max_tokens, with the trailing object incomplete. The old extractor
    # discarded all of it; now the two complete objects must be recovered.
    truncated = (
        '```json\n'
        '[\n'
        '  {"kind": "character", "name": "张若尘", "description": "主角"},\n'
        '  {"kind": "character", "name": "林妃", "description": "妃子"},\n'
        '  {"kind": "character", "name": "八王'  # cut mid-string, no closing
    )
    extracted = _extract_json_from_text(truncated)
    assert extracted is not None
    entities = parse_and_validate(truncated, ["character"], {"character": {"description": "fill"}})
    names = [e["name"] for e in entities]
    assert names == ["张若尘", "林妃"], names


def test_extract_json_complete_fenced_array():
    good = '```json\n[{"kind": "item", "name": "洗髓液"}]\n```'
    entities = parse_and_validate(good, ["item"], {"item": {}})
    assert [e["name"] for e in entities] == ["洗髓液"]


def test_parse_stats_distinguishes_empty_from_rejected():
    # OBS/M2 — the discriminator the batch-outcome taxonomy needs.
    # Empty array: parse_ok, raw_count 0 → empty_valid territory.
    _, empty = parse_and_validate_with_stats("[]", ["item"], {"item": {}})
    assert empty.parse_ok and empty.raw_count == 0

    # Non-empty but wrong kind → all rejected: parse_ok, raw_count 2, 0 validated.
    ents, rejected = parse_and_validate_with_stats(
        '[{"kind":"wrong","name":"A"},{"kind":"wrong","name":"B"}]', ["item"], {"item": {}})
    assert rejected.parse_ok and rejected.raw_count == 2 and len(ents) == 0

    # Unparseable garbage → parse failed.
    _, bad = parse_and_validate_with_stats("not json at all", ["item"], {"item": {}})
    assert not bad.parse_ok and bad.raw_count == 0


def test_block_hints_off_is_default_unchanged_prompt():
    # D-PROV-MODEL-OFFSET-HINT default OFF: the prompt is the plain chapter text, no ⟦B#⟧.
    text = "para one\npara two"
    assert "⟦B" not in build_user_prompt(text)
    assert "evidence_block" not in build_extraction_prompt(
        ["item"], {"item": {}}, [{"code": "item", "attributes": []}])


def test_block_hints_on_numbers_blocks_and_adds_schema_field():
    text = "para one\npara two"
    up = build_user_prompt(text, block_hints=True)
    assert "⟦B0⟧ para one" in up and "⟦B1⟧ para two" in up
    schema = build_extraction_prompt(
        ["item"], {"item": {}}, [{"code": "item", "attributes": []}], block_hints=True)
    assert "evidence_block" in schema


def test_extract_json_bare_array_no_fence():
    bare = '[{"kind": "location", "name": "黄极境"}]'
    entities = parse_and_validate(bare, ["location"], {"location": {}})
    assert [e["name"] for e in entities] == ["黄极境"]
