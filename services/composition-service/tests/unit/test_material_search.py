"""Quote-first search for a kind the board reported absent — and the grounding gate on it.

Measured basis (POC §6e/§6f): on the author's real document `planner_variables` came back absent and
the search found it ALREADY WRITTEN, so the loop must look before it asks. And the three lines it
offered were all wrong, so it must show rather than conclude.
"""

from __future__ import annotations

import json

import pytest

from app.engine.plan_forge.material_search import (
    _KIND_MEANING,
    kinds_worth_searching,
    search_material,
)

DOC = """# Mị Đế

## Nhân vật
Lâm Uyên là thiên tài của Thanh Vân tông.

## Công pháp
Âm Dương Hợp Hoan: hấp thụ linh khí qua đối tác.
Chân Linh là bất biến, không thể thay đổi.
"""


class _LLM:
    """Returns canned content the way `call_json` reads it."""

    def __init__(self, payload):
        self._payload = payload
        self.calls: list[dict] = []

    async def submit_and_wait(self, **kwargs):
        from types import SimpleNamespace
        self.calls.append(kwargs)
        content = self._payload if isinstance(self._payload, str) else json.dumps(self._payload)
        return SimpleNamespace(
            status="completed",
            result={"messages": [{"role": "assistant", "content": content}]},
        )


async def _search(payload, kind="planner_variables", doc=DOC, **kw):
    llm = _LLM(payload)
    out = await search_material(
        llm, user_id="u", model_source="user_model", model_ref="m",
        document_markdown=doc, kind=kind, **kw,
    )
    return out, llm


async def test_a_verbatim_line_survives():
    out, _ = await _search({"quotes": [
        {"quote": "Chân Linh là bất biến, không thể thay đổi.", "why": "an invariant"},
    ]})
    assert [c["quote"] for c in out["candidates"]] == ["Chân Linh là bất biến, không thể thay đổi."]
    assert out["dropped_ungrounded"] == 0 and out["note"] == ""


async def test_an_INVENTED_line_is_dropped_and_counted():
    """The grounding gate. A line not in the document, shown under "here is what you already wrote",
    is worse than showing nothing: the author keeps it and it enters their plan as their own."""
    out, _ = await _search({"quotes": [
        {"quote": "Chân Linh là bất biến, không thể thay đổi."},
        {"quote": "Tu vi tăng 10 điểm mỗi chương.", "why": "a stat"},   # nowhere in DOC
    ]})
    assert len(out["candidates"]) == 1
    assert out["dropped_ungrounded"] == 1
    assert "dropped as invented" in out["note"]


async def test_an_ALL_INVENTED_search_is_a_FAILED_search_not_an_empty_one():
    """Zero candidates from invention and zero candidates from an honest miss are the same list. The
    note is what separates them, and without it the loop would ask the author for material it never
    actually looked for properly."""
    out, _ = await _search({"quotes": [{"quote": "Không có trong tài liệu."}]})
    assert out["candidates"] == [] and out["dropped_ungrounded"] == 1
    assert "FAILED search, not an empty one" in out["note"]


async def test_an_honest_EMPTY_result_says_nothing_alarming():
    out, _ = await _search({"quotes": []})
    assert out["candidates"] == [] and out["dropped_ungrounded"] == 0 and out["note"] == ""


async def test_whitespace_and_case_differences_are_forgiven():
    """The model re-wrapping a line is not an invention; changing its words is."""
    out, _ = await _search({"quotes": [
        {"quote": "  chân linh   là bất biến,\n không thể thay đổi.  "},
    ]})
    assert len(out["candidates"]) == 1


async def test_duplicates_collapse():
    out, _ = await _search({"quotes": [
        {"quote": "Chân Linh là bất biến, không thể thay đổi."},
        {"quote": "Chân  Linh là bất biến, không thể thay đổi."},
    ]})
    assert len(out["candidates"]) == 1 and out["dropped_ungrounded"] == 0


async def test_a_non_completing_call_is_NOT_evidence_of_absence():
    """`call_json` returns None when the job did not complete. Reporting that as "the document has
    none" is the silent-degrade shape: the loop would then ask the author to write something they may
    already have."""
    out, _ = await _search("")
    assert out["candidates"] == []
    assert "NOT evidence" in out["note"]


