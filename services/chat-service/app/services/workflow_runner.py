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

import logging

logger = logging.getLogger(__name__)

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


# WS-3 (C6) — the PINNED rail.
#
# A binding may PIN a workflow for a mode. A pin renders that workflow's rail straight
# into the system prompt (and pre-activates its step tools), so the agent never has to
# *decide to load* it. This is the S06 fix: the agent had the right workflow advertised
# and a directive telling it to load one, and still improvised — because the user never
# ASKED ("set up my world"), they only ASSENTED to the agent's own offer ("yeah do it").
# Recognising a workflow from an assent is a step a mid-tier model does not reliably
# take; pinning removes the step.
#
# It reuses ``workflow_load_result`` verbatim — ONE rail format, so a pinned rail and a
# loaded rail can never drift apart.
#
# The per-rail prose ceiling (Context Budget Law: an always-on block must be bounded).
# It is a SAFETY VALVE, not a design budget — an authored rail is expected to fit well
# inside it. The registry's own seed lint (migrate_lint_test.go) holds System workflow
# notes under NOTES_SEED_BUDGET_CHARS so a seeded rail can never be cut here; if this
# ever DOES cut, it is logged loudly, because of what a silent cut costs:
#
#   Measured 2026-07-11 — the flagship vision-to-book rail's notes were 3218 chars against a 3000 cap,
#   so the tail was dropped. The tail was the SPEAK-PLAINLY vocabulary block ("never say
#   workflow/glossary/spec… this recipe is PRIVATE"), i.e. the exact rules that stop the
#   agent leaking the machinery to the user. The leak they were written to fix therefore
#   survived, and the truncation said nothing. A cap that silently eats the end of a
#   prompt is worse than no cap: the block still LOOKS complete.
NOTES_CHAR_CAP = 6000

# The TOTAL ceiling for the whole pinned-rail block (all rails together). notes_char_cap
# bounds ONE rail's prose; this bounds the BLOCK. Without it, a binding pinning many
# workflows (the PUT allows up to 32) would inflate every single turn of that mode without
# limit — and an always-on block with no ceiling is exactly what the Context Budget Law
# exists to forbid.
TOTAL_CHAR_CAP = 12000


