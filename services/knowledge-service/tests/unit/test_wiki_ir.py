"""M0 — Wiki Article IR + parser + mappers (pure, no I/O). Phase-1 §C1/C2/C3.

Load-bearing behaviours (the contract M3/M4/M5 depend on):
  - cite labels are OURS → unknown bracket tokens are DROPPED (no hallucinated refs);
  - a non-trivial span with zero resolved cites is flagged grounded=False (rule-gate);
  - IR→TipTap emits ContentRenderer-vocabulary nodes + a structured `citation` mark;
  - IR↔Markdown round-trips (feedback-gold diffs).
"""

from app.wiki import (
    Source,
    has_grounded_content,
    ir_to_markdown,
    ir_to_plaintext,
    ir_to_tiptap,
    parse_article,
    parse_blocks,
)
from app.wiki.parse import _is_nontrivial, _parse_inline

SOURCES = [
    Source(cite_id="G1", kind="glossary", snippet="姜尚"),
    Source(cite_id="P1", kind="passage", chapter_id="ch15", block_index=34,
           chapter_sort_order=15, score=0.94, snippet="昆仑山玉虚宫"),
    Source(cite_id="P2", kind="passage", chapter_id="ch23", block_index=12,
           chapter_sort_order=23, score=0.88, snippet="渭水之畔"),
]

MARKDOWN = """\
姜子牙，姓姜名尚[G1]，是元始天尊弟子[P1]。

## 生平

他于渭水垂钓[P2]，后辅佐周室建立功业流传千古。

- 师承元始天尊[P1]
- 道号飞熊

> 此为自动增补的补充设定[P9]，非原典正史，仅供参考阅读。

这一段没有任何引用却是非平凡的论断应当被标记为未接地。
"""


def _ir():
    return parse_article(
        MARKDOWN, entity_id="e1", display_name="姜子牙", kind="character",
        language="zh", sources=SOURCES,
    )


# ── parsing / block structure ────────────────────────────────────────────────

def test_block_structure_and_lead():
    blocks = parse_blocks(MARKDOWN, SOURCES)
    types = [b.type for b in blocks]
    # first paragraph (before any heading) is the lead
    assert types[0] == "lead"
    assert "heading" in types and "list" in types and "enriched" in types
    assert "paragraph" in types
    heading = next(b for b in blocks if b.type == "heading")
    assert heading.level == 2
    assert "".join(s.text for s in heading.spans).strip() == "生平"
    lst = next(b for b in blocks if b.type == "list")
    assert lst.ordered is False and len(lst.items) == 2


def test_cite_lift_and_unknown_dropped():
    blocks = parse_blocks(MARKDOWN, SOURCES)
    all_cites = {c for b in blocks for s in b.all_spans() for c in s.cites}
    assert all_cites == {"G1", "P1", "P2"}        # P9 (not in sources) dropped
    enriched = next(b for b in blocks if b.type == "enriched")
    # the enriched span only had the unknown [P9] → no resolved cite → grounded False
    assert all(s.source_type == "enriched" for s in enriched.spans)
    assert any(s.grounded is False and not s.cites for s in enriched.spans)


def test_grounded_flag():
    blocks = parse_blocks(MARKDOWN, SOURCES)
    # the trailing uncited non-trivial paragraph is flagged grounded=False
    last = blocks[-1]
    assert last.type == "paragraph"
    assert last.spans and last.spans[0].grounded is False and not last.spans[0].cites
    # a cited span is grounded
    lead = blocks[0]
    assert any(s.grounded and s.cites for s in lead.spans)


def test_nontrivial_heuristic():
    assert _is_nontrivial("姜子牙是元始天尊弟子")
    assert not _is_nontrivial("。，")
    assert not _is_nontrivial("飞熊")  # 2 content chars → trivial


def test_trivial_uncited_span_stays_grounded():
    spans = _parse_inline("据载[P1]。", {"P1"})
    # the trailing "。" is trivial → grounded stays True (no false flag)
    trailing = [s for s in spans if not s.cites]
    assert all(s.grounded for s in trailing)


def test_source_chapter_max_and_spoiler_horizon():
    ir = _ir()
    # the 生平 paragraph cites P2 (chapter sort 23)
    para = next(b for b in ir.blocks if b.type == "paragraph" and any("P2" in s.cites for s in b.spans))
    assert para.source_chapter_max == 23
    assert ir.spoiler_horizon == 23          # max over blocks
    assert ir.grounded_claim_count >= 3
    assert has_grounded_content(ir) is True


