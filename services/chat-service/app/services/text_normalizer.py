"""Text normalizer for voice TTS — strips markdown, code, emojis before speech synthesis.

Layer 1 of 3-layer normalization:
  Layer 0: Voice system prompt (tells LLM to avoid formatting)
  Layer 1: This module — rule-based cleanup of remaining formatting
  Layer 2: Optional LLM rewriter (future, user-enabled)
"""
from __future__ import annotations

import re


class TextNormalizer:
    """Strip markdown/code/emoji from LLM output before TTS."""

    _BOLD = re.compile(r'\*\*(.+?)\*\*')
    _ITALIC = re.compile(r'(?<!\*)\*(\w(?:.*?\w)?)\*(?!\*)')
    _STRIKE = re.compile(r'~~(.+?)~~')
    _CODE_INLINE = re.compile(r'`([^`]+)`')
    _HEADING = re.compile(r'^#{1,6}\s+', re.MULTILINE)
    _LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
    _CODE_BLOCK = re.compile(r'```[\s\S]*?```')
    _SPECIAL_CHARS = re.compile(r'[*_~`#|]')
    _MULTI_SPACE = re.compile(r'\s{2,}')

    _EMOJIS = [
        '\U0001f60a', '\U0001f916', '\u2728', '\U0001f680',
        '\U0001f44b', '\u2764\ufe0f', '\U0001f389', '\U0001f4a1',
        '\u26a1', '\U0001f525', '\u2705', '\u274c',
    ]

    def normalize(self, text: str) -> tuple[str, bool]:
        """Normalize text for TTS.

        Returns:
            (speakable_text, was_skipped) — skipped means the text
            should not be sent to TTS at all (code block, JSON, table).
        """
        # Skip code blocks entirely
        if self._CODE_BLOCK.search(text):
            return ('', True)

        # Skip JSON objects / markdown tables
        stripped = text.strip()
        if stripped.startswith('{') or stripped.startswith('|'):
            return ('', True)

        result = text

        # Strip markdown formatting (order matters — bold before italic)
        result = self._BOLD.sub(r'\1', result)
        result = self._ITALIC.sub(r'\1', result)
        result = self._STRIKE.sub(r'\1', result)
        result = self._CODE_INLINE.sub(r'\1', result)
        result = self._HEADING.sub('', result)
        result = self._LINK.sub(r'\1', result)

        # Remove emojis
        for emoji in self._EMOJIS:
            result = result.replace(emoji, '')

        # Clean remaining special chars + collapse whitespace
        result = self._SPECIAL_CHARS.sub('', result)
        result = self._MULTI_SPACE.sub(' ', result).strip()

        if len(result) < 2:
            return ('', True)

        return (result, False)
