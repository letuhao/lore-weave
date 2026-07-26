"""CD4 · the liveness manifest reader (Track D · WS-D3).

CD4: *"`tool_list` MUST NOT advertise a tool with a RED G3. A tool the LLM cannot
successfully execute is worse than an absent one: it burns turns and produces false
'saved!' claims."*

The verdicts come from ``contracts/tool-liveness.json``, GENERATED from the liveness
matrix (``scripts/eval/tool_liveness/manifest.py``) and never hand-maintained. The copy
next to this module is byte-identical to the SoT — ``test_tool_liveness.py`` reds if they
drift. It is a copy only because Python package data cannot climb out of its module;
agent-registry embeds the same file for the same reason.

The manifest carries two DERIVED fields so this reader and agent-registry's Go gate do
not re-implement the verdict logic in two languages (the schema-drift trap):

    executes  True   the tool ran when called correctly
              False  the tool FAILED when called correctly — proven broken
              None   never checked (paid, no authored args, or no probe)
    proven    every gate G1..G4 passed under a real model

The three-valued ``executes`` is the whole point. ``None`` must NEVER be read as False:
"we didn't check" is not "it's broken", and hiding every unchecked tool would empty the
catalog. Symmetrically it must never be read as True. Hence :func:`tool_is_broken` tests
for an EXPLICIT ``False``.

Note what is deliberately NOT hidden: a ``RED-SELECT`` tool (``executes: True``) works
perfectly — the model just failed to pick it from its description. Hiding it would
guarantee the model never picks it. That is an F5 description problem, fixed by writing a
better description, not by removing the tool.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MANIFEST_PATH = Path(__file__).with_name("tool-liveness.json")


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover — degrade-safe, never brick discovery
        # An unreadable manifest must not empty the tool catalog. The gate goes inert
        # and says so, loudly, rather than hiding every tool.
        logger.exception("tool-liveness manifest unreadable — CD4 tool_list gate is INERT")
        return {"tools": {}}
    if not isinstance(data, dict) or not isinstance(data.get("tools"), dict):
        logger.error("tool-liveness manifest malformed — CD4 tool_list gate is INERT")
        return {"tools": {}}
    return data


_MANIFEST = _load()
TOOLS: dict[str, dict] = _MANIFEST.get("tools", {})
SCHEMA_VERSION: int = _MANIFEST.get("schema_version", 0)


def tool_is_broken(name: str) -> bool:
    """True iff the tool is PROVEN BROKEN — the liveness matrix called it correctly, with
    valid args, and it failed. Only an explicit ``executes: false`` counts. An absent tool
    or ``executes: null`` is unknown, not broken."""
    return TOOLS.get(name, {}).get("executes") is False


def tool_is_proven(name: str) -> bool:
    """True iff every gate G1..G4 passed under a real model."""
    return bool(TOOLS.get(name, {}).get("proven"))


def broken_tool_names() -> set[str]:
    """The set `tool_list`/`tool_load` must not advertise."""
    return {n for n, v in TOOLS.items() if v.get("executes") is False}
