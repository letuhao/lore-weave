"""V3 cross-chapter memo + cold-start name record (M4c, G4).

Two pure helpers:

- ``harvest_names`` — a lightweight, deterministic proper-noun harvester over the
  *translated* text. With zero glossary the pipeline still needs the SAME run to
  stay self-consistent (DelTA §11.3.C); this records the recurring target-side
  names actually used so the next chapter can reuse the exact spelling. It is a
  heuristic, not NER: recurring (freq ≥ 2) capitalized tokens, skipping
  sentence-initial positions (grammar capitalization) and short/stopword tokens.
  Latin-script targets only (zh/ja/ko targets don't capitalize — skipped).

- ``build_prev_memo_block`` — turns the previous chapter's persisted memo
  (story_summary + terms_used names) into a sanitized prompt block. Injected by
  the V3 orchestrator into the Translator **opportunistically** (§12.1): used
  when chapter N-1's memo already exists, never a correctness dependency.
"""
from __future__ import annotations

import re
from collections import Counter

from .knowledge_context import _sanitize

# Target languages that don't use capitalization for proper nouns → skip harvest.
_NON_LATIN = frozenset({"zh", "ja", "ko"})
_MIN_COUNT = 2
_MAX_NAMES = 30
_MIN_LEN = 2

# Tiny stopword guard — common capitalized sentence-leaders / function words that
# slip past the sentence-initial filter (e.g. in dialogue or after punctuation).
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "but", "or", "if", "then", "so", "he", "she", "it",
    "they", "we", "you", "i", "this", "that", "these", "those", "his", "her",
    "their", "what", "when", "where", "who", "why", "how", "yes", "no", "oh",
})

_SENT_SPLIT = re.compile(r"[.!?…\n;:]")
# A candidate token: starts uppercase (incl. accented Latin / Đ), rest letters/'-.
_NAME_TOKEN = re.compile(r"^[^\W\d_][\w'’\-]*$", re.UNICODE)
_STRIP = " \t\"'“”‘’()[]{}<>«»,.;:!?…"


def _primary(lang: str) -> str:
    return (lang or "").lower().split("-")[0]


def _is_name_token(tok: str) -> bool:
    if len(tok) < _MIN_LEN:
        return False
    if tok.lower() in _STOPWORDS:
        return False
    if not tok[0].isupper():
        return False
    if tok.isupper():  # ALL-CAPS (acronym / shout) — skip, high false-positive
        return False
    return bool(_NAME_TOKEN.match(tok))


def harvest_names(translated_text: str, target_lang: str) -> list[str]:
    """Recurring target-side proper-noun candidates (see module docstring)."""
    if not translated_text or _primary(target_lang) in _NON_LATIN:
        return []
    counts: Counter[str] = Counter()
    for sentence in _SENT_SPLIT.split(translated_text):
        words = sentence.split()
        # Skip index 0 — a sentence-initial capital is usually grammar, not a name.
        for tok in words[1:]:
            tok = tok.strip(_STRIP)
            if _is_name_token(tok):
                counts[tok] += 1
    return [name for name, c in counts.most_common(_MAX_NAMES) if c >= _MIN_COUNT]


def build_prev_memo_block(prev_memo: dict | None) -> str:
    """Sanitized prompt block from the previous chapter's memo (empty if none)."""
    if not prev_memo:
        return ""
    parts: list[str] = []
    names = prev_memo.get("terms_used") or []
    if isinstance(names, list):
        clean = [_sanitize(str(n), 60) for n in names if str(n).strip()][:_MAX_NAMES]
        clean = [n for n in clean if n]
        if clean:
            parts.append(
                "Names established in earlier chapters — reuse the EXACT spelling: "
                + ", ".join(clean))
    summary = _sanitize(str(prev_memo.get("story_summary") or ""), 500)
    if summary:
        parts.append("Story so far: " + summary)
    if not parts:
        return ""
    return "PREVIOUS-CHAPTER CONTEXT (for continuity):\n" + "\n".join(parts)
