"""M7d-2 — online translation-fidelity judge: run + persist + the gated hook."""

from __future__ import annotations

import json
import uuid

import pytest

from loreweave_eval.llm_judge import FidelityVerdict
from app.db.eval_repo import SCORE_CONFIG_SEED
from app.db.online_translation_judge import run_translation_judge, persist_translation_judge


# ── run_translation_judge (fake JudgeLLMClient) ───────────────────────────────

class _FakeJob:
    def __init__(self, content):
        self.status = "completed"
        self.result = {"messages": [{"content": content}]}


class _FakeJudgeClient:
    def __init__(self, content):
        self._content = content
        self.calls = 0

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        return _FakeJob(self._content)


async def test_run_translation_judge_returns_verdict():
    client = _FakeJudgeClient('{"score": 0.82, "reason": "faithful"}')
    v = await run_translation_judge(
        client, source_text="他来了。", translated_text="Anh ấy đã đến.",
        judge_model="gemma-judge", model_source="user_model", user_id="u1")
    assert isinstance(v, FidelityVerdict)
    assert v.score == 0.82


# ── persist_translation_judge (fake pool → persist_consumed_score) ────────────

def _cfg_rows():
    return [
        {"name": s["name"], "data_type": s["data_type"],
         "min_value": s.get("min_value"), "max_value": s.get("max_value"), "categories": None}
        for s in SCORE_CONFIG_SEED
    ]


class _FakeConn:
    def __init__(self):
        self._cfg = _cfg_rows()
        self.execs = []

    async def fetch(self, sql, *p):
        return self._cfg if "FROM score_config" in sql else []

    async def execute(self, sql, *p):
        self.execs.append((sql, p))
        return "INSERT 0 1"


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False

        return _Acq()


# INSERT param order: target_kind, target_id, user_id, book_id, metric_name, value_num,
# value_label, data_type, source, judge_model, comment, origin_service, origin_event_id
P_KIND, P_METRIC, P_VALUE, P_SOURCE, P_JUDGE, P_COMMENT, P_ORIGIN_SVC, P_ORIGIN_ID = 0, 4, 5, 8, 9, 10, 11, 12


async def test_persist_uses_judge_prefixed_origin_to_avoid_m7a_collision():
    conn = _FakeConn()
    ct = str(uuid.uuid4())
    await persist_translation_judge(
        _FakePool(conn), ct_id=ct, user_id=uuid.uuid4(), book_id=None,
        verdict=FidelityVerdict(score=0.7, reason="ok"),
        judge_model="gemma-judge", origin_event_id="ob-9")
    ins = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(ins) == 1
    p = ins[0][1]
    assert p[P_KIND] == "translation"
    assert p[P_METRIC] == "translation_judge_fidelity"
    assert p[P_VALUE] == 0.7
    assert p[P_SOURCE] == "auto"
    assert p[P_JUDGE] == "gemma-judge"
    # the dedup key is judge:<outbox> — distinct from M7a's bare <outbox>
    assert p[P_ORIGIN_ID] == "judge:ob-9"
    detail = json.loads(p[P_COMMENT])
    assert detail["reason"] == "ok" and detail["panel_safe"] is False


# ── the gated hook _maybe_judge_translation ───────────────────────────────────

from app.events.handlers import _maybe_judge_translation
from app.events.dispatcher import EventData


def _quality_event(**payload_over):
    payload = {"user_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()),
               "chapter_translation_id": str(uuid.uuid4()), "quality_score": 0.9}
    payload.update(payload_over)
    return EventData(stream="s", message_id="1-0", event_type="translation.quality",
                     aggregate_id="a", payload=payload, source="translation", raw={}, outbox_id="ob-1")


async def test_hook_noop_when_disabled(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "online_translation_judge_enabled", False)
    ev = _quality_event(source_text="x", translated_text="y")
    # Must not raise / not attempt a judge (no model, disabled).
    await _maybe_judge_translation(ev, ev.payload, "ct", pool=None)


async def test_hook_noop_when_no_texts(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "online_translation_judge_enabled", True)
    monkeypatch.setattr(cfg.settings, "online_judge_model_ref", "gemma-judge")
    ev = _quality_event()  # no source_text/translated_text → inert (M7d-3 feed off)
    await _maybe_judge_translation(ev, ev.payload, "ct", pool=None)


