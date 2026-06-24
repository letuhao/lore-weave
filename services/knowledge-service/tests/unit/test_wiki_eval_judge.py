"""D-WIKI-M8-EVAL-PLUS — run_wiki_eval --judge helpers (pure / fake-client).

The judge path posts each AI article's body text + cited snippets to the learning
groundedness endpoint and folds the scores into a mean. No network: a fake httpx
client captures the payload and returns a canned response.
"""

from __future__ import annotations

import base64
import json

from app.benchmark.wiki.run_wiki_eval import _jwt_sub, _judge_articles, _plaintext


def _jwt(sub: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
    return f"hdr.{payload}.sig"


def test_jwt_sub_reads_owner():
    assert _jwt_sub(_jwt("user-123")) == "user-123"
    assert _jwt_sub("garbage") == ""  # best-effort: no crash on a malformed token


def test_plaintext_flattens_tiptap():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "Mina"}, {"type": "text", "text": " is a teacher."}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "She lives in Exeter."}]},
        ],
    }
    txt = _plaintext(doc)
    assert "Mina" in txt and "is a teacher." in txt and "Exeter" in txt


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, body):
        self._body = body
        self.posted = None

    def post(self, url, *, json, headers):  # noqa: A002 — match httpx signature
        self.posted = {"url": url, "json": json, "headers": headers}
        return _FakeResp(self._body)


def test_judge_articles_builds_payload_and_means_scores():
    ai = [{"article_id": "a1"}, {"article_id": "a2"}]
    details = [
        {"body_json": {"type": "doc", "content": [
            {"type": "text", "text": "Mina is a teacher."},
            {"type": "text", "marks": [{"type": "citation", "attrs": {"cite_id": "1", "snippet": "Mina taught.", "source_type": "passage", "chapter_id": "c1"}}], "text": "x"},
        ]}},
        {"body_json": {"type": "doc", "content": [{"type": "text", "text": "Lucy."}]}},
    ]
    client = _FakeClient({"enabled": True, "scored": 2, "scores": [
        {"article_id": "a1", "score": 0.8, "reason": "ok"},
        {"article_id": "a2", "score": 0.6, "reason": "ok"},
    ]})
    out = _judge_articles(
        client, "http://learning:8094/", "tok", "book-1", ai, details,
        _jwt("owner-1"), "model-x")
    # payload: owner + model + the right endpoint + internal token
    p = client.posted
    assert p["url"] == "http://learning:8094/internal/learning/wiki/judge"
    assert p["headers"]["X-Internal-Token"] == "tok"
    assert p["json"]["judge_model"] == "model-x"
    assert p["json"]["run_id"]  # one run_id groups the whole audit (across chunks)
    arts = p["json"]["articles"]
    assert [a["article_id"] for a in arts] == ["a1", "a2"]
    assert arts[0]["user_id"] == "owner-1"
    assert "Mina is a teacher." in arts[0]["article_text"]
    assert "Mina taught." in arts[0]["sources"]  # cited snippet became a source
    # report: mean of the returned scores
    assert out["enabled"] is True and out["scored"] == 2
    assert abs(out["mean"] - 0.7) < 1e-9


def test_judge_articles_disabled_mean_zero():
    # a disabled judge (no model) → the endpoint returns enabled=False; the runner
    # reflects that and stops without scoring.
    client = _FakeClient({"enabled": False, "scored": 0, "scores": []})
    ai = [{"article_id": "a1"}]
    details = [{"body_json": {"type": "doc", "content": [{"type": "text", "text": "x"}]}}]
    out = _judge_articles(client, "http://learning:8094", "tok", "b", ai, details, _jwt("o"), None)
    assert out["enabled"] is False and out["scored"] == 0 and out["mean"] == 0.0
