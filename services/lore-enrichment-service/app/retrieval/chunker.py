"""CJK-aware deterministic chunker for source-corpus ingest (RAID C10).

Technique-(b) retrieval grounds proposals in the OWNED public-domain corpora
(山海经 + 封神演义). Before a corpus can be embedded + searched it must be split
into stable, comparable passages. This module does *only* that split — no I/O,
no embedding, no model names. It imports the stdlib only.

Design (locked by the C10 brief):
  * CJK-AWARE: Classical Chinese has no spaces, so we segment on CJK sentence
    terminators (。！？；…) — NOT on whitespace/words. The split keeps the
    terminator with its sentence (a passage reads naturally).
  * BYTE-SAFE: we operate on the decoded ``str`` (a sequence of Unicode code
    points), never on raw bytes, so a multi-byte 漢字 can never be cut in half.
    Mojibake is impossible here because we never re-encode mid-stream.
  * SENTENCE WINDOWS + OVERLAP: sentences are packed into passages up to a
    ``target_chars`` budget; consecutive passages share ``overlap_sentences``
    trailing sentences so a query that straddles a boundary still retrieves the
    right context.
  * DETERMINISTIC + STABLE IDS: same text + same params → byte-identical chunk
    list in the same order. The chunk ``index`` is its 0-based ordinal; the
    ``sha256`` is the content hash used downstream for idempotent re-ingest.

Boundaries: NO LLM, NO embedding, NO model name, NO DB. The store (``store.py``)
persists what this produces; the strategy (``strategy.py``) embeds + searches.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

__all__ = [
    "Chunk",
    "DEFAULT_TARGET_CHARS",
    "DEFAULT_OVERLAP_SENTENCES",
    "chunk_text",
    "sha256_text",
]


# ── tuning defaults (deterministic; documented so re-ingest is reproducible) ──
#: Soft upper bound on a passage's length in code points. Classical Chinese is
#: information-dense, so a few hundred characters is a meaty passage. A single
#: sentence longer than this is emitted whole (never split mid-sentence).
DEFAULT_TARGET_CHARS: int = 320

#: How many trailing sentences of a passage are repeated at the head of the
#: next passage (context bleed across boundaries). 0 disables overlap.
DEFAULT_OVERLAP_SENTENCES: int = 1


# CJK sentence terminators (full-width). We split AFTER a run of these so the
# terminator stays attached to its sentence. Newlines also force a boundary so
# the corpus's structural markers (chapter headers) start a fresh passage.
_TERMINATORS = "。！？；…"
# A sentence = text up to and including a run of terminators, OR a line break.
_SENTENCE_RE = re.compile(
    rf"[^{_TERMINATORS}\n]*[{_TERMINATORS}]+|[^{_TERMINATORS}\n]+",
)


def sha256_text(text: str) -> str:
    """Stable hex SHA-256 of ``text`` (UTF-8). Used as the idempotency key for a
    chunk's content so a re-ingest of identical text is a no-op downstream."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Chunk:
    """One passage of a corpus. ``index`` is the 0-based ordinal (a stable id
    within the corpus); ``sha256`` is the content hash. Pure value object."""

    index: int
    content: str
    sha256: str


def _split_sentences(text: str) -> list[str]:
    """Split ``text`` into CJK sentences (terminator kept with its sentence).

    Whitespace-only fragments are dropped; each returned sentence is stripped of
    surrounding whitespace but retains its internal characters + terminator.
    Deterministic: regex scan, left to right.
    """
    sentences: list[str] = []
    for match in _SENTENCE_RE.finditer(text):
        s = match.group().strip()
        if s:
            sentences.append(s)
    return sentences


def chunk_text(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_sentences: int = DEFAULT_OVERLAP_SENTENCES,
) -> list[Chunk]:
    """Deterministically split ``text`` into overlapping CJK sentence windows.

    Sentences are packed into passages up to ``target_chars`` code points; a
    sentence that alone exceeds the budget is emitted as its own passage (never
    split mid-sentence — byte-safe). Consecutive passages share the last
    ``overlap_sentences`` sentences of the previous window for boundary recall.

    Returns chunks in document order with 0-based ``index`` and a content hash.
    Empty / whitespace-only input → ``[]`` (no chunks, not an error).
    """
    if target_chars <= 0:
        raise ValueError("target_chars must be positive")
    if overlap_sentences < 0:
        raise ValueError("overlap_sentences must be >= 0")

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    window: list[str] = []
    window_len = 0
    idx = 0

    def _flush() -> None:
        nonlocal window, window_len, idx
        if not window:
            return
        content = "".join(window).strip()
        if content:
            chunks.append(Chunk(index=idx, content=content, sha256=sha256_text(content)))
            idx += 1

    for sentence in sentences:
        s_len = len(sentence)
        # If adding this sentence would overflow a non-empty window, flush first
        # then seed the new window with the overlap tail (deterministic).
        if window and window_len + s_len > target_chars:
            tail = window[-overlap_sentences:] if overlap_sentences else []
            _flush()
            window = list(tail)
            window_len = sum(len(t) for t in window)
        window.append(sentence)
        window_len += s_len

    _flush()
    return chunks
