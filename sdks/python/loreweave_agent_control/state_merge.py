"""Agent Control Plane SDK — the executive's PURE state-merge + prompt-build (ACP A1).

Extracted from knowledge-service `app/working_memory/executive.py` (RV-H1: `merge_state`
lives in knowledge, so knowledge is an A1 SDK consumer). These are the *pure* pieces —
no I/O, no LLM call, no repo. `run_executive` (which does the I/O) stays in knowledge and
imports these. Behavior is byte-identical to the original (RW-2 characterization golden).

- `merge_state` — safe-when-wrong merge of the LLM's reported progress into a new `state`:
  `covered` is MONOTONIC (union, never shrinks); `phase` must be a charter phase or the prior
  is kept; non-string fields dropped. The executive can never move the goal (writes `state` only).
- `build_messages` — bounds the recent-turns window + wraps the charter/state as the executive
  prompt. Pure (json only).
"""
from __future__ import annotations

import json

# How many recent turns the prompt is bounded to (chat-service sends the window).
EXECUTIVE_MAX_TURNS = 12

# Per-turn content cap — bound the prompt size so a single pasted wall of text can't blow
# the model context / cost (EXECUTIVE_MAX_TURNS bounds the count).
EXECUTIVE_MAX_TURN_CHARS = 2000

EXECUTIVE_SYSTEM_PROMPT = (
    "You are the silent director of a roleplay/interview session. You are given the "
    "session CHARTER (a FIXED goal, the planned phases, and a checklist) and the recent "
    "turns. Report ONLY the current progress as a JSON object — you do NOT change the "
    "goal. Output exactly:\n"
    '{"phase": <one of the charter phases>, '
    '"covered": [<checklist items demonstrably covered so far, by their exact charter '
    'wording>], '
    '"redirect_hint": <a short in-character nudge to steer back to the goal IF the '
    'conversation has drifted, else null>}\n'
    "Write any prose (redirect_hint) in the charter's language. Output JSON only, no prose."
)


def build_messages(charter: dict, state: dict, recent_turns: list[dict]) -> list[dict]:
    turns = [
        {
            "role": t.get("role", ""),
            "content": (t.get("content", "") or "")[:EXECUTIVE_MAX_TURN_CHARS],
        }
        for t in (recent_turns or [])[-EXECUTIVE_MAX_TURNS:]
    ]
    ctx = {"charter": charter, "current_state": state, "recent_turns": turns}
    user = (
        "Session context:\n"
        + json.dumps(ctx, ensure_ascii=False)
        + "\n\nReturn the updated progress JSON."
    )
    return [
        {"role": "system", "content": EXECUTIVE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def merge_state(charter: dict, old_state: dict, llm_state: dict) -> dict:
    """Merge the LLM's reported progress into a new state — safe-when-wrong.

    `covered` is monotonic (union, dedup-preserving order); `phase` must be a
    charter phase or the prior phase is kept; non-string fields are dropped.
    """
    old_cov = old_state.get("covered") or []
    new_cov = [c for c in (llm_state.get("covered") or []) if isinstance(c, str)]
    covered = list(dict.fromkeys([*old_cov, *new_cov]))  # union, monotonic, ordered

    phases = charter.get("phases") or []
    phase = llm_state.get("phase")
    if phase not in phases:
        phase = old_state.get("phase", "")

    def _str_or_none(v):
        return v if isinstance(v, str) and v.strip() else None

    return {
        "phase": phase,
        "covered": covered,
        "elapsed_min": old_state.get("elapsed_min"),
        "drift_note": _str_or_none(llm_state.get("drift_note")),
        "redirect_hint": _str_or_none(llm_state.get("redirect_hint")),
    }
