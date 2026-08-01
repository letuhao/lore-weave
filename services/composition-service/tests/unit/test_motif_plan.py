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
    """`by_query` (optional) maps the `query=` value → the candidates to return, so a test
    can distinguish the premise-seeded call from the unseeded fallback. Every call's kwargs
    land in `calls`; `kw` stays the LAST call for the existing assertions."""

    def __init__(self, cands, by_query=None):
        self._cands = cands
        self._by_query = by_query
        self.kw = None
        self.calls: list[dict] = []

    async def retrieve(self, caller_id, **kw):
        self.kw = kw
        self.calls.append(kw)
        if self._by_query is not None:
            return self._by_query.get(kw.get("query"), [])
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
    # arc-level retrieve: no beat / tension / prev_effects — but SEEDED WITH THE PREMISE.
    assert retr.kw["beat_role"] is None and retr.kw["tension"] is None and retr.kw["prev_effects"] is None
    assert retr.kw["genre_tags"] == ["xianxia"]
    assert retr.kw["query"] == "xianxia premise"


async def test_select_arc_motifs_seeds_retrieve_with_the_premise():
    """Without the premise the arc retrieve has NO query text, so every candidate falls to
    the degrade path where ranks tie and the cap goes to whichever pack sorts first — live,
    that made the library section 15/15 `cultivation.*` regardless of what the book was
    about. The premise was already in this function's signature, used only for the prompt."""
    seeded = [_Cand("romance.slow_thaw", "Slow Thaw", "accumulated small mercies")]
    retr = _Retriever(None, by_query={"a physician's daughter and the ruined heir": seeded})
    llm = _LLM(json.dumps([{"code": "romance.slow_thaw", "why": "spine", "arc_role": "spine"}]))
    out = await select_arc_motifs(
        llm, retr, user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", book_id=BOOK, project_id=PROJ,
        premise="a physician's daughter and the ruined heir", genre_tags=[],
        model_source="user_model", model_ref="m")
    assert [m.code for m in out] == ["romance.slow_thaw"]
    assert len(retr.calls) == 1                      # one call, and it carried the premise
    assert retr.calls[0]["query"] == "a physician's daughter and the ruined heir"


async def test_select_arc_motifs_falls_back_when_the_seeded_query_matches_nothing():
    """Seeding adds a cosine floor (`motif_min_score`) that the unseeded degrade path does
    not have, so a premise unlike anything in the library could return FEWER candidates than
    before. It must only ever ADD reach: an empty seeded result retries unseeded."""
    fallback = [_Cand("cultivation.face_slap", "Face Slap", "public reversal")]
    retr = _Retriever(None, by_query={"an unmatchable premise": [], None: fallback})
    llm = _LLM(json.dumps([{"code": "cultivation.face_slap", "why": "w", "arc_role": "r"}]))
    out = await select_arc_motifs(
        llm, retr, user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", book_id=BOOK, project_id=PROJ,
        premise="an unmatchable premise", genre_tags=[],
        model_source="user_model", model_ref="m")
    assert [m.code for m in out] == ["cultivation.face_slap"]
    assert [c["query"] for c in retr.calls] == ["an unmatchable premise", None]


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


# ── the silent drop that read as an empty library ────────────────────────────────────────────────

def test_an_INVENTED_code_is_reported_not_just_dropped():
    """Live: retrieval handed the model 30 candidates, it answered with codes that were not in the
    catalog, every one was dropped by a bare `continue`, and the pass reported "the library had no
    candidate for its language/genre". A selection failure wearing a retrieval failure's message —
    which sends the author to fix a library that is fine."""
    from app.engine.motif_plan import parse_selected_motifs

    by_code = {"real.one": {"code": "real.one", "name": "Real", "summary": "s"}}
    dropped: list[str] = []
    out = parse_selected_motifs(
        '[{"code":"cultivation.dao_heart_temper","why":"w","arc_role":"spine"},'
        ' {"code":"real.one","why":"w2","arc_role":"echo"}]',
        by_code, dropped=dropped)
    assert [m.code for m in out] == ["real.one"]          # never invents
    assert dropped == ["cultivation.dao_heart_temper"]    # …and says what it threw away


def test_a_CASE_or_WHITESPACE_near_miss_is_recovered_not_discarded():
    """Catalog codes are machine-ugly (`3b.faceslap.1784257099`), so a model echoing them fumbles
    case and padding. That is a near-miss, not an invention, and discarding it cost a real motif."""
    from app.engine.motif_plan import parse_selected_motifs

    by_code = {"3b.FaceSlap.1784257099": {"code": "3b.FaceSlap.1784257099", "name": "N", "summary": "s"}}
    dropped: list[str] = []
    out = parse_selected_motifs(
        '[{"code":"  3b.faceslap.1784257099 ","why":"w","arc_role":"r"}]', by_code, dropped=dropped)
    assert [m.code for m in out] == ["3b.FaceSlap.1784257099"]   # the REAL catalog code
    assert dropped == []


def test_recovery_never_becomes_invention():
    """The tolerance must not widen into fuzzy matching — a code that merely LOOKS similar is still
    an invention, and binding it would put a motif in the plan the model never chose."""
    from app.engine.motif_plan import parse_selected_motifs

    by_code = {"a.real.code": {"code": "a.real.code", "name": "N", "summary": "s"}}
    dropped: list[str] = []
    assert parse_selected_motifs('[{"code":"a.real.cod"}]', by_code, dropped=dropped) == []
    assert dropped == ["a.real.cod"]


def test_dropped_is_OPTIONAL_so_existing_callers_are_unchanged():
    from app.engine.motif_plan import parse_selected_motifs

    by_code = {"x": {"code": "x", "name": "N", "summary": "s"}}
    assert len(parse_selected_motifs('[{"code":"x"}]', by_code)) == 1
    assert parse_selected_motifs('[{"code":"nope"}]', by_code) == []
