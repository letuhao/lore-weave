"""The ingest/propose fixes of 2026-07-28 — measured against a document shaped like a real one.

## Why this file exists

This project's own Mị Đế planning document — 4,279 chars, 14 headings, premise + a cast of four +
relationships + the opening arc — parsed to **ZERO sections** and produced an entirely empty spec,
silently. `plan_run` still holds the row (`rules | proposed | 4278`); the author got nothing back and
switched to llm mode to work around it. Across the database, rules is 251 of 281 runs.

The cause was a parser that required `# <n>. Title`, which is the shape of the POC's OWN braindump.
`validate.py` already confesses the same disease about its rules: *"this whole module started as the
POC's OWN golden-fixture acceptance test ... reused directly as the LIVE per-user gate without ever
being generalized."*

So the document below is deliberately NOT the golden fixture. It is shaped like something a person
writes: unnumbered headings, a cast as a numbered list, an arc described in prose, a fenced code
block, a table of contents. Two of the assertions here are regressions I introduced while fixing
this and the golden tests caught — they are pinned so nobody has to catch them twice.
"""
from __future__ import annotations

import pathlib

from app.engine.plan_forge.ingest import ingest_markdown
from app.engine.plan_forge.propose import propose_spec

REAL_SHAPED = """# Truyện của tôi

Một cuốn huyền huyễn, thế giới tàn khốc.

# MỤC LỤC

- Bối cảnh
- Nhân vật

# Bối cảnh

Tu luyện được lượng hóa bằng khoa học.

# Nhân vật

## 1. Lâm Uyên (Nam chính)

-   Thiếu chủ dòng chính Lâm gia.
-   Thiên phú tuyệt thế.

## 2. Tô Thanh Dao

-   Đại tiểu thư Tô gia.
-   Thông minh, lý trí.

## 3. Lâm Trạch

-   Người của phân gia.

# Biến trạng thái

```
# the fence below must NOT split this section
DBT = Doubt        [0 -> 100]
      ↑ mỗi lần bị phản bội
```

# Arc mở đầu

Lâm Uyên bị bạn thân hãm hại trong lần tranh đoạt cơ duyên.

# Cốt truyện hàng vạn năm sau

Người kế thừa tìm lại dấu vết của Huyết Chủ.

# Một mục tôi tự bịa ra

Nội dung không thuộc loại nào cả.
"""


def _doc():
    return ingest_markdown(REAL_SHAPED)


# ── the parser ───────────────────────────────────────────────────────────────────────────────────

def test_an_unnumbered_heading_is_a_section():
    """The whole defect in one assertion. `# Bối cảnh` is how people write; `# 1. Bối cảnh` is how
    one fixture happened to."""
    titles = [s["title"] for s in _doc()["sections"]]
    assert "Bối cảnh" in titles and "Nhân vật" in titles and "Arc mở đầu" in titles


def test_a_numbered_document_still_parses_IDENTICALLY():
    """Loosening may only ADD. A document written the old way must keep its section ids, because
    those ids are stored in the `document` artifact of every run ever made."""
    md = "# 1. Nhân vật\n\nAi đó.\n\n# 2. Arc Overview\n\nChuyện gì đó.\n"
    secs = ingest_markdown(md)["sections"]
    assert [s["id"] for s in secs] == ["section_1", "section_2"]
    assert [s["kind"] for s in secs] == ["character_seed", "arc_overview"]


def test_a_hash_INSIDE_a_fenced_block_is_not_a_heading():
    """A regression I introduced fixing this, caught by the golden test rather than by review.

    The old regex never matched inside a code fence BY ACCIDENT. Loosening it split the fixture's
    variables block in two and every declared state variable vanished from the spec — a parse that
    silently halves a section is worse than the strict regex it replaced."""
    var = [s for s in _doc()["sections"] if s["title"] == "Biến trạng thái"]
    assert len(var) == 1
    assert "DBT = Doubt" in var[0]["body"], "the fenced block was split off its own section"
    assert not any(s["title"].startswith("the fence") for s in _doc()["sections"])


# ── the honesty block ────────────────────────────────────────────────────────────────────────────

def test_unread_names_what_it_could_not_classify():
    """`other` is ignored downstream, which makes an ignored section indistinguishable from one the
    author never wrote. Naming it is what makes it actionable — "6 sections ignored" is not."""
    unread = _doc()["unread"]
    assert "Một mục tôi tự bịa ra" in unread["unclassified"]
    assert "Một mục tôi tự bịa ra" in unread["note"]