# M1 (LLM re-arch Phase 3): the hook now STARTS a decoupled judge (durable job-row
# + terminal-event consumer) instead of inline submit_and_wait. The tests assert the
# hook submits the first batch with the right owner/billing/emit args; the fold +
# persist is covered by the decoupled_judge SM tests.

class _FakeSdk:
    async def aclose(self):
        pass


async def test_hook_runs_judge_when_enabled_and_fed(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "online_translation_judge_enabled", True)
    monkeypatch.setattr(cfg.settings, "online_judge_model_ref", "gemma-judge")
    monkeypatch.setattr("app.clients.llm_client.build_judge_sdk", lambda **k: _FakeSdk())

    ran = {}
    async def _fake_start(pool, sdk, **k):
        ran["start"] = k
        return True
    monkeypatch.setattr("app.judges.decoupled_judge.start_translation_judge", _fake_start)

    ev = _quality_event(source_text="他来了。", translated_text="Anh ấy đã đến.")
    await _maybe_judge_translation(ev, ev.payload, ev.payload["chapter_translation_id"], pool=object())
    assert ran["start"]["source_text"] == "他来了。"
    assert ran["start"]["translated_text"] == "Anh ấy đã đến."
    assert ran["start"]["origin_event_id"] == "ob-1"
    assert ran["start"]["judge_model"] == "gemma-judge"
    # global-config judge (no campaign ref) → no campaign eval_judged emit
    assert ran["start"]["emit_eval_judged"] is False


async def test_hook_bills_content_owner_not_operator(monkeypatch):
    # D-EVAL-JUDGE-PER-USER: the BYOK judge is billed to the CONTENT OWNER
    # (event user_id), not the operator's env-configured id.
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "online_translation_judge_enabled", True)
    monkeypatch.setattr(cfg.settings, "online_judge_model_ref", "gemma-judge")
    monkeypatch.setattr(cfg.settings, "online_judge_user_id", "operator-env-id")
    monkeypatch.setattr("app.clients.llm_client.build_judge_sdk", lambda **k: _FakeSdk())

    ran = {}
    async def _fake_start(pool, sdk, **k):
        ran["start"] = k
        return True
    monkeypatch.setattr("app.judges.decoupled_judge.start_translation_judge", _fake_start)

    owner = str(uuid.uuid4())
    ev = _quality_event(user_id=owner, source_text="他来了。", translated_text="Anh.")
    await _maybe_judge_translation(ev, ev.payload, ev.payload["chapter_translation_id"], pool=object())
    # billing_user_id (submit/get_job identity) is the content owner, not the env id
    assert ran["start"]["billing_user_id"] == owner
    assert ran["start"]["billing_user_id"] != "operator-env-id"
    # owner_user_id (persist target) matches too
    assert str(ran["start"]["owner_user_id"]) == owner


async def test_hook_campaign_judge_sets_emit_flag(monkeypatch):
    # A campaign-chosen judge (eval_judge_model_ref on the event) runs even with the
    # global flags off, and sets emit_eval_judged so the campaign projection records it.
    import app.config as cfg
    monkeypatch.setattr(cfg.settings, "online_translation_judge_enabled", False)
    monkeypatch.setattr(cfg.settings, "online_judge_model_ref", "")
    monkeypatch.setattr("app.clients.llm_client.build_judge_sdk", lambda **k: _FakeSdk())

    ran = {}
    async def _fake_start(pool, sdk, **k):
        ran["start"] = k
        return True
    monkeypatch.setattr("app.judges.decoupled_judge.start_translation_judge", _fake_start)

    ev = _quality_event(
        source_text="他来了。", translated_text="Anh.",
        eval_judge_model_ref="campaign-judge", eval_judge_model_source="user_model",
    )
    await _maybe_judge_translation(ev, ev.payload, ev.payload["chapter_translation_id"], pool=object())
    assert ran["start"]["judge_model"] == "campaign-judge"
    assert ran["start"]["emit_eval_judged"] is True
