"""The P0 probe set — 10 real tools spanning R / A / W / async.

Each probe is a black-box NATURAL-LANGUAGE ask (never the tool name — CD3 black-box
rule). The `oracle` verifies the effect through an INDEPENDENT path (DB read-back),
never the domain's own read tool (CD3 anti-oracle rule).

A probe:
  id, tool         — the tool we expect the model to select (G1)
  cls              — R | A | W | async  (selects the recipe)
  nl               — the user's words (black-box)
  permission_mode  — 'write' so writes execute; 'ask'/'plan' where relevant
  needs_context    — inject book/chapter/project ids from the fixture
  confirm          — Tier-W: resolve the confirm_token round-trip (G3)
  paid             — skip unless --allow-paid
  oracle(fixture, call, harness) -> (passed: bool, evidence: dict)
       call is the captured tool record {tool,args,ok,result,error}; None if G1 failed.

Paid tools (glossary_web_search, glossary_deep_research) are intentionally EXCLUDED
from P0 and marked UNTESTED-PAID → deferred to WS-D2/D-PAID (spend gate being built
by another agent). See build_probes()'s trailing note.
"""
from __future__ import annotations

from . import config, oracle


# ── R (read) oracles: result consistent with the seeded fixture ───────────────
def _oracle_book_list(fx, call, h):
    if not call or call.get("ok") is False:
        return False, {"why": "no successful call"}
    blob = str(call.get("result"))
    hit = fx.book_id in blob
    # read-tool G4: the fixture book (which truly exists in the DB) appears in the list
    db_exists = oracle.book_row(fx.book_id) is not None
    return (hit and db_exists), {"fixture_book_id": fx.book_id,
                                 "found_in_result": hit, "book_exists_in_db": db_exists}


def _oracle_book_get(fx, call, h):
    if not call or call.get("ok") is False:
        return False, {"why": "no successful call"}
    db = oracle.book_row(fx.book_id)
    blob = str(call.get("result"))
    # read-tool G4: the returned data matches the fixture's true title in the DB
    ok = bool(db) and (db["title"] in blob)
    return ok, {"db_title": db and db["title"], "title_in_result": ok}


def _oracle_ontology_read(fx, call, h):
    if not call or call.get("ok") is False:
        return False, {"why": "no successful call"}
    blob = str(call.get("result")).lower()
    # fixture adopted character/location/item; assert result reflects them
    present = [k for k in fx.adopted_kinds if k in blob]
    return len(present) >= 2, {"adopted": fx.adopted_kinds, "present_in_result": present}


# ── A (auto-write) oracles: read the target row back from the DB ──────────────
def _oracle_book_create(fx, call, h):
    # find a NEW book created by this probe, distinct from the fixture book
    db = oracle.config.DOMAIN_DB["book"]
    rows = oracle.db_query(
        db, "SELECT id,title FROM books WHERE title LIKE 'TLE-probe-%' "
            f"AND id <> '{fx.book_id}' ORDER BY created_at DESC LIMIT 3")
    if rows:
        fx.extra_books.append(rows[0][0])  # register for teardown
        return True, {"created_book_id": rows[0][0], "created_title": rows[0][1]}
    return False, {"why": "no TLE-probe-* book found in DB after the call"}


def _oracle_book_update_meta(fx, call, h):
    db = oracle.book_row(fx.book_id)
    desc = (db or {}).get("description") or ""
    ok = "edited-by-tle" in desc.lower()
    return ok, {"db_description": desc, "matched": ok}


def _oracle_propose_entities(fx, call, h):
    names = [n.lower() for n in oracle.glossary_entity_names(fx.book_id)]
    ok = any("corvin" in n for n in names)
    return ok, {"db_entity_names": oracle.glossary_entity_names(fx.book_id),
                "expected_contains": "Corvin", "matched": ok}


# ── W (confirm-token) oracles: after confirm round-trip, read back ────────────
def _oracle_propose_new_kind(fx, call, h):
    ok = oracle.book_kind_exists(fx.book_id, "faction")
    return ok, {"expected_kind_code": "faction", "kind_in_db": ok}


def _oracle_chapter_publish(fx, call, h):
    row = oracle.chapter_row(fx.chapter_id) if fx.chapter_id else None
    ok = bool(row) and (row.get("published_revision_id") is not None
                        or (row.get("lifecycle_state") or "").lower() in ("published", "canon"))
    return ok, {"chapter_id": fx.chapter_id, "db_row": row}


def _oracle_entity_delete(fx, call, h):
    target = h.get("delete_target_entity_id")
    if not target:
        return False, {"why": "no delete target entity was set up"}
    alive = oracle.glossary_entity_alive(target)
    ok = alive is False
    return ok, {"deleted_entity_id": target, "db_alive": alive, "matched_dead": ok}


# ── async oracle: poll to terminal, assert the ARTIFACT (graph nodes) ─────────
def _oracle_kg_build(fx, call, h):
    # G4 = the produced artifact exists, read independently (knowledge DB node count).
    proj = h.get("kg_project_id")
    if not proj:
        return False, {"why": "no kg project id"}
    db = oracle.config.DOMAIN_DB["knowledge"]
    try:
        n = oracle.count(db, f"kg_nodes WHERE project_id='{proj}'")
    except Exception as e:
        # table name may differ across schema versions; report honestly
        return False, {"why": f"artifact read failed: {e}", "kg_project_id": proj}
    return n > 0, {"kg_project_id": proj, "node_count": n}


