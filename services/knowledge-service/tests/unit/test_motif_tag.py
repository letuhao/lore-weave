"""D-W10-ARC-CONFORMANCE-SUCCESSION (F1) — the realized-motif classifier.

Pure pieces (build_messages / parse_assignments) + classify_event_motifs with a fake LLM
(advisory degrade, validate-against-vocabulary) + route mount/auth. Sibling of test_thread_tag.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.extraction.motif_tag import (
    build_messages, classify_event_motifs, parse_assignments,
)

MOTIFS = [{"code": "revenge.duel", "name": "Duel", "summary": "A one-on-one fight to settle a wrong."},
          {"code": "romance.tryst", "name": "Tryst"}]
EVENTS = [
    {"id": "e1", "title": "Duel at dawn", "summary": "A one-on-one fight.", "participants": ["Kai", "Lord"]},
    {"id": "e2", "title": "A quiet confession", "summary": "", "participants": ["Lin"]},
]


def test_build_messages_lists_codes_with_summaries_and_event_fields():
    user = build_messages(EVENTS, MOTIFS)[1]["content"]
    assert "revenge.duel" in user and "romance.tryst" in user
    assert "A one-on-one fight to settle a wrong." in user   # motif summary offered
    assert "id=e1" in user and "Kai, Lord" in user


def test_parse_keeps_valid_codes_drops_none_unknown_and_foreign_ids():
    content = '{"e1": "revenge.duel", "e2": "none", "e3": "revenge.duel", "e1": "x.y"}'
    # note: JSON dup key — last wins ("x.y"), which is not a valid code → dropped.
    out = parse_assignments(content, valid_codes={"revenge.duel", "romance.tryst"},
                            event_ids={"e1", "e2"})
    assert out == {}  # e1→x.y invalid, e2→none dropped, e3 not in batch


def test_parse_keeps_a_valid_assignment():
    out = parse_assignments('{"e1": "revenge.duel"}',
                            valid_codes={"revenge.duel"}, event_ids={"e1", "e2"})
    assert out == {"e1": "revenge.duel"}


def test_parse_tolerates_code_fence():
    out = parse_assignments('```json\n{"e1": "romance.tryst"}\n```',
                            valid_codes={"romance.tryst"}, event_ids={"e1"})
    assert out == {"e1": "romance.tryst"}


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
    llm = _FakeLLM(_job('{"e1": "revenge.duel", "e2": "romance.tryst"}'))
    out = await classify_event_motifs(llm, user_id="u", model_source="user_model",
                                      model_ref="m1", events=EVENTS, motifs=MOTIFS)
    assert out == {"e1": "revenge.duel", "e2": "romance.tryst"} and llm.calls == 1


async def test_classify_degrades_on_exception():
    llm = _FakeLLM(raises=True)
    assert await classify_event_motifs(llm, user_id="u", model_source="user_model",
                                       model_ref="m1", events=EVENTS, motifs=MOTIFS) == {}


async def test_classify_noops_without_vocab():
    llm = _FakeLLM(_job('{"e1": "revenge.duel"}'))
    assert await classify_event_motifs(llm, user_id="u", model_source="s", model_ref="m",
                                       events=EVENTS, motifs=[]) == {}
    assert llm.calls == 0


def test_tag_motifs_route_is_registered():
    from app.main import app
    assert "/internal/extraction/tag-motifs" in {r.path for r in app.routes}


def test_tag_motifs_requires_internal_token():
    from fastapi.testclient import TestClient
    from app.main import app
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/internal/extraction/tag-motifs",
        json={"user_id": "00000000-0000-0000-0000-000000000000",
              "book_id": "00000000-0000-0000-0000-000000000000",
              "motifs": [{"code": "revenge.duel"}], "model_source": "user_model", "model_ref": "m1"})
    assert resp.status_code == 401
