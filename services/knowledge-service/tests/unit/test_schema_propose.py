"""M3b — schema-propose engine: JSON extraction/salvage + the LLM call wrapper.

Pure-logic tests (no live LLM): the parser tolerates fenced/prose-wrapped JSON and
salvages a partial proposal; the async wrapper composes the call + maps a
non-completed job / empty premise to ProposeError.
"""
from __future__ import annotations

import pytest

from app.schema_propose.engine import ProposeError, parse_proposal, propose_schema


def test_parse_clean_json():
    p = parse_proposal(
        '{"node_kinds":[{"code":"character","label":"Character"}],'
        '"edge_types":[{"code":"MENTOR_OF","label":"mentor of",'
        '"source_kinds":["character"],"target_kinds":["character"]}]}'
    )
    assert [k.code for k in p.node_kinds] == ["character"]
    assert p.edge_types[0].source_kinds == ["character"]


def test_parse_fenced_json():
    p = parse_proposal('```json\n{"node_kinds":[{"code":"sect"}]}\n```')
    assert p.node_kinds[0].code == "sect"


def test_parse_prose_wrapped_json():
    p = parse_proposal("Here is the schema:\n{\"node_kinds\":[{\"code\":\"x\"}]}\nHope it helps!")
    assert p.node_kinds[0].code == "x"


def test_parse_salvages_bad_items():
    p = parse_proposal('{"node_kinds":[{"code":"ok"},{"label":"no code"}],"edge_types":"notalist"}')
    assert [k.code for k in p.node_kinds] == ["ok"]  # the code-less item dropped
    assert p.edge_types == []  # non-list edge_types salvaged to empty


def test_parse_non_json_raises():
    with pytest.raises(ProposeError):
        parse_proposal("sorry, I can't do that")


class _Job:
    def __init__(self, status="completed", content=None):
        self.status = status
        self.error = None
        self.result = {"messages": [{"content": content}]} if content is not None else None


@pytest.mark.asyncio
async def test_propose_schema_happy():
    seen = {}

    class _Fake:
        async def submit_and_wait(self, **kw):
            seen.update(kw)
            return _Job(content='{"node_kinds":[{"code":"character"}]}')

    p = await propose_schema(_Fake(), user_id="u", premise="a xianxia tale", genre="xianxia", model_ref="m1")
    assert p.node_kinds[0].code == "character"
    assert seen["operation"] == "chat" and seen["model_ref"] == "m1" and seen["model_source"] == "user_model"
    # genre + premise both reach the user message
    user_msg = seen["input"]["messages"][1]["content"]
    assert "xianxia" in user_msg and "a xianxia tale" in user_msg


@pytest.mark.asyncio
async def test_propose_empty_premise_raises():
    with pytest.raises(ProposeError):
        await propose_schema(None, user_id="u", premise="   ", genre=None, model_ref="m1")


@pytest.mark.asyncio
async def test_propose_failed_job_raises():
    class _Fake:
        async def submit_and_wait(self, **kw):
            return _Job(status="failed")

    with pytest.raises(ProposeError):
        await propose_schema(_Fake(), user_id="u", premise="x", genre=None, model_ref="m1")


@pytest.mark.asyncio
async def test_propose_sdk_error_wrapped():
    class _Fake:
        async def submit_and_wait(self, **kw):
            raise RuntimeError("transport boom")

    with pytest.raises(ProposeError):
        await propose_schema(_Fake(), user_id="u", premise="x", genre=None, model_ref="m1")
