"""wiki-llm M8 — unit tests for the thin advisory wiki-eval metrics (pure)."""

from __future__ import annotations

from app.benchmark.wiki.metrics import (
    aggregate_resolvability,
    citation_resolvability,
    collect_citation_marks,
    verify_flag_rate,
)


# ── verify-flag-rate ──────────────────────────────────────────────────────────


def test_verify_flag_rate_excludes_human_articles():
    articles = [
        {"generation_status": "generated"},
        {"generation_status": "generated"},
        {"generation_status": "needs_review"},
        {"generation_status": "blocked"},
        {"generation_status": None},  # human-authored — excluded
        {},  # no field — excluded
    ]
    r = verify_flag_rate(articles)
    assert r["total_ai"] == 4
    assert r["generated"] == 2 and r["needs_review"] == 1 and r["blocked"] == 1
    assert r["flagged"] == 2
    assert r["flagged_rate"] == 0.5
    assert r["clean_rate"] == 0.5


def test_verify_flag_rate_no_ai_articles_is_zero_not_div0():
    r = verify_flag_rate([{"generation_status": None}, {}])
    assert r["total_ai"] == 0
    assert r["flagged_rate"] == 0.0 and r["clean_rate"] == 0.0


# ── citation mark collection ──────────────────────────────────────────────────


def _doc(*paragraphs):
    return {"type": "doc", "content": list(paragraphs)}


def _cite(text, cite_id, *, snippet="ev", source_type="passage", chapter_id="ch1"):
    return {
        "type": "text",
        "text": text,
        "marks": [{"type": "citation", "attrs": {
            "cite_id": cite_id, "snippet": snippet,
            "source_type": source_type, "chapter_id": chapter_id,
        }}],
    }


def test_collect_dedups_by_cite_id_across_body_and_references():
    # P1 appears in the body prose AND the References list → counted once.
    body = _doc(
        {"type": "paragraph", "content": [_cite("[1]", "P1")]},
        {"type": "heading", "content": [{"type": "text", "text": "References"}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [_cite("[1] Harker...", "P1")]},
            ]},
        ]},
    )
    marks = collect_citation_marks(body)
    assert set(marks) == {"P1"}


# ── citation-resolvability ────────────────────────────────────────────────────


def test_resolvability_all_resolvable():
    body = _doc({"type": "paragraph", "content": [_cite("[1]", "P1"), _cite("[2]", "G1", source_type="glossary", chapter_id=None)]})
    r = citation_resolvability({"body_json": body, "generation_provenance": {"citations": [{}, {}]}})
    # P1 passage has snippet+chapter; G1 glossary resolves on snippet alone
    assert r["total"] == 2 and r["resolvable"] == 2 and r["ratio"] == 1.0
    assert r["declared"] == 2


def test_resolvability_flags_passage_without_anchor_and_empty_snippet():
    body = _doc({"type": "paragraph", "content": [
        _cite("[1]", "P1", chapter_id=None),     # passage with no chapter → unresolvable
        _cite("[2]", "P2", snippet="   "),        # empty snippet → unresolvable
        _cite("[3]", "P3"),                        # fine
    ]})
    r = citation_resolvability({"body_json": body, "generation_provenance": {}})
    assert r["total"] == 3 and r["resolvable"] == 1
    assert round(r["ratio"], 2) == 0.33


def test_resolvability_no_citations_is_vacuously_one():
    body = _doc({"type": "paragraph", "content": [{"type": "text", "text": "no cites"}]})
    r = citation_resolvability({"body_json": body})
    assert r["total"] == 0 and r["ratio"] == 1.0


def test_aggregate_microaverages_and_counts_offenders():
    per = [
        {"total": 2, "resolvable": 2},
        {"total": 4, "resolvable": 2},  # has unresolvable
        {"total": 0, "resolvable": 0},
    ]
    agg = aggregate_resolvability(per)
    assert agg["articles"] == 3
    assert agg["citations"] == 6 and agg["resolvable"] == 4
    assert round(agg["ratio"], 2) == 0.67
    assert agg["articles_with_unresolvable"] == 1
