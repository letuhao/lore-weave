"""Federation-safety check: no BOOLEAN subschema in an advertised MCP tool schema.

JSON Schema 2020-12 lets ``true``/``false`` stand in for a whole schema. That is
legal — and **ai-gateway's federation validator rejects it**. The blast radius is
the PROVIDER, not the tool: one bad schema fails the entire ``tools/list`` response,
so every sibling tool disappears from the federated catalog.

This shipped for real (2026-07-23) on the Go side: ``glossary_curation_list`` typed
its union payload as ``Items any``, the go-sdk reflector emitted ``true``, and::

    WARN [FederationService] provider 'glossary' list-tools failed → PARTIAL
    LOG  [FederationService] catalog: 235 tools / 10 providers (... PARTIAL)

**All 54 glossary tools vanished** (measured: 0 ``glossary_*`` of 245 federated).
Every same-language gate stayed green, because the schema is valid IN ISOLATION —
the defect only exists at the federation boundary, in another service, in another
language, in another validator.

Python is *less* exposed than Go — pydantic renders ``Any`` as ``{}``, not ``true`` —
but a hand-written ``inputSchema``/``outputSchema`` dict can still do it, and the
consequence is identical: the whole provider drops out. Go now enforces this at
registration (``loreweave_mcp.RegisterTool`` panics); Python services assert it in a
test, since FastMCP has no equivalent shared registration chokepoint.

Usage in a service's test suite::

    from loreweave_mcp.schema_federation import assert_no_boolean_subschemas
    def test_schemas_are_federation_safe():
        assert_no_boolean_subschemas(await server.list_tools())
"""

from __future__ import annotations

from typing import Any, Iterable

# Keywords whose value is NOT a schema, so a boolean there is legitimate:
#   - schema-OR-boolean: `additionalProperties` (validators accept either form)
#   - INSTANCE-valued: `default`/`const`/`enum`/`examples` hold example VALUES, so
#     `default: true` on a bool flag is completely normal. Measured live across the
#     five Python providers, ALL 12 apparent hits were `.../<flag>/default` — every
#     one a false positive. Without this exemption the check is worse than useless.
NON_SUBSCHEMA_KEYWORDS = frozenset({
    "additionalProperties", "unevaluatedProperties", "unevaluatedItems",
    "uniqueItems", "readOnly", "writeOnly", "deprecated",
    "exclusiveMinimum", "exclusiveMaximum",
    "default", "const", "enum", "examples",
})


def find_boolean_subschemas(node: Any, path: str = "") -> list[str]:
    """Return the path of every boolean sitting where a SCHEMA belongs."""
    found: list[str] = []

    def walk(n: Any, p: str) -> None:
        if isinstance(n, bool):
            found.append(p)
        elif isinstance(n, dict):
            for k, v in n.items():
                if k in NON_SUBSCHEMA_KEYWORDS:
                    continue
                walk(v, f"{p}/{k}")
        elif isinstance(n, (list, tuple)):
            for i, v in enumerate(n):
                walk(v, f"{p}/{i}")

    walk(node, path)
    return sorted(found)


def _schema_of(tool: Any, attr: str) -> Any:
    """Read a schema off either an MCP Tool object or a plain dict."""
    for name in (attr, {"inputSchema": "input_schema", "outputSchema": "output_schema"}[attr]):
        value = tool.get(name) if isinstance(tool, dict) else getattr(tool, name, None)
        if isinstance(value, dict):
            return value
    return None


def check_tools(tools: Iterable[Any]) -> list[str]:
    """Return every offending ``<tool>.<schema>/<path>`` across the given tools."""
    bad: list[str] = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "?")
        for attr in ("inputSchema", "outputSchema"):
            schema = _schema_of(tool, attr)
            if schema is not None:
                bad.extend(find_boolean_subschemas(schema, f"{name}.{attr}"))
    return bad


def assert_no_boolean_subschemas(tools: Iterable[Any]) -> None:
    """Raise AssertionError naming every offending path. Call from a service test."""
    bad = check_tools(tools)
    assert not bad, (
        f"{len(bad)} boolean subschema(s) in advertised MCP tool schemas. ai-gateway's "
        f"federation validator rejects these and drops EVERY tool of this provider from "
        f"the catalog (measured: one such field erased all 54 glossary tools). Declare an "
        f"explicit schema stating the real shape instead. Offending paths: {bad}"
    )
