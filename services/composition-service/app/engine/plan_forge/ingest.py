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
# An unmatched section is `other`, and `other` is IGNORED, not guessed at. A section we cannot
# classify is a section we do not understand, and inventing a kind for it would put the user's prose
# into a slot the compiler then reasons about as if it meant something.
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


def _section_level(lines: list[str]) -> int:
    """The heading level THIS document uses for its sections — the shallowest one present.

    Hardcoding `# ` was the same level-binding as hardcoding `# <n>. `, one step less obvious. A
    grimdark sci-fi planning document written for this test opens at `## ` (as plenty of people do,
    especially when the title is plain text) and parsed to ZERO sections even after the numbering
    fix — nine headings, none readable.

    The shallowest level present is the document's own answer and needs no guessing. It also keeps
    every existing document identical: a document with `# ` sections and `## ` sub-blocks resolves
    to 1, so its character sub-headings stay sub-headings rather than being promoted into sections
    (which would split one protagonist's profile into six people — the exact bug the dotted-number
    rule in `propose._characters` exists to prevent).

    Fences are respected here too: a `#` comment inside a code block must not drag the level down to
    something no real heading uses.
    """
    in_fence = False
    best = 7
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING.match(line.strip())
        if m and m.group(3).strip():
            best = min(best, len(m.group(1)))
    return best if best <= 6 else 1


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
