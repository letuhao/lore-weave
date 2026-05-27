"""Plain-text parser — spec D5.

Multi-language regex sets for EN/ZH/VI/JA. All patterns are whole-line
anchored (M3 fix): a heading is its OWN line, not embedded mid-sentence.

Detection (when language="auto" or None): run all 4 chapter regexes, pick
the language whose chapter pattern appears earliest in the first 4000
chars. Falls back to single-chapter book when no marker found.
"""

from __future__ import annotations

import hashlib
import re

from loreweave_parse._types import (
    Chapter,
    Part,
    Scene,
    StructuralTree,
)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ─── Regex sets (D5) ─────────────────────────────────────────────────────────
# All compiled with re.MULTILINE; EN+VI also IGNORECASE (Latin scripts).

_CN_NUM = "一二三四五六七八九十百千两兩"

# C-fix: all part/chapter regexes use this trailing-title fragment which
# requires (a) end-of-line immediately OR (b) mandatory whitespace + a title
# that does NOT contain sentence-ending punctuation (period/Chinese full stop).
# This rejects body lines like "Part 1 ch 1 body." that the previous .*$
# tail over-matched.
_EN_TAIL = r"(?:\s+[^.\n]*)?$"
_CJK_TAIL = r"(?:\s+[^。.\n]*)?$"

# D-fix: scene-break regexes allow either consecutive-marks OR space-separated
# triplets (so VI "– – –" and ZH "※ ※ ※" both work).
_EN_SCENE_BREAK = r"^\s*(?:\*(?:\s*\*){2,}|[—–](?:\s*[—–]){2,})\s*$"
_VI_SCENE_BREAK = r"^\s*(?:\*(?:\s*\*){2,}|[–-](?:\s*[–-]){2,})\s*$"
_CJK_SCENE_BREAK = r"^\s*(?:※(?:\s*※){2,}|◇(?:\s*◇){1,})\s*$"

_PATTERNS = {
    "en": {
        "part": re.compile(
            r"^(?:Part|Book|Volume)\s+\d+" + _EN_TAIL,
            re.MULTILINE | re.IGNORECASE,
        ),
        "chapter": re.compile(
            r"^(?:Chapter\s+\d+" + _EN_TAIL + r"|[IVXLCDM]+\.\s*$)",
            re.MULTILINE | re.IGNORECASE,
        ),
        "scene_break": re.compile(_EN_SCENE_BREAK, re.MULTILINE),
    },
    "zh": {
        "part": re.compile(
            rf"^第[{_CN_NUM}]+(?:部|卷)" + _CJK_TAIL,
            re.MULTILINE,
        ),
        "chapter": re.compile(
            rf"^第[{_CN_NUM}]+(?:章|回)" + _CJK_TAIL,
            re.MULTILINE,
        ),
        "scene_break": re.compile(_CJK_SCENE_BREAK, re.MULTILINE),
    },
    "vi": {
        "part": re.compile(
            r"^(?:Phần|Quyển)\s+(?:\d+|[IVXLCDM]+)" + _EN_TAIL,
            re.MULTILINE | re.IGNORECASE,
        ),
        "chapter": re.compile(
            r"^(?:Chương|Hồi)\s+\d+" + _EN_TAIL,
            re.MULTILINE | re.IGNORECASE,
        ),
        "scene_break": re.compile(_VI_SCENE_BREAK, re.MULTILINE),
    },
    "ja": {
        "part": re.compile(
            rf"^第[{_CN_NUM}]+(?:部|巻)" + _CJK_TAIL,
            re.MULTILINE,
        ),
        "chapter": re.compile(
            rf"^(?:第[{_CN_NUM}]+章|その[{_CN_NUM}]+)" + _CJK_TAIL,
            re.MULTILINE,
        ),
        "scene_break": re.compile(_CJK_SCENE_BREAK, re.MULTILINE),
    },
}


_DETECT_WINDOW = 4000


def detect_language(content: str) -> str | None:
    """Run all 4 chapter regexes over the first _DETECT_WINDOW chars.

    Spec D5: "pick the language whose chapter marker matches the most
    lines; tie-break: prefer the language with the FIRST chapter match by
    file position; final tie-break: dict insertion order (en, zh, vi, ja —
    so ZH wins ZH/JA ties on overlapping `第N章` patterns)."

    Returns None when no chapter marker matched in any language.
    """
    window = content[:_DETECT_WINDOW]
    best: tuple[int, int, int] | None = None  # (-count, first_pos, dict_idx)
    best_lang: str | None = None
    for idx, (lang, regs) in enumerate(_PATTERNS.items()):
        matches = list(regs["chapter"].finditer(window))
        if not matches:
            continue
        score = (-len(matches), matches[0].start(), idx)
        if best is None or score < best:
            best = score
            best_lang = lang
    return best_lang


