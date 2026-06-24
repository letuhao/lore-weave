"""MCP-fanout S-CONSUMER — tool discovery + tier metadata (C-FT, C-TOOL).

This is the *consumer-side* tool-scaling foundation. At ~200 federated tools,
shipping the full catalog to the LLM every turn is context bloat + degraded
tool selection (spec P0). Instead the agent first *searches* with the
``find_tools`` meta-tool, and only the matched tools' full schemas are
advertised on the next pass.

Everything here operates on the catalog chat already caches
(``KnowledgeClient.get_tool_definitions()``); ``find_tools`` is **consumer-local**
— NOT a federated domain tool — so it carries no user-data envelope and needs
no ownership guard (spec OD-1 / C-FT).

Key pieces
----------
* ``FIND_TOOLS_TOOL`` / ``FIND_TOOLS_NAME`` — the meta-tool schema (C-FT).
* ``ALWAYS_ON_CORE`` — the ≤8 tools advertised every universal ``/chat`` turn.
* ``search_catalog()`` — in-memory fuzzy search over name + description +
  ``_meta.synonyms`` (stdlib token-overlap + difflib; no embeddings in v1, no
  new dependency). Returns ``(matches, confident)`` so the loop can apply the
  H6 low-confidence/empty escalation.
* ``tool_tier()`` / ``tool_undo_hint()`` — read C-TOOL ``_meta`` for the
  consumer's tier-driven behaviour.
* ``strip_tool_meta()`` — drop ``_meta`` before a def goes over the wire to the
  provider (the LLM must see only a standard OpenAI function def).
* ``provider_availability()`` — H10 helper turning the gateway's catalog-meta
  into "is this tool's provider temporarily unavailable?".
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# ── C-FT: the find_tools meta-tool ───────────────────────────────────────────

FIND_TOOLS_NAME = "find_tools"

# Default number of matches returned to the agent.
FIND_TOOLS_DEFAULT_LIMIT = 8

FIND_TOOLS_TOOL: dict = {
    "type": "function",
    "function": {
        "name": FIND_TOOLS_NAME,
        "description": (
            "Find tools that can perform an intent. Call this FIRST when the user "
            "asks for something you don't already have a tool advertised for "
            "(e.g. editing a book, starting a translation, changing settings). "
            "Returns matching tool names + descriptions; the matched tools become "
            "callable on your NEXT step. If it returns nothing useful, you may try "
            "once more with broader wording before telling the user you can't."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "What the user wants to do, in your own words.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max tools to return (default 8).",
                    "default": FIND_TOOLS_DEFAULT_LIMIT,
                },
            },
            "required": ["intent"],
            "additionalProperties": False,
        },
    },
}


# ── C-FT: the always-on core (advertised every universal /chat turn, ≤8) ──────
# Domain reads/writes are discovered via find_tools; only the meta-tool + the
# generic frontend tools are always present. The frontend-tool schemas live in
# frontend_tools.py (S-CONSUMER sole-owns that file); this names which are core.
ALWAYS_ON_CORE_NAMES: tuple[str, ...] = (
    FIND_TOOLS_NAME,
    "ui_navigate",
    "ui_open_book",
    "ui_show_panel",
    "ui_watch_job",
    "propose_edit",
    "propose_record_edit",
    "confirm_action",
)


# ── C-TOOL: tier + meta readers ──────────────────────────────────────────────


def _fn(tool_def: dict) -> dict:
    """The OpenAI `function` object of a tool def (or {} if malformed)."""
    fn = tool_def.get("function")
    return fn if isinstance(fn, dict) else {}


def tool_name(tool_def: dict) -> str:
    return _fn(tool_def).get("name", "") or ""


def tool_meta(tool_def: dict) -> dict:
    """The C-TOOL `_meta` block for a tool def, or {} when absent (legacy
    glossary/knowledge tools predate `_meta` — they're treated as untiered)."""
    meta = _fn(tool_def).get("_meta")
    return meta if isinstance(meta, dict) else {}


def tool_tier(tool_def: dict) -> str:
    """C-TOOL `_meta.tier` ∈ R|A|W|S. Defaults to "R" (read / inert) when a tool
    carries no tier — a missing tier must NEVER auto-commit a write."""
    tier = tool_meta(tool_def).get("tier")
    return tier if tier in ("R", "A", "W", "S") else "R"


def tool_undo_hint(result_meta: dict | None) -> dict | None:
    """C-ACTIVITY — the `_meta.undo_hint` a Tier-A tool RESULT carries
    (``{tool, args}``), or None. Read from the tool *result*, not the def."""
    if not isinstance(result_meta, dict):
        return None
    hint = result_meta.get("undo_hint")
    return hint if isinstance(hint, dict) else None


def strip_tool_meta(tool_def: dict) -> dict:
    """Return a copy of a tool def with the consumer-only `_meta` removed, so
    the provider sees a standard OpenAI function def (C-TOOL: identity/tier
    metadata is consumer-side only, never advertised to the LLM)."""
    fn = _fn(tool_def)
    if "_meta" not in fn:
        return tool_def
    clean_fn = {k: v for k, v in fn.items() if k != "_meta"}
    out = dict(tool_def)
    out["function"] = clean_fn
    return out


# ── C-FT: in-memory fuzzy search ─────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Below this best-match score the result is "low confidence" → the loop may
# escalate once to the full curated group rather than denying (H6).
CONFIDENCE_THRESHOLD = 0.30
# A tool must score at least this to appear in results at all — keeps pure-noise
# difflib near-misses (a few shared characters) out of the match list, so a true
# "no such tool" reads as empty (H10) rather than a bogus suggestion.
INCLUSION_FLOOR = 0.20


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _score(intent_tokens: set[str], intent_raw: str, tool_def: dict) -> float:
    """Heuristic relevance score in [0, 1] of a tool for an intent.

    Combines token overlap (Jaccard-ish, the dominant signal) over the tool's
    name + description + synonyms with a difflib ratio on the raw strings, so a
    near-miss spelling still scores. No embeddings (v1, C-FT)."""
    name = tool_name(tool_def)
    desc = _fn(tool_def).get("description", "") or ""
    synonyms = tool_meta(tool_def).get("synonyms") or []
    syn_text = " ".join(s for s in synonyms if isinstance(s, str))
    # The name often encodes the verb (book_create, translation_start_job);
    # split snake_case so its tokens participate.
    hay = f"{name.replace('_', ' ')} {desc} {syn_text}"
    hay_tokens = _tokens(hay)
    if not intent_tokens:
        return 0.0

    overlap = len(intent_tokens & hay_tokens)
    token_score = overlap / len(intent_tokens)
    # difflib catches typo/near-miss matches the token set misses (e.g.
    # "translit" ~ "translate"), compared PER token against the name + synonym
    # tokens (more discriminating than the whole raw string, which would let an
    # unrelated long word like "frobnicate" score on incidental shared chars).
    target_tokens = _tokens(f"{name} {syn_text}")
    best_ratio = 0.0
    for it in intent_tokens:
        for tt in target_tokens:
            r = SequenceMatcher(None, it, tt).ratio()
            if r > best_ratio:
                best_ratio = r
    # Only a STRONG fuzzy hit (≥0.8, i.e. a near-spelling) rescues a tool with no
    # token overlap — a weak char-similarity must not invent a match (H10).
    fuzzy = best_ratio if best_ratio >= 0.8 else 0.0
    return max(token_score, fuzzy)


def search_catalog(
    catalog: list[dict],
    intent: str,
    limit: int = FIND_TOOLS_DEFAULT_LIMIT,
    *,
    exclude: set[str] | None = None,
) -> tuple[list[dict], bool]:
    """C-FT — fuzzy-search the cached catalog for tools matching ``intent``.

    Returns ``(matches, confident)`` where:
      * ``matches`` — up to ``limit`` ``{"name", "description"}`` dicts (names +
        descriptions only — NOT full schemas; the schemas are advertised next
        pass once the names are unioned into the active set).
      * ``confident`` — False when the result is empty OR the best score is
        below ``CONFIDENCE_THRESHOLD`` (H6 low-confidence → the loop may
        escalate once to the full curated surface rather than denying).

    ``exclude`` — names already always-on (the core); they're skipped so a
    search never re-suggests a tool the agent already has.
    """
    exclude = exclude or set()
    intent_tokens = _tokens(intent)
    scored: list[tuple[float, dict]] = []
    for tool_def in catalog:
        name = tool_name(tool_def)
        if not name or name in exclude:
            continue
        s = _score(intent_tokens, intent, tool_def)
        if s >= INCLUSION_FLOOR:
            scored.append((s, tool_def))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, limit)] if scored else []
    matches = [
        {"name": tool_name(td), "description": _fn(td).get("description", "") or ""}
        for _, td in top
    ]
    confident = bool(scored) and scored[0][0] >= CONFIDENCE_THRESHOLD
    return matches, confident


