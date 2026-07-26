"""Ingest NL markdown into PlanDocument."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

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
    (re.compile(r"nhân vật|character|protagonist|cast|dramatis", re.I), "character_seed"),
    (re.compile(r"công pháp|âm dương hợp hoan|đạo hóa|cuồng mỹ", re.I), "mechanics"),
    (re.compile(r"mechanic|system|magic|power|rules? of", re.I), "mechanics"),
    (re.compile(r"planner variables|variables|state var|stat", re.I), "planner_variables"),
    (re.compile(r"arc overview|arcs?\b|outline|structure|plot", re.I), "arc_overview"),
    (re.compile(r"nguyên tắc viết|writing principles|style|voice|tone", re.I), "writing_principles"),
    (re.compile(r"open questions|questions|unknowns|todo", re.I), "open_questions"),
]


def _classify_section(title: str) -> str:
    for pattern, kind in SECTION_KIND_MAP:
        if pattern.search(title):
            return kind
    return "other"


def _parse_top_sections(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    headers: list[tuple[int, str, int]] = []
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^# (\d+)\.\s+(.+)$", line.strip())
        if m:
            headers.append((int(m.group(1)), m.group(2).strip(), i))

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


def ingest_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return ingest_markdown(text, source_path=str(path))


def ingest_markdown(text: str, *, source_path: str = "inline") -> dict[str, Any]:
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "version": 1,
        "source": {
            "path": source_path,
            "checksum_sha256": checksum,
            "char_count": len(text),
        },
        "sections": _parse_top_sections(text),
    }
