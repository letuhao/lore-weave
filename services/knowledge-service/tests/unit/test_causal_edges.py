"""D-W10-ARC-CONFORMANCE-SUCCESSION (F2) — causal-edge inference.

Pure pieces (build_messages / parse_edges) + infer_causal_edges with a fake LLM (forward-only
guard, window dedupe, advisory degrade) + the two route mounts/auth.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.extraction.causal_edges import build_messages, infer_causal_edges, parse_edges

EVENTS = [
    {"id": "e1", "title": "Humiliation", "summary": "A public shaming."},
    {"id": "e2", "title": "Exile", "summary": ""},
    {"id": "e3", "title": "Face slap", "summary": "The retort."},
]
ORDER = {"e1": 0, "e2": 1, "e3": 2}
WIN = {"e1", "e2", "e3"}


def test_build_messages_numbers_events_in_order():
    user = build_messages(EVENTS)[1]["content"]
    assert "1. id=e1" in user and "3. id=e3" in user and "A public shaming." in user


def test_parse_edges_keeps_forward_drops_backward_self_and_foreign():
    content = '[["e1","e3"], ["e3","e1"], ["e2","e2"], ["e1","ghost"]]'
    out = parse_edges(content, order_index=ORDER, window_ids=WIN)
    assert out == [("e1", "e3")]  # forward only; backward/self/foreign dropped


def test_parse_edges_tolerates_edges_wrapper_and_fence():
    content = '```json\n{"edges": [["e1","e2"]]}\n```'
    assert parse_edges(content, order_index=ORDER, window_ids=WIN) == [("e1", "e2")]


def test_parse_edges_junk_is_empty():
    assert parse_edges("no json", order_index=ORDER, window_ids=WIN) == []


def _job(content, status="completed"):
    return SimpleNamespace(status=status, result={"messages": [{"content": content}]})


class _FakeLLM:
    def __init__(self, job=None, raises=False):
        self._job, self._raises = job, raises
        self.calls = 0
    async def submit_and_wait(self, **kw):
        self.calls += 1
        if self._raises:
            raise RuntimeError("down")
        return self._job


async def test_infer_returns_validated_forward_edges():
    llm = _FakeLLM(_job('[["e1","e2"], ["e2","e3"]]'))
    out = await infer_causal_edges(llm, user_id="u", model_source="user_model",
                                   model_ref="m1", events=EVENTS)
    assert out == [("e1", "e2"), ("e2", "e3")]


async def test_infer_degrades_on_exception():
    llm = _FakeLLM(raises=True)
    assert await infer_causal_edges(llm, user_id="u", model_source="user_model",
                                    model_ref="m1", events=EVENTS) == []


async def test_infer_noops_under_two_events():
    llm = _FakeLLM(_job("[]"))
    assert await infer_causal_edges(llm, user_id="u", model_source="s", model_ref="m",
                                    events=EVENTS[:1]) == []
    assert llm.calls == 0


def test_causal_routes_are_registered():
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/internal/extraction/causal-edges" in paths
    assert "/internal/extraction/causal-motif-pairs" in paths


def test_causal_edges_requires_internal_token():
    from fastapi.testclient import TestClient
    from app.main import app
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/internal/extraction/causal-edges",
        json={"user_id": "00000000-0000-0000-0000-000000000000",
              "book_id": "00000000-0000-0000-0000-000000000000",
              "model_source": "user_model", "model_ref": "m1"})
    assert resp.status_code == 401
