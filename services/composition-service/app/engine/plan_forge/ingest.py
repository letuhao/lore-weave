"""Ingest NL markdown into PlanDocument."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 27 V2-G — the section classifier is STRUCTURAL, not fixture-bound.
#
# It used to match only the POC's own Vietnamese headings ("công pháp", "âm dương hợp hoan",
# "đạo hóa", "cuồng mỹ"), so an English document's "# 1. Characters" fell through to `other` and its
# character section was simply never seen. The POC's titles are kept — that document must still
# parse — but each kind now also matches the ordinary words a person would actually write.
#
# ADVISORY, NOT A GATE. `kind` is this matcher's best GUESS at what a section is for. It decides
# what gets STRUCTURED EXTRACTION — never what gets SEEN.
#
# It used to be a gate: an unmatched section was `other`, and `other` was dropped entirely, so a
# heading this map happens not to know deleted the author's paragraphs from the plan. Measured
# 2026-07-28 on a second corpus (grimdark sci-fi, English, `tests/fixtures/plan-forge/`), this
# matcher recovers exactly ONE kind out of nine sections and that one is WRONG — a state-variable
# section filed as cast because its title contains the substring "character". A vocabulary cannot
# be widened into generality; the previous widening was fitted to the one document in front of me
# and collapsed on the next one.
#
# So an unmatched section is still `other`, and `other` still gets no structured extraction —
# inventing a kind would put the user's prose into a slot the compiler reasons about as if it meant
# something. But its TEXT now travels: `propose_spec` carries it into the spec and `compile` into
# `planning_package.author_notes`, where the LLM passes read it. PlanForge must work when this
# matcher is wrong or silent, because on any document it has not been fitted to, it is.
SECTION_KIND_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"nhân vật|quan hệ|character|protagonist|cast|dramatis|relationship", re.I),
     "character_seed"),
    (re.compile(r"công pháp|âm dương hợp hoan|đạo hóa|cuồng mỹ", re.I), "mechanics"),
    (re.compile(r"mechanic|system|magic|power|rules? of", re.I), "mechanics"),
    # A SETTING section is mechanics material: it is where a document states how the world works,
    # which is what the compiler reads `mechanics` for. Added as ORDINARY vocabulary in both
    # languages, deliberately not as the phrases of any one document — over-fitting the map to a
    # single book is the mistake this whole module is recovering from. The `unread` block below is
    # what keeps the map honest about whatever it still misses.
    (re.compile(r"bối cảnh|thiết lập|thế giới|setting|world[- ]?building|lore|premise", re.I),
     "mechanics"),
    (re.compile(r"planner variables|variables|state var|stat|chỉ số|biến trạng thái", re.I),
     "planner_variables"),
    (re.compile(r"arc overview|arcs?\b|outline|structure|plot|cốt truyện|tuyến truyện|"
                r"diễn biến|synopsis", re.I), "arc_overview"),
    (re.compile(r"nguyên tắc viết|writing principles|style|voice|tone|văn phong|giọng (văn|kể)",
                re.I), "writing_principles"),
    (re.compile(r"open questions|questions|unknowns|todo|còn bỏ ngỏ|chưa quyết|câu hỏi", re.I),
     "open_questions"),
    # Recognised-and-deliberately-ignored, which is NOT the same as `other`. `other` means "I could
    # not understand this", and the honesty block reports it so the author can act. A table of
    # contents is understood perfectly and is simply not planning material — reporting it would make
    # the note cry wolf on every well-organised document, and a signal that cries wolf gets ignored,
    # which would defeat the guard it belongs to. Nothing consumes this kind, on purpose.
    (re.compile(r"^\s*(mục lục|table of contents|contents|toc|index)\s*$", re.I), "front_matter"),
]


def _classify_section(title: str) -> str:
    for pattern, kind in SECTION_KIND_MAP:
        if pattern.search(title):
            return kind
    return "other"


#: A top-level heading. The `<n>.` enumerator is OPTIONAL.
#
# It used to be REQUIRED (`^# (\d+)\.\s+`), which is fixture shape, not document shape: the POC's own
# braindump numbered its sections, so the parser demanded a number nothing ever told an author to
# write. Measured 2026-07-28 on this project's real Mị Đế planning document — 4,279 chars, 14
# headings, a full premise + cast of four + relationships + opening arc — it parsed to **0 sections**
# and produced an entirely empty spec, with no error. That run is in the database
# (`rules | proposed | 4278`); the author got nothing back and switched to llm mode to get around it.
#
# Loosening can only ADD sections, never change an existing one: a numbered heading still matches and
# still yields the same id, so a document written the old way parses byte-identically.
_FENCE = re.compile(r"^\s*(?:```|~~~)")

_HEADING = re.compile(r"^(#{1,6})\s+(?:(\d+)\.\s*)?(.+)$")


#: `## 2.3 Ngoại Hình` — a heading the author explicitly numbered as a CHILD of section 2. The
#: dotted form is an authored statement of subordination, and `propose._characters` already relies on
#: it for the same reason.
_DOTTED_SUB = re.compile(r"^#{1,6}\s+\d+\.\d")


def _headings_by_level(lines: list[str]) -> dict[int, list[str]]:
    """Every heading in the document as RAW text after the hashes, bucketed by level.

    Raw rather than the parsed title because `_HEADING` eats a leading `N.` enumerator, which would
    hide the `N.M` sub-numbering `_section_level` needs to see. Fences are respected: a `#` comment
    inside a code block must not drag the level down to something no real heading uses.
    """
    out: dict[int, list[str]] = {}
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        m = _HEADING.match(stripped)
        if m and m.group(3).strip():
            out.setdefault(len(m.group(1)), []).append(stripped)
    return out


def _section_level(lines: list[str]) -> int:
    """The heading level THIS document uses for its sections.

    Hardcoding `# ` was the same level-binding as hardcoding `# <n>. `, one step less obvious. A
    grimdark sci-fi planning document written for this test opens at `## ` (as plenty of people do,
    especially when the title is plain text) and parsed to ZERO sections even after the numbering
    fix — nine headings, none readable. So the level is READ from the document, not assumed.

    "Shallowest present" was the first answer and it was still too simple, because it cannot tell a
    SECTION from the document's TITLE. Measured 2026-07-29 over every distinct `source_markdown` ever
    submitted to `plan_run`: **5 of 17** real documents are written

        # Some Title
        ## First real section
        ## Second real section

    — the single most ordinary markdown convention there is. Shallowest-present picks level 1, finds
    exactly one heading, and reads the WHOLE document as one section named after its own title. Four
    of those five then produced a completely empty spec: 0 characters, 0 mechanics, 0 arcs, 0 events.
    Exactly the Mị Đế failure, four more times, still silent.

    So: **descend past a lone heading only when the level BELOW it holds two or more.** One heading
    with siblings underneath is a title wrapping the real sections; one heading with a single child
    is a section that happens to be the document's only one.

    Measured against every ambiguous document in the corpus — this rule, and only this rule, splits
    them correctly:

        # THE CORE TRAGEDY              L2 has 4  → descend    (title)
        # Story Concept: The Weight…    L2 has 5  → descend    (title)
        # The Weight of a Thousand…     L2 has 6  → descend    (title)
        # Story Premise: The Weight…    L2 has 4  → descend    (title)
        # Dracula's Legacy              L2 has 3  → descend    (title)
        # 1. Arc Overview               L2 has 1  → STAY       (a real, lone section)

    My first attempt asked the kind map instead — descend when the lone heading is UNRECOGNISED —
    and it got `# Story Premise: The Weight of Divinity` wrong, because "premise" is vocabulary, so a
    document title classified as a section and stayed collapsed. The heading SHAPE settles this
    without consulting the vocabulary at all, which is also the right dependency direction: the kind
    map is advisory, and structure should not be decided by an advisory signal.

    Note this is deliberately not "the shallowest level with ≥2 headings". The two `# 1. Arc Overview`
    documents have a lone `## ` arc and many `### ` scenes, so that formulation would descend all the
    way to level 3 and shatter the arc the extractor reads. Descent stops as soon as a level has
    siblings — one step at a time, never past the first level that holds more than one.

    And it does not descend into DOTTED sub-numbering. The golden regression caught this: a real
    character sheet reads

        # 1. Nhân Vật Chính
        ## 1.1 Hồ Sơ Cơ Bản
        ## 1.2 Ngoại Hình

    — a lone top heading with several children, structurally identical to a title-plus-sections
    document. Descending shattered one protagonist's profile into sub-sections and lost the character
    entirely. The `N.M` numbering is the author SAYING these are parts of section N, so it is taken
    at its word; `propose._characters` already leans on the same signal for the same reason.
    """
    by_level = _headings_by_level(lines)
    if not by_level:
        return 1
    levels = sorted(by_level)
    level = levels[0]
    for nxt in levels[1:]:
        children = by_level[nxt]
        if len(by_level[level]) > 1 or len(children) < 2:
            break
        if any(_DOTTED_SUB.match(h) for h in children):
            break
        level = nxt
    return level


def _parse_top_sections(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    level = _section_level(lines)
    headers: list[tuple[str, str, int]] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        # A `#` inside a fenced block is a comment or a literal, never a heading. The old regex
        # required `# <n>. ` and so never matched inside a fence BY ACCIDENT; loosening it exposed
        # this, and the damage was silent and specific: the fixture's variable block is a fenced
        # code block containing a `#` line, so it was split in two and all four declared state
        # variables disappeared from the spec. A parse that quietly halves a section is worse than
        # the strict regex it replaced.
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING.match(line.strip())
        if m and len(m.group(1)) == level and m.group(3).strip():
            # Keep the author's own number when they wrote one (ids stay stable for existing
            # documents); fall back to reading order when they did not.
            headers.append((m.group(2) or str(len(headers) + 1), m.group(3).strip(), i))

    sections: list[dict[str, Any]] = []
    for idx, (num, title, start) in enumerate(headers):
        end = headers[idx + 1][2] - 1 if idx + 1 < len(headers) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        sections.append(
            {
                "id": f"section_{num}",
                "kind": _classify_section(title),
                "title": title,
                "body": body,
                "line_start": start,
                "line_end": end,
            }
        )
    return sections


def _unread(text: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    """What the ingest SAW but could not use — the honesty block.

    `other` is ignored downstream, and an ignored section is indistinguishable from a section the
    author never wrote. That indistinguishability is the whole defect: a document can be read as
    nothing at all and the run still reports success, so the author has no way to tell a failed read
    from an empty book. Same law the rest of this codebase already follows — absent is reported WITH
    A NOTE (`ResolvedStructure.source`, `AnchorPreloadUnavailable`), never as zero.

    Deliberately reports the DROPPED HEADINGS by name rather than a count: "I did not understand
    'Giọt nước tràn ly'" is actionable, "6 sections ignored" is not. It also keeps the kind map
    self-reporting — whatever vocabulary it still misses shows up here instead of vanishing.
    """
    # `front_matter` is excluded: it was understood, and it is not material. Only genuine
    # incomprehension is worth the author's attention.
    dropped = [s["title"] for s in sections if s["kind"] == "other"]
    headings = sum(1 for ln in text.splitlines() if ln.lstrip().startswith("#"))
    # An UNCLOSED ``` is valid-looking markdown that swallows every heading after it, so the first
    # sections classify fine and nothing else is ever seen — a partial read that would otherwise be
    # reported as a clean one.
    #
    # Detected by counting fences, not by comparing heading counts: a `#` line INSIDE a legitimate
    # fenced block is intentional and would make any count-comparison heuristic fire on a perfectly
    # healthy document. An odd number of fence lines is the actual condition, exactly.
    fences = sum(1 for ln in text.splitlines() if _FENCE.match(ln))
    note = ""
    if fences % 2:
        note = (
            "This document has an unclosed ``` code fence, which hides every heading after it from "
            "the planner. Check the fences are balanced."
        )
    elif text.strip() and not sections:
        note = (
            f"This document has {headings} heading(s) but none could be read as a section. "
            f"Sections are top-level '# ' headings — check the document uses them."
            if headings else
            "This document has no '# ' headings, so it has no sections the planner can read."
        )
    elif dropped:
        note = (f"{len(dropped)} section(s) were read but matched no known kind, so the planner "
                f"ignored them: {', '.join(dropped[:8])}")
    return {
        "headings_seen": headings,
        "sections_read": len(sections),
        "unclassified": dropped,
        "note": note,
    }


def ingest_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return ingest_markdown(text, source_path=str(path))


def ingest_markdown(text: str, *, source_path: str = "inline") -> dict[str, Any]:
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    sections = _parse_top_sections(text)
    unread = _unread(text, sections)
    if unread["note"]:
        # Logged as well as returned: the artifact carries it for the author, and this carries it
        # for whoever is asked why a book planned into nothing.
        logger.warning("ingest: %s (path=%s)", unread["note"], source_path)
    return {
        "version": 1,
        "source": {
            "path": source_path,
            "checksum_sha256": checksum,
            "char_count": len(text),
        },
        "sections": sections,
        # NEVER omitted, including on a clean read — a consumer that only sees this key when
        # something went wrong cannot distinguish "nothing was dropped" from "an older ingest that
        # never reported". Same reason `ResolvedStructure` always emits its provenance block.
        "unread": unread,
    }