def test_unread_is_ALWAYS_present_even_on_a_clean_read():
    """A key that appears only on failure cannot be distinguished from an older ingest that never
    reported at all — the same reason `ResolvedStructure` always emits its provenance."""
    clean = ingest_markdown("# 1. Nhân vật\n\nAi đó.\n")
    assert clean["unread"]["note"] == ""
    assert clean["unread"]["sections_read"] == 1
    assert clean["unread"]["unclassified"] == []


def test_an_UNCLOSED_fence_that_swallows_the_document_says_so():
    """The nastiest shape, and the one the fence fix creates: an unbalanced ``` is valid-looking
    markdown that eats every heading after it. Without this the first sections classify fine and the
    note stays empty — a PARTIAL read reported as a clean one, which is the same silence this whole
    guard exists to end, just quieter."""
    md = "# Nhân vật\n\nAi đó.\n\n```\nchưa đóng fence\n\n# Arc mở đầu\n\nChuyện gì đó.\n"
    doc = ingest_markdown(md)
    assert len(doc["sections"]) == 1, "the fence should have swallowed the second heading"
    unread = doc["unread"]
    assert unread["sections_read"] == 1
    assert "unclosed" in unread["note"] and "fence" in unread["note"]


def test_a_document_that_reads_as_NOTHING_says_so():
    """The defect's own signature: headings present, sections zero. Silence here is what let an
    author submit a full planning document and receive an empty spec marked `proposed`."""
    unread = ingest_markdown("Chỉ là văn xuôi, không có heading nào.\n")["unread"]
    assert unread["sections_read"] == 0
    assert "no '# ' headings" in unread["note"]


def test_a_table_of_contents_is_understood_and_ignored_not_reported():
    """`front_matter` ≠ `other`. A guard that fires on every well-organised document is a guard
    nobody reads, and then it is not a guard."""
    doc = _doc()
    assert any(s["kind"] == "front_matter" for s in doc["sections"])
    assert "MỤC LỤC" not in doc["unread"]["unclassified"]


# ── extraction ───────────────────────────────────────────────────────────────────────────────────

def test_a_cast_of_three_is_three_characters_not_one_TBD():
    """`_characters` returned AT MOST ONE — hardcoded `id="protagonist"`, name from a `Name:` field
    — so four named characters collapsed to one entry called "[TBD]", and the cast pass then planned
    with that placeholder in its prompt."""
    chars = (propose_spec(_doc())["layers"] or {})["characters"]
    assert [c["name"] for c in chars] == ["Lâm Uyên", "Tô Thanh Dao", "Lâm Trạch"]
    assert chars[0]["id"] == "protagonist", "the first listed is still the protagonist"
    assert chars[0]["role"] == "Nam chính", "the parenthetical is how a braindump states a role"
    # Each person's OWN bullets — not the section-wide anchors, which would give every character
    # the same personality.
    assert "Thiên phú tuyệt thế." in chars[0]["traits"]
    assert "Thiên phú tuyệt thế." not in chars[1]["traits"]


def test_a_DOTTED_subsection_is_not_a_character():
    """The ambiguity `## ` carries: "the next character" vs "the next aspect of this character".
    A dotted `N.M` header is a sub-section of section N — splitting on it turned one protagonist's
    six profile sections into six people named after their own headings."""
    md = ("# Nhân vật\n\n## 1.1 Hồ Sơ Cơ Bản\n\n**Tên:** Lâm Uyên\n\n"
          "## 1.2 Ngoại Hình\n\n-   Cao gầy.\n")
    chars = (propose_spec(ingest_markdown(md))["layers"] or {})["characters"]
    assert [c["name"] for c in chars] == ["Lâm Uyên"]


def test_an_explicit_Name_field_BEATS_the_heading():
    """A regression I introduced, caught by the golden test: a document may use the sub-heading as a
    LABEL ("## The Detective") and state the real name in the field. Taking the header
    unconditionally renamed that character to their own role."""
    md = "# Characters\n\n## The Detective\n**Name:** Mara Vance\n**Baseline:** She stopped believing.\n"
    chars = (propose_spec(ingest_markdown(md))["layers"] or {})["characters"]
    assert [c["name"] for c in chars] == ["Mara Vance"]


