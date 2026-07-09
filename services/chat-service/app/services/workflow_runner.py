"""WS-2b — the Workflow primitive's consumer-local meta-tools + step-runner rail.

A **workflow** is a curated, tiered (system|user|book) object declaring a
machine-readable ORDERED step sequence (contract C3) — unlike a skill (prose) or a
command (macro). The chat agent lists them (``workflow_list``) and loads one
(``workflow_load``) to follow an explicit rail instead of orchestrating 15-25 calls
blind (spec §4.3). Both meta-tools are CONSUMER-LOCAL (resolved in chat-service from
the registry-fetched set, never federated) — the same shape as tool_list/tool_load.

``workflow_load`` does two things: (1) returns the ordered rail (each step's id, tool,
gate, and async annotation) + declared inputs + notes; (2) reports the set of step
TOOLS to ACTIVATE, so the next pass advertises their real schemas (reusing the
hot-seed budget, exactly like tool_load). The agent then walks the steps in order;
each step's tool call goes through the EXISTING per-tool tier/approval gate — the
runner never bypasses confirm/approval (spec §4.3 runtime).

**Async-honesty structural guard (OQ9 / F7).** Prose async-honesty already lives in
``workflow_skill.py``; here it becomes STRUCTURAL: a step whose tool starts an async
job is annotated ``async_job: true`` in the rail, and the load result's guidance
tells the agent to watch the job and NOT proceed to a dependent step until it
reaches a terminal status. A step marked async is never implicitly "done" when the
tool returns.
"""

from __future__ import annotations

WORKFLOW_LIST_NAME = "workflow_list"
WORKFLOW_LOAD_NAME = "workflow_load"

# The closed set of per-step gates (mirrors the registry's validWorkflowGates / C3).
VALID_GATES = ("none", "confirm", "approval")

# Structural async-honesty guard — the LAST-RESORT fallback. Precedence (see _rail_step):
#   1. the step's authored `async_job` boolean,
#   2. the CATALOG's `_meta.async` flag (every LoreWeave async tool now declares it),
#   3. this name heuristic — only for a tool that carries neither.
# Substring-based + conservative; the annotation only ADDS a "watch the job" hint, never
# blocks. Verbs avoid matching common READ tools ("media" was dropped — it hits
# media_list/get_media/…, and a read has no job to watch, which would strand the agent
# on ui_watch_job). kg_build_* no longer need a verb: knowledge-service declares
# `_meta.async` on them (D-KNOWLEDGE-META-ADOPTION cleared).
_ASYNC_JOB_VERBS = (
    "translat",  # translation_* / retranslate_* (job starters)
    "generate_wiki",
    "wiki_generate",
    "extract_entities",
    "start_extraction",
    "bulk_extract",
    "import_book",
    "book_import",
    "generate_media",
    "media_generate",
    "narrate",
    "auto_enrich",
    "composition_generate",
)


def is_async_job_tool(tool_name: str) -> bool:
    """True if calling this tool STARTS a background job (async-honesty HEURISTIC).

    Fallback only — a step's authored ``async_job`` flag overrides this (see _rail_step)."""
    n = (tool_name or "").lower()
    return any(v in n for v in _ASYNC_JOB_VERBS)