def pinned_rail_block(
    workflows: list[dict],
    slugs: list[str],
    async_tools: frozenset[str] = frozenset(),
    *,
    notes_char_cap: int = NOTES_CHAR_CAP,
    progress_by_slug: "dict[str, str] | None" = None,
) -> tuple[str | None, list[str]]:
    """Render the pinned workflows as ONE prompt block.

    Returns ``(text, step_tool_names)``. A slug that resolves to no visible workflow is
    SKIPPED (it cannot be run) and reported by the caller — never a silent no-op.

    ``progress_by_slug`` (Track C Phase 2) is the RAIL DRIVER's rendered block for each
    slug: where the user actually is, computed server-side from the book's artifacts + the
    session's real tool-call history, and what the single next action is. Absent (or a
    slug missing from it) ⇒ the rail renders exactly as before, so a failed probe degrades
    to the pre-Phase-2 behavior instead of breaking the turn.
    """
    progress_by_slug = progress_by_slug or {}
    rails: list[str] = []
    tools: list[str] = []
    used = 0
    for slug in slugs:
        # TOTAL ceiling across all pinned rails. `notes_char_cap` alone bounds only ONE
        # rail's notes — a binding may pin up to 32 workflows (the PUT's list cap), each
        # with an unbounded title/description/step list, so a per-rail cap leaves the
        # always-on block itself unbounded. This block rides EVERY turn of its mode, so
        # an unbounded always-on block is precisely what the Context Budget Law forbids.
        if used >= TOTAL_CHAR_CAP:
            logger.warning(
                "pinned rails truncated: %d/%d rendered before the %d-char total ceiling "
                "— the remaining pins are NOT in context this turn",
                len(rails), len(slugs), TOTAL_CHAR_CAP,
            )
            break
        payload, step_tools = workflow_load_result(workflows, slug, async_tools)
        if payload.get("not_found"):
            continue
        lines = [f'YOUR RECIPE (internal, slug "{payload["slug"]}"): {payload["title"]}']
        if payload.get("description"):
            lines.append(payload["description"])
        lines.append("Steps, in order:")
        for i, st in enumerate(payload["steps"], 1):
            bits = [f'  {i}. {st["id"]} → {st["tool"]}']
            if st.get("gate") != "none":
                bits.append(f'[{st["gate"]}: the user must approve]')
            if st.get("async_job"):
                bits.append("[background job — NOT done when the tool returns]")
            lines.append(" ".join(bits))
        notes = str(payload.get("notes_md") or "").strip()
        if notes:
            if len(notes) > notes_char_cap:
                logger.warning(
                    "pinned rail %r: notes_md truncated %d → %d chars — the END of a rail's "
                    "prose is where its vocabulary/honesty rules live, so a cut here silently "
                    "removes them. Shorten the workflow's notes_md or raise NOTES_CHAR_CAP.",
                    payload["slug"], len(notes), notes_char_cap,
                )
                notes = notes[:notes_char_cap].rstrip() + " …"
            lines.append("How to run it:")
            lines.append(notes)
        for g in payload.get("guidance", []):
            lines.append(f"- {g}")
        # The rail driver's block goes LAST — recency matters in a long system prompt, and
        # this is the part the model must actually act on. Everything above is the recipe;
        # this is where it currently stands and what to do next.
        prog = progress_by_slug.get(slug)
        if prog:
            lines.append("")
            lines.append(prog)
        rail_text = "\n".join(lines)
        rails.append(rail_text)
        used += len(rail_text)
        for t in step_tools:
            if t not in tools:
                tools.append(t)
    if not rails:
        return None, []

    # The memory clause points AT the progress block, so it may only promise what was
    # actually rendered — on TWO axes:
    #  1. It must name the REAL headings. render_progress_block emits "WHERE THE BOOK ACTUALLY
    #     IS" and "YOUR PLACE IN THE RECIPE"; an earlier cut of the clause said "YOUR NEXT
    #     ACTION", a section that never exists — a dangling instruction the model resolves by
    #     inventing something to satisfy it.
    #  2. It must not claim "from the book itself" when the book-state probe FAILED. When the
    #     probe returns nothing, the block still renders from the call log alone (no snapshot),
    #     and swearing that a tool "wrote nothing per the book" when the book was never read is
    #     the exact false-grounding this whole mechanism exists to prevent.
    book_grounded = any(
        "WHERE THE BOOK ACTUALLY IS" in progress_by_slug.get(s, "") for s in slugs
    )
    progress_present = any(s in progress_by_slug for s in slugs)
    if book_grounded:
        memory_clause = (
            "You do NOT have to remember where you got to. Below each recipe, \"WHERE THE "
            "BOOK ACTUALLY IS\" and \"YOUR PLACE IN THE RECIPE\" are computed fresh from the "
            "book itself and from what you really called — they are the truth. Follow them. "
            "If they say a step is done, it is done, even if you do not remember doing it; if "
            "they say the effect never landed, then it did not land, even if the tool said "
            "\"success\".\n"
        )
    elif progress_present:
        memory_clause = (
            "You do NOT have to remember where you got to. \"YOUR PLACE IN THE RECIPE\" below "
            "is computed from the tools you actually called this session — follow it, and do "
            "not repeat a step it lists as already done.\n"
        )
    else:
        memory_clause = (
            "Do NOT redo a step you already completed in this conversation — look back at "
            "what you have already called, and continue from the first step still "
            "outstanding.\n"
        )

    header = (
        "YOU HAVE A READY-MADE RECIPE FOR THIS JOB. Its ordered steps are below and its "
        "tools are already available to you — you do NOT need to look it up or load it.\n"
        "\n"
        "RUN it when the user asks for the job it covers, AND — this is the case you keep "
        "missing — when the user simply AGREES to an offer you made (\"yeah\", \"do it\", "
        "\"sure\", \"go ahead\", \"please\"). Their yes refers to YOUR offer: honour it by "
        "running these steps, not by inventing a different tool sequence.\n"
        "\n"
        "CALL THE TOOLS — DO NOT NARRATE THEM. Describing what you are *about to* do ("
        "\"first I'll look at the categories, then I'll…\") is NOT doing it, and it leaves "
        "the user with nothing. When a step is due, CALL its tool in that same turn, then "
        "tell the user what CHANGED. Chain the steps you can: do not stop after one tool "
        "and wait to be asked again.\n"
        "\n"
        + memory_clause
        + "\n"
        "THE RECIPE IS PRIVATE. Never mention it, its name/slug, its steps, or the word "
        "\"workflow\" to the user — they are a novelist, not an engineer. Speak only about "
        "THEIR story: \"let me set up the categories your world tracks\", never \"I'll run "
        "the vision-to-book workflow\".\n"
    )
    return header + "\n\n" + "\n\n".join(rails), tools