def test_an_arc_section_of_plain_PROSE_is_one_arc():
    """Arcs needed `## ` blocks inside the section. An author who writes `# Arc mở đầu` followed by
    prose has described exactly one arc, and reading zero out of a section the classifier just
    called `arc_overview` is a contradiction the caller cannot see."""
    arcs = propose_spec(_doc())["arcs"]
    assert "Arc mở đầu" in [a["title"] for a in arcs]


def test_EVERY_arc_section_is_read_and_ids_stay_unique():
    """`_section` returns the FIRST match, so a document with several arc sections contributed only
    one — the rest were classified, stored, and never read. Ids must stay unique across them or
    events point at a shared arc."""
    arcs = propose_spec(_doc())["arcs"]
    titles = [a["title"] for a in arcs]
    assert "Arc mở đầu" in titles and "Cốt truyện hàng vạn năm sau" in titles
    ids = [a["id"] for a in arcs]
    assert len(ids) == len(set(ids)), f"duplicate arc ids: {ids}"


def test_open_questions_written_as_plain_BULLETS_are_still_read():
    """The same format-bound assumption one layer deeper, and much better hidden: the section was
    correctly CLASSIFIED as `open_questions` and still extracted nothing, so the gap looked closed at
    the classifier and stayed open at the compiler. Found by round-tripping a composed section back
    through the real ingest — a check worth having precisely because the classification succeeded."""
    md = ("# Câu hỏi còn bỏ ngỏ\n\n"
          "- Lâm Uyên có thật sự trùng sinh?\n"
          "- Tô Thanh Dao cuối cùng đứng về phía nào?\n")
    spec = propose_spec(ingest_markdown(md))
    assert len(spec["meta"]["open_questions"]) == 2


def test_a_CHECKBOX_still_wins_over_a_bullet():
    """Checkboxes carry the author's own done/not-done state, which a plain bullet cannot — so the
    fallback must not start swallowing statements that sit beside real checkboxes."""
    md = ("# Open Questions\n\n"
          "- [ ] Does she survive the duel?\n"
          "- A statement that is not a question.\n")
    spec = propose_spec(ingest_markdown(md))
    assert spec["meta"]["open_questions"] == ["Does she survive the duel?"]


def test_the_whole_document_produces_a_NON_empty_spec():
    """The end-to-end statement of the bug: this shape used to yield 0 characters, 0 mechanics,
    0 arcs — an empty spec, reported as a successful propose."""
    spec = propose_spec(_doc())
    layers = spec["layers"]
    assert len(layers["characters"]) == 3
    assert len(layers["mechanics"]) >= 1
    assert len(spec["arcs"]) >= 2


# ── generalisation: a SECOND corpus, chosen to break the first one's assumptions ──────────────────

_GRIMDARK = (pathlib.Path(__file__).resolve().parents[1]
             / "fixtures" / "plan-forge" / "corpus-grimdark-scifi.md")


def test_a_document_whose_top_level_is_double_hash_still_parses():
    """Every number this project measured came from ONE document — Vietnamese, xianxia, one author.
    A grimdark sci-fi corpus written to be structurally hostile opens at `## ` (as plenty of people
    do when the title is plain text) and parsed to ZERO sections even after the numbering fix.

    Hardcoding `# ` was the same level-binding as hardcoding `# <n>. `, one step less obvious. The
    document's own shallowest heading level is the answer and needs no guessing."""
    doc = ingest_markdown(_GRIMDARK.read_text(encoding="utf-8"))
    assert len(doc["sections"]) == 9
    assert [s["title"] for s in doc["sections"]][:3] == ["What this is", "The setup", "Crew"]


def test_a_hash_document_is_UNCHANGED_by_the_level_rule():
    """The rule may only help. A document with `# ` sections and `## ` sub-blocks must resolve to
    level 1, or its character sub-headings get promoted into sections and one protagonist's profile
    becomes six people."""
    doc = ingest_markdown(REAL_SHAPED)
    assert [s["title"] for s in doc["sections"]][:3] == ["Truyện của tôi", "MỤC LỤC", "Bối cảnh"]
    chars = (propose_spec(doc)["layers"] or {})["characters"]
    assert [c["name"] for c in chars] == ["Lâm Uyên", "Tô Thanh Dao", "Lâm Trạch"]