def _find_marker_positions(content: str, regex: re.Pattern[str]) -> list[tuple[int, int, str]]:
    """Return list of (start, end, line_text) for each whole-line match."""
    out: list[tuple[int, int, str]] = []
    for m in regex.finditer(content):
        out.append((m.start(), m.end(), m.group(0).strip()))
    return out


def parse_plain(
    content: str,
    language: str | None = None,
    filename: str | None = None,
) -> StructuralTree:
    """Parse plain text into a StructuralTree.

    language: ISO-639-1 hint. None or "auto" runs detection.
    """
    detected_lang: str | None = None
    effective_lang: str | None = language if language and language != "auto" else None
    if effective_lang is None:
        detected_lang = detect_language(content)
        effective_lang = detected_lang

    book_title: str | None = None
    if filename:
        book_title = filename.rsplit(".", 1)[0] or filename

    if effective_lang is None or effective_lang not in _PATTERNS:
        # No language detected (or unknown language hint) — single-everything tree.
        leaf_text = content.strip()
        return StructuralTree(
            source_format="plain",
            detected_language=detected_lang,
            walker_path="fallback_single",
            book_title=book_title,
            parts=[
                Part(
                    sort_order=1,
                    title=None,
                    path="book/part-1",
                    chapters=[
                        Chapter(
                            sort_order=1,
                            title=book_title,
                            path="book/part-1/chapter-1",
                            html="",
                            scenes=[
                                Scene(
                                    sort_order=1,
                                    path="book/part-1/chapter-1/scene-1",
                                    leaf_text=leaf_text,
                                    content_hash=_sha256_hex(leaf_text),
                                )
                            ],
                        )
                    ],
                )
            ],
        )

    regs = _PATTERNS[effective_lang]
    part_marks = _find_marker_positions(content, regs["part"])
    chapter_marks = _find_marker_positions(content, regs["chapter"])

    if not chapter_marks:
        # No chapter markers — single-chapter book in this language.
        leaf_text = content.strip()
        return StructuralTree(
            source_format="plain",
            detected_language=detected_lang,
            walker_path="fallback_single",
            book_title=book_title,
            parts=[
                Part(
                    sort_order=1,
                    title=None,
                    path="book/part-1",
                    chapters=[
                        Chapter(
                            sort_order=1,
                            title=book_title,
                            path="book/part-1/chapter-1",
                            html="",
                            scenes=[
                                Scene(
                                    sort_order=1,
                                    path="book/part-1/chapter-1/scene-1",
                                    leaf_text=leaf_text,
                                    content_hash=_sha256_hex(leaf_text),
                                )
                            ],
                        )
                    ],
                )
            ],
        )

    # Build the part list. If no part markers, synthesise one implicit part covering [0, len(content)).
    if not part_marks:
        part_spans: list[tuple[int, str | None]] = [(0, None)]
    else:
        # Each part spans from its marker position to the next part marker (or EOF).
        part_spans = [(start, title) for start, _end, title in part_marks]
        # If chapters appear before the first part marker, prepend an implicit part.
        if chapter_marks and chapter_marks[0][0] < part_marks[0][0]:
            part_spans.insert(0, (0, None))

    # Compute part end positions.
    part_ends: list[int] = []
    for i, (start, _t) in enumerate(part_spans):
        if i + 1 < len(part_spans):
            part_ends.append(part_spans[i + 1][0])
        else:
            part_ends.append(len(content))

    parts: list[Part] = []
    for part_idx, ((p_start, p_title), p_end) in enumerate(
        zip(part_spans, part_ends, strict=True),
        start=1,
    ):
        # Chapter markers within this part's span.
        in_part_chapters = [
            (c_start, c_end, c_title)
            for (c_start, c_end, c_title) in chapter_marks
            if p_start <= c_start < p_end
        ]
        if not in_part_chapters:
            # Part with no chapters detected — treat all part text as one virtual chapter.
            ch_text = content[p_start:p_end].strip()
            if not ch_text:
                continue  # skip empty part entirely (e.g. ToC-only)
            parts.append(
                Part(
                    sort_order=part_idx,
                    title=p_title,
                    path=f"book/part-{part_idx}",
                    chapters=[
                        Chapter(
                            sort_order=1,
                            title=None,
                            path=f"book/part-{part_idx}/chapter-1",
                            html="",
                            scenes=[
                                Scene(
                                    sort_order=1,
                                    path=f"book/part-{part_idx}/chapter-1/scene-1",
                                    leaf_text=ch_text,
                                    content_hash=_sha256_hex(ch_text),
                                )
                            ],
                        )
                    ],
                )
            )
            continue

        # Build chapters within this part.
        chapters: list[Chapter] = []
        for ch_idx, ((c_start, c_end, c_title), next_anchor) in enumerate(
            _pairwise_with_end(in_part_chapters, p_end),
            start=1,
        ):
            ch_text = content[c_end:next_anchor].strip()
            ch_title = c_title or None
            # Scene split via scene_break regex.
            scenes = _split_scenes_plain(
                ch_text,
                regs["scene_break"],
                part_idx,
                ch_idx,
            )
            chapters.append(
                Chapter(
                    sort_order=ch_idx,
                    title=ch_title,
                    path=f"book/part-{part_idx}/chapter-{ch_idx}",
                    html="",
                    scenes=scenes,
                )
            )
        parts.append(
            Part(
                sort_order=part_idx,
                title=p_title,
                path=f"book/part-{part_idx}",
                chapters=chapters,
            )
        )

    if not parts:
        # Edge case: all parts ended up empty. Fall back to single tree.
        leaf_text = content.strip()
        return StructuralTree(
            source_format="plain",
            detected_language=detected_lang,
            walker_path="fallback_single",
            book_title=book_title,
            parts=[
                Part(
                    sort_order=1,
                    title=None,
                    path="book/part-1",
                    chapters=[
                        Chapter(
                            sort_order=1,
                            title=book_title,
                            path="book/part-1/chapter-1",
                            html="",
                            scenes=[
                                Scene(
                                    sort_order=1,
                                    path="book/part-1/chapter-1/scene-1",
                                    leaf_text=leaf_text,
                                    content_hash=_sha256_hex(leaf_text),
                                )
                            ],
                        )
                    ],
                )
            ],
        )

    return StructuralTree(
        source_format="plain",
        detected_language=detected_lang,
        walker_path="headings",
        book_title=book_title,
        parts=parts,
    )


