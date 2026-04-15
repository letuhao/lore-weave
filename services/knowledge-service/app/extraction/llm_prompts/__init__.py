"""K17.1 — LLM extraction prompt loader.

Loads markdown prompt templates from this package directory and
performs strict placeholder substitution. Used by K17.4..K17.7 LLM
extractors (entity / relation / event / fact) and Pass 2
orchestrator (K17.8) to build the prompts sent to the BYOK provider.

**Strict substitution:** `load_prompt` uses `str.format_map` with a
dict that raises on missing keys. This catches typos in caller
kwargs at call time rather than silently embedding a literal
`{text}` in the prompt sent to the LLM — a failure mode that
would only surface as confusing model output hours later.

**LRU-cached raw loads:** the markdown files are read once per
process via `@lru_cache`. Prompt content is effectively immutable
at runtime (baked into the container image), so re-reading on
every extract call would be pure waste. Tests that hot-swap prompt
files must call `load_prompt.cache_clear()` — see the K17.1 test
file.

**Closed prompt name set:** `_ALLOWED_NAMES` is a frozenset of the
four extractor kinds. Attempting to load anything else raises
`KeyError` to prevent user-controlled prompt injection via dynamic
file paths (e.g. `name=../../etc/passwd`).

Reference: KSA §5.1.6 (LLM extraction), K17.1 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

__all__ = [
    "PromptName",
    "load_prompt",
    "ALLOWED_PROMPT_NAMES",
]

PromptName = str  # one of ALLOWED_PROMPT_NAMES, enforced at runtime

ALLOWED_PROMPT_NAMES: frozenset[str] = frozenset(
    {"entity", "relation", "event", "fact"}
)

_PROMPTS_DIR = Path(__file__).parent


class _StrictDict(dict):
    """Dict subclass used with `str.format_map` so missing keys
    raise `KeyError` with a clear message instead of returning the
    literal placeholder. Prevents typoed kwargs from leaking into
    the prompt text sent to the LLM."""

    def __missing__(self, key: str) -> str:
        raise KeyError(
            f"prompt template requires '{{{key}}}' but it was not "
            f"provided in kwargs"
        )


@lru_cache(maxsize=8)
def _load_raw(name: str) -> str:
    if name not in ALLOWED_PROMPT_NAMES:
        raise KeyError(
            f"unknown prompt '{name}'; allowed: "
            f"{sorted(ALLOWED_PROMPT_NAMES)}"
        )
    path = _PROMPTS_DIR / f"{name}_extraction.md"
    return path.read_text(encoding="utf-8")


def load_prompt(name: PromptName, **substitutions: str) -> str:
    """Load a prompt template and substitute placeholders.

    Args:
        name: one of `ALLOWED_PROMPT_NAMES`
            ({entity, relation, event, fact}).
        **substitutions: template variables to interpolate. Missing
            keys raise `KeyError` — callers must supply every
            placeholder the template declares.

    Returns:
        The fully-substituted prompt text ready to pass to the
        LLM provider.

    Raises:
        KeyError: if `name` is not in `ALLOWED_PROMPT_NAMES`, or
            if the template references a placeholder not provided
            in `substitutions`.
    """
    template = _load_raw(name)
    return template.format_map(_StrictDict(substitutions))


def _cache_clear() -> None:
    """Test hook: clear the raw-load LRU cache so tests that write
    to a temporary prompt file see fresh contents. Not part of the
    public API — underscore-prefixed."""
    _load_raw.cache_clear()
