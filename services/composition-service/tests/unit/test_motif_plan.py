"""Unit tests for planning Stage 1 — select_arc_motifs (engine/motif_plan.py).

Focus: the code→catalog mapping (drop invented/unknown/dup codes — never invent a
motif), the arc-level retrieve call shape (no beat/query), and the degrade paths.
"""

import json
from types import SimpleNamespace
from uuid import UUID

from app.engine import motif_plan
from app.engine.motif_plan import build_select_motifs_messages, parse_selected_motifs, select_arc_motifs

BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")
PROJ = UUID("019f1783-ecca-7331-afab-9543762a8b68")
_CATALOG = {
    "xau_hoa_my": {"code": "xau_hoa_my", "name": "Xấu hóa mỹ", "summary": "ugly → perfect"},
    "ma_cong": {"code": "ma_cong", "name": "Ma công phản phệ", "summary": "forbidden power"},
}


def test_parse_selected_maps_codes_and_drops_unknown_and_dup():
    content = ('noise ['
               '{"code":"xau_hoa_my","why":"core arc","arc_role":"central spine"},'
               '{"code":"INVENTED","why":"nope"},'          # not in catalog → drop
               '{"code":"ma_cong","why":"the price","arc_role":"recurring"},'
               '{"code":"xau_hoa_my","why":"dup"}'          # duplicate → drop
               '] noise')
    out = parse_selected_motifs(content, _CATALOG)
    assert [m.code for m in out] == ["xau_hoa_my", "ma_cong"]
    assert out[0].name == "Xấu hóa mỹ" and out[0].arc_role == "central spine"
    assert out[1].why == "the price"
    assert parse_selected_motifs("no json", _CATALOG) == []
    assert parse_selected_motifs("", _CATALOG) == []


def test_build_messages_lists_catalog_and_cap():
    cands = [{"code": "a", "name": "A", "summary": "s1"}, {"code": "b", "name": "B", "summary": "s2"}]
    system, user = build_select_motifs_messages("a premise", cands, max_select=3, source_language="vi")
    assert "at most 3" in system and "EXACT `code`" in system
    assert "a: A — s1" in user and "b: B — s2" in user and "PREMISE:" in user


class _Cand:
    def __init__(self, code, name, summary):
        self.motif = SimpleNamespace(code=code, name=name, summary=summary)


class _Retriever:
    def __init__(self, cands):
        self._cands = cands
        self.kw = None

    async def retrieve(self, caller_id, **kw):
        self.kw = kw
        return self._cands


class _LLM:
    def __init__(self, content, status="completed"):
        self._content, self._status = content, status

    async def submit_and_wait(self, **kw):
        return SimpleNamespace(status=self._status, result={"messages": [{"content": self._content}]})


async def test_select_arc_motifs_happy_and_retrieve_shape():
    retr = _Retriever([_Cand("xau_hoa_my", "Xấu hóa mỹ", "ugly→perfect"),
                       _Cand("ma_cong", "Ma công phản phệ", "forbidden power")])
    llm = _LLM(json.dumps([{"code": "xau_hoa_my", "why": "core", "arc_role": "spine"}]))
    out = await select_arc_motifs(
        llm, retr, user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", book_id=BOOK, project_id=PROJ,
        premise="xianxia premise", genre_tags=["xianxia"], source_language="vi",
        model_source="user_model", model_ref="m")
    assert len(out) == 1 and out[0].code == "xau_hoa_my" and out[0].summary == "ugly→perfect"
    # arc-level retrieve: NO beat / tension / query (the full-pool degrade path)
    assert retr.kw["beat_role"] is None and retr.kw["tension"] is None and retr.kw["prev_effects"] is None
    assert retr.kw["genre_tags"] == ["xianxia"]


async def test_select_arc_motifs_no_candidates_is_empty():
    llm = _LLM(json.dumps([{"code": "x"}]))
    out = await select_arc_motifs(
        llm, _Retriever([]), user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
        book_id=BOOK, project_id=PROJ, premise="p", genre_tags=["xianxia"],
        model_source="user_model", model_ref="m")
    assert out == []


async def test_select_arc_motifs_degrades_on_non_completion():
    retr = _Retriever([_Cand("xau_hoa_my", "X", "s")])
    out = await select_arc_motifs(
        _LLM("", "failed"), retr, user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
        book_id=BOOK, project_id=PROJ, premise="p", genre_tags=["xianxia"],
        model_source="user_model", model_ref="m")
    assert out == []
