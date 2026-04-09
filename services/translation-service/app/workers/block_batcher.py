"""
Block-aware batch builder for Tiptap JSON translation.

Groups consecutive translatable blocks into batches that fit within
a token budget. Uses numbered [BLOCK N] markers for reliable block
alignment after LLM translation.

V2 improvements:
- CJK-aware token estimation (via chunk_splitter.estimate_tokens)
- Expansion-ratio-aware budget: reserves tokens for system prompt,
  glossary context, and output based on language pair
- Hard cap of MAX_BLOCKS_PER_BATCH (40) to prevent LLM block-count confusion
- Context overhead reservation for system + glossary + rolling summary

Non-translatable blocks (passthrough, caption_only) are tracked
separately and reinserted during reassembly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .block_classifier import classify_block, extract_translatable_text, BlockAction
from .chunk_splitter import estimate_tokens

# Marker format: [BLOCK 0], [BLOCK 1], etc.
BLOCK_MARKER = "[BLOCK {i}]"

# Hard cap: LLMs start confusing block indices above this count
MAX_BLOCKS_PER_BATCH = 40

# Fixed overhead tokens reserved for system prompt + formatting
_SYSTEM_PROMPT_OVERHEAD = 500
# Glossary context budget (tiered injection — §4 of V2 design)
_GLOSSARY_OVERHEAD = 1500
# Rolling summary between batches
_ROLLING_SUMMARY_OVERHEAD = 300

# Output expansion ratios by language pair category.
# Used to reserve enough output space in the context window.
# Key: (source_category, target_category) → expansion ratio
_EXPANSION_RATIOS: dict[tuple[str, str], float] = {
    ("cjk", "latin"):  2.0,   # CJK → Vietnamese/English: output ~2x input
    ("cjk", "cjk"):    1.2,   # CJK → CJK (e.g. Chinese → Japanese)
    ("latin", "latin"): 1.3,  # Latin → Latin
    ("latin", "cjk"):  0.7,   # English → Chinese: output shorter
}
_DEFAULT_EXPANSION_RATIO = 1.5


def _lang_category(lang_code: str) -> str:
    """Classify a language code as 'cjk' or 'latin' for expansion ratio lookup."""
    code = lang_code.lower().split("-")[0] if lang_code else ""
    if code in ("zh", "ja", "ko"):
        return "cjk"
    return "latin"


def get_expansion_ratio(source_lang: str, target_lang: str) -> float:
    """Get the expected output/input token expansion ratio for a language pair."""
    src = _lang_category(source_lang)
    tgt = _lang_category(target_lang)
    return _EXPANSION_RATIOS.get((src, tgt), _DEFAULT_EXPANSION_RATIO)


def compute_input_budget(
    context_window: int,
    source_lang: str = "",
    target_lang: str = "",
    glossary_tokens: int = _GLOSSARY_OVERHEAD,
) -> int:
    """Compute the max input tokens per batch given context window and overheads.

    Budget formula:
      available = context_window - system - glossary - rolling_summary
      input_budget = available / (1 + expansion_ratio)
    """
    overhead = _SYSTEM_PROMPT_OVERHEAD + glossary_tokens + _ROLLING_SUMMARY_OVERHEAD
    available = context_window - overhead
    if available < 200:
        available = 200

    ratio = get_expansion_ratio(source_lang, target_lang)
    input_budget = int(available / (1.0 + ratio))
    return max(100, input_budget)


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
    source_lang: str = "",
    target_lang: str = "",
) -> BatchPlan:
    """Build a batch plan from a Tiptap block array.

    Args:
        blocks: Tiptap content array (top-level blocks only).
        context_window_tokens: Model's context window size.
        budget_ratio: Legacy param, ignored when source/target langs provided.
        source_lang: Source language code (e.g. "zh", "ja").
        target_lang: Target language code (e.g. "vi", "en").

    Returns:
        BatchPlan with batches and block entries.
    """
    # V2: use expansion-ratio-aware budget when languages are known
    if source_lang and target_lang:
        max_tokens = compute_input_budget(context_window_tokens, source_lang, target_lang)
    else:
        # Legacy fallback
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

        # Flush if adding this block exceeds token budget OR block count cap
        if current_batch.entries and (
            current_batch.token_estimate + tokens + marker_overhead > max_tokens
            or len(current_batch.entries) >= MAX_BLOCKS_PER_BATCH
        ):
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