def _pairwise_with_end(
    items: list[tuple[int, int, str]],
    final_end: int,
) -> list[tuple[tuple[int, int, str], int]]:
    """Yield (item, next_item_start_or_final_end) pairs."""
    out: list[tuple[tuple[int, int, str], int]] = []
    for i, item in enumerate(items):
        if i + 1 < len(items):
            out.append((item, items[i + 1][0]))
        else:
            out.append((item, final_end))
    return out


def _split_scenes_plain(
    chapter_text: str,
    scene_break_re: re.Pattern[str],
    part_idx: int,
    ch_idx: int,
) -> list[Scene]:
    """Split a chapter's text into scenes at scene-break-regex matches."""
    if not chapter_text.strip():
        # Empty chapter — emit one empty scene to keep the invariant scenes>=1.
        return [
            Scene(
                sort_order=1,
                path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-1",
                leaf_text="",
                content_hash=_sha256_hex(""),
            )
        ]
    matches = list(scene_break_re.finditer(chapter_text))
    if not matches:
        text = chapter_text.strip()
        return [
            Scene(
                sort_order=1,
                path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-1",
                leaf_text=text,
                content_hash=_sha256_hex(text),
            )
        ]
    scenes: list[Scene] = []
    cursor = 0
    sc_idx = 1
    for m in matches:
        seg = chapter_text[cursor : m.start()].strip()
        if seg:
            scenes.append(
                Scene(
                    sort_order=sc_idx,
                    path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-{sc_idx}",
                    leaf_text=seg,
                    content_hash=_sha256_hex(seg),
                )
            )
            sc_idx += 1
        cursor = m.end()
    # Trailing segment after the last scene-break.
    tail = chapter_text[cursor:].strip()
    if tail:
        scenes.append(
            Scene(
                sort_order=sc_idx,
                path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-{sc_idx}",
                leaf_text=tail,
                content_hash=_sha256_hex(tail),
            )
        )
    if not scenes:
        # All segments were empty — one empty scene to preserve invariant.
        scenes.append(
            Scene(
                sort_order=1,
                path=f"book/part-{part_idx}/chapter-{ch_idx}/scene-1",
                leaf_text="",
                content_hash=_sha256_hex(""),
            )
        )
    return scenes


__all__ = ["detect_language", "parse_plain"]
