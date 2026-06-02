"""Pass 2 extraction prompt loader (moved from knowledge-service in Phase 4b-α).

Loads markdown prompt templates from this package directory and
performs strict placeholder substitution. Used by the extractor
modules (entity / relation / event / fact) and the high-level
`extract_pass2` orchestrator to build the prompts sent to the BYOK
provider via the loreweave_llm SDK.

**Strict substitution:** `load_prompt` uses `str.format_map` with a
dict that raises on missing keys. This catches typos in caller
kwargs at call time rather than silently embedding a literal
`{text}` in the prompt sent to the LLM — a failure mode that
would only surface as confusing model output hours later.

**LRU-cached raw loads:** the markdown files are read once per
process via `@lru_cache` on `_load_raw`. Prompt content is
effectively immutable at runtime, so re-reading on every extract
call would be pure waste. Tests that hot-swap prompt files must
call `_load_raw.cache_clear()` to see fresh contents.

**Closed prompt name set:** `ALLOWED_PROMPT_NAMES` is a frozenset
of the four extractor kinds plus their `_system` variants.
Attempting to load anything else raises `KeyError` to prevent
user-controlled prompt injection via dynamic file paths
(e.g. `name=../../etc/passwd`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, get_args

__all__ = [
    "PromptName",
    "load_prompt",
    "ALLOWED_PROMPT_NAMES",
    "OUTPUT_CONTRACT_REMINDER",
    "apply_prompt_override",
]

# B2-B-b2 — the SDK-controlled output-contract block. ALWAYS appended LAST to a
# project's custom system prompt so a hostile/garbage override cannot remove the
# JSON-only discipline that persistence depends on (DESIGN §2.5 injection
# defense). It enforces FORMAT only — the custom prompt still owns field/schema
# guidance, so a wrong-schema prompt degrades the user's OWN extraction quality
# (their BYOK spend) but can never break the contract, escalate, or reach
# another tenant's data.
OUTPUT_CONTRACT_REMINDER = (
    "\n\n---\n"
    "CRITICAL OUTPUT CONTRACT (enforced by the system, not optional): respond "
    "with ONLY a single valid JSON value matching the structure described "
    "above. No prose, no explanation before or after, no markdown code fences, "
    "no <think> tags. Output JSON and nothing else."
)


def apply_prompt_override(default_system: str, override_system: str | None) -> str:
    """Return the effective system prompt for an op (B2-B-b2).

    No override (None/blank) → the default verbatim (it already carries the
    contract). A custom override → the custom text verbatim + the SDK-controlled
    `OUTPUT_CONTRACT_REMINDER` appended LAST, so the JSON-only discipline is
    guaranteed regardless of what the custom prompt says (DESIGN §2.5)."""
    if not override_system or not override_system.strip():
        return default_system
    return override_system.rstrip() + OUTPUT_CONTRACT_REMINDER

# Real Literal type so static checkers flag typoed callers at
# compile-time instead of relying only on the runtime KeyError.
#
# `*_system` variants are system-message-only prompts that exclude
# the chapter `{text}` block, used alongside a separate user-message
# text payload so the gateway's chunker can split the user message
# without shredding instructions.
PromptName = Literal[
    "entity",
    "relation",
    "event",
    "fact",
    "entity_system",
    "relation_system",
    "event_system",
    "fact_system",
    # P3 (hierarchical extraction T4 + T7 stage 1) — single-prompt
    # summarize_level (no _system variant; input is bounded, no chunking).
    "summarize_level",
]

ALLOWED_PROMPT_NAMES: frozenset[str] = frozenset(get_args(PromptName))

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
    # `*_system` maps to `<base>_extraction_system.md`; other names
    # follow the legacy `<name>_extraction.md` pattern.
    if name.endswith("_system"):
        base = name[: -len("_system")]
        path = _PROMPTS_DIR / f"{base}_extraction_system.md"
    else:
        path = _PROMPTS_DIR / f"{name}_extraction.md"
    return path.read_text(encoding="utf-8")


def load_prompt(name: PromptName, **substitutions: str) -> str:
    """Load a prompt template and substitute placeholders.

    Args:
        name: one of `ALLOWED_PROMPT_NAMES`.
        **substitutions: template variables to interpolate. Missing
            keys raise `KeyError` — callers must supply every
            placeholder the template declares.

    Returns:
        The fully-substituted prompt text ready to pass to the LLM.

    Raises:
        KeyError: if `name` is not in `ALLOWED_PROMPT_NAMES`, or if
            the template references a placeholder not provided in
            `substitutions`.
    """
    template = _load_raw(name)
    return template.format_map(_StrictDict(substitutions))