def test_the_KIND_VOCABULARY_does_not_generalise_and_the_guard_says_so():
    """The decisive generalisation result, pinned so it is not quietly "fixed" by adding grimdark
    words to the map.

    On this corpus the vocabulary matcher recovers exactly ONE kind, and it is WRONG: "Things I
    track per character" matches on the substring "character" and files a state-variable section as
    cast. Ordinary English section names — "The setup", "Shape of it", "How I want it written",
    "Still open" — match nothing at all.

    Widening the map again would be chasing an infinite tail with the same mistake that produced
    this: fitting the vocabulary to whichever document is in front of me. A local model classifying
    the same nine sections scores 8/9 across BOTH corpora. What matters here is that the `unread`
    block reports the shortfall by name rather than letting an almost-empty read look successful."""
    doc = ingest_markdown(_GRIMDARK.read_text(encoding="utf-8"))
    kinds = {s["kind"] for s in doc["sections"]} - {"other", "front_matter"}
    assert kinds == {"character_seed"}, (
        "if this now recovers more kinds, check WHY — adding this corpus's words to the map is the "
        "over-fitting this test exists to prevent"
    )
    unread = doc["unread"]
    assert len(unread["unclassified"]) >= 6
    assert "The setup" in unread["unclassified"] and "Still open" in unread["unclassified"]


# ── the classifier is a SUGGESTION, not a gate ───────────────────────────────────────────────────

def test_a_section_the_matcher_cannot_place_is_CARRIED_not_deleted():
    """The architectural correction: the kind matcher decides what gets STRUCTURED EXTRACTION, never
    what gets SEEN.

    It used to be a gate. An unmatched section was `other` and `other` was dropped entirely, so a
    heading this vocabulary happens not to know DELETED the author's paragraphs from their own plan.
    Measured: 4,411 of the grimdark corpus's 5,276 characters were going nowhere — 84% of what the
    author wrote — and 1,501 of Mị Đế's, including its whole premise section.

    PlanForge has to work when the matcher is wrong or silent, because on any document it was not
    fitted to, it is."""
    doc = ingest_markdown(_GRIMDARK.read_text(encoding="utf-8"))
    notes = propose_spec(doc)["author_notes"]
    titles = [n["title"] for n in notes]
    assert "The setup" in titles and "How the bad thing works" in titles and "Still open" in titles
    assert sum(len(n["text"]) for n in notes) > 3000, "the author's material is being dropped again"


def test_the_carried_text_reaches_the_planning_package_the_passes_read():
    """Carrying it into the spec is not enough — the passes read `planning_package`, and material
    that stops at the spec is material nobody sees."""
    from app.engine.plan_forge.compile import compile_artifacts

    doc = ingest_markdown(_GRIMDARK.read_text(encoding="utf-8"))
    spec = propose_spec(doc)
    arc_id = (spec.get("arcs") or [{"id": "arc_1"}])[0]["id"]
    pkg = compile_artifacts(spec, arc_id=arc_id)["planning_package"]
    assert [n["title"] for n in pkg["author_notes"]] == [n["title"] for n in spec["author_notes"]]


def test_carrying_it_does_NOT_change_the_structured_extraction():
    """This may only ADD. Unplaced prose must not leak into the extractors — a section nobody could
    classify has no business becoming a character or an arc, because that is the invented-kind
    failure the drop was protecting against in the first place."""
    doc = _doc()
    spec = propose_spec(doc)
    chars = (spec["layers"] or {})["characters"]
    assert [c["name"] for c in chars] == ["Lâm Uyên", "Tô Thanh Dao", "Lâm Trạch"]
    assert [a["title"] for a in spec["arcs"]] == ["Arc mở đầu", "Cốt truyện hàng vạn năm sau"]
    # …and the unplaced section rides alongside rather than inside them.
    assert "Một mục tôi tự bịa ra" in [n["title"] for n in spec["author_notes"]]


def test_front_matter_is_not_carried():
    """A table of contents was UNDERSTOOD and is genuinely not planning material. Carrying it would
    spend prompt budget in every pass on a list of section names."""
    notes = [n["title"] for n in propose_spec(_doc())["author_notes"]]
    assert "MỤC LỤC" not in notes


def test_the_carried_material_is_BOUNDED():
    """It rides in every pass prompt. A long braindump must not crowd out the plan itself."""
    sep = chr(10) * 2
    big = sep.join("# Section %d nobody can classify%s%s" % (i, sep, "x " * 2000)
                   for i in range(12))
    notes = propose_spec(ingest_markdown(big))["author_notes"]
    assert sum(len(n["text"]) for n in notes) <= 6000

