"""T2-M1: heuristic source-side segmentation of a chapter's blocks into ~N-token,
heading-aware ranges. Pure (no IO) — reuses chunk_splitter.estimate_tokens.

A segment is a contiguous range of `chapter_blocks` (language-independent). It is the
foundation for per-part translate/status (M2) + dirty-only re-translate; `block_hashes`
(the ordered chapter_blocks.content_hash of the range) gives the dirty signal.
"""
import hashlib
from dataclasses import dataclass

from .chunk_splitter import estimate_tokens

_HEADING_TYPES = frozenset({"heading"})
DEFAULT_MAX_TOKENS = 2000


@dataclass
class Segment:
    segment_index: int
    start_block_index: int
    end_block_index: int
    segment_text: str
    block_hashes: list[str]
    token_estimate: int


def segment_blocks(blocks: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS) -> list[Segment]:
    """Group ordered chapter_blocks into contiguous ~max_tokens segments.

    Rules:
      - A heading starts a NEW segment when the current one already has content (keep a
        heading attached to the section it titles).
      - Adding a block that would overflow the cap flushes the current segment first
        (unless the current segment is empty — a single over-cap block stays whole).
      - Empty-text blocks still join a segment (preserve block_index continuity).
    Input blocks must be ordered by block_index and each carry block_index, block_type,
    text_content, content_hash.
    """
    segments: list[Segment] = []
    cur: list[dict] = []
    cur_tokens = 0

    def flush() -> None:
        nonlocal cur, cur_tokens
        if not cur:
            return
        text = "\n\n".join((b.get("text_content") or "") for b in cur)
        segments.append(Segment(
            segment_index=len(segments),
            start_block_index=cur[0]["block_index"],
            end_block_index=cur[-1]["block_index"],
            segment_text=text,
            block_hashes=[b.get("content_hash") or "" for b in cur],
            token_estimate=estimate_tokens(text),
        ))
        cur = []
        cur_tokens = 0

    for b in blocks:
        btok = estimate_tokens(b.get("text_content") or "")
        is_heading = b.get("block_type") in _HEADING_TYPES
        if cur and (is_heading or cur_tokens + btok > max_tokens):
            flush()
        cur.append(b)
        cur_tokens += btok
    flush()
    return segments


def segment_source_hash(seg: Segment) -> str:
    """A stable digest of a segment's source (its ordered block content hashes). Drives
    idempotent re-segmentation: unchanged source → unchanged hash → skip rewrite."""
    h = hashlib.sha256()
    h.update(b"\x00".join(x.encode("utf-8") for x in seg.block_hashes))
    return h.hexdigest()