# ── H10: provider availability ───────────────────────────────────────────────


def _provider_prefix(name: str) -> str:
    """The provider prefix of a tool name (`book_create` → `book`). Frontend
    + meta tools (no prefix convention) return ""."""
    return name.split("_", 1)[0] if "_" in name else ""


def provider_availability(catalog_meta: dict) -> set[str]:
    """H10 — the set of provider prefixes the gateway reports as temporarily
    unavailable (partial catalog). Reads the catalog-level `_meta` from
    ``KnowledgeClient.get_catalog_meta()``.

    S-GATEWAY (C-GW) owns the exact key; we accept the most likely shapes
    (``unavailable_providers`` list / ``providers`` availability map) and return
    an empty set when none is present — so this never invents an outage.
    TODO(S-GATEWAY): freeze the key at COMPOSE A.
    """
    if not isinstance(catalog_meta, dict):
        return set()
    unavailable = catalog_meta.get("unavailable_providers")
    if isinstance(unavailable, (list, tuple, set)):
        return {str(p) for p in unavailable}
    providers = catalog_meta.get("providers")
    if isinstance(providers, dict):
        # {"book": {"available": false}, ...} or {"book": "down"}
        out: set[str] = set()
        for prov, state in providers.items():
            if isinstance(state, dict) and state.get("available") is False:
                out.add(str(prov))
            elif isinstance(state, str) and state.lower() in ("down", "unavailable"):
                out.add(str(prov))
        return out
    return set()


