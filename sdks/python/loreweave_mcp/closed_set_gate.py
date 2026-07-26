"""K20 (Python half) — a closed set must be declared in the schema, not only in prose.

The Go services got this gate first (`TestEveryEnumeratedClosedSetHasAnEnum` in
book-service), because that is where the audit found the defect: `book_structure_edit.op`
enumerated `create_part | rename_part | …` in its DESCRIPTION while advertising a bare
string. The model is validated against the schema and reads the prose only as advice, so a
near-miss value is accepted and then silently does nothing — the shipped `panel_id` bug.

Python services have the same failure with a different spelling. A handler written

    scope: Annotated[str, "mine | system | all"] = "all"
    ...
    if scope not in ("mine", "system", "all"):
        return {"error": "scope must be one of: mine, system, all"}

REJECTS anything else, so the set is real and closed — but the model was never told it, and
gets a hard error it had no way to avoid. `Literal["mine","system","all"]` is the fix:
FastMCP emits a real `enum` from it, which is the only form the validator reads.

This module is the shared detector so each service's test is three lines. Deliberately
conservative — it requires at least two pipe-joined BARE tokens, so ordinary prose
containing a stray "|" never trips it.
"""

from __future__ import annotations

import re

_BARE_TOKEN = re.compile(r"^[\w.-]+$")


def enumerated_values_in_description(desc: str | None) -> list[str] | None:
    """Return the closed set a description ENUMERATES in prose, else None.

    Mirrors the Go detector (lwmcp.EnumeratedValuesInDescription) so both halves of the
    catalog are judged by the same rule.
    """
    if not desc:
        return None
    body = desc
    # Cut a leading "…:" label ("the structure operation: a | b | c").
    if ":" in body:
        body = body.rsplit(":", 1)[1]
    # Stop at a parenthetical / sentence end so trailing prose is not swallowed.
    for stop in ("(", ". ", "—", " -- "):
        i = body.find(stop)
        if i > 0:
            body = body[:i]
    parts = body.split("|")
    if len(parts) < 2:
        return None
    out: list[str] = []
    for p in parts:
        tok = p.strip().strip("\"'")
        if not tok or not _BARE_TOKEN.match(tok):
            return None
        out.append(tok)
    return out


def _has_enum(prop: dict) -> bool:
    if not isinstance(prop, dict):
        return False
    if "enum" in prop or "const" in prop:
        return True
    for branch in (prop.get("anyOf") or prop.get("oneOf") or []):
        if isinstance(branch, dict) and ("enum" in branch or "const" in branch):
            return True
    return False


def find_undeclared_closed_sets(tools) -> list[tuple[str, str, list[str]]]:
    """Scan advertised tools for args whose description enumerates a set the schema omits.

    `tools` is whatever `await mcp_server.list_tools()` returns. Yields
    ``(tool_name, arg_name, values)`` so the caller can fail with a specific message.
    """
    findings: list[tuple[str, str, list[str]]] = []
    for tool in tools:
        schema = getattr(tool, "inputSchema", None) or {}
        for name, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict):
                continue
            vals = enumerated_values_in_description(prop.get("description"))
            if vals and not _has_enum(prop):
                findings.append((tool.name, name, vals))
    return findings


def count_enumerating_descriptions(tools) -> int:
    """How many args enumerate a set in prose at all — declared or not.

    Guards the guard: if this hits zero the detector has gone blind (a reworded description,
    a stricter regex) and the gate above would start passing vacuously.
    """
    n = 0
    for tool in tools:
        schema = getattr(tool, "inputSchema", None) or {}
        for prop in (schema.get("properties") or {}).values():
            if isinstance(prop, dict) and enumerated_values_in_description(
                prop.get("description")
            ):
                n += 1
    return n
