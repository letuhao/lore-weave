"""Unit tests for the wiki generation rule-gate (wiki-llm M3 / §C2)."""
from __future__ import annotations

from app.wiki.ir import Source
from app.wiki.parse import parse_article
from app.wiki.rulegate import evaluate


def _ir(markdown: str, sources: list[Source]):
    return parse_article(
        markdown, entity_id="e1", display_name="姜子牙", kind="character",
        language="zh", sources=sources,
    )


_P1 = Source(cite_id="P1", kind="passage", chapter_id="c", block_index=1,
             chapter_sort_order=3, snippet="x")


def test_grounded_article_passes():
    ir = _ir("姜子牙是封神演义的主角，奉命下山伐纣 [P1]。", [_P1])
    g = evaluate(ir)
    assert g.passed is True
    assert g.grounded_claims >= 1
    assert g.reasons == []


def test_zero_grounded_fails():
    ir = _ir("姜子牙是一个非常重要的封神人物。", [_P1])  # non-trivial, no cite
    g = evaluate(ir)
    assert g.passed is False
    assert g.grounded_claims == 0
    assert any("no grounded claims" in r for r in g.reasons)


def test_empty_body_fails():
    g = evaluate(_ir("", [_P1]))
    assert g.passed is False
    assert g.block_count == 0
    assert any("empty" in r for r in g.reasons)


def test_high_ungrounded_ratio_passes_with_soft_warning():
    # 1 grounded + 2 ungrounded non-trivial spans → ratio 2/3 > 0.5 → soft note,
    # still passes (Q2-A: only zero-grounded hard-fails at M3).
    md = (
        "姜子牙是主角 [P1]。\n\n"
        "他在昆仑山修行了许多年并且法力高强非常厉害。\n\n"
        "后来他辅佐周室建立了不朽的功勋名垂青史。"
    )
    g = evaluate(_ir(md, [_P1]))
    assert g.passed is True
    assert g.grounded_claims == 1
    assert g.ungrounded_nontrivial >= 2
    assert g.ungrounded_ratio > 0.5
    assert any("soft" in r for r in g.reasons)