# ── `direct` — deterministic MCP-direct args for the CAPABILITY re-probe ──────────
#
# When G1 fails (the model never called the tool) the probe short-circuits, so the tool
# is NEVER exercised and a *selection* failure is indistinguishable from a *capability*
# failure. That collapse hid F6 for a whole eval cycle: `kg_build_graph` was scored
# "model did not call it" while the tool could not have succeeded if it had.
#
# `direct(fx) -> dict | None` supplies authored, fixture-scoped args so run.py can call
# the tool deterministically after a G1 miss and score the two causes apart.
#
# SAFETY, and why this is sound:
#   * Tier-W tools MINT a confirm_token and write NOTHING at call time — we never redeem it.
#   * Tier-A tools write only into the throwaway fixture (or a `TLE-probe-*` row).
#   * PAID tools are skipped outright — a capability probe must never spend the user's money.
#   * No probe may address an id it did not create (the fixture-factory boundary).


def build_probes() -> list[dict]:
    return [
        # ---- R (read) ----
        {"id": "R1", "tool": "book_list", "cls": "R", "permission_mode": "ask",
         "nl": "Show me my library — list the books I have.",
         "needs_context": False, "confirm": False, "oracle": _oracle_book_list,
         "direct": lambda fx, h: {}},
        {"id": "R2", "tool": "book_get", "cls": "R", "permission_mode": "ask",
         "nl": "What exact title and description are saved for this book on the server? "
               "Look up its stored details and quote them back to me.",
         "needs_context": True, "confirm": False, "oracle": _oracle_book_get,
         "direct": lambda fx, h: {"book_id": fx.book_id}},
        {"id": "R3", "tool": "glossary_book_ontology_read", "cls": "R", "permission_mode": "ask",
         "nl": "Which entity kinds (types) are configured in this book's glossary right "
               "now? List them.",
         "needs_context": True, "confirm": False, "oracle": _oracle_ontology_read,
         "direct": lambda fx, h: {"book_id": fx.book_id}},
        # ---- A (auto-write) ----
        {"id": "A1", "tool": "book_create", "cls": "A", "permission_mode": "write",
         "nl": "Create a brand new, separate book titled exactly "
               "'TLE-probe-created' written in English.",
         "needs_context": False, "confirm": False, "oracle": _oracle_book_create,
         "direct": lambda fx, h: {"title": "TLE-probe-created", "original_language": "en"}},
        {"id": "A2", "tool": "book_update_meta", "cls": "A", "permission_mode": "write",
         "nl": "Change this book's description to exactly: edited-by-tle",
         "needs_context": True, "confirm": False, "oracle": _oracle_book_update_meta,
         "direct": lambda fx, h: {"book_id": fx.book_id, "description": "edited-by-tle"}},
        {"id": "A3", "tool": "glossary_propose_entities", "cls": "A", "permission_mode": "write",
         "nl": "Add a new character named 'Corvin Ashe' to this book's glossary.",
         "needs_context": True, "confirm": False, "oracle": _oracle_propose_entities,
         "direct": lambda fx, h: {"book_id": fx.book_id,
                                  "items": [{"name": "Corvin Ashe", "kind": "character"}]}},
        # ---- W (confirm-token) ----
        {"id": "W1", "tool": "glossary_propose_new_kind", "cls": "W", "permission_mode": "write",
         "nl": "Add a brand-new entity type called 'Faction' (code: faction) to this "
               "book's glossary schema.",
         "needs_context": True, "confirm": True, "oracle": _oracle_propose_new_kind,
         "direct": lambda fx, h: {"book_id": fx.book_id, "code": "faction",
                                  "display_name": "Faction"}},
        {"id": "W2", "tool": "book_chapter_publish", "cls": "W", "permission_mode": "write",
         "nl": "Publish the first chapter of this book — make it canon.",
         "needs_context": True, "confirm": True, "oracle": _oracle_chapter_publish,
         "direct": lambda fx, h: ({"book_id": fx.book_id, "chapter_id": fx.chapter_id}
                                  if fx.chapter_id else None)},
        {"id": "W3", "tool": "glossary_entity_delete", "cls": "W", "permission_mode": "write",
         "nl": "Delete the glossary entity named 'Ember Codex' from this book — "
               "it's junk and I want it gone.",
         "needs_context": True, "confirm": True, "oracle": _oracle_entity_delete,
         # Tier-W: this MINTS a delete confirm_token and deletes nothing. We never redeem it.
         "direct": lambda fx, h: ({"book_id": fx.book_id,
                                   "entity_ids": [fx.entities[0]["entity_id"]]}
                                  if fx.entities else None)},
        # ---- async ----
        {"id": "X1", "tool": "kg_build_graph", "cls": "async", "permission_mode": "write",
         "nl": "Build the knowledge graph for this project from its glossary now.",
         "needs_context": True, "confirm": True, "oracle": _oracle_kg_build,
         "status_tool": "kg_graph_query", "poll_timeout_s": 80,
         # F6: a fresh project has NO embedding model, so kg_build_graph refuses to mint
         # its confirm_token. `setup` runs before the capability probe — the same chain
         # an agent now follows (kg_project_set_embedding_model → kg_run_benchmark → build).
         "setup": lambda fx, h: (
             [("kg_project_set_embedding_model",
               {"project_id": h["kg_project_id"],
                "embedding_model": config.EMBEDDING_MODEL_REF})]
             if h.get("kg_project_id") and config.EMBEDDING_MODEL_REF else []),
         "direct": lambda fx, h: ({"project_id": h["kg_project_id"],
                                   "llm_model": config.MODEL_REF,
                                   "scope": "glossary_sync"}
                                  if h.get("kg_project_id") else None)},
    ]


# Paid tools excluded from P0 (spend gate under construction by another agent):
PAID_DEFERRED = ["glossary_web_search", "glossary_deep_research"]
