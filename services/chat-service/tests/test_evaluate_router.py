"""Evaluate router tests (M6) — ownership, EC-10 (no model), EC-13 (partial),
EC-4 (degraded → seed fallback), and the persisted scorecard output.

The LLM call (`_run_evaluator_llm`) and the knowledge client are patched; the DB
is the shared `mock_pool`. These prove the HTTP contract + the wiring, not the
model — the coercion guarantees are unit-tested in test_evaluate.py.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_MODEL_REF, TEST_USER_ID, make_message_record, make_session_record

_CHARTER = {
    "goal": "Senior backend interview",
    "phases": ["warmup", "technical", "behavioral", "wrap"],
    "checklist": ["system design", "conflict story"],
    "time_budget_min": 60,
    "language": "en",
}

# A good scorecard JSON the patched LLM "returns".
_GOOD_REPLY = json.dumps({
    "overall_score": 78,
    "star_coverage": "Gave a clear Situation and Action but a thin Result.",
    "clarity": "Communicated clearly.",
    "filler": "Some rambling in the warmup.",
    "checklist": [
        {"item": "system design", "covered": True, "note": "sharding + cache-aside"},
        {"item": "conflict story", "covered": False, "note": "never told one"},
    ],
    "strengths": ["strong system design"],
    "improvements": ["prepare a STAR conflict story"],
    "summary": "Solid technical, weak behavioral.",
})


def _seed(charter=_CHARTER, state=None, rubric=None) -> str:
    block = {"version": 1, "charter": charter, "state": state or {"phase": "", "covered": []}}
    if rubric is not None:
        block["rubric"] = rubric
    return json.dumps(block)


def _wm(state) -> str:
    """A knowledge-block working_memory JSON (SSOT)."""
    return json.dumps({"version": 1, "charter": _CHARTER, "state": state})


def _patch_kc(working_memory: str):
    kc = AsyncMock()
    kc.build_context.return_value = SimpleNamespace(working_memory=working_memory)
    return patch("app.routers.evaluate.get_knowledge_client", return_value=kc)


def _session(**over):
    base = dict(working_memory_seed=_seed(), title="FAANG SWE")
    base.update(over)
    return make_session_record(**base)


# Gate 2 (WS-5.10): every evaluate resolves a CRITIC distinct from the session actor.
# Default fixture = a distinct live critic so the existing happy-path tests still score;
# the Gate-2 tests below reconfigure it to exercise the refuse-to-self-grade path.
_CRITIC_REF = "9999aaaa-bbbb-cccc-dddd-000000000001"


@pytest.fixture(autouse=True)
def _critic(monkeypatch):
    pc = AsyncMock()
    pc.get_default_model = AsyncMock(return_value=("user_model", _CRITIC_REF))
    monkeypatch.setattr("app.client.provider_client.get_provider_client", lambda: pc)
    return pc


class TestEvaluateHappyPath:
    @pytest.mark.asyncio
    async def test_full_transcript_returns_and_persists_scorecard(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [
            make_message_record(role="assistant", content="Let's begin.", sequence_num=1),
            make_message_record(role="user", content="I'd shard by user id...", sequence_num=2),
        ]
        with _patch_kc(_wm({"phase": "wrap", "covered": ["system design"]})), \
             patch("app.routers.evaluate._run_evaluator_llm",
                   AsyncMock(return_value=_GOOD_REPLY)):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")

        assert resp.status_code == 201, resp.text
        body = resp.json()
        card = body["scorecard"]
        assert card["overall_score"] == 78
        assert card["partial"] is False  # reached wrap, not clipped
        verdicts = {v["item"]: v["covered"] for v in card["checklist"]}
        assert verdicts == {"system design": True, "conflict story": False}
        # persisted as a 'scorecard' ChatOutput anchored to the LAST message.
        ins = mock_pool.execute.call_args
        assert "INSERT INTO chat_outputs" in ins.args[0]
        assert "'scorecard'" in ins.args[0]

    @pytest.mark.asyncio
    async def test_degraded_knowledge_falls_back_to_seed(self, client, mock_pool):
        # knowledge returns no block → charter comes from the immutable seed (EC-4).
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [make_message_record(role="user", content="hi", sequence_num=1)]
        with _patch_kc(""), \
             patch("app.routers.evaluate._run_evaluator_llm",
                   AsyncMock(return_value=_GOOD_REPLY)):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 201, resp.text
        # seed state has phase "" → partial flagged.
        assert resp.json()["scorecard"]["partial"] is True


class TestEvaluatePartial:
    @pytest.mark.asyncio
    async def test_unfinished_session_flags_partial(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [make_message_record(role="user", content="x", sequence_num=1)]
        with _patch_kc(_wm({"phase": "technical", "covered": []})), \
             patch("app.routers.evaluate._run_evaluator_llm",
                   AsyncMock(return_value=_GOOD_REPLY)):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 201
        assert resp.json()["scorecard"]["partial"] is True


class TestEvaluateGuards:
    @pytest.mark.asyncio
    async def test_non_owner_is_404(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None  # WHERE owner = caller matched nothing
        resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 404
        # prove ownership scoping is wired
        q = mock_pool.fetchrow.call_args.args[0]
        assert "owner_user_id=$2" in q
        assert TEST_USER_ID in mock_pool.fetchrow.call_args.args

    @pytest.mark.asyncio
    async def test_no_model_is_409(self, client, mock_pool):
        # EC-10 — session carries no model → cannot evaluate (no hardcoded fallback).
        mock_pool.fetchrow.return_value = _session(model_source=None, model_ref=None)
        resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_no_charter_is_400(self, client, mock_pool):
        # seed without a charter AND knowledge empty → not an interview session.
        mock_pool.fetchrow.return_value = _session(working_memory_seed=json.dumps({"foo": "bar"}))
        with _patch_kc(""):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_transcript_is_400(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = []  # no messages
        with _patch_kc(_wm({"phase": "wrap", "covered": []})):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_unusable_model_reply_is_502(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [make_message_record(role="user", content="x", sequence_num=1)]
        with _patch_kc(_wm({"phase": "wrap", "covered": []})), \
             patch("app.routers.evaluate._run_evaluator_llm",
                   AsyncMock(return_value="not json at all")):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 502
        # nothing persisted on a failed evaluation
        mock_pool.execute.assert_not_called()


class TestGate2JudgeNotActor:
    """WS-5.10 — the session model played the roleplay partner; it must NEVER grade itself.
    The evaluator LLM is driven by the resolved CRITIC, and scoring is refused when no
    critic distinct from the actor resolves (a weak/self judge ⇒ no score, WS-5.18)."""

    @pytest.mark.asyncio
    async def test_distinct_critic_drives_the_judge_not_the_actor(self, client, mock_pool, _critic):
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [make_message_record(role="user", content="x", sequence_num=1)]
        seen = {}

        async def _fake_llm(*, user_id, model_source, model_ref, messages):
            seen["judge_ref"] = model_ref
            return _GOOD_REPLY

        with _patch_kc(_wm({"phase": "wrap", "covered": []})), \
             patch("app.routers.evaluate._run_evaluator_llm", _fake_llm):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 201, resp.text
        assert seen["judge_ref"] == _CRITIC_REF                 # judge drove the eval
        assert seen["judge_ref"] != TEST_MODEL_REF              # NOT the actor
        assert resp.json()["model_ref"] == _CRITIC_REF          # response reports the judge

    @pytest.mark.asyncio
    async def test_critic_equal_actor_refuses_to_self_grade(self, client, mock_pool, _critic):
        _critic.get_default_model = AsyncMock(return_value=("user_model", TEST_MODEL_REF))  # == actor
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [make_message_record(role="user", content="x", sequence_num=1)]
        with _patch_kc(_wm({"phase": "wrap", "covered": []})):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 409
        assert "critic" in resp.text.lower()
        mock_pool.execute.assert_not_called()  # nothing self-graded persisted

    @pytest.mark.asyncio
    async def test_no_critic_resolvable_refuses(self, client, mock_pool, _critic):
        _critic.get_default_model = AsyncMock(return_value=None)  # neither critic nor chat default
        mock_pool.fetchrow.return_value = _session()
        mock_pool.fetch.return_value = [make_message_record(role="user", content="x", sequence_num=1)]
        with _patch_kc(_wm({"phase": "wrap", "covered": []})):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 409


class TestRubricThreading:
    @pytest.mark.asyncio
    async def test_rubric_from_seed_reaches_the_prompt(self, client, mock_pool):
        rubric = {"weights": {"system design": 0.6}}
        mock_pool.fetchrow.return_value = _session(working_memory_seed=_seed(rubric=rubric))
        mock_pool.fetch.return_value = [make_message_record(role="user", content="x", sequence_num=1)]
        captured = {}

        async def _capture(**kwargs):
            captured.update(kwargs)
            return _GOOD_REPLY

        with _patch_kc(_wm({"phase": "wrap", "covered": []})), \
             patch("app.routers.evaluate._run_evaluator_llm", _capture):
            resp = await client.post(f"/v1/chat/sessions/{uuid4()}/evaluate")
        assert resp.status_code == 201
        # the rubric (seed-carried) is serialized into the user message
        user_msg = captured["messages"][1]["content"]
        assert "weights" in user_msg and "system design" in user_msg