# ── IR → TipTap (the stored body) ────────────────────────────────────────────

def test_tiptap_shape_and_vocabulary():
    doc = ir_to_tiptap(_ir())
    assert doc["type"] == "doc"
    node_types = {n["type"] for n in doc["content"]}
    # only nodes the FE ContentRenderer supports
    assert node_types <= {"paragraph", "heading", "bulletList", "orderedList",
                          "blockquote", "callout", "horizontalRule"}
    assert {"paragraph", "heading", "bulletList", "callout"} <= node_types
    callout = next(n for n in doc["content"] if n["type"] == "callout")
    assert callout["attrs"]["source_type"] == "enriched"


def test_tiptap_citation_mark():
    doc = ir_to_tiptap(_ir())

    def marks(node):
        out = []
        for m in node.get("marks", []):
            out.append(m)
        for c in node.get("content", []):
            out.extend(marks(c))
        return out

    all_marks = [m for n in doc["content"] for m in marks(n)]
    cites = [m for m in all_marks if m["type"] == "citation"]
    assert cites, "no citation marks emitted"
    attrs = cites[0]["attrs"]
    assert set(attrs) >= {"cite_id", "n", "source_type", "chapter_id", "block_index", "score", "snippet"}
    # a passage citation carries its jump-to-source anchor
    p1 = next(m["attrs"] for m in cites if m["attrs"]["cite_id"] == "P1")
    assert p1["chapter_id"] == "ch15" and p1["block_index"] == 34 and p1["snippet"] == "昆仑山玉虚宫"
    # references section present
    assert any(n["type"] == "heading" and "References" in n["content"][0]["text"] for n in doc["content"])


def test_tiptap_no_empty_paragraph_content_key():
    # paragraphs with content carry it; an empty one omits the key (valid TipTap)
    doc = ir_to_tiptap(_ir())
    for n in doc["content"]:
        if n["type"] == "paragraph" and "content" in n:
            assert n["content"]


# ── IR → Markdown round-trip + plaintext ─────────────────────────────────────

def test_markdown_roundtrip_stable():
    ir1 = _ir()
    md = ir_to_markdown(ir1)
    assert "## 生平" in md and "[P1]" in md and md.count("> ") >= 1
    # re-parse → same block types + same resolved cites (P9 already gone)
    ir2 = parse_article(md, entity_id="e1", display_name="姜子牙",
                        kind="character", language="zh", sources=SOURCES)
    assert [b.type for b in ir1.blocks] == [b.type for b in ir2.blocks]
    cites1 = {c for b in ir1.blocks for s in b.all_spans() for c in s.cites}
    cites2 = {c for b in ir2.blocks for s in b.all_spans() for c in s.cites}
    assert cites1 == cites2 == {"G1", "P1", "P2"}


def test_plaintext_has_no_markers():
    txt = ir_to_plaintext(_ir())
    assert "姜子牙" in txt and "生平" not in txt.split("\n")[0]
    assert "[P1]" not in txt and "##" not in txt


# ── coverage: ordered list · heading levels · empty article (review-impl LOW-2) ──

def test_ordered_list():
    md = "1. 第一条记载[P1]\n2. 第二条记载\n"
    blocks = parse_blocks(md, SOURCES)
    lst = next(b for b in blocks if b.type == "list")
    assert lst.ordered is True and len(lst.items) == 2
    doc = ir_to_tiptap(parse_article(md, entity_id="e", display_name="x", sources=SOURCES))
    assert any(n["type"] == "orderedList" for n in doc["content"])


def test_heading_levels_clamp():
    md = "## H2\n\n### H3\n\n#### deeper clamps to three\n"
    levels = [b.level for b in parse_blocks(md, SOURCES) if b.type == "heading"]
    assert levels == [2, 3, 3]  # only h2/h3 in the reader; #### clamps to 3


def test_empty_article():
    ir = parse_article("", entity_id="e", display_name="x", sources=[])
    assert ir.blocks == []
    assert ir.spoiler_horizon is None
    assert ir.grounded_claim_count == 0
    assert has_grounded_content(ir) is False
    assert ir_to_tiptap(ir) == {"type": "doc", "content": []}
    assert ir_to_markdown(ir).strip() == ""
    assert ir_to_plaintext(ir) == ""