def find_tools_result(
    catalog: list[dict],
    intent: str,
    limit: int,
    *,
    exclude: set[str],
    catalog_meta: dict,
) -> tuple[dict, list[str]]:
    """Build the ``find_tools`` tool RESULT payload + the list of matched names
    to union into the active set (C-FT loop semantics).

    The payload distinguishes (H10): a genuinely empty result from one where the
    only plausible providers are *temporarily unavailable* — so the agent says
    "try again", never a false "I can't"."""
    matches, confident = search_catalog(catalog, intent, limit, exclude=exclude)
    unavailable = provider_availability(catalog_meta)
    payload: dict = {"tools": matches}
    if not matches:
        if unavailable:
            # H10: capability may exist but its provider is briefly down.
            payload["unavailable_providers"] = sorted(unavailable)
            payload["note"] = (
                "No matching tool is currently available. One or more services are "
                "temporarily unavailable — tell the user the capability exists but "
                "to try again shortly; do NOT say you can't do it."
            )
        else:
            payload["note"] = (
                "No tool matched. Reconsider the wording and search once more before "
                "telling the user this isn't supported."
            )
    elif not confident:
        payload["low_confidence"] = True
        payload["note"] = (
            "These are weak matches. If none fit, you may search once more with "
            "different wording."
        )
    matched_names = [m["name"] for m in matches]
    return payload, matched_names
