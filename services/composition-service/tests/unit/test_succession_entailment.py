"""D-SUCCESSION-ENTAILMENT-JUDGE — the deepest succession signal.

Pure pieces (build_messages / parse_verdicts / _texts) are the main surface; judge_entailments
is covered with a fake LLM (batching, the advisory degrade, the validate-against-edge-ids guard).
Plus build_deep_report's entailment wiring and the worker passing llm so the job runs the judge.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.engine.arc_conformance import build_deep_report
from app.engine.succession_entailment import (
    _texts, build_messages, edge_id, judge_entailments, parse_verdicts,
)

EDGES = [
    {"from_code": "humiliation", "to_code": "face_slap",
     "from_name": "Humiliation", "to_name": "Face Slap",
     "from_effects": [{"desc": "the hero is publicly shamed and burns for revenge"}],
     "to_preconditions": [{"condition": "the hero seeks to repay a public humiliation"}]},
    {"from_code": "exile", "to_code": "tryst",
     "from_effects": [{"desc": "the hero is cast out, alone"}],
     "to_preconditions": [{"desc": "two lovers meet in secret"}]},
]


# ── _texts (pure, tolerant) ──────────────────────────────────────────────────────

def test_texts_flattens_strings_dicts_and_skips_empty():
    assert _texts([{"desc": "a shaming"}, "a vow", {"condition": "the debt stands"}]) \
        == "a shaming; a vow; the debt stands"
    assert _texts([{"x": 1, "y": "note"}]) == "1; note"   # falls back to scalar values
    assert _texts([]) == "" and _texts(None) == ""


# ── build_messages (pure) ────────────────────────────────────────────────────────

def test_build_messages_lists_each_edge_with_effects_and_preconditions():
    msgs = build_messages(EDGES)
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    assert "id=humiliation->face_slap" in user and "id=exile->tryst" in user
    assert "publicly shamed" in user and "repay a public humiliation" in user


# ── parse_verdicts (pure) ────────────────────────────────────────────────────────

def test_parse_keeps_valid_edge_bools_drops_unknown():
    content = ('{"humiliation->face_slap": true, "exile->tryst": false, '
               '"ghost->x": true}')
    out = parse_verdicts(content, valid_edge_ids={"humiliation->face_slap", "exile->tryst"})
    assert out == {"humiliation->face_slap": True, "exile->tryst": False}


def test_parse_accepts_string_bools_and_tolerates_a_fence():
    content = '```json\n{"a->b": "true", "c->d": "FALSE"}\n```'
    out = parse_verdicts(content, valid_edge_ids={"a->b", "c->d"})
    assert out == {"a->b": True, "c->d": False}


def test_parse_junk_is_empty():
    assert parse_verdicts("not json", valid_edge_ids={"a->b"}) == {}


# ── judge_entailments (fake LLM) ─────────────────────────────────────────────────

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


async def test_judge_returns_only_entailed_pairs():
    llm = _FakeLLM(_job('{"humiliation->face_slap": true, "exile->tryst": false}'))
    out = await judge_entailments(llm, user_id="u", model_source="user_model", model_ref="m",
                                  edges=EDGES)
    assert out == {("humiliation", "face_slap")} and llm.calls == 1


async def test_judge_degrades_to_empty_on_llm_exception():
    llm = _FakeLLM(raises=True)
    out = await judge_entailments(llm, user_id="u", model_source="s", model_ref="m", edges=EDGES)
    assert out == set()  # advisory — never raises


async def test_judge_noops_without_edges():
    llm = _FakeLLM(_job("{}"))
    assert await judge_entailments(llm, user_id="u", model_source="s", model_ref="m", edges=[]) == set()
    assert llm.calls == 0


def test_edge_id_is_stable():
    assert edge_id("a", "b") == "a->b"


# ── build_deep_report entailment wiring ──────────────────────────────────────────

def test_deep_succession_entailment_verified_when_judge_backs_a_legal_transition():
    seqs = [[{"realized_motif_code": "humiliation"}, {"realized_motif_code": "face_slap"}]]
    out = build_deep_report(
        sequences=seqs, chapter_index_by_id={}, planned_by_index={},
        precedes_code_pairs={("humiliation", "face_slap")},
        entailed_code_pairs={("humiliation", "face_slap")})
    s = out["succession"]
    assert s["legal"] == 1 and s["entailed"] == 1 and s["entailment_verified"] is True
    # entailment is independent of causal — no causal pairs here.
    assert s["causal_verified"] is False


def test_deep_succession_structural_only_has_zero_entailed():
    seqs = [[{"realized_motif_code": "humiliation"}, {"realized_motif_code": "face_slap"}]]
    out = build_deep_report(sequences=seqs, chapter_index_by_id={}, planned_by_index={},
                            precedes_code_pairs={("humiliation", "face_slap")})
    s = out["succession"]
    assert s["entailed"] == 0 and s["entailment_verified"] is False
