"""T6 D6 — the compaction summary prompt is FACT-PRESERVING EXTRACTIVE.

A lossy prose summary silently drops load-bearing facts. D6 requires the summary
to lead with an explicit verbatim FACTS block (the system of record) before prose,
and to keep names EXACT. These deterministic checks pin the contract; the live
smoke (docs/eval) proves a planted fact actually survives.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.services.compact_service import _SUMMARY_SYSTEM_PROMPT, transcript_of


def test_prompt_is_two_section_extractive():
    p = _SUMMARY_SYSTEM_PROMPT
    assert "FACTS:" in p and "SYNOPSIS:" in p
    # the load-bearing categories the FACTS block must enumerate
    for cat in ("Entities", "Decisions", "Established", "Open threads"):
        assert cat in p, cat


def test_prompt_forbids_name_paraphrase_and_reasoning():
    p = _SUMMARY_SYSTEM_PROMPT.lower()
    assert "verbatim" in p
    assert "never" in p and "paraphrase" in p  # names must stay exact
    assert "do not reason aloud" in p


def test_transcript_of_compact_tool_call_turn():
    # a prose-less tool-call turn is represented compactly (not dropped)
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "story_search"}},
            {"function": {"name": "memory_search"}},
        ]},
    ]
    t = transcript_of(msgs)
    assert "user: hi" in t
    assert "(called story_search, memory_search)" in t
