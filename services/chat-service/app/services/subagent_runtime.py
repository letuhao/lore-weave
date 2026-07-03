"""P5 REG-P5-01 runtime — scoped nested subagent execution (pure helpers).

A subagent delegates a bounded sub-task to a named persona and gets a
synthesized answer back — WITHOUT polluting the main context and WITHOUT the
subagent touching anything outside its declared ``tool_scope``.

This module holds the PURE, side-effect-free pieces (unit-tested in isolation);
the loop wiring lives in ``stream_service._stream_with_tools``. Spec:
``docs/specs/2026-07-03-subagent-runtime.md``.

The security crux is ``resolve_scoped_tools`` — the ``tool_scope`` whitelist
enforced at *advertise* time (only scoped tools are offered); the loop enforces
it a second time at *execute* time (defense-in-depth).
"""

from __future__ import annotations

from fnmatch import fnmatch

from app.services.frontend_tools import is_frontend_tool

__all__ = [
    "RUN_SUBAGENT_NAME",
    "MAX_SUBAGENT_DEPTH",
    "SUBAGENT_META_EXCLUDE",
    "SUBAGENT_RESULT_CHAR_CAP",
    "resolve_scoped_tools",
    "scoped_tool_names",
    "build_run_subagent_tool",
    "cap_result",
    "tool_name_of",
]

RUN_SUBAGENT_NAME = "run_subagent"

# Depth is capped at 1: a subagent can NEVER spawn another subagent (no
# recursion, no fan-out DoS). The scoped set also excludes run_subagent itself.
MAX_SUBAGENT_DEPTH = 1

# Meta/loop tools are never in a subagent's scope regardless of its globs —
# excluding run_subagent kills recursion; excluding find_tools keeps the sub-run
# on its fixed scoped set (no discovery escape hatch out of the whitelist).
SUBAGENT_META_EXCLUDE: frozenset[str] = frozenset({RUN_SUBAGENT_NAME, "find_tools"})

# The synthesized result returned to the MAIN turn is capped: a subagent that
# returned 50 KB would re-pollute the main context and defeat the whole point of
# isolation. Over-cap → truncate + a note.
SUBAGENT_RESULT_CHAR_CAP = 4000


def tool_name_of(tool_def: object) -> str | None:
    """Read a tool def's function name, tolerating malformed entries."""
    if not isinstance(tool_def, dict):
        return None
    fn = tool_def.get("function")
    if isinstance(fn, dict):
        name = fn.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _is_scopeable(name: str) -> bool:
    """A tool may be scoped to a subagent iff it is neither a meta/loop tool nor
    a frontend/UI tool (headless nested loop — a UI tool would hang/no-op)."""
    return name not in SUBAGENT_META_EXCLUDE and not is_frontend_tool(name)


def resolve_scoped_tools(catalog: list[dict], tool_scope: list) -> list[dict]:
    """The subagent's advertised tool set = the caller's full catalog INTERSECT
    the def's ``tool_scope`` globs (fnmatch), MINUS meta/loop tools and frontend
    tools (always excluded, even if a glob would match them).

    An empty / all-non-matching scope yields ``[]`` — a valid text-only
    (pure-reasoning) sub-run, NOT an error.
    """
    globs = [g for g in (tool_scope or []) if isinstance(g, str) and g]
    if not globs:
        return []
    out: list[dict] = []
    for td in catalog:
        name = tool_name_of(td)
        if not name or not _is_scopeable(name):
            continue
        if any(fnmatch(name, g) for g in globs):
            out.append(td)
    return out


def scoped_tool_names(catalog: list[dict], tool_scope: list) -> set[str]:
    """The names of the scoped set — the execute-time whitelist the loop checks a
    nested tool call against (defense-in-depth)."""
    return {tool_name_of(td) for td in resolve_scoped_tools(catalog, tool_scope)} - {None}  # type: ignore[arg-type]


def build_run_subagent_tool(names: list[str]) -> dict | None:
    """The ``run_subagent`` tool schema, advertised in the main turn IFF the user
    has ≥1 enabled subagent. ``subagent`` is a CLOSED-SET enum of the resolved
    names (Frontend-Tool-Contract rule: a finite value set is an enum, never a
    bare string — a weak model can't pass a bogus name, and the enum reinforces
    the arg name). Returns ``None`` when there are no subagents (tool absent)."""
    ordered: list[str] = []
    for n in names:
        if isinstance(n, str) and n and n not in ordered:
            ordered.append(n)
    if not ordered:
        return None
    return {
        "type": "function",
        "function": {
            "name": RUN_SUBAGENT_NAME,
            "description": (
                "Delegate a bounded sub-task to a named subagent persona and get "
                "back a synthesized answer. The subagent runs in its own isolated "
                "context with ONLY its scoped tools — use it to offload a focused "
                "lookup or transformation without cluttering this conversation. "
                "Returns the subagent's final answer as text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent": {
                        "type": "string",
                        "enum": ordered,
                        "description": "Which subagent persona to run.",
                    },
                    "task": {
                        "type": "string",
                        "description": "The sub-task for the subagent, in natural language.",
                    },
                },
                "required": ["subagent", "task"],
                "additionalProperties": False,
            },
        },
    }


def cap_result(text: str) -> tuple[str, bool]:
    """Cap the synthesized sub-result. Over ``SUBAGENT_RESULT_CHAR_CAP`` →
    truncate + append a one-line note. Returns ``(text, was_truncated)``."""
    if text is None:
        return "", False
    if len(text) <= SUBAGENT_RESULT_CHAR_CAP:
        return text, False
    note = "\n\n[subagent result truncated — it exceeded the size cap]"
    return text[:SUBAGENT_RESULT_CHAR_CAP] + note, True
