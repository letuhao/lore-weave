"""
Block-aware batch builder for Tiptap JSON translation.

Groups consecutive translatable blocks into batches that fit within
a token budget. Uses numbered [BLOCK N] markers for reliable block
alignment after LLM translation.

Non-translatable blocks (passthrough, caption_only) are tracked
separately and reinserted during reassembly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .block_classifier import classify_block, extract_translatable_text, BlockAction
from .chunk_splitter import estimate_tokens

# Marker format: [BLOCK 0], [BLOCK 1], etc.
BLOCK_MARKER = "[BLOCK {i}]"


@dataclass
class BlockEntry:
    """A single block with its classification and extracted text."""
    index: int
    action: BlockAction
    text: str
    block: dict


@dataclass
class BatchGroup:
    """A batch of translatable blocks to send as one LLM request."""
    entries: list[BlockEntry] = field(default_factory=list)
    token_estimate: int = 0

    def combined_text(self) -> str:
        """Combine block texts with numbered markers for LLM prompt."""
        parts = []
        for entry in self.entries:
            parts.append(f"{BLOCK_MARKER.format(i=entry.index)}\n{entry.text}")
        return "\n\n".join(parts)

    @property
    def block_indices(self) -> list[int]:
        return [e.index for e in self.entries]


@dataclass
class BatchPlan:
    """Full batch plan for a chapter's blocks."""
    batches: list[BatchGroup]
    all_entries: list[BlockEntry]

    @property
    def translatable_count(self) -> int:
        return sum(1 for e in self.all_entries if e.action == "translate")

    @property
    def passthrough_count(self) -> int:
        return sum(1 for e in self.all_entries if e.action == "passthrough")

    @property
    def caption_count(self) -> int:
        return sum(1 for e in self.all_entries if e.action == "caption_only")


def build_batch_plan(
    blocks: list[dict],
    context_window_tokens: int = 8192,
    budget_ratio: float = 0.25,
) -> BatchPlan:
    """Build a batch plan from a Tiptap block array.

    Args:
        blocks: Tiptap content array (top-level blocks only).
        context_window_tokens: Model's context window size.
        budget_ratio: Fraction of context window per batch (default 1/4).

    Returns:
        BatchPlan with batches and block entries.
    """
    max_tokens = int(context_window_tokens * budget_ratio)
    if max_tokens < 100:
        max_tokens = 100

    # 1. Classify all blocks and extract text
    entries: list[BlockEntry] = []
    for i, block in enumerate(blocks):
        action = classify_block(block)
        text = extract_translatable_text(block)
        entries.append(BlockEntry(index=i, action=action, text=text, block=block))

    # 2. Group translatable + caption_only blocks into batches
    batches: list[BatchGroup] = []
    current_batch = BatchGroup()

    for entry in entries:
        if entry.action == "passthrough":
            continue

        text_to_translate = entry.text
        if not text_to_translate:
            # Empty block — skip (reassembly uses original for untranslated indices)
            continue

        tokens = estimate_tokens(text_to_translate)
        marker_overhead = estimate_tokens(BLOCK_MARKER.format(i=entry.index)) + 2  # newlines

        # If adding this block would exceed budget, flush current batch
        if current_batch.entries and (current_batch.token_estimate + tokens + marker_overhead > max_tokens):
            batches.append(current_batch)
            current_batch = BatchGroup()

        current_batch.entries.append(entry)
        current_batch.token_estimate += tokens + marker_overhead

        # If single block exceeds budget, it gets its own batch
        if current_batch.token_estimate > max_tokens and len(current_batch.entries) == 1:
            batches.append(current_batch)
            current_batch = BatchGroup()

    # Flush remaining
    if current_batch.entries:
        batches.append(current_batch)

    return BatchPlan(batches=batches, all_entries=entries)


def parse_translated_blocks(response_text: str, expected_indices: list[int]) -> dict[int, str]:
    """Parse LLM response with [BLOCK N] markers back into per-block texts.

    Args:
        response_text: Raw LLM output with [BLOCK N] markers.
        expected_indices: Block indices we expect to find.

    Returns:
        Dict mapping block_index → translated text.
        Missing blocks are omitted from the result.
    """
    import re

    result: dict[int, str] = {}
    # Split on [BLOCK N] markers
    pattern = re.compile(r'\[BLOCK\s+(\d+)\]')
    parts = pattern.split(response_text)

    # parts alternates: [text_before_first_marker, index1, text1, index2, text2, ...]
    i = 1  # skip text before first marker
    while i + 1 < len(parts):
        try:
            block_idx = int(parts[i])
            block_text = parts[i + 1].strip()
            if block_idx in set(expected_indices):
                result[block_idx] = block_text
        except (ValueError, IndexError):
            pass
        i += 2

    return result