async def test_an_unparseable_response_is_NOT_evidence_of_absence():
    out, _ = await _search("here you go: {oops")
    assert out["candidates"] == []
    assert "NOT evidence" in out["note"]


async def test_an_unknown_kind_RAISES_rather_than_returning_empty():
    """Returning empty for a typo'd kind would render as "your document has none of that"."""
    with pytest.raises(ValueError, match="unknown planning kind"):
        await _search({"quotes": []}, kind="protagonist_seed")


async def test_the_prompt_carries_no_worked_example():
    """Measured: a hand-written example took recall to ZERO in a controlled arm, and a hand-written
    tie-break rule cost 0.26 F1 elsewhere in the same POC. The prompt says what the kind is and stops.
    """
    _, llm = await _search({"quotes": []})
    user = llm.calls[0]["input"]["messages"][1]["content"]
    assert "--- DOCUMENT ---" in user
    body = user.split("--- DOCUMENT ---")[0]
    for tell in ("for example", "e.g.", "such as", "like this", "Example:"):
        assert tell.lower() not in body.lower(), f"a worked example crept into the prompt: {tell!r}"
    # and no yes/no gate: the instruction asks for lines, never for a verdict first
    assert "yes" not in body.lower().split("document")[0]


async def test_max_candidates_is_honoured():
    doc = "\n".join(f"line number {i} of the plan." for i in range(10))
    out, _ = await _search(
        {"quotes": [{"quote": f"line number {i} of the plan."} for i in range(10)]},
        doc=doc, max_candidates=3,
    )
    assert len(out["candidates"]) == 3


def test_UNKNOWN_kinds_are_searched_TOO_and_carry_their_status():
    """The regression this exists for is one I shipped and a LIVE run caught.

    `kinds_worth_searching` first returned `absent` only, reasoning that an `unknown` kind is probably
    sitting in a section the matcher could not place. That inverts itself: if the material is probably
    there, finding it is the job — and the search reads the RAW document, not the classified sections.

    On the author's real Mị Đế document all three empty kinds are `unknown`, so the loop searched
    NOTHING — on the very document whose measured result (POC §6e Arm 1) is that the "absent" kind was
    already written. This unit test previously asserted the wrong contract, which is why only the live
    run caught it.

    What must never happen without a search is ASKING; that is the ask step's job, and it is why each
    entry carries its status.
    """
    board = {"absent": ["writing_principles"], "unknown": ["planner_variables"],
             "recovered": ["character_seed"]}
    out = kinds_worth_searching(board)
    assert {e["kind"] for e in out} == {"writing_principles", "planner_variables"}
    assert {e["kind"]: e["status"] for e in out} == {
        "writing_principles": "absent", "planner_variables": "unknown",
    }
    assert "character_seed" not in {e["kind"] for e in out}, "a recovered kind must not be searched"


def test_every_board_kind_has_a_meaning():
    """A kind the board can report absent but the search cannot look for is a dead end the caller
    only finds at runtime."""
    from app.engine.plan_forge.coverage import _BOARD_KINDS

    assert {k for k, _, _ in _BOARD_KINDS} == set(_KIND_MEANING)


async def test_the_schema_reaches_the_provider_wrapped_EXACTLY_once():
    """The bug a stub cannot see, and it cost a live run to find.

    `call_json` wraps the schema itself (`json_format(schema_name, schema)`). Passing an already
    wrapped one nests `json_schema` inside `json_schema`; the provider rejects it, `call_json` falls
    back silently to free-form, and every search on the author's real document came back "the search
    did not complete". The mocked tests all passed throughout — a stub ignores the input shape, so
    only an assertion about what actually goes on the wire can catch this.
    """
    _, llm = await _search({"quotes": []})
    fmt = llm.calls[0]["input"]["response_format"]
    assert fmt["type"] == "json_schema"
    inner = fmt["json_schema"]
    assert "schema" in inner and "json_schema" not in inner, f"double-wrapped: {inner.keys()}"
    assert inner["schema"]["properties"]["quotes"]["type"] == "array"
    assert inner["name"].startswith("material_")
