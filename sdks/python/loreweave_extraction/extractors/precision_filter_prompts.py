"""Single source of truth (SOT) for the precision filter / judge prompt.

Why a separate module: this prompt is reused by BOTH the SDK-level
`pass2_filter` (cycle 72 — production filter) AND the eval-side
`llm_judge.py` (eval-only judging). Promoting it to the SDK ensures
both paths stay byte-identical without manual sync.

The thinking-suppression prefix is exposed separately because:
- Reasoning-capable judges (gemma-4-26b, claude-4.7-opus) burn
  ~1000 reasoning tokens per call when not suppressed, finishing
  ~67% of calls with finish_reason=length and truncated JSON.
- Some downstream consumers may legitimately want thinking enabled
  for the judge call (e.g. external red-team verification).

Builder helper `build_precision_prompt(suppress_thinking=True)` is
the canonical entry point. Direct constant access is permitted for
regression tests (e.g. `test_precision_filter_prompts.py` byte-hash
assertions).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

__all__ = [
    "NO_THINK_PREFIX",
    "build_precision_prompt",
    "precision_prompt_body",
]


# Reasoning-suppression preamble. Empirically required for thinking-tuned
# judges on LM Studio (session-67 cont.5 calibration; see llm_judge.py
# comment block for history). Plain models tolerate the prefix as a
# harmless instruction; thinking-tuned models obey it ~95% of the time
# under temperature=0.
NO_THINK_PREFIX: str = (
    "RESPOND DIRECTLY. Do NOT think aloud, do NOT use <think> tags, do "
    "NOT write reasoning. Emit ONLY the JSON object below — no prose "
    "before or after, no markdown fences.\n\n"
)


_PROMPT_BODY_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "precision_filter_system.md"
)


@lru_cache(maxsize=1)
def precision_prompt_body() -> str:
    """Load the precision filter prompt body from disk (cached).

    The body is the verdict-shape prompt without the thinking-suppression
    preamble — `build_precision_prompt` composes the two.
    """
    return _PROMPT_BODY_PATH.read_text(encoding="utf-8").rstrip("\n")


def build_precision_prompt(*, suppress_thinking: bool = True) -> str:
    """Single SOT entry point for the precision filter / judge prompt.

    Args:
        suppress_thinking: when True (default), prepends `NO_THINK_PREFIX`.
            Required for thinking-tuned local judges to keep
            finish_reason!=length on tight token budgets.

    Returns:
        Fully assembled system-prompt string ready to pass to the LLM.
    """
    body = precision_prompt_body()
    if suppress_thinking:
        return NO_THINK_PREFIX + body
    return body