WORKFLOW_LIST_TOOL: dict = {
    "type": "function",
    "function": {
        "name": WORKFLOW_LIST_NAME,
        "description": (
            "List the curated multi-step WORKFLOWS available here — named, ordered recipes for "
            "common jobs (e.g. \"set up a glossary for this book\"). Returns {slug, title, "
            "description} per workflow. Prefer a workflow over improvising a long tool sequence; "
            "then call workflow_load(slug) to get its exact steps."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}

WORKFLOW_LOAD_TOOL: dict = {
    "type": "function",
    "function": {
        "name": WORKFLOW_LOAD_NAME,
        "description": (
            "Load one workflow's ordered steps by slug — the explicit rail to follow. Returns the "
            "declared inputs and each step's tool + gate (none/confirm/approval) + whether it starts "
            "a background job. Loading also makes the step tools callable; it does NOT run anything. "
            "Walk the steps in order: call each step's tool, honor its gate, and for a step that "
            "starts a job, watch the job before the next dependent step."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The workflow slug to load (from workflow_list)."},
            },
            "required": ["slug"],
            "additionalProperties": False,
        },
    },
}


def workflow_list_result(workflows: list[dict]) -> dict:
    """Deterministic list of the visible workflows (slug/title/description/tier). Unranked."""
    items = [
        {
            "slug": wf.get("slug", ""),
            "title": wf.get("title") or wf.get("slug", ""),
            "description": wf.get("description", ""),
            "tier": wf.get("tier", ""),
        }
        for wf in workflows
        if wf.get("slug")
    ]
    items.sort(key=lambda w: w["slug"])
    out: dict = {"count": len(items), "workflows": items}
    if not items:
        out["reason"] = "no workflows"
    return out


def _rail_step(step: dict, async_tools: frozenset[str] = frozenset()) -> dict:
    """Normalize one C3 step into the rail shape the agent reads.

    ``async_tools`` is the set of tool names the CATALOG marks `_meta.async` — the
    durable async-honesty signal."""
    tool = str(step.get("tool", "") or "")
    gate = step.get("gate") or "none"
    if gate not in VALID_GATES:
        gate = "none"
    rail: dict = {"id": step.get("id", ""), "tool": tool, "gate": gate}
    # Async-honesty precedence: (1) an AUTHORED `async_job` boolean on the step wins;
    # else (2) the CATALOG `_meta.async` flag; else (3) the tool-name heuristic fallback.
    authored = step.get("async_job")
    if isinstance(authored, bool):
        is_async = authored
    else:
        is_async = tool in async_tools or is_async_job_tool(tool)
    if is_async:
        rail["async_job"] = True
    if step.get("when"):
        rail["when"] = step["when"]
    if step.get("repeat") and step["repeat"] != "none":
        rail["repeat"] = step["repeat"]
    if isinstance(step.get("inputs_map"), dict) and step["inputs_map"]:
        rail["inputs_map"] = step["inputs_map"]
    return rail


def workflow_load_result(
    workflows: list[dict], slug: str, async_tools: frozenset[str] = frozenset(),
) -> tuple[dict, list[str]]:
    """Return (payload, step_tool_names) for one workflow.

    payload is the ordered rail + inputs + notes + guidance; step_tool_names is the
    de-duplicated list of tools to ACTIVATE so the next pass advertises their schemas.
    ``async_tools`` = the catalog's `_meta.async` tool names (durable async signal).
    A missing slug returns a not_found payload and an empty activation list.
    """
    wf = next((w for w in workflows if w.get("slug") == slug), None)
    if wf is None:
        return {
            "not_found": slug,
            "reason": f"no workflow '{slug}' — call workflow_list to see what's available",
        }, []

    raw_steps = wf.get("steps") if isinstance(wf.get("steps"), list) else []
    # Skip malformed steps (non-dict, or an empty `tool` the agent couldn't act on).
    rail = [
        _rail_step(s, async_tools)
        for s in raw_steps
        if isinstance(s, dict) and str(s.get("tool", "") or "").strip()
    ]
    tool_names: list[str] = []
    for step in rail:
        t = step.get("tool")
        if t and t not in tool_names:
            tool_names.append(t)

    has_gate = any(s["gate"] != "none" for s in rail)
    has_async = any(s.get("async_job") for s in rail)
    guidance = [
        "Follow the steps IN ORDER. Call each step's tool, then move to the next.",
    ]
    if has_gate:
        guidance.append(
            "A step with gate 'confirm' or 'approval' needs the user — the confirm/approval "
            "card appears when you call that tool; wait for the user, never skip it."
        )
    if has_async:
        guidance.append(
            "A step marked async_job STARTS a background job — it is not done when the tool "
            "returns. Watch the job (ui_watch_job) and do NOT begin a step that depends on its "
            "output until it has actually finished."
        )
    guidance.append(
        "If a step fails, STOP — report which steps completed and which did not; do not claim "
        "the workflow finished."
    )

    payload = {
        "slug": wf.get("slug", ""),
        "title": wf.get("title") or wf.get("slug", ""),
        "description": wf.get("description", ""),
        "inputs": wf.get("inputs") if isinstance(wf.get("inputs"), dict) else {},
        "steps": rail,
        "notes_md": wf.get("notes_md", ""),
        "guidance": guidance,
    }
    return payload, tool_names
