"""D-W10-ARC-CONFORMANCE-THREAD-TAG — the narrative-thread classifier.

Pure pieces (build_messages / parse_assignments) are the main surface; classify_event_threads
is covered with a fake LLM (batching, the advisory degrade on failure / non-completed job /
junk output, and the validate-against-vocabulary guard). The route + Cypher are integration
concerns (the SET is a one-liner; the route mirrors motif-beats).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.extraction.thread_tag import (
    build_messages, classify_event_threads, parse_assignments,
)

THREADS = [{"key": "combat", "label": "Combat"}, {"key": "romance", "label": "Romance"}]
EVENTS = [
    {"id": "e1", "title": "Duel at dawn", "summary": "A one-on-one fight.", "participants": ["Kai", "Lord"]},
    {"id": "e2", "title": "A quiet confession", "summary": "", "participants": ["Lin"]},
]


# ── build_messages (pure) ────────────────────────────────────────────────────────

def test_build_messages_lists_keys_ids_and_fields():
    msgs = build_messages(EVENTS, THREADS)
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    # thread keys are offered, each event id appears, and present summary/participants ride along.
    assert "combat" in user and "romance" in user
    assert "id=e1" in user and "id=e2" in user
    assert "A one-on-one fight." in user and "Kai, Lord" in user
    # an empty summary is omitted (no dangling "summary:" line for e2).
    assert "  summary: \n" not in user


# ── parse_assignments (pure) ─────────────────────────────────────────────────────

def test_parse_keeps_valid_drops_unknown_and_none():
    content = '{"e1": "combat", "e2": "none", "e3": "combat", "e1x": "wizardry"}'
    out = parse_assignments(content, valid_keys={"combat", "romance"}, event_ids={"e1", "e2"})
    # e1 valid; e2 "none" dropped; e3 not in batch ids; "wizardry" not a legal key.
    assert out == {"e1": "combat"}


def test_parse_tolerates_a_json_code_fence():
    content = '```json\n{"e1": "romance"}\n```'
    out = parse_assignments(content, valid_keys={"combat", "romance"}, event_ids={"e1"})
    assert out == {"e1": "romance"}


def test_parse_tolerates_surrounding_prose():
    content = 'Sure! Here you go:\n{"e1": "combat"} — hope that helps'
    out = parse_assignments(content, valid_keys={"combat"}, event_ids={"e1"})
    assert out == {"e1": "combat"}


def test_parse_junk_is_empty():
    assert parse_assignments("not json at all", valid_keys={"combat"}, event_ids={"e1"}) == {}


# ── classify_event_threads (fake LLM) ────────────────────────────────────────────

def _job(content, status="completed"):
    return SimpleNamespace(status=status, result={"messages": [{"content": content}]})


class _FakeLLM:
    def __init__(self, job=None, raises=False):
        self._job, self._raises = job, raises
        self.calls = 0
    async def submit_and_wait(self, **kw):
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider down")
        return self._job


async def test_classify_returns_validated_map():
    llm = _FakeLLM(_job('{"e1": "combat", "e2": "romance"}'))
    out = await classify_event_threads(
        llm, user_id="u1", model_source="user_model", model_ref="m1",
        events=EVENTS, threads=THREADS)
    assert out == {"e1": "combat", "e2": "romance"} and llm.calls == 1


async def test_classify_degrades_to_empty_on_llm_exception():
    llm = _FakeLLM(raises=True)
    out = await classify_event_threads(
        llm, user_id="u1", model_source="user_model", model_ref="m1",
        events=EVENTS, threads=THREADS)
    assert out == {}  # advisory — never raises


async def test_classify_skips_a_non_completed_job():
    llm = _FakeLLM(_job("{}", status="failed"))
    out = await classify_event_threads(
        llm, user_id="u1", model_source="user_model", model_ref="m1",
        events=EVENTS, threads=THREADS)
    assert out == {}


async def test_classify_noops_without_threads_or_events():
    llm = _FakeLLM(_job('{"e1": "combat"}'))
    assert await classify_event_threads(llm, user_id="u", model_source="s", model_ref="m",
                                        events=EVENTS, threads=[]) == {}
    assert llm.calls == 0  # no vocabulary → no LLM call


# ── route wiring (mount + auth) ──────────────────────────────────────────────────

def test_tag_threads_route_is_registered():
    from app.main import app
    assert "/internal/extraction/tag-threads" in {r.path for r in app.routes}


def test_tag_threads_requires_internal_token():
    from fastapi.testclient import TestClient
    from app.main import app
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/internal/extraction/tag-threads",
        json={"user_id": "00000000-0000-0000-0000-000000000000",
              "book_id": "00000000-0000-0000-0000-000000000000",
              "threads": [{"key": "combat"}], "model_source": "user_model", "model_ref": "m1"})
    assert resp.status_code == 401
