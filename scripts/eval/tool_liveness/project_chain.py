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
    # book-scoped glossary/book chains
    "book_list_revisions",               # surfaces the fixture chapter's revision_id
    "book_chapter_restore_revision",     # ← consumes it
    "glossary_ontology_upsert",          # creates a book kind
    "glossary_ontology_delete",          # ← mints a delete token for it
    # authoring-run consumers of the seeded run (get/gate before close terminates it)
    "composition_authoring_run_get",
    "composition_authoring_run_gate",
    "composition_authoring_run_close",   # ← transitions draft→closed, so LAST
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
        case "glossary_propose_new_kind":
            # Tier W: mints a confirm_token for a NEW book kind. `code` is the code being
            # MINTED (not a lookup), so authored, not fill_args-refused.
            return {"book_id": book, "code": "tle_probe_kind", "name": "TLE Probe Kind"} \
                if book else None
        case "glossary_propose_new_attribute":
            # a NEW attribute (code+name) on an EXISTING kind — the fixture adopts
            # character/location/item, so kind_code='character' is a live kind.
            return {"book_id": book, "kind_code": "character",
                    "code": "tle_probe_attr", "name": "TLE Probe Attr"} if book else None
        case "book_chapter_restore_revision":
            # the fixture chapter carries a seed revision; book_list_revisions (ordered
            # before this) surfaces its id.
            revs = (state.get("book_list_revisions") or {}).get("revisions") or []
            rid = revs[0].get("revision_id") if revs else None
            return {"book_id": book, "chapter_id": chapter_id, "revision_id": rid} \
                if (book and chapter_id and rid) else None
        # ── glossary array-payload tools (item shapes mapped from the Go structs) ──
        case "glossary_ontology_upsert":
            # Tier A, writes immediately. Omit base_version ⇒ CREATE a book kind.
            return {"scope": "book", "book_id": book,
                    "items": [{"level": "kind", "code": "tle_upsert_kind",
                               "name": "TLE Upsert Kind"}]} if book else None
        case "glossary_ontology_delete":
            # Tier W: mints a confirm_token (we never redeem it). Targets the kind
            # glossary_ontology_upsert created (ordered before this).
            return {"scope": "book", "book_id": book,
                    "items": [{"level": "kind", "code": "tle_upsert_kind"}]} if book else None
        case "glossary_propose_aliases":
            # Tier A draft. Needs an existing entity; the fixture seeds 'Aldric Vane'.
            return {"book_id": book, "language_code": "en",
                    "items": [{"entity_id": entity_id, "aliases": ["Aldric", "Vane"]}]} \
                if (book and entity_id) else None
        case "glossary_propose_translation":
            return {"book_id": book, "language_code": "vi",
                    "items": [{"entity_id": entity_id, "value": "Aldric Vane"}]} \
                if (book and entity_id) else None
        case "glossary_propose_kinds":
            # Tier W: mints a confirm_token for a batch of kinds.
            return {"book_id": book,
                    "kinds": [{"code": "tle_kinds_kind", "name": "TLE Kinds Kind"}]} if book else None
        case "glossary_propose_batch":
            # Tier W: mints an execute_plan token. create_kinds is self-contained; every
            # attribute needs a non-empty description (extraction instruction) — none here.
            return {"book_id": book, "goal": "probe",
                    "ops": [{"type": "create_kinds",
                             "params": {"kinds": [{"code": "tle_batch_kind",
                                                   "name": "TLE Batch Kind"}]},
                             "rationale": "probe"}]} if book else None
        case "composition_authoring_run_get" | "composition_authoring_run_gate" \
                | "composition_authoring_run_close":
            # the seeded authoring_runs row (see seed_authoring_run). get reads it, gate
            # mints a token, close transitions draft→closed (ordered LAST so it doesn't
            # close the run before gate/get run). These wrap args in the composition `args`
            # envelope (like the other composition_* tools).
            arun = ids.get("authoring_run_id")
            return {"args": {"book_id": book, "run_id": arun}} if (book and arun) else None
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


def seed_authoring_run(ids: dict) -> None:
    """Seed a throwaway authoring_runs row so its get/gate/close consumers are reachable at
    $0. authoring_run_create is Tier-W + a paid confirm (`budget_usd`), so nothing minted a
    run for the sweep. But the row only needs a `plan_run_id`, which plan_propose_spec mints
    synchronously in rules mode (free). Mint one, INSERT the run in `draft`, stash its id.
    (Book-scoped, so teardown_composition cleans it with the rest.)"""
    import uuid

    from .mcp_direct import MCPDirect

    book = ids.get("book_id")
    if not book:
        return
    try:
        plan = MCPDirect().call(
            "plan_propose_spec",
            {"book_id": book, "source_markdown": "# Arc One\n\nA hero sets out."})
        plan_run_id = plan.get("run_id")
        if not plan_run_id:
            return
        run_id = str(uuid.uuid4())
        oracle.db_query(
            config.DOMAIN_DB["composition"],
            "INSERT INTO authoring_runs(run_id, created_by, book_id, plan_run_id, level, status) "
            f"VALUES ('{run_id}','{config.USER_ID}','{book}','{plan_run_id}',3,'draft')")  # level ∈ {3,4}
        ids["authoring_run_id"] = run_id
    except Exception as e:  # non-fatal — the 3 consumers just stay null
        print(f"  (no authoring-run seed: {type(e).__name__}: {e})")


def teardown_composition(book_id: str) -> dict:
    """Delete EVERY composition row under the throwaway book, and verify none survive.

    A hardcoded table list is the wrong tool here: the sweep calls Tier-W tools that write
    rows I did not anticipate (the first version listed 5 tables and leaked a `generation_job`
    row per run — the exact trap this cleanup exists to prevent). So discover every
    book-scoped table at runtime from information_schema, and delete from all of them.

    Order-agnostic by RETRY: an FK-child row can block a parent delete, so pass over the
    tables a few times — once a child is gone, the next pass clears its parent. Converges
    without hardcoding dependency order. Scoped strictly to the created book id.
    """
    if not book_id or config.KEEP_FIXTURES:
        return {"kept": True}
    bid = str(book_id).replace("'", "''")
    db = config.DOMAIN_DB["composition"]
    try:
        tables = [r[0] for r in oracle.db_query(
            db, "SELECT table_name FROM information_schema.columns "
                "WHERE column_name='book_id' AND table_schema='public'")]
    except Exception as e:
        return {"discover": f"FAILED ({type(e).__name__})"}
    for _ in range(3):  # FK depth in composition is shallow; 3 passes clears it
        for table in tables:
            try:
                oracle.db_query(db, f"DELETE FROM {table} WHERE book_id='{bid}'")
            except Exception:  # FK-blocked this pass — a later pass clears it
                pass
    # Verify completeness — a surviving row is a leak, and silence would hide it.
    leaked = {}
    for table in tables:
        try:
            n = int(oracle.scalar(db, f"SELECT count(*) FROM {table} WHERE book_id='{bid}'") or 0)
            if n:
                leaked[table] = n
        except Exception:
            pass
    return {"tables": len(tables), "leaked": leaked} if leaked else {"tables": len(tables), "clean": True}
