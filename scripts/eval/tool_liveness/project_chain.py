"""Phase-1 chaining for BOOK/PROJECT-scoped creators (the composition + planforge families).

`user_fixture.authored_user_args` chains the USER-scoped writes (motif, glossary_user,
registry). This is its book-scoped twin: the composition and planforge tools that mint an
id a later tool consumes, but whose scope is `book`/`project`, so they run in PHASE 1
against the throwaway fixture book — not phase 2.

The lever that makes this cheap:
  * `composition_create_work` mints the COMPOSITION `project_id` (distinct from the kg
    project the fixture already holds — composition has its own `composition_work` table;
    a kg project_id fails these tools with "not found or not accessible").
  * `plan_propose_spec` in the default `rules` mode runs SYNCHRONOUSLY ($0, no LLM) and
    returns a real `run_id` immediately — so the whole `run_id` consumer cluster is
    reachable without spending on an async plan job.
  * `composition_outline_node_create` (kind `beat` — `scene`/`chapter` need a chapter_id,
    `act` fails the kind check) and `composition_canon_rule_create` each return `{id,
    version}`, which their update/delete twins consume.

Everything here writes only under the throwaway book; `teardown_composition` deletes those
rows (leaking a row per sweep is the trap this module is careful to avoid).
"""
from __future__ import annotations

from typing import Any

from . import config, oracle

# Creators FIRST, then read/update consumers, then DELETES last (a delete before its
# sibling read/update silently starves them). A tool not listed keeps catalog order and
# falls back to fill_args.
PROJECT_SWEEP_ORDER: tuple[str, ...] = (
    "composition_create_work",           # mints the composition project_id
    "plan_propose_spec",                 # mints run_id (sync, rules mode)
    "composition_outline_node_create",   # mints node_id + version
    "composition_canon_rule_create",     # mints rule_id + version
    # run_id consumers
    "plan_apply_revision",
    "plan_handoff_autofix",
    "plan_interpret_feedback",
    # node consumers (read/update BEFORE the node is deleted)
    "composition_get_outline_node",
    "composition_outline_node_update",
    "composition_motif_suggest_for_chapter",
    # rule consumer
    "composition_canon_rule_update",
    # deletes LAST — they destroy the id their siblings above need
    "composition_canon_rule_delete",
    "composition_outline_node_delete",
)


def _id(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def authored_project_args(tool: str, ids: dict, state: dict) -> dict | None:
    """`ids` holds the fixture (book_id, kg project_id, chapter_id…); `state` holds the
    RESULT of every earlier successful call this phase, so a consumer can read the id its
    creator minted. Returns None ⇒ fall back to fill_args (the ~170 tools not in a chain).
    """
    book = ids.get("book_id")
    work = state.get("composition_create_work") or {}
    cproj = _id(work, "project_id")  # the COMPOSITION project, not the kg one
    run_id = _id(state.get("plan_propose_spec") or {}, "run_id")
    node = state.get("composition_outline_node_create") or {}
    node_id, node_ver = _id(node, "id", "node_id"), node.get("version")
    rule = state.get("composition_canon_rule_create") or {}
    rule_id, rule_ver = _id(rule, "id", "rule_id"), rule.get("version")

    entity_id = ids.get("entity_id")
    chapter_id = ids.get("chapter_id")
    match tool:
        # ── cheap semantic fixes: a required-only call is a no-op ("no fields to update");
        #    supply one optional field on purpose so the write actually exercises ─────────
        case "book_update_meta":
            return {"book_id": book, "description": "TLE sweep touched this"} if book else None
        case "book_chapter_update_meta":
            return {"book_id": book, "chapter_id": chapter_id, "title": "TLE chapter v2"} \
                if (book and chapter_id) else None
        case "glossary_entity_set_attributes":
            # "attributes or scope_label must be provided"; attributes are keyed by the
            # entity kind's DECLARED codes (which the fixture entity has none of), so use the
            # free-form scope_label instead.
            return {"book_id": book, "entity_id": entity_id,
                    "scope_label": "TLE swept"} if (book and entity_id) else None
        case "composition_get_outline_node":
            node = state.get("composition_outline_node_create") or {}
            nid = _id(node, "id", "node_id")
            return {"project_id": cproj, "node_id": nid} if (cproj and nid) else None
        case "composition_create_work":
            return {"book_id": book} if book else None
        case "plan_propose_spec":
            # rules mode (no model_ref) is synchronous + free; a minimal outline is enough
            # to mint the run row that the run_id consumers operate on.
            return {"book_id": book,
                    "source_markdown": "# Arc One\n\nA hero answers the call and sets out."} \
                if book else None
        case "composition_outline_node_create":
            return {"args": {"project_id": cproj, "kind": "beat", "title": "TLE node"}} \
                if cproj else None
        case "composition_canon_rule_create":
            return {"args": {"project_id": cproj, "text": "TLE canon rule: the sky is green."}} \
                if cproj else None
        # ── run_id consumers ────────────────────────────────────────────────────
        case "plan_apply_revision":
            return {"book_id": book, "run_id": run_id} if run_id else None
        case "plan_handoff_autofix":
            return {"book_id": book, "run_id": run_id} if run_id else None
        case "plan_interpret_feedback":
            return {"book_id": book, "run_id": run_id, "user_message": "tighten the pacing"} \
                if run_id else None
        # ── outline node consumers ──────────────────────────────────────────────
        case "composition_outline_node_update":
            if not (cproj and node_id):
                return None
            a = {"project_id": cproj, "node_id": node_id, "title": "TLE node v2"}
            if node_ver is not None:
                a["expected_version"] = node_ver
            return {"args": a}
        case "composition_motif_suggest_for_chapter":
            return {"project_id": cproj, "node_id": node_id} if (cproj and node_id) else None
        # ── canon rule consumers ────────────────────────────────────────────────
        case "composition_canon_rule_update":
            if not (cproj and rule_id):
                return None
            a = {"project_id": cproj, "rule_id": rule_id, "text": "TLE canon rule v2."}
            if rule_ver is not None:
                a["expected_version"] = rule_ver
            return {"args": a}
        case "composition_canon_rule_delete":
            return {"project_id": cproj, "rule_id": rule_id} if (cproj and rule_id) else None
        case "composition_outline_node_delete":
            return {"project_id": cproj, "node_id": node_id} if (cproj and node_id) else None
        case _:
            return None  # not in a chain → fill_args


# Book-scoped composition tables this chain writes to, child→parent so FKs don't block the
# delete. Enumerated from information_schema, scoped to the throwaway book id.
_COMPOSITION_OWNED: tuple[str, ...] = (
    "outline_node",
    "canon_rule",
    "authoring_runs",
    "plan_run",
    "composition_work",
)


def teardown_composition(book_id: str) -> dict:
    """Delete every composition row under the throwaway book. Best-effort per table so one
    schema drift cannot leak the rest; scoped strictly to the created book id."""
    if not book_id or config.KEEP_FIXTURES:
        return {"kept": True}
    bid = str(book_id).replace("'", "''")
    out: dict[str, str] = {}
    for table in _COMPOSITION_OWNED:
        try:
            oracle.db_query(config.DOMAIN_DB["composition"],
                            f"DELETE FROM {table} WHERE book_id='{bid}'")
            out[table] = "ok"
        except Exception as e:
            out[table] = f"skip ({type(e).__name__})"
    return out
