"""D-RERANK-NOT-BYOK — RerankerClient now sends the user's BYOK rerank model
(user_id query + model_source/model_ref body) to provider-registry /internal/rerank,
with NO hardcoded model name. Degrades to None on any non-200/error."""

from unittest.mock import AsyncMock

from app.clients.reranker_client import RerankerClient


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


async def test_rerank_sends_byok_user_and_model_ref(monkeypatch):
    rc = RerankerClient(base_url="http://pr:8085", internal_token="t", timeout_s=5.0)
    captured: dict = {}

    async def _post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Resp(200, {"results": [{"index": 0, "relevance_score": 0.9}]})

    monkeypatch.setattr(rc._http, "post", AsyncMock(side_effect=_post))
    out = await rc.rerank(
        "q", ["d0", "d1"], user_id="u1", model_source="user_model", model_ref="m1",
    )
    assert out == [{"index": 0, "relevance_score": 0.9}]
    assert captured["url"].endswith("/internal/rerank")
    assert captured["params"] == {"user_id": "u1"}          # BYOK owner on the wire
    assert captured["json"]["model_source"] == "user_model"
    assert captured["json"]["model_ref"] == "m1"            # the user's model_ref
    assert captured["json"]["query"] == "q"
    assert captured["json"]["documents"] == ["d0", "d1"]
    assert "model" not in captured["json"]                   # no hardcoded model name
    await rc.aclose()


async def test_rerank_degrades_on_non_200(monkeypatch):
    rc = RerankerClient(base_url="http://pr:8085", internal_token="t", timeout_s=5.0)
    monkeypatch.setattr(rc._http, "post", AsyncMock(return_value=_Resp(404, {})))
    out = await rc.rerank("q", ["d"], user_id="u1", model_source="user_model", model_ref="m1")
    assert out is None  # caller keeps fusion order
    await rc.aclose()


async def test_rerank_empty_documents_short_circuits(monkeypatch):
    rc = RerankerClient(base_url="http://pr:8085", internal_token="t", timeout_s=5.0)
    post = AsyncMock()
    monkeypatch.setattr(rc._http, "post", post)
    out = await rc.rerank("q", [], user_id="u1", model_source="user_model", model_ref="m1")
    assert out == []
    post.assert_not_awaited()  # no call when there's nothing to rank
    await rc.aclose()
