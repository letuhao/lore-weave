"""SentenceBuffer — accumulates LLM tokens into complete sentences for TTS.

Synchronous, server-side version. No timers — the caller drives the pipeline
by pushing tokens and collecting emitted sentences.

Design ref: VOICE_PIPELINE_V2.md §3.7
"""
from __future__ import annotations

import re


# Sentence-ending punctuation followed by optional quotes/parens and whitespace
_SENTENCE_END = re.compile(r'([.!?]["\')\]]*)\s')
_CJK_SENTENCE_END = re.compile(r'([。！？]["\'」）]*)\s?')

# Common abbreviations that end with "." but are NOT sentence boundaries
_ABBREVIATIONS = frozenset([
    'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr', 'St', 'Ave', 'Blvd',
    'vs', 'etc', 'i.e', 'e.g', 'a.m', 'p.m',
])

# Clause delimiters for voice mode (lower latency splitting)
_CLAUSE_DELIMS = [', ', ' — ', '; ', ' but ', ' and ', ' so ', ' because ']
_CJK_CLAUSE_DELIMS = ['、', '，']

_CLAUSE_MIN_LENGTH = 40
_MAX_LENGTH = 300


class SentenceBuffer:
    """Accumulate LLM tokens, emit complete sentences for TTS."""

    def __init__(self, clause_mode: bool = False):
        self._buffer = ''
        self._clause_mode = clause_mode

    @property
    def pending(self) -> str:
        return self._buffer

    def push(self, token: str) -> list[str]:
        """Push a token, return list of complete sentences (may be empty)."""
        self._buffer += token
        sentences: list[str] = []

        while True:
            # Force-split very long text without boundaries
            if len(self._buffer) > _MAX_LENGTH:
                split_at = self._find_split_point(self._buffer, _MAX_LENGTH)
                chunk = self._buffer[:split_at].strip()
                self._buffer = self._buffer[split_at:].lstrip()
                if chunk:
                    sentences.append(chunk)
                continue

            # Try sentence boundaries
            emitted = self._try_sentence_boundary()
            if emitted:
                sentences.append(emitted)
                continue

            # Try clause-mode splits (voice only, 40+ chars)
            if self._clause_mode:
                emitted = self._try_clause_split()
                if emitted:
                    sentences.append(emitted)
                    continue

            break

        return sentences

    def flush(self) -> str | None:
        """Flush remaining buffer (call when LLM stream ends).

        Returns the remaining text, or None if empty.
        """
        remaining = self._buffer.strip()
        self._buffer = ''
        return remaining if remaining else None

    def _try_sentence_boundary(self) -> str | None:
        """Try to find and emit at a sentence boundary."""
        search_from = 0
        while search_from < len(self._buffer):
            # Try standard sentence ends
            match = _SENTENCE_END.search(self._buffer, search_from)
            if not match:
                # Try CJK sentence ends
                match = _CJK_SENTENCE_END.search(self._buffer, search_from)
            if not match:
                return None

            end = match.end()
            sentence = self._buffer[:end].strip()

            # Check abbreviation
            if self._is_abbreviation(sentence):
                search_from = end
                continue

            self._buffer = self._buffer[end:]
            return sentence

        return None

    def _try_clause_split(self) -> str | None:
        """Try clause-level splitting when buffer is long enough."""
        if len(self._buffer) <= _CLAUSE_MIN_LENGTH:
            return None

        all_delims = _CLAUSE_DELIMS + _CJK_CLAUSE_DELIMS
        for delim in all_delims:
            idx = self._buffer.rfind(delim)
            if idx > _CLAUSE_MIN_LENGTH:
                end = idx + len(delim)
                clause = self._buffer[:end].strip()
                self._buffer = self._buffer[end:]
                return clause

        return None

    @staticmethod
    def _find_split_point(text: str, max_len: int) -> int:
        """Find a natural split point near max_len."""
        half = max_len // 2
        for char in [',', ';', ':', ' ']:
            idx = text.rfind(char, half, max_len)
            if idx > half:
                return idx + 1
        return max_len

    @staticmethod
    def _is_abbreviation(sentence: str) -> bool:
        """Check if the trailing '.' is an abbreviation, not a sentence end."""
        trimmed = sentence.rstrip()
        if not trimmed.endswith('.'):
            return False
        words = trimmed.split()
        if not words:
            return False
        last_word = words[-1].rstrip('.')
        return last_word in _ABBREVIATIONS
