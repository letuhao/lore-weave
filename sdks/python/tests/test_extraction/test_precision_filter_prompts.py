"""Cycle 72 — regression test for the precision-filter prompt SOT.

The prompt is sourced from the SDK module
`loreweave_extraction.extractors.precision_filter_prompts` and reused
by both the production filter (`pass2_filter.apply_precision_filter`)
and the eval-side judge (`services/knowledge-service/tests/quality/
llm_judge.py::_PRECISION_SYSTEM`). This regression locks the prompt
text + builder behavior so a future edit to either side cannot drift
silently.

Round-1 HIGH-2 fold: both `_NO_THINK_PREFIX` and the prompt BODY are
promoted to the SDK via `build_precision_prompt(suppress_thinking=...)`.
This test exercises both the prefix-on and prefix-off paths.
"""

from __future__ import annotations

from loreweave_extraction.extractors.precision_filter_prompts import (
    NO_THINK_PREFIX,
    build_precision_prompt,
    precision_prompt_body,
)


# ── Constants — match the llm_judge.py source-of-record literal ────────


# What llm_judge.py historically had as _NO_THINK_PREFIX. If this
# changes intentionally, update SDK + llm_judge + this constant together.
_EXPECTED_NO_THINK_PREFIX = (
    "RESPOND DIRECTLY. Do NOT think aloud, do NOT use <think> tags, do "
    "NOT write reasoning. Emit ONLY the JSON object below — no prose "
    "before or after, no markdown fences.\n\n"
)


# What llm_judge.py historically had as the precision body (after the
# NO_THINK_PREFIX). Concatenated with the prefix this yields the
# pre-SOT _PRECISION_SYSTEM byte sequence.
_EXPECTED_PRECISION_BODY = (
    "You are a meticulous literary-extraction auditor. You are given the "
    "SOURCE TEXT of one chapter of a novel and a numbered list of items "
    "that some system claims to have extracted from it. For EACH item, "
    "decide whether the item is actually supported by the SOURCE TEXT.\n\n"
    "Judge by MEANING, not by surface wording — a different phrasing of "
    "the same fact is still supported. The text may be in English, "
    "Chinese, or Vietnamese; judge it in its own language and script.\n\n"
    "Verdict values:\n"
    '  - "supported": the item is clearly stated or unambiguously implied '
    "by the text.\n"
    '  - "partial": partially correct — e.g. right entity but wrong kind, '
    "right relation but wrong direction, or only weakly implied.\n"
    '  - "unsupported": not present in the text, contradicted by it, or '
    "hallucinated.\n\n"
    "Reply with ONLY a JSON object, no prose or markdown fences:\n"
    '{"verdicts":[{"idx":<int>,"verdict":"supported|partial|unsupported",'
    '"reason":"<=15 words"}]}\n'
    "Return exactly one verdict per input item, preserving idx."
)


# ── Tests ──────────────────────────────────────────────────────────────


def test_no_think_prefix_byte_matches_historical_literal() -> None:
    """SDK's NO_THINK_PREFIX is byte-identical to the pre-SOT literal."""
    assert NO_THINK_PREFIX == _EXPECTED_NO_THINK_PREFIX


def test_precision_prompt_body_byte_matches_historical_literal() -> None:
    """The loaded prompt body is byte-identical to the pre-SOT literal."""
    assert precision_prompt_body() == _EXPECTED_PRECISION_BODY


def test_build_precision_prompt_suppress_thinking_true_assembles_prefix_plus_body() -> None:
    """Default (suppress_thinking=True) yields NO_THINK_PREFIX + body."""
    expected = _EXPECTED_NO_THINK_PREFIX + _EXPECTED_PRECISION_BODY
    assert build_precision_prompt(suppress_thinking=True) == expected


def test_build_precision_prompt_suppress_thinking_false_skips_prefix() -> None:
    """suppress_thinking=False returns body without the prefix."""
    assert build_precision_prompt(suppress_thinking=False) == _EXPECTED_PRECISION_BODY


def test_build_precision_prompt_default_is_suppress_thinking_true() -> None:
    """Default kwarg = suppress_thinking=True. Defensive lock."""
    assert build_precision_prompt() == build_precision_prompt(suppress_thinking=True)


def test_precision_prompt_body_is_cached() -> None:
    """Multiple loads return identity-equal strings (lru_cache)."""
    a = precision_prompt_body()
    b = precision_prompt_body()
    assert a is b


def test_llm_judge_precision_system_imports_from_sdk() -> None:
    """The eval-side llm_judge module reuses the SDK SOT helper.

    Regression-lock for the 1-line `_PRECISION_SYSTEM = build_precision_prompt(...)`
    edit in cycle 72 Phase 1.e. If this test fails, either the import
    was removed or a parallel definition was added (which defeats the
    purpose of the SOT migration).
    """
    try:
        # The eval module isn't importable from the SDK test suite
        # without the knowledge-service runtime — instead, parse the
        # source and grep for the import line.
        from pathlib import Path
        # Walk up from this test file to the repo root.
        here = Path(__file__).resolve()
        repo_root = here.parents[4]  # sdks/python/tests/test_extraction → up 4
        judge_path = (
            repo_root
            / "services"
            / "knowledge-service"
            / "tests"
            / "quality"
            / "llm_judge.py"
        )
        if not judge_path.is_file():
            # Defensive: if the repo layout shifted, fall back to skip.
            import pytest
            pytest.skip(
                f"llm_judge.py not at expected path {judge_path}; SOT "
                "migration check requires manual verification"
            )
        text = judge_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        import pytest
        pytest.skip(f"llm_judge.py inspection failed: {exc}")

    # Both signals must be present.
    assert (
        "from loreweave_extraction import" in text
        and "build_precision_prompt" in text
    ), "llm_judge.py must import build_precision_prompt from SDK"

    assert (
        "_PRECISION_SYSTEM = build_precision_prompt(" in text
    ), "_PRECISION_SYSTEM must be assigned from SDK helper"

    # Pre-SOT literal MUST be gone. The precision-body verdict shape
    # is unique to the PRECISION prompt (recall uses "gold_idx" not
    # "idx"). If this token still appears in llm_judge, the precision
    # literal wasn't fully removed.
    assert (
        '{"idx":<int>,"verdict":"supported|partial|unsupported"'
        not in text
    ), (
        "llm_judge.py still contains the precision verdict-shape "
        "literal — SOT migration is incomplete (parallel definitions "
        "exist)"
    )
