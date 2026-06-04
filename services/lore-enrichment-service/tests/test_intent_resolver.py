"""Mode-B intent resolver (app/compose/intent.py) — unit tests with a stub complete."""

from __future__ import annotations

import asyncio

import pytest

from app.compose.intent import IntentResolutionError, build_intent_prompt, resolve_intent
from app.db.book_profile import NEUTRAL_PROFILE


def _stub(text: str):
    async def _complete(prompt: str, ctx) -> str:  # noqa: ANN001
        return text
    return _complete


def _run(text, **over):
    kw = dict(
        complete=_stub(text), intent_text="a wise advisor to the king",
        entities=[{"name": "姜子牙", "kind": "character"}],
        profile=NEUTRAL_PROFILE, user_id="u", project_id="p", model_ref="m",
    )
    kw.update(over)
    return asyncio.run(resolve_intent(**kw))


def test_resolves_existing_target():
    r = _run('{"target":{"mode":"existing","canonical_name":"姜子牙","entity_kind":"character"},'
             '"dimensions":["历史","能力"],"technique":"retrieval","rationale":"matches list"}')
    assert r.target_mode == "existing" and r.canonical_name == "姜子牙"
    assert r.entity_kind == "character" and r.dimensions == ["历史", "能力"]
    assert r.technique == "retrieval" and "matches" in r.rationale


def test_tolerates_fences_and_prose():
    r = _run('Sure! Here you go:\n```json\n{"target":{"mode":"new","canonical_name":"玉鼎真人",'
             '"entity_kind":"character"},"dimensions":["性格"],"technique":"fabrication"}\n```\nDone.')
    assert r.target_mode == "new" and r.canonical_name == "玉鼎真人"


def test_defaults_technique_to_fabrication_on_invalid():
    r = _run('{"target":{"mode":"new","canonical_name":"X","entity_kind":"generic"},"technique":"recook"}')
    assert r.technique == "fabrication"  # recook is not an allowed resolver technique


def test_defaults_mode_to_new_when_absent():
    r = _run('{"target":{"canonical_name":"X","entity_kind":"item"}}')
    assert r.target_mode == "new" and r.entity_kind == "item"


def test_missing_name_raises():
    with pytest.raises(IntentResolutionError):
        _run('{"target":{"mode":"new","entity_kind":"generic"},"dimensions":[]}')


def test_no_json_raises():
    with pytest.raises(IntentResolutionError):
        _run("the model refused and wrote only prose, no object")


def test_prompt_includes_intent_and_entities():
    p = build_intent_prompt("find the king's advisor", [{"name": "姜子牙", "kind": "character"}], NEUTRAL_PROFILE)
    assert "find the king's advisor" in p and "姜子牙" in p
