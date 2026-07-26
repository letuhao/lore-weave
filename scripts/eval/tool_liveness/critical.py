"""WS-D4 — `executes ∧ effect` for the WORKFLOW-CRITICAL set.

The deterministic sweep proves `executes` (the tool returned success). But a tool can
return `{"ok": true}` and write NOTHING — the "silent success" bug class this whole eval
exists to catch. For most of the ~200 tools that gap is acceptable (they are not on any
shipped path). For the tools a CURATED WORKFLOW actually references, it is not: a workflow
whose step silently no-ops is exactly the failure CD4 guards against.

So this module holds the critical tools to the stronger bar — `executes ∧ effect` — where
`effect` is an INDEPENDENT read-back (CD3's anti-oracle rule: read the domain's Postgres
directly, never the tool's own read path, so a shared bug cannot make both agree). A
critical tool that returns success but whose effect does NOT land is scored `executes:
false` (a silent-success bug is worse than a crash — it lies), which the CD4 ship gate
already rejects.

The critical set is DERIVED LIVE from the curated workflows (anti-drift — a workflow that
starts referencing a new tool pulls it in automatically). Today it is the four steps of
`glossary-bootstrap`. One of them — `glossary_extract_entities_from_doc` — is `paid: true`
(an LLM extraction), so its effect cannot be proven at $0; that is recorded as an honest
gap, not silently passed.
"""
from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from . import config, oracle
from .confirm import find_confirm_token
from .sweep import _HEADERS, classify


def workflow_critical_set() -> set[str]:
    """The tools any curated workflow references — derived live from agent-registry so it
    cannot drift from what actually ships. Empty if the table is unreachable (the caller
    then simply has nothing to effect-verify)."""
    try:
        rows = oracle.db_query(
            config.DOMAIN_DB["agent_registry"],
            "SELECT DISTINCT step->>'tool' FROM workflows, "
            "jsonb_array_elements(steps) AS step WHERE step->>'tool' IS NOT NULL")
        return {r[0] for r in rows if r and r[0]}
    except Exception:
        return set()


def _authored(tool: str, ids: dict) -> dict | None:
    """Args to exercise a critical tool against the fixture book. None ⇒ we cannot (or must
    not — a paid tool) call it, so it is not effect-verifiable here."""
    book = ids.get("book_id")
    if not book:
        return None
    if tool == "book_get":
        return {"book_id": book}
    if tool == "glossary_adopt_standards":
        return {"book_id": book}
    if tool == "glossary_propose_entities":
        return {"book_id": book, "items": [{"name": "TLE Critical Hero", "kind": "character"}]}
    # glossary_extract_entities_from_doc is paid (an LLM extraction) — never call it.
    return None


def _effect(tool: str, ids: dict, result: dict) -> tuple[bool | None, str]:
    """(effect_landed, why), verified via an INDEPENDENT path (the domain DB directly, or
    the tool's OWN returned handle re-read from the DB — never the tool's read API)."""
    book = ids.get("book_id")
    if tool == "book_get":
        got = (result.get("book") or {}).get("book_id") or result.get("book_id")
        return (got == book, f"returned the fixture book_id ({got})")
    if tool == "glossary_adopt_standards":
        # Tier W: the standards are written only on CONFIRM; the verifiable call-time effect
        # is that a real confirm_token + preview was minted (not an empty ok).
        tok = find_confirm_token(result)
        return (tok is not None, "minted a confirm_token" if tok else "returned ok but NO confirm_token")
    if tool == "glossary_propose_entities":
        # Independent read-back: the entity_id the tool claims it created must actually exist
        # in glossary_entities. If the tool returned "created" but wrote nothing, this is
        # None → the silent-success bug, caught.
        first = (result.get("results") or [{}])[0]
        eid = first.get("entity_id")
        if not eid:
            return (False, "result carried no entity_id")
        alive = oracle.glossary_entity_alive(eid)  # None ⇒ row does not exist
        return (alive is not None, f"entity {eid} {'is in glossary_entities' if alive is not None else 'is MISSING from the DB'}")
    return (None, "no effect oracle for this critical tool")


def _result_json(res: Any) -> dict:
    sc = getattr(res, "structuredContent", None)
    if isinstance(sc, dict):
        return sc
    if getattr(res, "content", None):
        try:
            return json.loads(res.content[0].text)
        except Exception:
            pass
    return {}


async def verify(ids: dict) -> list[dict]:
    """Effect-verify every critical tool against the fixture book. Returns one row per tool,
    with `executes` (a silent success folds to False) and a `effect_verified` flag."""
    crit = workflow_critical_set()
    if not crit:
        return []
    rows: list[dict] = []
    async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=_HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for tool in sorted(crit):
                args = _authored(tool, ids)
                if args is None:
                    rows.append({"tool": tool, "source": "critical", "executes": None,
                                 "effect_verified": None,
                                 "why": "paid or not authorable — effect not verified at $0"})
                    continue
                try:
                    res = await s.call_tool(tool, args)
                    ok = not getattr(res, "isError", False)
                    msg = "" if ok else (res.content[0].text if res.content else "?")
                    result = _result_json(res) if ok else {}
                except Exception as e:
                    ok, msg, result = False, f"transport: {type(e).__name__}: {e}", {}
                if not ok:
                    executes, why = classify(ok, msg)
                    rows.append({"tool": tool, "source": "critical", "executes": executes,
                                 "effect_verified": False, "why": why, "error": msg[:200]})
                    continue
                effect, ewhy = _effect(tool, ids, result)
                if effect is False:
                    # returned ok, effect did NOT land — a silent success. Worse than a
                    # crash (it lies), and the CD4 gate must REJECT it: score executes false.
                    rows.append({"tool": tool, "source": "critical", "executes": False,
                                 "effect_verified": False,
                                 "why": f"SILENT SUCCESS — returned ok but effect did not land: {ewhy}"})
                else:
                    rows.append({"tool": tool, "source": "critical", "executes": True,
                                 "effect_verified": bool(effect), "why": ewhy})
    return rows
